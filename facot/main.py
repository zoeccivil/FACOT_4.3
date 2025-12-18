from __future__ import annotations
import sys, os, json, types
from pathlib import Path

# Evita problemas de sandbox del WebEngine en algunos entornos
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

# FIJAR ATRIBUTO ANTES DE CREAR QApplication
from PyQt6.QtCore import Qt, QCoreApplication
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

# (Opcional) Import temprano del WebEngine
try:
    from PyQt6 import QtWebEngineWidgets, QtWebEngineCore  # noqa: F401
except Exception:
    pass

from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox


def _ensure_facot_config_loaded(app: QApplication) -> None:
    try:
        import facot_config  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    QMessageBox.information(
        None,
        "Configuración requerida",
        "No se encontró 'facot_config'. Selecciona la base de datos SQLite (*.db) que usará la aplicación.\n"
        "Este ajuste se guardará para la próxima vez."
    )
    fn, _ = QFileDialog.getOpenFileName(
        None,
        "Selecciona la base de datos",
        "",
        "SQLite (*.db);;Todos (*.*)"
    )
    if not fn:
        QMessageBox.critical(None, "Configuración", "No se seleccionó una base de datos. La aplicación se cerrará.")
        sys.exit(1)

    # Módulo dinámico mínimo
    mod = types.ModuleType("facot_config")
    def get_db_path() -> str:
        return fn
    mod.get_db_path = get_db_path  # type: ignore[attr-defined]
    def get_empresa_activa():
        return None
    mod.get_empresa_activa = get_empresa_activa  # type: ignore[attr-defined]
    sys.modules["facot_config"] = mod

    # Persistir JSON junto al ejecutable/cwd
    try:
        cfg_path = Path(os.getcwd()) / "facot_config.json"
        cfg_path.write_text(json.dumps({"db_path": fn}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        try:
            appdata = os.environ.get("APPDATA") or str(Path.home())
            cfg_dir = Path(appdata) / "FACOT"
            cfg_dir.mkdir(parents=True, exist_ok=True)
            (cfg_dir / "facot_config.json").write_text(
                json.dumps({"db_path": fn}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

def main():
    app = QApplication.instance() or QApplication(sys.argv)

    _ensure_facot_config_loaded(app)

    # ---------------------------
    # Aplicar tema GUARDADO (si hay uno) y asegurar aplicación
    # ---------------------------
    try:
        from utils.theme_manager import get_theme_manager
        tm = get_theme_manager()
        tm.set_app(app)
        saved_id = tm.load_saved_theme()
        theme_to_apply = saved_id or "light"  # default razonable
        tm.apply_theme(app, theme_to_apply)
        print(f"[THEME] Tema aplicado al inicio: {theme_to_apply}")
    except Exception as e:
        print(f"[THEME] No se pudo aplicar tema al inicio: {e}")

    # Primer inicio: materializa al lado del EXE y valida recursos
    try:
        from utils.bootstrap import ensure_first_run, ensure_required_resources
        ensure_first_run()
        # Valida solo los templates que realmente usas
        ensure_required_resources(required_template_names=["invoice_template.html", "quotation_template.html"], parent=None)
    except Exception:
        pass

    # Inicializar Firebase (abre diálogo si faltan credenciales)
    try:
        from firebase.firebase_client import ensure_initialized
        firebase_ready = ensure_initialized()
        if firebase_ready:
            print("[MAIN] Firebase inicializado correctamente")
        else:
            print("[MAIN] Firebase no disponible, usando modo offline")
    except Exception as e:
        print(f"[MAIN] Error inicializando Firebase: {e}")

    # Iniciar scheduler de backups (solo si Firebase está disponible)
    try:
        from firebase.firebase_client import get_firebase_client
        client = get_firebase_client()
        if client.is_available():
            from utils.backups import start_backup_scheduler
            start_backup_scheduler()
            print("[MAIN] Scheduler de backups iniciado")
    except Exception as e:
        print(f"[MAIN] Error iniciando scheduler de backups: {e}")

    from ui_mainwindow import MainWindow
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()