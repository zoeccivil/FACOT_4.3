"""
icon_manager.py
Gestor centralizado de iconos para PROGRAIN 5.0.
Utiliza 'qtawesome' para iconos vectoriales FontAwesome 6.
"""
from PyQt6.QtGui import QIcon, QColor
import logging

# Intentar importar qtawesome, si falla, usar modo fallback
try:
    import qtawesome as qta
    HAS_QTAWESOME = True
except ImportError:
    HAS_QTAWESOME = False
    logging.warning("qtawesome no está instalado. Usando iconos fallback. Ejecuta: pip install qtawesome")

class IconManager:
    """
    Provee acceso centralizado a los iconos de la aplicación.
    Mapea nombres semánticos (ej: 'dashboard') a iconos específicos (ej: 'fa6s.chart-pie').
    """
    
    # Mapa de Iconos Semánticos -> Identificadores FontAwesome
    ICON_MAP = {
        "dashboard": "fa6s.chart-pie",
        "transactions": "fa6s.money-bill-transfer",
        "cashflow": "fa6s.chart-line",
        "budget": "fa6s.piggy-bank",
        "accounts": "fa6s.building-columns",
        "categories": "fa6s.tags",
        "reports": "fa6s.file-pdf",
        "settings": "fa6s.gear",
        "import_export": "fa6s.file-import",
        "attachments": "fa6s.paperclip",
        "add": "fa6s.plus",
        "edit": "fa6s.pen",
        "delete": "fa6s.trash",
        "save": "fa6s.floppy-disk",
        "search": "fa6s.magnifying-glass",
        "refresh": "fa6s.rotate",
        "menu": "fa6s.bars",
        "close": "fa6s.xmark",
        "check": "fa6s.check",
        "theme": "fa6s.palette"
    }

    @staticmethod
    def get_icon(name: str, color: str = None) -> QIcon:
        """
        Obtiene un QIcon basado en el nombre semántico.
        Args:
            name: Nombre del icono (ej: 'dashboard')
            color: Hex color string (ej: '#FFFFFF'). Si es None, usa el default.
        """
        if not HAS_QTAWESOME:
            return QIcon() # Retorna icono vacío si no hay librería

        icon_code = IconManager.ICON_MAP.get(name, "fa6s.question")
        
        options = {}
        if color:
            options['color'] = color
            
        return qta.icon(icon_code, **options)

    @staticmethod
    def apply_icon_to_button(button, icon_name, color=None):
        """Helper para establecer icono en un botón existente"""
        button.setIcon(IconManager.get_icon(icon_name, color))