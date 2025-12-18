# Compat shim `config_facot.py` — reexporta (o delega) a facot_config.py cuando está disponible,
# y proporciona implementaciones fallback consistentes cuando no lo está.
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Intentar delegar en facot_config si existe (esa es la implementación canónica).
_facot = None
try:
    import facot_config as _facot  # preferimos facot_config si está presente
except Exception:
    _facot = None

_CONFIG_FILE = "facot_config.json"

def _read_json_config() -> Dict[str, Any]:
    try:
        if os.path.exists(_CONFIG_FILE):
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _write_json_config(data: Dict[str, Any]) -> None:
    try:
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def load_config() -> Dict[str, Any]:
    if _facot and hasattr(_facot, "load_config"):
        try:
            return _facot.load_config() or {}
        except Exception:
            pass
    return _read_json_config()

def save_config(data: Dict[str, Any]) -> None:
    if _facot and hasattr(_facot, "save_config"):
        try:
            return _facot.save_config(data)
        except Exception:
            pass
    _write_json_config(data)

# DB path helpers
def get_db_path() -> str:
    if _facot and hasattr(_facot, "get_db_path"):
        try:
            return _facot.get_db_path() or ""
        except Exception:
            pass
    cfg = load_config()
    return cfg.get("db_path", "")

def set_db_path(path: str) -> None:
    if _facot and hasattr(_facot, "set_db_path"):
        try:
            return _facot.set_db_path(path)
        except Exception:
            pass
    cfg = load_config()
    cfg["db_path"] = path
    save_config(cfg)

# Theme persistence (get/set)
def get_theme() -> str:
    if _facot and hasattr(_facot, "get_theme"):
        try:
            return _facot.get_theme() or "light"
        except Exception:
            pass
    cfg = load_config()
    return cfg.get("theme", "light")

def set_theme(theme: str) -> None:
    if _facot and hasattr(_facot, "set_theme"):
        try:
            return _facot.set_theme(theme)
        except Exception:
            pass
    cfg = load_config()
    cfg["theme"] = theme
    save_config(cfg)

# Connection mode (used by MainWindow._init_db)
def get_connection_mode() -> str:
    if _facot and hasattr(_facot, "get_connection_mode"):
        try:
            return _facot.get_connection_mode() or "AUTO"
        except Exception:
            pass
    cfg = load_config()
    return cfg.get("connection_mode", "AUTO")

def set_connection_mode(mode: str) -> None:
    if _facot and hasattr(_facot, "set_connection_mode"):
        try:
            return _facot.set_connection_mode(mode)
        except Exception:
            pass
    cfg = load_config()
    cfg["connection_mode"] = str(mode).upper()
    save_config(cfg)