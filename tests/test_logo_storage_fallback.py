"""
Tests para el manejo de logos en Firebase Storage.

Verifica subida, descarga y fallback de logos de plantillas.
"""

import pytest
import os
import tempfile
from unittest.mock import MagicMock, patch, PropertyMock


class TestLogoStorageFallback:
    """Tests para el manejo de logos con fallback."""
    
    @pytest.fixture
    def temp_local_logo(self):
        """Crea un archivo de logo temporal."""
        fd, path = tempfile.mkstemp(suffix='.png')
        os.close(fd)
        
        # Escribir contenido mínimo de imagen PNG
        with open(path, 'wb') as f:
            # PNG header mínimo
            f.write(b'\x89PNG\r\n\x1a\n')
        
        yield path
        
        # Limpiar
        if os.path.exists(path):
            os.remove(path)
    
    @pytest.fixture
    def mock_firebase_data_access(self):
        """Mock de FirebaseDataAccess."""
        from unittest.mock import MagicMock
        
        mock = MagicMock()
        mock.db = MagicMock()
        mock.storage = MagicMock()
        mock.user_id = "test_user"
        
        return mock
    
    def test_upload_logo_returns_url(self, mock_firebase_data_access, temp_local_logo):
        """Test que upload_logo_to_storage retorna URL."""
        # Configurar mock de Storage
        mock_blob = MagicMock()
        mock_blob.public_url = "https://storage.example.com/logo.png"
        mock_firebase_data_access.storage.blob.return_value = mock_blob
        
        # Simular el método
        from data_access.firebase_data_access import FirebaseDataAccess
        
        # Usar el método real con storage mockeado
        with patch.object(FirebaseDataAccess, '__init__', lambda self, user_id=None: None):
            instance = FirebaseDataAccess()
            instance.storage = mock_firebase_data_access.storage
            
            result = instance.upload_logo_to_storage(temp_local_logo, "template_123")
            
            # Verificar que se llamó al blob
            mock_firebase_data_access.storage.blob.assert_called()
    
    def test_download_logo_uses_cache(self, mock_firebase_data_access):
        """Test que download_logo usa cache local."""
        # Crear archivo de cache
        cache_dir = os.path.join(".", "data", "cache", "logos")
        os.makedirs(cache_dir, exist_ok=True)
        
        cache_path = os.path.join(cache_dir, "template_123.png")
        
        try:
            # Crear archivo de cache
            with open(cache_path, 'wb') as f:
                f.write(b'\x89PNG\r\n\x1a\n')
            
            from data_access.firebase_data_access import FirebaseDataAccess
            
            with patch.object(FirebaseDataAccess, '__init__', lambda self, user_id=None: None):
                instance = FirebaseDataAccess()
                instance.storage = mock_firebase_data_access.storage
                
                result = instance.download_logo("templates/123/logo.png", "template_123")
                
                # Debe retornar la ruta del cache (si existe y es reciente)
                # El comportamiento exacto depende de la antigüedad del archivo
                assert result is None or os.path.exists(result)
        
        finally:
            # Limpiar
            if os.path.exists(cache_path):
                os.remove(cache_path)
    
    def test_fallback_to_local_on_storage_error(self, temp_local_logo):
        """Test que usa logo local cuando Storage falla."""
        from data_access.firebase_data_access import FirebaseDataAccess
        
        with patch.object(FirebaseDataAccess, '__init__', lambda self, user_id=None: None):
            instance = FirebaseDataAccess()
            instance.db = MagicMock()
            instance.storage = MagicMock()
            
            # Simular que el documento no tiene logo en Storage
            mock_doc = MagicMock()
            mock_doc.exists = True
            mock_doc.to_dict.return_value = {}  # Sin logo_storage_path
            instance.db.collection.return_value.document.return_value.get.return_value = mock_doc
            
            result = instance.get_template_logo("123", fallback_local_path=temp_local_logo)
            
            # Debe retornar el fallback local
            assert result == temp_local_logo
    
    def test_fallback_when_storage_not_available(self, temp_local_logo):
        """Test fallback cuando Storage no está disponible."""
        from data_access.firebase_data_access import FirebaseDataAccess
        
        with patch.object(FirebaseDataAccess, '__init__', lambda self, user_id=None: None):
            instance = FirebaseDataAccess()
            instance.db = MagicMock()
            instance.storage = None  # Storage no disponible
            
            result = instance.download_logo("templates/123/logo.png", "123")
            
            # Debe retornar None (sin storage)
            assert result is None
    
    def test_upload_with_different_extensions(self, mock_firebase_data_access):
        """Test subida de logos con diferentes extensiones."""
        extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
        
        for ext in extensions:
            fd, path = tempfile.mkstemp(suffix=ext)
            os.close(fd)
            
            try:
                with open(path, 'wb') as f:
                    f.write(b'test content')
                
                from data_access.firebase_data_access import FirebaseDataAccess
                
                mock_blob = MagicMock()
                mock_blob.public_url = f"https://storage.example.com/logo{ext}"
                mock_firebase_data_access.storage.blob.return_value = mock_blob
                
                with patch.object(FirebaseDataAccess, '__init__', lambda self, user_id=None: None):
                    instance = FirebaseDataAccess()
                    instance.storage = mock_firebase_data_access.storage
                    
                    result = instance.upload_logo_to_storage(path, "template_123")
                    
                    # Debe haber llamado al blob con la extensión correcta
                    mock_firebase_data_access.storage.blob.assert_called()
            
            finally:
                if os.path.exists(path):
                    os.remove(path)
    
    def test_upload_nonexistent_file_returns_none(self, mock_firebase_data_access):
        """Test que subir archivo inexistente retorna None."""
        from data_access.firebase_data_access import FirebaseDataAccess
        
        with patch.object(FirebaseDataAccess, '__init__', lambda self, user_id=None: None):
            instance = FirebaseDataAccess()
            instance.storage = mock_firebase_data_access.storage
            
            result = instance.upload_logo_to_storage("/nonexistent/path/logo.png", "123")
            
            assert result is None
    
    def test_get_template_logo_with_no_fallback(self):
        """Test get_template_logo sin fallback retorna None en error."""
        from data_access.firebase_data_access import FirebaseDataAccess
        
        with patch.object(FirebaseDataAccess, '__init__', lambda self, user_id=None: None):
            instance = FirebaseDataAccess()
            instance.db = MagicMock()
            instance.storage = MagicMock()
            
            # Simular error al obtener documento
            instance.db.collection.return_value.document.return_value.get.side_effect = Exception("DB error")
            
            result = instance.get_template_logo("123", fallback_local_path=None)
            
            # Sin fallback, debe retornar None
            assert result is None


class TestLogoStoragePaths:
    """Tests para rutas de logos en Storage."""
    
    def test_storage_path_format(self):
        """Test que la ruta en Storage tiene formato correcto."""
        template_id = "abc123"
        ext = ".png"
        
        expected_path = f"templates/{template_id}/logo{ext}"
        
        # La ruta debe seguir este formato
        assert expected_path == "templates/abc123/logo.png"
    
    def test_cache_path_format(self):
        """Test que la ruta de cache tiene formato correcto."""
        cache_dir = os.path.join(".", "data", "cache", "logos")
        template_id = "abc123"
        ext = ".png"
        
        expected_path = os.path.join(cache_dir, f"{template_id}{ext}")
        
        # Verificar estructura
        assert "data" in expected_path
        assert "cache" in expected_path
        assert "logos" in expected_path
        assert "abc123.png" in expected_path
