#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import webbrowser
import re
import urllib.parse
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QDialog, QFileDialog, QMessageBox
)

# Optional config import
try:
    import config_facot
except Exception:
    class _Cfg:
        INVOICE_DUE_DAYS = 0
        INVOICE_FIXED_DUE_DATE = ""
        COMPANY_LOGOS = {}
        DEFAULT_LOGO_PATH = ""
        PDF_SIGNED_URL_DAYS = 7
    config_facot = _Cfg()

# local helpers
try:
    from utils.html_injector import build_html_with_json_block
except Exception:
    build_html_with_json_block = None

try:
    from utils.template_manager import get_data_root
except Exception:
    def get_data_root():
        return os.getcwd()

# PDF generator import (use the new utils/pdf_generator.py)
try:
    from utils.pdf_generator import PDFGenerator
except Exception:
    PDFGenerator = None  # We'll check at runtime and show message if missing


def _to_file_uri(path: str) -> str:
    if not path:
        return ""
    p = os.path.abspath(path)
    if os.name == "nt":
        return "file:///" + p.replace("\\", "/")
    return "file://" + p


def _resolve_logo_uri(company: Dict[str, Any], tpl_from_db: Optional[Dict[str, Any]] = None) -> str:
    candidates: List[str] = []
    db_logo = (company or {}).get("logo_path") or ""
    if db_logo:
        candidates.append(db_logo)
    tpl_logo = (tpl_from_db or {}).get("logo_path") or ""
    if tpl_logo:
        candidates.append(tpl_logo)

    logos = getattr(config_facot, "COMPANY_LOGOS", {}) or {}
    cid = company.get("id")
    name = (company.get("name") or "").strip()
    if cid is not None:
        key_id = str(cid)
        if key_id in logos:
            candidates.append(logos[key_id])
    if name and name in logos:
        candidates.append(logos[name])

    default_logo = getattr(config_facot, "DEFAULT_LOGO_PATH", "") or ""
    if default_logo:
        candidates.append(default_logo)

    root = get_data_root()

    for c in candidates:
        if not c:
            continue

        if isinstance(c, str) and c.startswith("file:///"):
            local = c.replace("file:///", "")
            if os.path.exists(local):
                return c
            continue

        try:
            rel = os.path.join(root, c)
            if os.path.exists(rel):
                return _to_file_uri(rel)
        except Exception:
            pass

        if os.path.isabs(c) and os.path.exists(c):
            return _to_file_uri(c)

        if c.startswith(("http://", "https://")):
            return c

    return ""


def _local_build_html_with_json_block(template_path: str, company: Dict[str, Any], tpl: Dict[str, Any], quotation: Dict[str, Any]) -> str:
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()
    payload = {"COMPANY": company or {}, "TEMPLATE": tpl or {}, "QUOTATION": quotation or {}}
    js = json.dumps(payload, ensure_ascii=False)
    js = js.replace("</script>", "<\\/script>")
    html = html.replace("/* INJECT_JSON_PLACEHOLDER */", js)
    return html


def compute_display_number(q: Dict[str, Any], comp: Dict[str, Any]) -> str:
    if q and (q.get("display_number") or q.get("number")):
        return q.get("display_number") or q.get("number")
    name = (comp and comp.get("name")) or ""
    try:
        letters = name.encode("ascii", "ignore").decode("ascii")
    except Exception:
        letters = re.sub(r"[^A-Za-z]", "", name)
    letters = re.sub(r"[^A-Za-z]", "", letters)
    prefix = (letters[:3] or "EMP").upper()
    try:
        idv = int(q.get("id") or 0)
    except Exception:
        idv = 0
    return f"COT-{prefix}-{idv:06d}"


def _safe_for_filename(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"[^A-Za-z0-9 \\-_]+", "", s)
    s = s.replace(" ", "_")
    return s or "company"


def _prepare_company_data_for_preview(company_record: Dict[str, Any], tpl_from_db: Optional[Dict[str, Any]] = None, logic_controller=None) -> Dict[str, Any]:
    company = dict(company_record or {})

    try:
        cid = company.get("id")
        if logic_controller and cid:
            fresh = logic_controller.get_company_details(cid) or {}
            for key in [
                "address_line1","address_line2","address","signature_name","authorized_name","logo_path",
                "phone","email","rnc","invoice_due_date",
                "primary_color","secondary_color","font_name","font_size","layout","header_lines","footer_lines","show_logo"
            ]:
                if company.get(key) in (None, "", []) and fresh.get(key) is not None:
                    company[key] = fresh.get(key)
    except Exception as e:
        print(f"  [FALLBACK ERROR] get_company_details failed: {e}")

    company["name"] = company.get("name") or "Nombre Empresa"
    company["rnc"] = company.get("rnc") or company.get("rnc_number") or ""
    company["phone"] = company.get("phone") or company.get("telefono") or ""
    company["email"] = company.get("email") or company.get("correo") or ""

    a1 = (company.get("address_line1") or company.get("address") or "").strip()
    a2 = (company.get("address_line2") or "").strip()
    full_addr = (a1 + (" " + a2 if a2 else "")).strip()
    company["address"] = full_addr or "Dirección no especificada"

    company["logo_path"] = _resolve_logo_uri(company, tpl_from_db)

    company["primary_color"] = company.get("primary_color") or (tpl_from_db or {}).get("primary_color") or "#0087C3"
    company["secondary_color"] = company.get("secondary_color") or (tpl_from_db or {}).get("secondary_color") or "#F5F5F5"

    sig = company.get("authorized_name") or company.get("signature_name") or ""
    company["signature_name"] = sig
    company["authorized_name"] = sig

    return company


class QuotationPreviewDialog(QDialog):
    """
    Versión sin preview HTML: se usa solo para generar / subir PDFs de cotización.
    Recomendación: instanciar con auto_export=True.
    """

    def __init__(
        self,
        company: Dict[str, Any],
        template: Dict[str, Any],
        quotation: Dict[str, Any],
        template_path: str = "templates/quotation_template.html",
        parent=None,
        debug: bool = False,
        auto_export: bool = False,          # Si True: generar PDF y salir (sin mostrar diálogo)
        open_after_generate: bool = False,  # Abrir PDF local después de generarlo
    ):
        super().__init__(parent)
        self.setWindowTitle("Exportar cotización a PDF")

        self.raw_company = company or {}
        self.raw_template = template or {}
        self.raw_quotation = quotation or {}
        self.template_path = template_path
        self.debug = bool(debug)
        self.auto_export = bool(auto_export)
        self.open_after_generate = bool(open_after_generate)
        self._last_payload: Dict[str, Any] = {}

        company_p, tpl_p, q_p = self._build_injectable_payloads()
        self._last_payload = {"COMPANY": company_p, "TEMPLATE": tpl_p, "QUOTATION": q_p}

        if self.auto_export:
            try:
                self._on_export_pdf()
            except Exception as e:
                print(f"[AUTO_EXPORT QUOT ERROR] {e}")
            return

        # Si se abre manualmente, exportamos una sola vez y cerramos.
        self._on_export_pdf()
        self.accept()

    # ---------------------------------------------------------------- utils
    def _build_injectable_payloads(self):
        logic_ctrl = None
        try:
            if hasattr(self.parent(), "logic"):
                logic_ctrl = self.parent().logic
        except Exception:
            logic_ctrl = None

        company = _prepare_company_data_for_preview(self.raw_company, self.raw_template, logic_controller=logic_ctrl)

        tpl = dict(self.raw_template or {})
        tpl["primary_color"] = company.get("primary_color") or tpl.get("primary_color", "#0087C3")
        tpl["secondary_color"] = company.get("secondary_color") or tpl.get("secondary_color", "#F5F5F5")

        quotation = dict(self.raw_quotation or {})
        items = quotation.get("items") or quotation.get("_items") or []
        quotation["items"] = list(items or [])

        for it in quotation["items"]:
            if not it.get("unit"):
                it["unit"] = "UND"

        subtotal = 0.0
        for it in quotation["items"]:
            try:
                subtotal += float(it.get("quantity", 0)) * float(it.get("unit_price", 0))
            except Exception:
                pass

        try:
            rate = float(tpl.get("itbis_rate", 0.18) or 0.18)
        except Exception:
            rate = 0.18

        apply = quotation.get("apply_itbis")
        if apply is None:
            apply = True
        else:
            apply = bool(apply)

        itbis_val = subtotal * rate if apply else 0.0
        quotation["subtotal"] = subtotal
        quotation["itbis"] = itbis_val
        quotation["total_amount"] = subtotal + itbis_val
        quotation["apply_itbis"] = apply
        quotation["itbis_rate"] = rate

        print("[QP] _build_injectable_payloads() -> company.id/name:", company.get("id"), company.get("name"))
        print("[QP] _build_injectable_payloads() -> quotation.id/date:", quotation.get("id"), quotation.get("date"))
        print("[QP] _build_injectable_payloads() -> items len:", len(quotation.get("items", [])))

        return company, tpl, quotation

    # ---------------------------------------------------------------- PDF
    def _on_export_pdf(self):
        """
        Genera PDF con ReportLab (utils.pdf_generator.PDFGenerator),
        guarda localmente, luego intenta upload y registra PDF info en backend.
        """
        try:
            if PDFGenerator is None:
                QMessageBox.critical(
                    self,
                    "Exportar PDF",
                    "Módulo PDFGenerator no está disponible. Instala reportlab (pip install reportlab).",
                )
                return

            payload = getattr(self, "_last_payload", {}) or {}
            comp = (payload.get("COMPANY") or self.raw_company or {}) or {}
            tpl = (payload.get("TEMPLATE") or self.raw_template or {}) or {}
            q = (payload.get("QUOTATION") or self.raw_quotation or {}) or {}

            display_number = compute_display_number(q, comp)
            q["display_number"] = display_number

            company_name = (comp.get("name") or "").strip() or "EMPRESA"
            safe_company = _safe_for_filename(company_name)
            suggested = f"{safe_company}-{display_number}.pdf"

            fn, _ = QFileDialog.getSaveFileName(
                self,
                "Guardar Cotización como PDF",
                suggested,
                "PDF Files (*.pdf)",
            )
            if not fn:
                return
            save_path = fn if fn.lower().endswith(".pdf") else fn + ".pdf"

            print(f"[QP] Generating PDF -> {save_path}")
            generator = PDFGenerator(
                primary_color=tpl.get("primary_color", "#0087C3"),
                secondary_color=tpl.get("secondary_color", "#F5F5F5"),
            )
            gen_payload = {"COMPANY": comp, "TEMPLATE": tpl, "QUOTATION": q}

            try:
                generator.generate_pdf(gen_payload, save_path)
            except Exception as e_pdf:
                print(f"[QP] Error generating PDF: {e_pdf}")
                QMessageBox.critical(self, "PDF", f"No se pudo generar el PDF:\n{e_pdf}")
                return

            if getattr(self, "open_after_generate", False):
                try:
                    if os.name == "nt":
                        os.startfile(save_path)
                    else:
                        webbrowser.open("file://" + os.path.abspath(save_path))
                except Exception:
                    pass

            QMessageBox.information(self, "PDF", f"PDF generado:\n{save_path}")

            # ---- Upload logic ----
            try:
                file_name = (
                    q.get("quotation_number")
                    or q.get("number")
                    or display_number
                    or f"DRAFT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
                ).strip()
                year = (q.get("date") or datetime.utcnow().strftime("%Y-%m-%d"))[:4]
                month = (q.get("date") or datetime.utcnow().strftime("%Y-%m-%d"))[5:7]
                storage_path = f"cotizacion/{safe_company}/{year}/{month}/{file_name}.pdf"
                print(f"[QT-UPLOAD] local={save_path} -> storage_path={storage_path}")
            except Exception as e_st:
                print(f"[QT-UPLOAD] Error building storage_path: {e_st}")
                storage_path = None

            logic = None
            try:
                if hasattr(self.parent(), "logic"):
                    logic = getattr(self.parent(), "logic")
            except Exception:
                logic = None
            da = None
            if logic is not None:
                da = getattr(logic, "data_access", None) or logic
            else:
                try:
                    from data_access.firebase_data_access import FirebaseDataAccess  # type: ignore
                    da = FirebaseDataAccess(user_id="system")
                except Exception:
                    da = None

            upload_url = None
            if storage_path:
                try:
                    if logic and hasattr(logic, "upload_file_to_storage"):
                        upload_url = logic.upload_file_to_storage(save_path, storage_path)
                    elif da and hasattr(da, "upload_file_to_storage"):
                        upload_url = da.upload_file_to_storage(save_path, storage_path)
                    else:
                        print("[QT-UPLOAD] No se encontró upload_file_to_storage en logic/data_access")
                except Exception as ex_up:
                    print(f"[QT-UPLOAD] Excepción durante upload: {ex_up}")

            print(f"[QT-UPLOAD] upload_url -> {upload_url}")

            expires_at = ""
            if upload_url:
                try:
                    days = int(getattr(config_facot, "PDF_SIGNED_URL_DAYS", 7) or 7)
                    days = min(days, 7)
                except Exception:
                    days = 7
                expires_at = (datetime.utcnow() + timedelta(days=days)).isoformat()

            quotation_id = q.get("id") or q.get("_id") or None
            if quotation_id:
                try:
                    if logic and hasattr(logic, "set_quotation_pdf_info"):
                        try:
                            logic.set_quotation_pdf_info(
                                quotation_id,
                                storage_path,
                                upload_url,
                                expires_at=expires_at,
                            )
                        except TypeError:
                            logic.set_quotation_pdf_info(
                                quotation_id, storage_path, upload_url
                            )
                    elif da and hasattr(da, "set_quotation_pdf_info"):
                        try:
                            da.set_quotation_pdf_info(
                                quotation_id,
                                storage_path,
                                upload_url,
                                expires_at=expires_at,
                            )
                        except TypeError:
                            da.set_quotation_pdf_info(
                                quotation_id, storage_path, upload_url
                            )
                    print(
                        f"[QT-UPLOAD] set_quotation_pdf_info called for quotation_id={quotation_id}"
                    )
                except Exception as ex_set:
                    print(f"[QT-UPLOAD] Error calling set_quotation_pdf_info: {ex_set}")
            else:
                try:
                    parent = getattr(self, "parent", None) and self.parent()
                    if parent and hasattr(parent, "_preview_pdf_info_quotation"):
                        parent._preview_pdf_info_quotation = {
                            "storage_path": storage_path,
                            "url": upload_url,
                            "company_id": comp.get("id"),
                            "quotation_number": file_name,
                            "expires_at": expires_at,
                        }
                        print(
                            "[QT-UPLOAD] Preview PDF info guardada en parent._preview_pdf_info_quotation"
                        )
                    else:
                        print(
                            "[QT-UPLOAD] NO quotation_id disponible. Debes guardar manualmente pdf_storage_path/pdf_url"
                        )
                except Exception as e_parent:
                    print(
                        f"[QT-UPLOAD] Error guardando preview info en parent: {e_parent}"
                    )

            if upload_url:
                try:
                    from PyQt6.QtGui import QGuiApplication

                    msg = QMessageBox(self)
                    msg.setWindowTitle("PDF subido")
                    msg.setText("El PDF fue subido correctamente. ¿Qué deseas hacer?")
                    open_btn = msg.addButton(
                        "Abrir enlace", QMessageBox.ButtonRole.AcceptRole
                    )
                    copy_btn = msg.addButton(
                        "Copiar enlace", QMessageBox.ButtonRole.ActionRole
                    )
                    msg.addButton("Cerrar", QMessageBox.ButtonRole.RejectRole)
                    msg.exec()

                    clicked = msg.clickedButton()
                    if clicked is open_btn:
                        try:
                            webbrowser.open(upload_url)
                        except Exception as e:
                            QMessageBox.warning(
                                self,
                                "Abrir enlace",
                                f"No se pudo abrir el enlace:\n{e}",
                            )
                    elif clicked is copy_btn:
                        try:
                            QGuiApplication.clipboard().setText(upload_url)
                            QMessageBox.information(
                                self, "Copiar enlace", "Enlace copiado al portapapeles."
                            )
                        except Exception as e:
                            QMessageBox.warning(
                                self,
                                "Copiar enlace",
                                f"No se pudo copiar el enlace:\n{e}",
                            )
                except Exception as e_popup:
                    print(f"[QT-UPLOAD] Error mostrando popup enlace: {e_popup}")

        except Exception as e:
            print(f"[QP] _on_export_pdf error: {e}")
            QMessageBox.critical(
                self, "Exportar PDF", f"Error generando o subiendo PDF:\n{e}"
            )

    # ---------------------------------------------------------------- HTML (opcional)
    def _on_save_html(self):
        """
        Solo si quieres guardar el HTML con el JSON inyectado para debugging.
        """
        try:
            company, tpl, quotation = self._build_injectable_payloads()

            if build_html_with_json_block:
                html = build_html_with_json_block(
                    self.template_path, company, tpl, quotation
                )
            else:
                html = _local_build_html_with_json_block(
                    self.template_path, company, tpl, quotation
                )

            fn, _ = QFileDialog.getSaveFileName(
                self,
                "Guardar HTML de Vista Previa",
                "quotation_preview.html",
                "HTML Files (*.html *.htm)",
            )
            if not fn:
                return
            save_path = fn if fn.lower().endswith((".html", ".htm")) else fn + ".html"

            with open(save_path, "w", encoding="utf-8") as f:
                f.write(html)

            QMessageBox.information(
                self, "Guardar HTML", f"Archivo HTML guardado en:\n{save_path}"
            )

        except Exception as e:
            QMessageBox.critical(
                self, "Guardar HTML", f"No se pudo generar/guardar el HTML:\n{e}"
            )