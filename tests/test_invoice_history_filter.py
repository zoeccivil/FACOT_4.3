"""
Tests para el filtrado de facturas en InvoiceHistoryTab.

Verifica que solo se muestren facturas de tipo ingreso (ventas).
"""

import pytest
from typing import List, Dict, Any


class TestInvoiceHistoryFilter:
    """Tests para el filtrado de facturas por tipo ingreso."""
    
    @pytest.fixture
    def ingreso_types(self):
        """Conjunto de tipos considerados ingresos."""
        return {
            "INGRESO", "FACTURA", "FACTURA PRIVADA", "EMITIDA", "VENTA",
            "CREDITO FISCAL", "CONSUMIDOR FINAL", "GUBERNAMENTAL",
            "REGIMEN ESPECIAL", "EXPORTACION", "B01", "B02", "B14", "B15", "B16"
        }
    
    @pytest.fixture
    def mixed_invoices(self) -> List[Dict[str, Any]]:
        """Fixture con mezcla de facturas ingreso y gasto."""
        return [
            # Ingresos
            {"id": 1, "type": "FACTURA", "invoice_number": "B0100000001", "total_amount": 1000},
            {"id": 2, "type": "INGRESO", "invoice_number": "B0200000001", "total_amount": 2000},
            {"id": 3, "invoice_type": "FACTURA PRIVADA", "invoice_number": "B0100000002", "total_amount": 1500},
            {"id": 4, "category": "CONSUMIDOR FINAL", "invoice_number": "B0200000002", "total_amount": 500},
            {"id": 5, "invoice_type": "EMITIDA", "ncf": "B0100000003", "total_amount": 3000},
            
            # Gastos (no deben aparecer)
            {"id": 6, "type": "GASTO", "invoice_number": "E3100000000001", "total_amount": 800},
            {"id": 7, "invoice_type": "RECIBIDA", "invoice_number": "B0400000001", "total_amount": 1200},
            {"id": 8, "category": "COMPRA", "invoice_number": "B0300000001", "total_amount": 600},
            {"id": 9, "type": "EGRESO", "invoice_number": "B0400000002", "total_amount": 400},
            
            # Sin tipo pero con NCF de ingreso (debe incluirse)
            {"id": 10, "invoice_number": "B0100000004", "total_amount": 700},
            {"id": 11, "ncf": "B0200000003", "total_amount": 900},
        ]
    
    def _filter_ingreso_invoices(self, facturas: List[Dict[str, Any]], ingreso_types: set) -> List[Dict[str, Any]]:
        """
        Reimplementación del filtro para testing.
        Debe coincidir con la lógica en InvoiceHistoryTab.
        """
        filtered = []
        for inv in facturas:
            invoice_type = (
                inv.get('type') or 
                inv.get('invoice_type') or 
                inv.get('category') or 
                inv.get('invoice_category') or
                ''
            ).upper().strip()
            
            ncf = (inv.get('invoice_number') or inv.get('ncf') or '').upper()
            ncf_prefix = ncf[:3] if len(ncf) >= 3 else ''
            
            if invoice_type in ingreso_types or ncf_prefix in ingreso_types:
                filtered.append(inv)
            elif not invoice_type and ncf:
                filtered.append(inv)
        
        return filtered
    
    def test_filter_returns_only_ingresos(self, mixed_invoices, ingreso_types):
        """Verifica que solo se retornen facturas de tipo ingreso."""
        filtered = self._filter_ingreso_invoices(mixed_invoices, ingreso_types)
        
        # Deben haber 7 facturas de ingreso (5 explícitas + 2 sin tipo pero con NCF de ingreso)
        assert len(filtered) == 7
        
        # Verificar IDs de ingresos
        ingreso_ids = {inv['id'] for inv in filtered}
        assert ingreso_ids == {1, 2, 3, 4, 5, 10, 11}
    
    def test_filter_excludes_gastos(self, mixed_invoices, ingreso_types):
        """Verifica que se excluyan facturas de tipo gasto."""
        filtered = self._filter_ingreso_invoices(mixed_invoices, ingreso_types)
        
        # Los IDs de gastos no deben estar
        gasto_ids = {6, 7, 8, 9}
        filtered_ids = {inv['id'] for inv in filtered}
        
        assert gasto_ids.isdisjoint(filtered_ids)
    
    def test_filter_by_type_factura(self, ingreso_types):
        """Test con tipo FACTURA."""
        invoices = [{"id": 1, "type": "FACTURA", "invoice_number": "B0100000001"}]
        filtered = self._filter_ingreso_invoices(invoices, ingreso_types)
        assert len(filtered) == 1
    
    def test_filter_by_invoice_type_ingreso(self, ingreso_types):
        """Test con invoice_type INGRESO."""
        invoices = [{"id": 1, "invoice_type": "INGRESO", "invoice_number": "B0100000001"}]
        filtered = self._filter_ingreso_invoices(invoices, ingreso_types)
        assert len(filtered) == 1
    
    def test_filter_by_category_consumidor_final(self, ingreso_types):
        """Test con category CONSUMIDOR FINAL."""
        invoices = [{"id": 1, "category": "consumidor final", "invoice_number": "B0200000001"}]
        filtered = self._filter_ingreso_invoices(invoices, ingreso_types)
        assert len(filtered) == 1
    
    def test_filter_by_ncf_prefix_b01(self, ingreso_types):
        """Test filtro por prefijo NCF B01."""
        invoices = [{"id": 1, "invoice_number": "B0100000001"}]
        filtered = self._filter_ingreso_invoices(invoices, ingreso_types)
        assert len(filtered) == 1
    
    def test_filter_by_ncf_prefix_b02(self, ingreso_types):
        """Test filtro por prefijo NCF B02."""
        invoices = [{"id": 1, "ncf": "B0200000001"}]
        filtered = self._filter_ingreso_invoices(invoices, ingreso_types)
        assert len(filtered) == 1
    
    def test_filter_excludes_gasto_type(self, ingreso_types):
        """Test que excluye tipo GASTO."""
        invoices = [{"id": 1, "type": "GASTO", "invoice_number": "E3100000000001"}]
        filtered = self._filter_ingreso_invoices(invoices, ingreso_types)
        assert len(filtered) == 0
    
    def test_filter_excludes_compra_type(self, ingreso_types):
        """Test que excluye tipo COMPRA."""
        invoices = [{"id": 1, "category": "COMPRA", "invoice_number": "B0300000001"}]
        filtered = self._filter_ingreso_invoices(invoices, ingreso_types)
        assert len(filtered) == 0
    
    def test_filter_includes_no_type_with_valid_ncf(self, ingreso_types):
        """Test que incluye facturas sin tipo pero con NCF válido."""
        invoices = [{"id": 1, "invoice_number": "B0100000001"}]
        filtered = self._filter_ingreso_invoices(invoices, ingreso_types)
        assert len(filtered) == 1
    
    def test_filter_empty_list(self, ingreso_types):
        """Test con lista vacía."""
        filtered = self._filter_ingreso_invoices([], ingreso_types)
        assert len(filtered) == 0
    
    def test_filter_case_insensitive(self, ingreso_types):
        """Test que el filtro es case-insensitive."""
        invoices = [
            {"id": 1, "type": "factura", "invoice_number": "B0100000001"},
            {"id": 2, "type": "Factura Privada", "invoice_number": "B0100000002"},
        ]
        filtered = self._filter_ingreso_invoices(invoices, ingreso_types)
        # Deberían incluirse ambas porque el tipo se convierte a mayúsculas
        assert len(filtered) == 2
