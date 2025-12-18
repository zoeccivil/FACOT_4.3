"""
Tests para persistencia de temas en FACOT.

Verifica que los temas se apliquen y persistan correctamente.
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
        """Test que get_theme retorna 'light' por defecto."""
        with patch('facot_config.load_config', return_value={}):
            import facot_config
            theme = facot_config.get_theme()
            assert theme == "light"
    
    def test_get_theme_saved(self):
        """Test que get_theme retorna el tema guardado."""
        with patch('facot_config.load_config', return_value={"theme": "dark"}):
            import facot_config
            theme = facot_config.get_theme()
            assert theme == "dark"
    
    def test_set_theme(self):
        """Test que set_theme guarda el tema."""
        saved_config = {}
        
        def mock_save(config):
            saved_config.update(config)
        
        with patch('facot_config.load_config', return_value={}):
            with patch('facot_config.save_config', side_effect=mock_save):
                import facot_config
                facot_config.set_theme("midnight")
                
                assert saved_config.get("theme") == "midnight"
    
    def test_theme_manager_available_themes(self):
        """Test que el theme manager tiene temas disponibles."""
        from utils.theme_manager import get_available_themes
        
        themes = get_available_themes()
        
        # Debe haber al menos 5 temas
        assert len(themes) >= 5
        
        # Deben existir los temas básicos
        assert "light" in themes
        assert "dark" in themes
        assert "midnight" in themes
        assert "coral" in themes
        assert "high_contrast" in themes
    
    def test_theme_manager_get_colors(self):
        """Test que se obtienen colores de temas."""
        from utils.theme_manager import get_theme_colors
        
        # Tema light
        light_colors = get_theme_colors("light")
        assert "background" in light_colors
        assert "foreground" in light_colors
        assert "primary" in light_colors
        assert light_colors["background"] == "#ffffff"
        
        # Tema dark
        dark_colors = get_theme_colors("dark")
        assert dark_colors["background"] == "#1e1e1e"
    
    def test_theme_manager_generate_stylesheet(self):
        """Test que se genera stylesheet válido."""
        from utils.theme_manager import generate_stylesheet
        
        # Generar para tema light
        qss = generate_stylesheet("light")
        
        # Debe contener propiedades CSS válidas
        assert "background-color" in qss
        assert "color" in qss
        assert "QMainWindow" in qss
        assert "QPushButton" in qss
    
    def test_theme_manager_invalid_theme_fallback(self):
        """Test que un tema inválido usa fallback a light."""
        from utils.theme_manager import get_theme_colors
        
        colors = get_theme_colors("invalid_theme")
        
        # Debe retornar colores del tema light
        assert colors["background"] == "#ffffff"
    
    def test_theme_manager_singleton(self):
        """Test que ThemeManager es singleton."""
        from utils.theme_manager import get_theme_manager
        
        manager1 = get_theme_manager()
        manager2 = get_theme_manager()
        
        assert manager1 is manager2
    
    @pytest.mark.skip(reason="Requiere QApplication")
    def test_apply_theme_to_app(self):
        """Test aplicar tema a la aplicación."""
        from utils.theme_manager import apply_theme
        from PyQt6.QtWidgets import QApplication
        
        app = QApplication.instance() or QApplication([])
        
        result = apply_theme(app, "dark")
        
        assert result is True
        assert "background-color" in app.styleSheet()
    
    @pytest.mark.skip(reason="Requiere QApplication")
    def test_save_and_apply_theme(self):
        """Test guardar y aplicar tema."""
        from utils.theme_manager import get_theme_manager
        from PyQt6.QtWidgets import QApplication
        
        app = QApplication.instance() or QApplication([])
        
        manager = get_theme_manager()
        manager.set_app(app)
        
        # Simular reinicio leyendo configuración
        with patch('facot_config.save_config'):
            result = manager.save_and_apply_theme("coral")
            assert result is True


class TestThemeColors:
    """Tests para colores de temas específicos."""
    
    def test_light_theme_is_light(self):
        """Test que el tema light tiene fondo claro."""
        from utils.theme_manager import get_theme_colors
        
        colors = get_theme_colors("light")
        
        # El fondo debe ser blanco o muy claro
        bg = colors["background"]
        assert bg.startswith("#f") or bg == "#ffffff"
    
    def test_dark_theme_is_dark(self):
        """Test que el tema dark tiene fondo oscuro."""
        from utils.theme_manager import get_theme_colors
        
        colors = get_theme_colors("dark")
        
        # El fondo debe ser oscuro
        bg = colors["background"]
        assert bg.startswith("#1") or bg.startswith("#2") or bg.startswith("#0")
    
    def test_high_contrast_has_max_contrast(self):
        """Test que high_contrast tiene máximo contraste."""
        from utils.theme_manager import get_theme_colors
        
        colors = get_theme_colors("high_contrast")
        
        # Fondo negro, texto blanco
        assert colors["background"] == "#000000"
        assert colors["foreground"] == "#ffffff"
    
    def test_all_themes_have_required_colors(self):
        """Test que todos los temas tienen los colores requeridos."""
        from utils.theme_manager import THEMES
        
        required_colors = [
            "background", "foreground", "primary", "secondary",
            "accent", "success", "warning", "error", "surface", "border"
        ]
        
        for theme_id, theme_data in THEMES.items():
            for color in required_colors:
                assert color in theme_data, f"Tema '{theme_id}' no tiene '{color}'"
                assert theme_data[color].startswith("#"), f"Color inválido en '{theme_id}.{color}'"
