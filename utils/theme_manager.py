"""
Compat + Theme utilities for FACOT_2.0 (persist theme id in facot_config.json)

This version ensures theme id persistence via facot_config.get_theme()/set_theme.
If those functions do not exist, it falls back to reading/writing the JSON file
facot_config.json under the project root (key: "theme").

Public API (compat):
- get_available_themes() -> dict { "dark": "Dark Focus", ... }
- get_theme_manager()    -> singleton ThemeManager
- ThemeManager.set_app(app)
- ThemeManager.load_saved_theme() -> returns saved theme id (e.g., "light")
- ThemeManager.save_and_apply_theme(theme_id) -> persist + apply
- ThemeManager.generate_stylesheet(theme_id|filename)
- ThemeManager.apply_theme(app, theme_id|filename)
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

# Paths
_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
_THEMES_DIR = os.path.join(_PROJECT_ROOT, "themes")
_BASE_QSS = os.path.join(_THEMES_DIR, "style_template.qss")
_INFOFIELDS_QSS = os.path.join(_THEMES_DIR, "infofields_transparent.qss")
_FACOT_CONFIG_JSON = os.path.join(_PROJECT_ROOT, "facot_config.json")

# Try to import facot_config helpers; if missing, we use JSON file directly
try:
    import facot_config
except Exception:
    facot_config = None


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return ""


def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


def _write_json(path: str, data: dict) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data or {}, fh, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _list_theme_files() -> List[str]:
    try:
        return [
            os.path.join(_THEMES_DIR, f)
            for f in os.listdir(_THEMES_DIR)
            if f.lower().endswith(".json")
        ]
    except Exception:
        return []


def _load_json(path: str) -> dict:
    return _read_json(path)


def _resolve_theme_file(selector: str) -> Optional[str]:
    if not selector:
        return None

    # direct filename
    if selector.endswith(".json"):
        p = os.path.join(_THEMES_DIR, selector)
        return p if os.path.exists(p) else None

    # bare name
    p = os.path.join(_THEMES_DIR, f"{selector}.json")
    if os.path.exists(p):
        return p

    # with "theme_" prefix
    p = os.path.join(_THEMES_DIR, f"theme_{selector}.json")
    if os.path.exists(p):
        return p

    # search by "id" inside files
    for path in _list_theme_files():
        data = _load_json(path)
        if str(data.get("id", "")).strip().lower() == selector.strip().lower():
            return path

    # fallback
    fallback = os.path.join(_THEMES_DIR, "theme_light.json")
    return fallback if os.path.exists(fallback) else None


def _flatten_vars_from_theme(theme_json: dict) -> Dict[str, str]:
    palette = theme_json.get("palette") or {}
    return {str(k): str(v) for k, v in palette.items()}


def _replace_tokens(qss: str, vars_map: Dict[str, str]) -> str:
    if not qss:
        return ""
    for k, v in vars_map.items():
        qss = qss.replace("{{" + k + "}}", v)
    qss = re.sub(r"\{\{[^\}]+\}\}", "", qss)
    return qss


def get_available_themes() -> Dict[str, str]:
    """
    Return dict {theme_id: display_name} by reading all themes/*.json.
    """
    out: Dict[str, str] = {}
    for path in _list_theme_files():
        data = _load_json(path)
        theme_id = str(data.get("id", "")).strip() or os.path.splitext(os.path.basename(path))[0]
        name = str(data.get("name", theme_id)).strip()
        out[theme_id] = name
    return out


def _get_saved_theme_id() -> Optional[str]:
    """
    Read saved theme id from facot_config (preferred) or facot_config.json (fallback).
    """
    # Preferred: facot_config.get_theme()
    try:
        if facot_config and hasattr(facot_config, "get_theme"):
            t = facot_config.get_theme()
            return str(t) if t else None
    except Exception:
        pass

    # Fallback: read facot_config.json
    cfg = _read_json(_FACOT_CONFIG_JSON)
    val = cfg.get("theme")
    return str(val) if val else None


def _set_saved_theme_id(theme_id: str) -> bool:
    """
    Persist theme id via facot_config.set_theme or facot_config.json fallback.
    """
    # Preferred: facot_config.set_theme
    try:
        if facot_config and hasattr(facot_config, "set_theme"):
            facot_config.set_theme(str(theme_id))
            return True
    except Exception:
        pass

    # Fallback: write to facot_config.json
    cfg = _read_json(_FACOT_CONFIG_JSON)
    cfg["theme"] = str(theme_id)
    return _write_json(_FACOT_CONFIG_JSON, cfg)


class ThemeManager:
    def __init__(self):
        self._app = None

    def set_app(self, qt_app) -> None:
        self._app = qt_app

    def generate_stylesheet(self, theme_selector: str = "light") -> str:
        theme_file = _resolve_theme_file(theme_selector)
        if not theme_file:
            return ""
        theme_json = _load_json(theme_file)
        vars_map = _flatten_vars_from_theme(theme_json)
        base_qss = _read_text(_BASE_QSS)
        info_qss = _read_text(_INFOFIELDS_QSS)
        combined = "\n\n".join([base_qss, info_qss]).strip()
        return _replace_tokens(combined, vars_map) if combined else ""

    def apply_theme(self, qt_app, theme_selector: str = "light") -> None:
        try:
            if qt_app is None:
                return
            qss = self.generate_stylesheet(theme_selector)
            if qss:
                qt_app.setStyleSheet(qss)
        except Exception:
            pass

    def load_saved_theme(self) -> Optional[str]:
        return _get_saved_theme_id()

    def save_and_apply_theme(self, theme_id: str) -> bool:
        ok = _set_saved_theme_id(str(theme_id))
        try:
            app = self._app
            if app is not None:
                self.apply_theme(app, str(theme_id))
        except Exception:
            pass
        return ok


_default_mgr: Optional[ThemeManager] = None


def get_theme_manager() -> ThemeManager:
    global _default_mgr
    if _default_mgr is None:
        _default_mgr = ThemeManager()
    return _default_mgr


def generate_stylesheet(theme_selector: str = "light") -> str:
    return get_theme_manager().generate_stylesheet(theme_selector)


def apply_theme(qt_app, theme_selector: str = "light") -> None:
    return get_theme_manager().apply_theme(qt_app, theme_selector)