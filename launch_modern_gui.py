#!/usr/bin/env python3
"""
Launcher for the modern GUI using the Firebase logic controller.

- Crea QApplication primero para poder mostrar diálogos durante el bootstrap.
- Carga modern_gui.py por ruta absoluta (busca en CURRENT_DIR y cwd).
- Solicita configuración de Firebase si no está presente (usa firebase_config_bootstrap).
- Inicializa LogicControllerFirebase y lanza ModernMainWindow.
"""

from __future__ import annotations

import os
import sys
import importlib.util
import traceback
from typing import Optional

# Asegurar que la carpeta del launcher esté en sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Crear QApplication al inicio para poder mostrar QMessageBox si hace falta
from PyQt6.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication(sys.argv)

# Cargar modern_gui.py desde ruta conocida (CURRENT_DIR o cwd)
candidates = [
    os.path.join(CURRENT_DIR, "modern_gui.py"),
    os.path.join(os.getcwd(), "modern_gui.py"),
]

modern_gui_path: Optional[str] = None
for p in candidates:
    if p and os.path.exists(p) and os.path.isfile(p):
        modern_gui_path = p
        break

if modern_gui_path is None:
    QMessageBox.critical(
        None,
        "Error de importación",
        "No se encontró modern_gui.py en las rutas esperadas.\n"
        f"Se buscaron:\n  - {candidates[0]}\n  - {candidates[1]}\n\n"
        "Asegúrate de que modern_gui.py exista en el proyecto o ejecuta el launcher "
        "desde la carpeta correcta.",
    )
    sys.exit(1)

spec = importlib.util.spec_from_file_location("modern_gui", modern_gui_path)
if spec is None or spec.loader is None:
    QMessageBox.critical(
        None,
        "Error de importación",
        f"No se pudo construir el spec para modern_gui.py ({modern_gui_path})",
    )
    sys.exit(1)

modern_gui = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(modern_gui)  # type: ignore[attr-defined]
except Exception as e:
    QMessageBox.critical(
        None,
        "Error al importar modern_gui",
        f"Ocurrió un error al inicializar modern_gui.py desde:\n{modern_gui_path}\n\nError: {e}",
    )
    traceback.print_exc()
    sys.exit(1)

ModernMainWindow = getattr(modern_gui, "ModernMainWindow", None)
STYLESHEET = getattr(modern_gui, "STYLESHEET", "")

if ModernMainWindow is None:
    QMessageBox.critical(
        None,
        "Error de importación",
        "modern_gui.py se cargó pero no contiene ModernMainWindow.",
    )
    sys.exit(1)

# Aplicar stylesheet (si existe)
try:
    if STYLESHEET:
        app.setStyleSheet(STYLESHEET)
except Exception:
    pass

# Intentar inicializar LogicControllerFirebase
controller = None
try:
    from logic_firebase import LogicControllerFirebase  # type: ignore
except Exception as e:
    QMessageBox.warning(
        None,
        "Backend Firebase",
        f"No se pudo importar logic_firebase: {e}\nSe intentará operar en modo offline si es posible.",
    )
    LogicControllerFirebase = None  # type: ignore

# helper para pedir configuración si hace falta
def _ensure_controller_initialized() -> Optional[object]:
    """
    Inicializa y devuelve una instancia de LogicControllerFirebase si es posible.
    Usa firebase_config_bootstrap.ensure_firebase_config() para pedir credenciales si hace falta.
    Devuelve None si no se puede inicializar.
    """
    try:
        import facot_config  # type: ignore
    except Exception:
        facot_config = None  # type: ignore

    # Si no tenemos la clase, no hay Firebase backend disponible
    if LogicControllerFirebase is None:
        return None

    # Primero intentar inicializar sin parámetros
    try:
        ctrl = LogicControllerFirebase()
        if getattr(ctrl, "_db", None) is not None:
            return ctrl
    except Exception:
        ctrl = None

    # Intentar bootstrap de configuración (diálogo) y reintentar
    try:
        from firebase_config_bootstrap import ensure_firebase_config  # type: ignore
    except Exception:
        ensure_cfg = None
    else:
        ensure_cfg = ensure_firebase_config

    if ensure_cfg is None:
        # No hay helper para pedir config: no podemos avanzar
        return None

    cfg = ensure_cfg(parent=None)
    if not cfg:
        return None

    service_json = cfg.get("service_account_json")
    # Intentar pasar la ruta al constructor si lo soporta
    try:
        ctrl = LogicControllerFirebase(service_account_json_path=service_json)
    except TypeError:
        try:
            ctrl = LogicControllerFirebase()
        except Exception:
            ctrl = None
    except Exception:
        ctrl = None

    # Si seguimos sin db, devolver None
    if ctrl is None or getattr(ctrl, "_db", None) is None:
        return None
    return ctrl

# Inicializar controller (si posible)
controller = _ensure_controller_initialized()

# Si no hay controller Firebase, intentar fallback a LogicController local (logic.py)
if controller is None:
    try:
        from logic import LogicController  # type: ignore
        # Crear instancia local si aplica (puede necesitar path a DB)
        try:
            controller = LogicController()
        except Exception:
            controller = LogicController(db_path=getattr(None, "db_path", None))  # type: ignore
    except Exception:
        controller = None

if controller is None:
    # No es fatal si quieres abrir la UI en modo limitado, avisamos al usuario
    QMessageBox.information(
        None,
        "Modo limitado",
        "La aplicación se ejecutará en modo limitado: no se pudo inicializar el backend (Firebase/Local).",
    )

# Lanzar ventana principal
try:
    window = ModernMainWindow(controller)
    window.show()
    exit_code = app.exec()
    sys.exit(exit_code)
except Exception as e:
    QMessageBox.critical(
        None,
        "Error crítico",
        f"Ocurrió un error al iniciar la ventana principal:\n{e}",
    )
    traceback.print_exc()
    sys.exit(1)