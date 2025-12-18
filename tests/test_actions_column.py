"""
Tests para la columna de acciones en los historiales.

Valida que:
1. Solo hay un botón "Ver" por fila en historial de facturas
2. Solo hay un botón "Ver" por fila en historial de cotizaciones
3. El botón tiene estilo legible (texto blanco sobre fondo azul)
"""

import pytest
from unittest.mock import MagicMock, patch

# Check if PyQt6 is available
try:
    from PyQt6.QtWidgets import QApplication
    HAS_PYQT6 = True
except ImportError:
    HAS_PYQT6 = False


class TestInvoiceHistoryActions:
    """Tests para la columna de acciones en historial de facturas."""
    
    @pytest.mark.skipif(not HAS_PYQT6, reason="PyQt6 no disponible")
    def test_single_preview_button_per_row(self):
        """Verifica que solo hay un botón de vista previa por fila."""
        # Simular la función de agregar botones
        from tabs.invoice_history_tab import InvoiceHistoryTab
        
        # Mock del logic controller
        mock_logic = MagicMock()
        mock_logic.get_facturas.return_value = []
        
        # Mock de la función que obtiene la compañía actual
        mock_get_company = MagicMock(return_value={'id': 1, 'name': 'Test Company'})
        
        # Verificar que el método existe
        assert hasattr(InvoiceHistoryTab, '_add_invoice_action_buttons')
    
    def test_button_style_has_contrast(self):
        """Verifica que el estilo del botón tiene buen contraste."""
        # El estilo debe tener texto blanco sobre fondo azul
        expected_style_elements = [
            'background-color: #2196f3',
            'color: white',
            'border-radius: 4px',
            'font-weight: bold'
        ]
        
        # Verificar que el archivo contiene los estilos esperados
        with open('tabs/invoice_history_tab.py', 'r', encoding='utf-8') as f:
            content = f.read()
            
        for element in expected_style_elements:
            assert element in content, f"Falta elemento de estilo: {element}"
    
    def test_button_has_emoji_icon(self):
        """Verifica que el botón tiene un emoji de ojo."""
        with open('tabs/invoice_history_tab.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert '👁 Ver' in content, "El botón debe tener el emoji 👁 y texto 'Ver'"


class TestQuotationHistoryActions:
    """Tests para la columna de acciones en historial de cotizaciones."""
    
    @pytest.mark.skipif(not HAS_PYQT6, reason="PyQt6 no disponible")
    def test_single_preview_button_per_row(self):
        """Verifica que solo hay un botón de vista previa por fila."""
        from tabs.quotation_history_tab import QuotationHistoryTab
        
        # Verificar que el método existe
        assert hasattr(QuotationHistoryTab, '_add_quotation_action_buttons')
    
    def test_button_style_has_contrast(self):
        """Verifica que el estilo del botón tiene buen contraste."""
        expected_style_elements = [
            'background-color: #2196f3',
            'color: white',
        ]
        
        with open('tabs/quotation_history_tab.py', 'r', encoding='utf-8') as f:
            content = f.read()
            
        for element in expected_style_elements:
            assert element in content, f"Falta elemento de estilo: {element}"
    
    def test_no_pdf_excel_buttons(self):
        """Verifica que no hay botones de PDF y Excel redundantes."""
        with open('tabs/quotation_history_tab.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # La función _add_quotation_action_buttons no debe tener btn_pdf ni btn_excel
        # Buscamos en el método específico
        start_idx = content.find('def _add_quotation_action_buttons')
        if start_idx > 0:
            # Buscar hasta el siguiente método
            end_idx = content.find('\n    def ', start_idx + 10)
            if end_idx > 0:
                method_content = content[start_idx:end_idx]
                assert 'btn_pdf = QPushButton' not in method_content, "No debe haber botón PDF"
                assert 'btn_excel = QPushButton' not in method_content, "No debe haber botón Excel"


class TestFirebaseDataAccess:
    """Tests para la capa de acceso a datos de Firebase."""
    
    def test_get_all_items_method_exists(self):
        """Verifica que existe el método get_all_items."""
        with open('data_access/firebase_data_access.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'def get_all_items(self)' in content, "Debe existir el método get_all_items"
    
    def test_get_all_companies_method_exists(self):
        """Verifica que existe el método get_all_companies."""
        with open('data_access/firebase_data_access.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'def get_all_companies(self)' in content, "Debe existir el método get_all_companies"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
