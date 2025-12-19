"""
Tests for menu styling and theme application in packaged builds.

Verifies that the FACOT Professional theme includes proper menu styles
and that the global stylesheet is applied correctly.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestMenuStyling:
    """Tests for menu bar and menu styling in FACOT Professional theme."""
    
    def test_apply_safe_menu_styles_is_noop(self):
        """Test that _apply_safe_menu_styles is now a no-op (menu styles in global stylesheet)."""
        from main import _apply_safe_menu_styles
        
        # Mock QApplication
        mock_app = MagicMock()
        
        # Apply menu styles - should do nothing now
        _apply_safe_menu_styles(mock_app)
        
        # Should not set style or stylesheet (it's a pass function now)
        mock_app.setStyle.assert_not_called()
        mock_app.setStyleSheet.assert_not_called()
    
    def test_global_stylesheet_has_menu_styles(self):
        """Test that GLOBAL_STYLESHEET includes menu styles."""
        from styles.global_stylesheet import GLOBAL_STYLESHEET
        
        # Verify menu styles are present
        assert "QMenuBar" in GLOBAL_STYLESHEET
        assert "QMenu" in GLOBAL_STYLESHEET
        
        # Verify menu styling properties
        assert "background" in GLOBAL_STYLESHEET
        assert "color" in GLOBAL_STYLESHEET
    
    def test_global_stylesheet_has_light_menu_colors(self):
        """Test that GLOBAL_STYLESHEET uses light theme menu colors."""
        from styles.global_stylesheet import GLOBAL_STYLESHEET
        
        # Should have light background for menus
        assert "#ffffff" in GLOBAL_STYLESHEET  # white background
        assert "#0f172a" in GLOBAL_STYLESHEET  # dark text


class TestTableStyling:
    """Tests for table styling in FACOT Professional theme."""
    
    def test_table_items_have_background_color(self):
        """Test that table items have explicit background colors in stylesheet."""
        from styles.global_stylesheet import GLOBAL_STYLESHEET
        
        # Should have table item styles
        assert "QTableWidget" in GLOBAL_STYLESHEET or "QTableView" in GLOBAL_STYLESHEET
        assert "background-color" in GLOBAL_STYLESHEET
    
    def test_table_alternate_rows_styled(self):
        """Test that alternate rows have proper styling."""
        from styles.global_stylesheet import GLOBAL_STYLESHEET
        
        # Should have alternate row styling
        assert "alternate" in GLOBAL_STYLESHEET.lower()
    
    def test_table_selected_items_styled(self):
        """Test that selected table items have proper styling."""
        from styles.global_stylesheet import GLOBAL_STYLESHEET
        
        # Should have selection styling
        assert "selection-background-color" in GLOBAL_STYLESHEET or "selected" in GLOBAL_STYLESHEET.lower()
    
    def test_light_theme_table_not_black(self):
        """Test that tables don't have black backgrounds."""
        from styles.global_stylesheet import GLOBAL_STYLESHEET
        
        # Check that table widgets have light colors defined
        assert "#ffffff" in GLOBAL_STYLESHEET or "#f8fafc" in GLOBAL_STYLESHEET
        
        # Ensure pure black is not used as a primary background color
        assert "background-color: #000000" not in GLOBAL_STYLESHEET.lower()


class TestThemeIntegration:
    """Tests for theme integration in main.py."""
    
    def test_global_stylesheet_can_be_imported_in_main(self):
        """Test that GLOBAL_STYLESHEET can be imported from main.py."""
        # This simulates what main.py does
        try:
            from styles.global_stylesheet import GLOBAL_STYLESHEET
            assert len(GLOBAL_STYLESHEET) > 0
            assert isinstance(GLOBAL_STYLESHEET, str)
        except ImportError as e:
            pytest.fail(f"Failed to import GLOBAL_STYLESHEET: {e}")
    
    def test_colors_can_be_imported(self):
        """Test that COLORS dict can be imported."""
        try:
            from styles.global_stylesheet import COLORS
            assert isinstance(COLORS, dict)
            assert len(COLORS) > 0
        except ImportError as e:
            pytest.fail(f"Failed to import COLORS: {e}")

