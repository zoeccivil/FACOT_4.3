"""
FACOT Professional - Global Stylesheet
Paleta de colores moderna y profesional para toda la aplicación
"""

GLOBAL_STYLESHEET = """
/* Configuraciones Base */
QWidget {
    font-family: 'Inter', 'Segoe UI', sans-serif;
    font-size: 14px;
    color: #0f172a;
}

QMainWindow {
    background-color: #f8fafc;
}

/* Sidebar */
#sidebar {
    background-color: #0f172a;
    min-width: 250px;
    max-width: 250px;
}

#sidebar QLabel {
    color: #f8fafc;
    font-weight: bold;
    font-size: 22px;
    margin-bottom: 20px;
}

#sidebar QPushButton {
    background-color: transparent;
    color: #94a3b8;
    border: none;
    border-radius: 8px;
    padding: 12px 20px;
    text-align: left;
    font-weight: 500;
}

#sidebar QPushButton:hover {
    background-color: #1e293b;
    color: #f8fafc;
}

#sidebar QPushButton[active="true"] {
    background-color: #1e293b;
    color: #f8fafc;
    border-left: 4px solid #3b82f6;
    border-top-left-radius: 0px;
    border-bottom-left-radius: 0px;
}

/* Header */
#header {
    background-color: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    min-height: 64px;
}

/* Cards */
#card, QGroupBox {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
}

#card_title {
    color: #64748b;
    font-size: 13px;
    font-weight: 600;
}

#card_value {
    font-size: 24px;
    font-weight: bold;
}

/* Botones Primarios */
QPushButton[class="primary"], #btn_primary {
    background-color: #2563eb;
    color: white;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    border: none;
}

QPushButton[class="primary"]:hover, #btn_primary:hover {
    background-color: #1d4ed8;
}

/* Botones Secundarios */
QPushButton {
    background-color: #f1f5f9;
    color: #0f172a;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #e2e8f0;
}

/* Tablas */
QTableWidget, QTableView {
    background-color: #ffffff;
    border: none;
    gridline-color: #e2e8f0;
    selection-background-color: #dbeafe;
    selection-color: #1e40af;
    border-radius: 8px;
}

QHeaderView::section {
    background-color: #f8fafc;
    padding: 10px;
    border: none;
    border-bottom: 1px solid #e2e8f0;
    color: #64748b;
    font-weight: bold;
    text-transform: uppercase;
    font-size: 11px;
    letter-spacing: 0.5px;
}

QTableWidget::item:alternate {
    background-color: #f8fafc;
}

QTableWidget::item:hover {
    background-color: #f1f5f9;
}

/* Inputs y Formularios */
QLineEdit, QTextEdit, QDateEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #f1f5f9;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 8px 12px;
    color: #0f172a;
}

QLineEdit:focus, QTextEdit:focus, QDateEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 2px solid #3b82f6;
    background-color: #ffffff;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #64748b;
    margin-right: 8px;
}

/* Labels */
QLabel {
    color: #0f172a;
}

QLabel[class="muted"] {
    color: #64748b;
}

QLabel[class="title"] {
    font-size: 18px;
    font-weight: bold;
}

/* Scrollbars */
QScrollBar:vertical {
    background: #f8fafc;
    width: 8px;
    margin: 0;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #e2e8f0;
    border-radius: 4px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #cbd5e1;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background: #f8fafc;
    height: 8px;
    margin: 0;
    border-radius: 4px;
}

QScrollBar::handle:horizontal {
    background: #e2e8f0;
    border-radius: 4px;
    min-width: 20px;
}

QScrollBar::handle:horizontal:hover {
    background: #cbd5e1;
}

/* Menús */
QMenuBar {
    background: #ffffff;
    color: #0f172a;
    spacing: 6px;
    border-bottom: 1px solid #e2e8f0;
}

QMenuBar::item {
    background: transparent;
    padding: 6px 12px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background: #f1f5f9;
}

QMenu {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 6px;
}

QMenu::item {
    padding: 8px 24px;
    background: transparent;
    border-radius: 4px;
}

QMenu::item:selected {
    background: #f1f5f9;
}

QMenu::separator {
    height: 1px;
    background: #e2e8f0;
    margin: 6px 12px;
}

/* Badges y Estados */
QLabel[class="badge-success"] {
    background-color: #dcfce7;
    color: #10b981;
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
}

QLabel[class="badge-warning"] {
    background-color: #fef3c7;
    color: #f59e0b;
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
}

QLabel[class="badge-error"] {
    background-color: #fee2e2;
    color: #ef4444;
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
}

/* NCF Styling (Números de Comprobante Fiscal) */
QLabel[class="ncf"], QLineEdit[class="ncf"] {
    font-family: 'Courier New', 'JetBrains Mono', monospace;
    color: #2563eb;
    font-weight: bold;
}
"""


# Paleta de colores exportable para uso programático
COLORS = {
    "sidebar_bg": "#0f172a",
    "sidebar_text": "#94a3b8",
    "sidebar_text_active": "#f8fafc",
    "sidebar_hover": "#1e293b",
    "sidebar_accent": "#3b82f6",
    
    "background": "#f8fafc",
    "surface": "#ffffff",
    "surface_alt": "#f1f5f9",
    
    "foreground": "#0f172a",
    "foreground_muted": "#64748b",
    "foreground_disabled": "#94a3b8",
    
    "primary": "#2563eb",
    "primary_hover": "#1d4ed8",
    "primary_text": "#ffffff",
    
    "secondary": "#f1f5f9",
    "secondary_hover": "#e2e8f0",
    
    "border": "#e2e8f0",
    "border_focus": "#3b82f6",
    
    "success": "#10b981",
    "warning": "#f59e0b",
    "error": "#ef4444",
    "info": "#0ea5e9",
    
    "table_header_bg": "#f8fafc",
    "table_grid": "#e2e8f0",
    "table_row_hover": "#f1f5f9",
    
    "selection_bg": "#dbeafe",
    "selection_text": "#1e40af",
    
    "header_bg": "#ffffff",
    "header_border": "#e2e8f0",
    
    # Compatibility aliases for ui_mainwindow.py
    "text_main": "#0f172a",      # alias for foreground
    "text_muted": "#64748b",     # alias for foreground_muted
    "card_bg": "#ffffff",        # alias for surface
    "card_border": "#e2e8f0"     # alias for border
}
