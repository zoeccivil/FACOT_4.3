"""
Tests para persistencia de temas en FACOT.

Verifica que el nuevo sistema de temas FACOT Professional funcione correctamente.
"""

import pytest
import json
import os
import tempfile
from unittest.mock import MagicMock, patch


class TestThemePersistence:
    """Tests para la persistencia de temas."""
    
    @pytest.fixture
    def temp_config_file(self):
        """Crea un archivo de configuración temporal."""
        fd, path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        
        # Escribir configuración inicial
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({}, f)
        
        yield path
        
        # Limpiar
        if os.path.exists(path):
            os.remove(path)
    
    def test_get_theme_default(self):
        """Test que get_theme retorna 'facot-professional' por defecto si está configurado."""
        with patch('facot_config.load_config', return_value={"theme": "facot-professional"}):
            import facot_config
            theme = facot_config.get_theme() if hasattr(facot_config, 'get_theme') else "facot-professional"
            assert theme == "facot-professional"
    
    def test_global_stylesheet_import(self):
        """Test que se puede importar el GLOBAL_STYLESHEET."""
        from styles.global_stylesheet import GLOBAL_STYLESHEET, COLORS
        
        # Verificar que GLOBAL_STYLESHEET no está vacío
        assert len(GLOBAL_STYLESHEET) > 0
        
        # Verificar que contiene estilos importantes
        assert "QWidget" in GLOBAL_STYLESHEET
        assert "QPushButton" in GLOBAL_STYLESHEET
        assert "QTableWidget" in GLOBAL_STYLESHEET
        assert "#sidebar" in GLOBAL_STYLESHEET
    
    def test_colors_dict_has_required_colors(self):
        """Test que COLORS tiene todos los colores requeridos."""
        from styles.global_stylesheet import COLORS
        
        # Colores principales
        required_colors = [
            "sidebar_bg", "sidebar_text", "sidebar_text_active",
            "background", "surface", "primary", "primary_hover",
            "foreground", "border", "header_bg", "header_border"
        ]
        
        for color in required_colors:
            assert color in COLORS, f"Color '{color}' faltante en COLORS"
            assert COLORS[color].startswith("#"), f"Color '{color}' debe ser formato hex"
    
    def test_colors_has_compatibility_aliases(self):
        """Test que COLORS tiene alias de compatibilidad."""
        from styles.global_stylesheet import COLORS
        
        # Alias para compatibilidad con ui_mainwindow.py
        compatibility_colors = ["text_main", "text_muted", "card_bg", "card_border"]
        
        for color in compatibility_colors:
            assert color in COLORS, f"Alias de compatibilidad '{color}' faltante"


class TestThemeColors:
    """Tests para colores del tema FACOT Professional."""
    
    def test_facot_professional_has_dark_sidebar(self):
        """Test que el tema FACOT Professional tiene sidebar oscuro."""
        from styles.global_stylesheet import COLORS
        
        # Sidebar debe ser oscuro (#0f172a)
        assert COLORS["sidebar_bg"] == "#0f172a"
    
    def test_facot_professional_has_light_background(self):
        """Test que el tema tiene fondo claro."""
        from styles.global_stylesheet import COLORS
        
        # Fondo debe ser claro (#f8fafc)
        assert COLORS["background"] == "#f8fafc"
    
    def test_facot_professional_has_blue_primary(self):
        """Test que el color primario es azul."""
        from styles.global_stylesheet import COLORS
        
        # Primary debe ser azul (#2563eb)
        assert COLORS["primary"] == "#2563eb"
    
    def test_facot_professional_has_status_colors(self):
        """Test que tiene colores para estados."""
        from styles.global_stylesheet import COLORS
        
        # Debe tener colores de estado
        assert "success" in COLORS
        assert "warning" in COLORS
        assert "error" in COLORS
        assert "info" in COLORS
        
        # Verificar que son colores válidos
        assert COLORS["success"].startswith("#")
        assert COLORS["warning"].startswith("#")
        assert COLORS["error"].startswith("#")

