"""
Tests para exportación de reportes a CSV.

Verifica que los reportes se exporten correctamente.
"""

import pytest
import os
import csv
import tempfile
from datetime import date, datetime
from unittest.mock import MagicMock


class TestReportsExportCSV:
    """Tests para exportación de reportes a CSV."""
    
    @pytest.fixture
    def sales_dataset(self):
        """Dataset simulado de ventas."""
        return [
            {
                "key": "2024-01-01",
                "count_invoices": 5,
                "total_amount": 10000.50,
                "avg_amount": 2000.10,
                "first_date": "2024-01-01",
                "last_date": "2024-01-01"
            },
            {
                "key": "2024-01-02",
                "count_invoices": 3,
                "total_amount": 5500.00,
                "avg_amount": 1833.33,
                "first_date": "2024-01-02",
                "last_date": "2024-01-02"
            },
            {
                "key": "2024-01-03",
                "count_invoices": 7,
                "total_amount": 15000.00,
                "avg_amount": 2142.86,
                "first_date": "2024-01-03",
                "last_date": "2024-01-03"
            },
        ]
    
    @pytest.fixture
    def clients_dataset(self):
        """Dataset simulado de clientes."""
        return [
            {
                "client_id": "123456789",
                "client_name": "Empresa ABC SRL",
                "invoices_count": 10,
                "total_amount": 50000.00,
                "last_invoice_date": "2024-01-15"
            },
            {
                "client_id": "987654321",
                "client_name": "Cliente XYZ",
                "invoices_count": 5,
                "total_amount": 25000.00,
                "last_invoice_date": "2024-01-10"
            },
        ]
    
    @pytest.fixture
    def temp_csv_file(self):
        """Crea un archivo CSV temporal."""
        fd, path = tempfile.mkstemp(suffix='.csv')
        os.close(fd)
        
        yield path
        
        if os.path.exists(path):
            os.remove(path)
    
    def test_export_sales_csv_creates_file(self, sales_dataset, temp_csv_file):
        """Test que export_sales_csv crea el archivo."""
        from services.reporting_service import export_sales_csv
        
        result = export_sales_csv(sales_dataset, temp_csv_file)
        
        assert result is True
        assert os.path.exists(temp_csv_file)
    
    def test_export_sales_csv_headers(self, sales_dataset, temp_csv_file):
        """Test que el CSV tiene las cabeceras correctas."""
        from services.reporting_service import export_sales_csv
        
        export_sales_csv(sales_dataset, temp_csv_file)
        
        with open(temp_csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
        
        expected_headers = ["key", "count_invoices", "total_amount", "avg_amount", "first_date", "last_date"]
        assert headers == expected_headers
    
    def test_export_sales_csv_row_count(self, sales_dataset, temp_csv_file):
        """Test que el CSV tiene el número correcto de filas."""
        from services.reporting_service import export_sales_csv
        
        export_sales_csv(sales_dataset, temp_csv_file)
        
        with open(temp_csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)
        
        # Header + 3 filas de datos
        assert len(rows) == 4
    
    def test_export_sales_csv_data_values(self, sales_dataset, temp_csv_file):
        """Test que los valores en el CSV son correctos."""
        from services.reporting_service import export_sales_csv
        
        export_sales_csv(sales_dataset, temp_csv_file)
        
        with open(temp_csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        # Verificar primera fila
        assert rows[0]["key"] == "2024-01-01"
        assert rows[0]["count_invoices"] == "5"
        assert rows[0]["total_amount"] == "10000.5"
    
    def test_export_clients_csv_creates_file(self, clients_dataset, temp_csv_file):
        """Test que export_clients_csv crea el archivo."""
        from services.reporting_service import export_clients_csv
        
        result = export_clients_csv(clients_dataset, temp_csv_file)
        
        assert result is True
        assert os.path.exists(temp_csv_file)
    
    def test_export_clients_csv_headers(self, clients_dataset, temp_csv_file):
        """Test que el CSV de clientes tiene las cabeceras correctas."""
        from services.reporting_service import export_clients_csv
        
        export_clients_csv(clients_dataset, temp_csv_file)
        
        with open(temp_csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
        
        expected_headers = ["client_id", "client_name", "invoices_count", "total_amount", "last_invoice_date"]
        assert headers == expected_headers
    
    def test_export_clients_csv_data_values(self, clients_dataset, temp_csv_file):
        """Test que los valores del CSV de clientes son correctos."""
        from services.reporting_service import export_clients_csv
        
        export_clients_csv(clients_dataset, temp_csv_file)
        
        with open(temp_csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        assert len(rows) == 2
        assert rows[0]["client_name"] == "Empresa ABC SRL"
        assert rows[0]["client_id"] == "123456789"
    
    def test_export_empty_dataset(self, temp_csv_file):
        """Test exportar dataset vacío."""
        from services.reporting_service import export_sales_csv
        
        result = export_sales_csv([], temp_csv_file)
        
        assert result is True
        
        with open(temp_csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)
        
        # Solo header
        assert len(rows) == 1
    
    def test_export_handles_special_characters(self, temp_csv_file):
        """Test que el CSV maneja caracteres especiales."""
        from services.reporting_service import export_clients_csv
        
        dataset = [{
            "client_id": "123",
            "client_name": "Empresa Ñoño & Cía, S.A.",
            "invoices_count": 1,
            "total_amount": 1000.00,
            "last_invoice_date": "2024-01-01"
        }]
        
        result = export_clients_csv(dataset, temp_csv_file)
        
        assert result is True
        
        with open(temp_csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        assert rows[0]["client_name"] == "Empresa Ñoño & Cía, S.A."


class TestReportingService:
    """Tests para el servicio de reportes."""
    
    @pytest.fixture
    def mock_data_access(self):
        """Mock de data_access."""
        mock = MagicMock()
        mock.get_invoices.return_value = [
            {
                "id": 1,
                "invoice_date": "2024-01-15",
                "client_name": "Cliente A",
                "client_rnc": "123456789",
                "total_amount": 5000.00
            },
            {
                "id": 2,
                "invoice_date": "2024-01-16",
                "client_name": "Cliente B",
                "client_rnc": "987654321",
                "total_amount": 3000.00
            },
            {
                "id": 3,
                "invoice_date": "2024-01-16",
                "client_name": "Cliente A",
                "client_rnc": "123456789",
                "total_amount": 2000.00
            },
        ]
        return mock
    
    def test_sales_by_period_day_grouping(self, mock_data_access):
        """Test agrupación por día."""
        from services.reporting_service import ReportingService
        
        service = ReportingService(mock_data_access)
        
        result = service.sales_by_period(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            group_by="day"
        )
        
        # Debe haber 2 grupos (2024-01-15 y 2024-01-16)
        assert len(result) == 2
    
    def test_sales_by_period_totals(self, mock_data_access):
        """Test que los totales son correctos."""
        from services.reporting_service import ReportingService
        
        service = ReportingService(mock_data_access)
        
        result = service.sales_by_period(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            group_by="day"
        )
        
        # Total de montos
        total = sum(r["total_amount"] for r in result)
        assert total == 10000.00  # 5000 + 3000 + 2000
    
    def test_clients_by_period_grouping(self, mock_data_access):
        """Test agrupación por cliente."""
        from services.reporting_service import ReportingService
        
        service = ReportingService(mock_data_access)
        
        result = service.clients_by_period(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31)
        )
        
        # Debe haber 2 clientes
        assert len(result) == 2
    
    def test_clients_by_period_client_totals(self, mock_data_access):
        """Test que los totales por cliente son correctos."""
        from services.reporting_service import ReportingService
        
        service = ReportingService(mock_data_access)
        
        result = service.clients_by_period(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31)
        )
        
        # Buscar Cliente A (debe tener 2 facturas y total de 7000)
        cliente_a = next((c for c in result if "Cliente A" in c["client_name"]), None)
        
        assert cliente_a is not None
        assert cliente_a["invoices_count"] == 2
        assert cliente_a["total_amount"] == 7000.00
    
    def test_empty_period_returns_empty_list(self, mock_data_access):
        """Test que período sin datos retorna lista vacía."""
        from services.reporting_service import ReportingService
        
        mock_data_access.get_invoices.return_value = []
        
        service = ReportingService(mock_data_access)
        
        result = service.sales_by_period(
            start_date=date(2024, 6, 1),
            end_date=date(2024, 6, 30)
        )
        
        assert result == []
