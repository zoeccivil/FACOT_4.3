from __future__ import annotations
import sys, os, json, types
from pathlib import Path
from PyQt6.QtCore import Qt, QCoreApplication
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
try:
    from PyQt6 import QtWebEngineWidgets, QtWebEngineCore  # noqa: F401
except Exception:
    pass
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox
from PyQt6.QtGui import QPalette, QColor

from data_access.firebase_data_access import FirebaseDataAccess
from logic import LogicController

def _ensure_facot_config_loaded(app: QApplication) -> None:
    try:
        import facot_config  # noqa: F401
        return
    except ModuleNotFoundError:
        pass
    QMessageBox.information(None, "Configuración requerida",
                            "No se encontró 'facot_config'. Selecciona la base de datos SQLite (*.db).")
    fn, _ = QFileDialog.getOpenFileName(None, "Selecciona la base de datos", "", "SQLite (*.db);;Todos (*.*)")
    if not fn:
        fn = str(Path(os.getcwd()) / "dummy_fallback.db")
    mod = types.ModuleType("facot_config")
    def get_db_path() -> str: return fn
    mod.get_db_path = get_db_path
    def get_empresa_activa(): return None
    mod.get_empresa_activa = get_empresa_activa
    def get_firebase_config():
        # Fallback vacío si no hay config persistida
        return "", ""
    mod.get_firebase_config = get_firebase_config
    sys.modules["facot_config"] = mod
    try:
        cfg_path = Path(os.getcwd()) / "facot_config.json"
        cfg_path.write_text(json.dumps({"db_path": fn}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def _apply_safe_menu_styles(app: QApplication, theme_id: str = "light") -> None:
    """
    Apply safe menu and menubar styles to ensure text is always readable.
    Does NOT override the full palette - only adds menu-specific stylesheet.
    Respects dark vs light theme.
    """
    try:
        app.setStyle("Fusion")
    except Exception:
        pass

    # Determine if this is a dark theme
    is_dark = theme_id and ("dark" in theme_id.lower() or "midnight" in theme_id.lower())

    if is_dark:
        # Dark theme menu styles
        menu_stylesheet = """
        QMenuBar {
            background: #1e293b;
            color: #f1f5f9;
            spacing: 6px;
        }
        QMenuBar::item {
            background: transparent;
            padding: 6px 12px;
        }
        QMenuBar::item:selected {
            background: #334155;
            color: #f1f5f9;
        }
        QMenuBar::item:pressed {
            background: #475569;
        }

        QMenu {
            background-color: #1e293b;
            color: #f1f5f9;
            border: 1px solid #475569;
            padding: 6px;
        }
        QMenu::item {
            padding: 6px 16px;
            background: transparent;
        }
        QMenu::item:selected {
            background: #334155;
            color: #ffffff;
        }
        QMenu::separator {
            height: 1px;
            background: #475569;
            margin: 4px 8px;
        }

        QMenu::item:disabled, QMenuBar::item:disabled {
            color: #64748b;
        }
        """
    else:
        # Light theme menu styles
        menu_stylesheet = """
        QMenuBar {
            background: #f8fafc;
            color: #1e293b;
            spacing: 6px;
        }
        QMenuBar::item {
            background: transparent;
            padding: 6px 12px;
        }
        QMenuBar::item:selected {
            background: #e2e8f0;
            color: #1e293b;
        }
        QMenuBar::item:pressed {
            background: #cbd5e1;
        }

        QMenu {
            background-color: #ffffff;
            color: #1e293b;
            border: 1px solid #e2e8f0;
            padding: 6px;
        }
        QMenu::item {
            padding: 6px 16px;
            background: transparent;
        }
        QMenu::item:selected {
            background: #f1f5f9;
            color: #1e293b;
        }
        QMenu::separator {
            height: 1px;
            background: #e2e8f0;
            margin: 4px 8px;
        }

        QMenu::item:disabled, QMenuBar::item:disabled {
            color: #94a3b8;
        }
        """

    # Get existing stylesheet and append menu styles
    existing = app.styleSheet() or ""
    # Use regex to check if QMenuBar styles already exist (more robust than simple string search)
    import re
    has_menubar_styles = bool(re.search(r'QMenuBar\s*\{', existing))
    
    if not has_menubar_styles:
        app.setStyleSheet(existing + "\n" + menu_stylesheet)




def main():
    app = QApplication.instance() or QApplication(sys.argv)

    _ensure_facot_config_loaded(app)
    import facot_config

    # Tema
    theme_to_apply = "light"  # default
    try:
        from utils.theme_manager import get_theme_manager
        tm = get_theme_manager()
        tm.set_app(app)
        saved_id = tm.load_saved_theme()
        # Use saved theme if it exists and is not None or empty string
        theme_to_apply = saved_id if (saved_id is not None and saved_id) else "light"
        tm.apply_theme(app, theme_to_apply)
        print(f"[THEME] Tema aplicado al inicio: {theme_to_apply}")
    except Exception as e:
        print(f"[THEME] No se pudo aplicar tema al inicio: {e}")

    # Paleta/estilos seguros para menú (soluciona texto blanco en exe)
    # Aplica después del tema para no sobrescribir, solo agrega estilos de menú
    try:
        _apply_safe_menu_styles(app, theme_to_apply)
    except Exception as e:
        print(f"[THEME] No se pudo aplicar estilos seguros de menú: {e}")

    # Recursos
    try:
        from utils.bootstrap import ensure_first_run, ensure_required_resources
        ensure_first_run()
        ensure_required_resources(required_template_names=["invoice_template.html", "quotation_template.html"], parent=None)
    except Exception:
        pass

    # FORZAR reinicialización de Firebase con valores del config
    firebase_ready = False
    try:
        cred_path, bucket = facot_config.get_firebase_config()
        from firebase.firebase_client import reinitialize_firebase
        if cred_path and bucket:
            # Normalizar bucket a appspot.com si fuera necesario
            b = bucket.strip()
            if b.endswith(".firebasestorage.app"):
                b = b.replace(".firebasestorage.app", ".appspot.com")
            if not b.endswith(".appspot.com"):
                b = f"{b}.appspot.com"
            firebase_ready = reinitialize_firebase(cred_path, b)
        else:
            from firebase.firebase_client import ensure_initialized
            firebase_ready = ensure_initialized()
        print("[MAIN] Firebase inicializado correctamente" if firebase_ready else "[MAIN] Firebase no disponible")
    except Exception as e:
        print(f"[MAIN] Error inicializando Firebase: {e}")

    # DataAccess
    data_access = None
    if firebase_ready:
        try:
            current_user = os.environ.get("USERNAME", "system")
            data_access = FirebaseDataAccess(user_id=current_user)
            print(f"[MAIN] DataAccess creado. Usuario: {current_user}")
        except Exception as e:
            print(f"[MAIN] Error crítico creando FirebaseDataAccess: {e}")

    # LogicController
    db_path = facot_config.get_db_path()
    logic = LogicController(db_path=db_path, data_access=data_access)

    if data_access:
        print("[MAIN] >>> MODO FIREBASE ACTIVADO <<<")
        try:
            from utils.backups import start_backup_scheduler
            start_backup_scheduler()
            print("[MAIN] Scheduler de backups iniciado")
        except Exception as e:
            print(f"[MAIN] Error iniciando scheduler: {e}")
    else:
        print("[MAIN] !!! MODO OFFLINE (SQLITE) !!!")

    from ui_mainwindow import MainWindow
    try:
        w = MainWindow(logic_controller=logic)
    except TypeError:
        print("[MAIN] Constructor de MainWindow no acepta argumentos. Iniciando estándar...")
        w = MainWindow()

    print("[MAIN] 🛡️  BLINDAJE: Forzando LogicController correcto en la ventana principal...")
    w.logic = logic
    if hasattr(w, 'controller'):
        w.controller = logic
    if hasattr(w, 'invoice_tab'):
        print("[MAIN] Inyectando lógica en Pestaña Facturas...")
        if hasattr(w.invoice_tab, 'logic'): w.invoice_tab.logic = logic
        if hasattr(w.invoice_tab, 'controller'): w.invoice_tab.controller = logic
        if hasattr(w.invoice_tab, 'load_invoices'): w.invoice_tab.load_invoices()
    if hasattr(w, 'quotation_tab'):
        print("[MAIN] Inyectando lógica en Pestaña Cotizaciones...")
        if hasattr(w.quotation_tab, 'logic'): w.quotation_tab.logic = logic
        if hasattr(w.quotation_tab, 'controller'): w.quotation_tab.controller = logic

    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()