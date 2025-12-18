"""
Tests para ncf_firestore_service.py

Pruebas unitarias para el servicio de NCF con Firestore.
"""
import os
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime


class TestNCFFirestoreService:
    """Tests para NCFFirestoreService."""
    
    @pytest.fixture
    def mock_db(self):
        """Mock de cliente Firestore."""
        db = Mock()
        return db
    
    @pytest.fixture
    def service(self, mock_db):
        """Crea instancia del servicio con mock."""
        from services.ncf_firestore_service import NCFFirestoreService
        svc = NCFFirestoreService(db=mock_db)
        return svc
    
    def test_derive_prefix_from_category(self, service):
        """Test de derivación de prefijo desde categoría."""
        assert service._derive_prefix("FACTURA PRIVADA") == "B01"
        assert service._derive_prefix("CONSUMIDOR FINAL") == "B02"
        assert service._derive_prefix("Crédito Fiscal") == "B01"
        assert service._derive_prefix("FACTURA GUBERNAMENTAL") == "B15"
        assert service._derive_prefix("FACTURA EXENTA") == "B14"
    
    def test_derive_prefix_with_explicit(self, service):
        """Test de prefijo explícito tiene prioridad."""
        assert service._derive_prefix("FACTURA PRIVADA", prefix="B02") == "B02"
        assert service._derive_prefix("CONSUMIDOR FINAL", prefix="B15") == "B15"
    
    def test_derive_prefix_unknown_category(self, service):
        """Test de categoría desconocida usa default."""
        assert service._derive_prefix("CATEGORIA DESCONOCIDA") == "B01"
    
    def test_format_ncf_standard(self, service):
        """Test de formateo de NCF estándar."""
        assert service._format_ncf("B01", 1) == "B0100000001"
        assert service._format_ncf("B01", 163) == "B0100000163"
        assert service._format_ncf("B02", 999) == "B0200000999"
        assert service._format_ncf("B15", 12345678) == "B1512345678"
    
    def test_format_ncf_ecf(self, service):
        """Test de formateo de NCF electrónico."""
        assert service._format_ncf("E31", 1) == "E3100000000001"
        assert service._format_ncf("E32", 999) == "E3200000000999"
    
    def test_parse_ncf(self, service):
        """Test de parseo de NCF."""
        prefix, seq = service._parse_ncf("B0100000163")
        assert prefix == "B01"
        assert seq == 163
        
        prefix, seq = service._parse_ncf("E3100000000001")
        assert prefix == "E31"
        assert seq == 1
    
    def test_parse_ncf_invalid(self, service):
        """Test de parseo de NCF inválido."""
        prefix, seq = service._parse_ncf("")
        assert prefix == "B01"
        assert seq == 0
        
        prefix, seq = service._parse_ncf("XXX")
        assert prefix == "B01"
        assert seq == 0
    
    def test_validate_ncf_valid(self, service):
        """Test de validación de NCF válidos."""
        assert service._validate_ncf("B0100000001") is True
        assert service._validate_ncf("B0299999999") is True
        assert service._validate_ncf("E3100000000001") is True
    
    def test_validate_ncf_invalid(self, service):
        """Test de validación de NCF inválidos."""
        assert service._validate_ncf("") is False
        assert service._validate_ncf("B01") is False
        assert service._validate_ncf("B010000000") is False  # Muy corto
        assert service._validate_ncf("B01000000001") is False  # Muy largo para estándar
    
    def test_get_padding_standard(self, service):
        """Test de padding para NCF estándar."""
        assert service._get_padding("B01") == 8
        assert service._get_padding("B02") == 8
        assert service._get_padding("B15") == 8
    
    def test_get_padding_ecf(self, service):
        """Test de padding para e-CF."""
        assert service._get_padding("E31") == 11
        assert service._get_padding("E32") == 11
    
    def test_sequence_info_existing(self, service, mock_db):
        """Test de obtener info de secuencia existente."""
        # Mock del documento existente
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            'category': 'FACTURA PRIVADA',
            'last_assigned': 'B0100000163',
            'next_sequence': 164,
            'effective_from': '2024-01-01',
            'updated_at': '2024-11-27T00:00:00'
        }
        
        mock_doc_ref = Mock()
        mock_doc_ref.get.return_value = mock_snapshot
        mock_db.collection.return_value.document.return_value = mock_doc_ref
        
        info = service.get_sequence_info(company_id=1, prefix="B01")
        
        assert info['exists'] is True
        assert info['prefix'] == 'B01'
        assert info['last_assigned'] == 'B0100000163'
        assert info['next_sequence'] == 164
        assert info['next_ncf'] == 'B0100000164'
    
    def test_sequence_info_not_existing(self, service, mock_db):
        """Test de obtener info de secuencia no existente."""
        # Mock de documento no existente
        mock_snapshot = Mock()
        mock_snapshot.exists = False
        
        mock_doc_ref = Mock()
        mock_doc_ref.get.return_value = mock_snapshot
        mock_db.collection.return_value.document.return_value = mock_doc_ref
        
        # Mock de query para buscar última factura
        mock_query = Mock()
        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = []
        mock_db.collection.return_value.where.return_value = mock_query
        
        info = service.get_sequence_info(company_id=1, prefix="B01")
        
        assert info['exists'] is False
        assert info['next_sequence'] == 1
        assert info['next_ncf'] == 'B0100000001'


class TestCategoryMapping:
    """Tests para el mapeo de categorías a prefijos."""
    
    def test_category_mapping_completeness(self):
        """Verifica que todas las categorías comunes estén mapeadas."""
        from services.ncf_firestore_service import CATEGORY_TO_PREFIX
        
        expected_categories = [
            "FACTURA PRIVADA",
            "CONSUMIDOR FINAL",
            "FACTURA EXENTA",
            "FACTURA GUBERNAMENTAL",
        ]
        
        for cat in expected_categories:
            assert cat in CATEGORY_TO_PREFIX, f"Categoría '{cat}' no está mapeada"
    
    def test_all_prefixes_valid(self):
        """Verifica que todos los prefijos mapeados son válidos."""
        from services.ncf_firestore_service import CATEGORY_TO_PREFIX
        
        valid_prefixes = {"B01", "B02", "B04", "B14", "B15", "B16", "E31", "E32", "E33", "E34"}
        
        for cat, prefix in CATEGORY_TO_PREFIX.items():
            assert prefix in valid_prefixes, f"Prefijo '{prefix}' para '{cat}' no es válido"


class TestNCFFormatting:
    """Tests para formateo de NCF."""
    
    @pytest.fixture
    def service(self):
        """Crea instancia del servicio con mock."""
        from services.ncf_firestore_service import NCFFirestoreService
        return NCFFirestoreService(db=Mock())
    
    def test_ncf_length_standard(self, service):
        """Verifica longitud correcta de NCF estándar."""
        ncf = service._format_ncf("B01", 1)
        assert len(ncf) == 11  # 3 + 8
        
        ncf = service._format_ncf("B01", 99999999)
        assert len(ncf) == 11
    
    def test_ncf_length_ecf(self, service):
        """Verifica longitud correcta de e-CF."""
        ncf = service._format_ncf("E31", 1)
        assert len(ncf) == 14  # 3 + 11
        
        ncf = service._format_ncf("E31", 99999999999)
        assert len(ncf) == 14


class TestCorrector:
    """Tests para el corrector de secuencias."""
    
    @pytest.fixture
    def mock_db(self):
        """Mock de cliente Firestore."""
        return Mock()
    
    @pytest.fixture
    def service(self, mock_db):
        """Crea instancia del servicio con mock."""
        from services.ncf_firestore_service import NCFFirestoreService
        svc = NCFFirestoreService(db=mock_db)
        return svc
    
    def test_corrector_detects_inconsistency(self, service):
        """Test de detección de inconsistencia."""
        # Mock de _find_last_invoice_ncf
        with patch.object(service, '_find_last_invoice_ncf', return_value=None):
            doc_data = {
                'last_assigned': 'B0100000163',
                'next_sequence': 160  # Debería ser 164
            }
            
            corrected = service._correct_sequence_if_needed(
                company_id=1,
                prefix="B01",
                doc_data=doc_data
            )
            
            # Debería devolver 164 (163 + 1)
            assert corrected == 164
    
    def test_corrector_no_change_when_consistent(self, service):
        """Test de que no cambia cuando es consistente."""
        doc_data = {
            'last_assigned': 'B0100000163',
            'next_sequence': 164  # Correcto: 163 + 1
        }
        
        corrected = service._correct_sequence_if_needed(
            company_id=1,
            prefix="B01",
            doc_data=doc_data
        )
        
        assert corrected == 164
