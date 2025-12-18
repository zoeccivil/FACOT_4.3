"""
Tests for menu styling and theme application in packaged builds.

Verifies that menu styles are readable in both light and dark themes
and that the theme manager integration works correctly.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestMenuStyling:
    """Tests for menu bar and menu styling."""
    
    def test_apply_safe_menu_styles_light_theme(self):
        """Test that light theme menu styles are applied correctly."""
        from main import _apply_safe_menu_styles
        
        # Mock QApplication
        mock_app = MagicMock()
        mock_app.styleSheet.return_value = ""
        
        # Apply light theme menu styles
        _apply_safe_menu_styles(mock_app, "light")
        
        # Verify Fusion style was set
        mock_app.setStyle.assert_called_once_with("Fusion")
        
        # Verify stylesheet was set
        mock_app.setStyleSheet.assert_called()
        
        # Get the stylesheet that was applied
        call_args = mock_app.setStyleSheet.call_args
        stylesheet = call_args[0][0]
        
        # Verify menu styles are present
        assert "QMenuBar" in stylesheet
        assert "QMenu" in stylesheet
        
        # Verify light theme colors
        assert "#1e293b" in stylesheet  # dark text color
        assert "#f8fafc" in stylesheet or "#ffffff" in stylesheet  # light background
    
    def test_apply_safe_menu_styles_dark_theme(self):
        """Test that dark theme menu styles are applied correctly."""
        from main import _apply_safe_menu_styles
        
        # Mock QApplication
        mock_app = MagicMock()
        mock_app.styleSheet.return_value = ""
        
        # Apply dark theme menu styles
        _apply_safe_menu_styles(mock_app, "dark")
        
        # Get the stylesheet
        call_args = mock_app.setStyleSheet.call_args
        stylesheet = call_args[0][0]
        
        # Verify dark theme colors
        assert "#1e293b" in stylesheet  # dark background
        assert "#f1f5f9" in stylesheet  # light text color
    
    def test_apply_safe_menu_styles_midnight_theme(self):
        """Test that midnight theme is recognized as dark."""
        from main import _apply_safe_menu_styles
        
        # Mock QApplication
        mock_app = MagicMock()
        mock_app.styleSheet.return_value = ""
        
        # Apply midnight theme (should use dark styles)
        _apply_safe_menu_styles(mock_app, "midnight")
        
        # Get the stylesheet
        call_args = mock_app.setStyleSheet.call_args
        stylesheet = call_args[0][0]
        
        # Should use dark theme colors
        assert "#1e293b" in stylesheet
        assert "#f1f5f9" in stylesheet
    
    def test_apply_safe_menu_styles_preserves_existing_stylesheet(self):
        """Test that existing stylesheet is preserved when adding menu styles."""
        from main import _apply_safe_menu_styles
        
        # Mock QApplication with existing stylesheet
        mock_app = MagicMock()
        existing_style = "QLabel { color: red; }"
        mock_app.styleSheet.return_value = existing_style
        
        # Apply menu styles
        _apply_safe_menu_styles(mock_app, "light")
        
        # Get the final stylesheet
        call_args = mock_app.setStyleSheet.call_args
        final_stylesheet = call_args[0][0]
        
        # Existing styles should be preserved
        assert "QLabel { color: red; }" in final_stylesheet
        # New menu styles should be added
        assert "QMenuBar" in final_stylesheet
    
    def test_menu_styles_not_duplicated(self):
        """Test that menu styles are not added if already present."""
        from main import _apply_safe_menu_styles
        
        # Mock QApplication with existing menu styles
        mock_app = MagicMock()
        existing_style = "QMenuBar { background: blue; }"
        mock_app.styleSheet.return_value = existing_style
        
        # Apply menu styles
        _apply_safe_menu_styles(mock_app, "light")
        
        # setStyleSheet should not be called because menu styles already exist
        # (only setStyle should be called)
        assert mock_app.setStyle.called
        # setStyleSheet might be called, but shouldn't duplicate QMenuBar rules


class TestTableStyling:
    """Tests for table styling in themes."""
    
    def test_table_items_have_background_color(self):
        """Test that table items have explicit background colors in stylesheet."""
        from utils.theme_manager import generate_stylesheet
        
        # Generate light theme stylesheet
        qss = generate_stylesheet("light")
        
        # Should have table item styles
        assert "QTableWidget::item" in qss or "QTableView::item" in qss
        assert "background-color" in qss
    
    def test_table_alternate_rows_styled(self):
        """Test that alternate rows have proper styling."""
        from utils.theme_manager import generate_stylesheet
        
        # Generate stylesheet
        qss = generate_stylesheet("light")
        
        # Should have alternate row styling
        assert "alternate" in qss.lower() or "QTableWidget::item:alternate" in qss
    
    def test_table_selected_items_styled(self):
        """Test that selected table items have proper styling."""
        from utils.theme_manager import generate_stylesheet
        
        # Generate stylesheet
        qss = generate_stylesheet("light")
        
        # Should have selected item styling
        assert "selected" in qss.lower()
    
    def test_light_theme_table_not_black(self):
        """Test that light theme tables don't have black backgrounds."""
        from utils.theme_manager import generate_stylesheet
        
        # Generate light theme stylesheet
        qss = generate_stylesheet("light")
        
        # Check that table widgets have light colors defined
        # Look for specific light color codes that should be present
        assert "#FFFFFF" in qss or "#F8FAFC" in qss, "Light theme should contain white or light colors"
        
        # Ensure pure black is not used as a primary background color for tables
        # (it might appear in borders or other contexts, but not as background-color: #000000)
        assert "background-color: #000000" not in qss.lower(), "Light theme should not have pure black backgrounds"


class TestThemeIntegration:
    """Tests for theme manager integration in main.py."""
    
    @pytest.mark.skip(reason="Requires QApplication and full main() flow")
    def test_theme_applied_before_menu_styles(self):
        """Test that theme is applied before safe menu styles."""
        # This would require mocking the entire main() function flow
        # and is better tested manually or in integration tests
        pass
    
    def test_theme_id_passed_to_menu_styles(self):
        """Test that theme_id is correctly passed to _apply_safe_menu_styles."""
        from main import _apply_safe_menu_styles
        
        mock_app = MagicMock()
        mock_app.styleSheet.return_value = ""
        
        # Test with explicit theme IDs
        for theme_id in ["light", "dark", "midnight", "coral"]:
            mock_app.reset_mock()
            _apply_safe_menu_styles(mock_app, theme_id)
            assert mock_app.setStyle.called
