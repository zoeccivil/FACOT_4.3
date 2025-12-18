#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import webbrowser
import re
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QDialog, QFileDialog, QMessageBox
)

# --- IMPORTAR EL GENERADOR DE PDF ---
try:
    from utils.pdf_generator import PDFGenerator
except Exception:
    PDFGenerator = None

# Config opcional (vencimientos y logos)
try:
    import config_facot
except Exception:
    class _Cfg:
        INVOICE_DUE_DAYS = 0
        INVOICE_FIXED_DUE_DATE = ""  # "YYYY-MM-DD"
        COMPANY_LOGOS = {}  # {company_id(str/int) or name: path}
        DEFAULT_LOGO_PATH = ""
    config_facot = _Cfg()

# Inyector HTML opcional (solo para guardar HTML manualmente si quieres)
try:
    from utils.html_injector import build_html_with_json_block
except Exception:
    build_html_with_json_block = None

# Raíz de datos para resolver rutas relativas
try:
    from utils.template_manager import get_data_root
except Exception:
    def get_data_root():
        return os.getcwd()


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
    company["address"] = (a1 + (" " + a2 if a2 else "")).strip() or "Dirección no especificada"

    company["logo_path"] = _resolve_logo_uri(company, tpl_from_db)

    company["primary_color"] = company.get("primary_color") or (tpl_from_db or {}).get("primary_color") or "#0087C3"
    company["secondary_color"] = company.get("secondary_color") or (tpl_from_db or {}).get("secondary_color") or "#F5F5F5"

    return company


def _compute_due_date_if_missing(invoice: Dict[str, Any], company: Dict[str, Any] | None = None) -> None:
    if not isinstance(invoice, dict):
        return

    inv_date = (invoice.get("date") or "").strip()
    due = (invoice.get("due_date") or "").strip()

    if due and due != inv_date:
        return

    fixed_company = ((company or {}).get("invoice_due_date") or "").strip()
    if fixed_company:
        invoice["due_date"] = fixed_company
        return

    fixed = getattr(config_facot, "INVOICE_FIXED_DUE_DATE", "") or ""
    if fixed:
        invoice["due_date"] = fixed
        return

    try:
        days = int(getattr(config_facot, "INVOICE_DUE_DAYS", 0) or 0)
    except Exception:
        days = 0
    if days > 0 and inv_date:
        try:
            d = datetime.strptime(inv_date[:10], "%Y-%m-%d")
            new_due_date = (d + timedelta(days=days)).strftime("%Y-%m-%d")
            if new_due_date != inv_date:
                invoice["due_date"] = new_due_date
        except Exception:
            pass


def _ensure_units(invoice: Dict[str, Any], logic_controller=None) -> None:
    try:
        items = invoice.get("items") or []
        for it in items:
            if not (it.get("unit") or "").strip():
                it["unit"] = "UND"
    except Exception:
        pass


def _local_build_html_with_json_block(template_path: str, company: Dict[str, Any], tpl: Dict[str, Any], invoice: Dict[str, Any]) -> str:
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()
    payload = {"COMPANY": company or {}, "TEMPLATE": tpl or {}, "INVOICE": invoice or {}}
    js = json.dumps(payload, ensure_ascii=False)
    js = js.replace("</script>", "<\\/script>")
    html = html.replace("/* INJECT_JSON_PLACEHOLDER */", js)
    return html


class InvoicePreviewDialog(QDialog):
    """
    Versión sin vista previa HTML: se utiliza solo para generar y subir el PDF
    (y opcionalmente Excel/HTML). Se recomienda instanciarlo con auto_export=True
    para que el usuario no vea ningún diálogo intermedio.
    """

    def __init__(
        self,
        company: Dict[str, Any],
        template: Dict[str, Any],
        invoice: Dict[str, Any],
        template_path: str = "templates/invoice_template.html",
        parent=None,
        debug: bool = False,
        auto_export: bool = False,          # si True: generar PDF sin mostrar diálogo
        open_after_generate: bool = False,  # abrir el PDF automáticamente al generar
    ):
        super().__init__(parent)
        self.setWindowTitle("Exportar factura a PDF")
        # No redimensionamos ni creamos widgets de vista previa

        self.raw_company = company or {}
        self.raw_template = template or {}
        self.raw_invoice = invoice or {}
        self.template_path = template_path
        self.debug = bool(debug)
        self.auto_export = bool(auto_export)
        self.open_after_generate = bool(open_after_generate)

        self._last_payload: Dict[str, Any] = {}

        # Siempre construimos el payload normalizado
        company_p, tpl_p, inv_p = self._build_injectable_payloads()
        self._last_payload = {"COMPANY": company_p, "TEMPLATE": tpl_p, "INVOICE": inv_p}

        # Si auto_export está activado, generamos y salimos
        if self.auto_export:
            try:
                self._on_export_pdf()
            except Exception as e:
                print(f"[AUTO_EXPORT ERROR] {e}")
            # cerramos sin mostrar
            return

        # Si por alguna razón se abre manualmente el diálogo, al aceptar se exporta
        # pero no mostramos ningún preview HTML.
        self._on_export_pdf()
        # y cerramos
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
        tpl["itbis_rate"] = tpl.get("itbis_rate", 0.18)

        invoice = dict(self.raw_invoice or {})
        items = invoice.get("items") or invoice.get("_items") or []
        invoice["items"] = list(items or [])

        try:
            _compute_due_date_if_missing(invoice, company)
        except Exception:
            pass

        try:
            _ensure_units(invoice, logic_controller=logic_ctrl)
        except Exception:
            pass

        if invoice.get("apply_itbis") is None:
            invoice["apply_itbis"] = True

        subtotal = 0.0
        for it in invoice.get("items", []):
            try:
                q = float(it.get("quantity", 0))
                p = float(it.get("unit_price", 0))
                disc = float(it.get("discount_pct", 0))
                subtotal += (q * p * (1 - disc / 100.0))
            except Exception:
                pass

        try:
            itbis_rate = float(tpl.get("itbis_rate", 0.18) or 0.0)
        except Exception:
            itbis_rate = 0.18

        apply_itbis = bool(invoice.get("apply_itbis"))
        invoice["subtotal"] = round(subtotal, 2)
        invoice["itbis"] = round((subtotal * itbis_rate) if apply_itbis else 0.0, 2)
        invoice["total_amount"] = round(invoice["subtotal"] + invoice["itbis"], 2)

        print("[INV] _build_injectable_payloads -> company:", company.get("id"), company.get("name"))
        print("[INV] invoice id:", invoice.get("id") or invoice.get("_id"), "items:", len(invoice.get("items", [])))

        return company, tpl, invoice

    # ---------------------------------------------------------------- PDF
    def _on_export_pdf(self):
        """
        Genera PDF usando utils.pdf_generator.PDFGenerator y luego sube el archivo.
        """
        try:
            if PDFGenerator is None:
                QMessageBox.critical(
                    self,
                    "Exportar PDF",
                    "Módulo PDFGenerator no está disponible. Instala reportlab (pip install reportlab).",
                )
                return

            company = self._last_payload.get("COMPANY", {}) or {}
            tpl = self._last_payload.get("TEMPLATE", {}) or {}
            inv = self._last_payload.get("INVOICE", {}) or {}

            display_number = (
                inv.get("display_number")
                or inv.get("number")
                or inv.get("_id")
                or "DRAFT"
            )
            inv["display_number"] = display_number

            safe_company = "".join(
                c for c in (company.get("name") or "empresa") if c.isalnum() or c in (" ", "-", "_")
            ).strip().replace(" ", "_")
            suggested = f"{safe_company}-{display_number}.pdf"

            fn, _ = QFileDialog.getSaveFileName(
                self,
                "Guardar factura como PDF",
                suggested,
                "PDF Files (*.pdf)",
            )
            if not fn:
                return
            save_path = fn if fn.lower().endswith(".pdf") else fn + ".pdf"

            gen_payload = {
                "COMPANY": company,
                "TEMPLATE": tpl,
                "INVOICE": inv,
            }

            generator = PDFGenerator(
                primary_color=tpl.get("primary_color", "#0087C3"),
                secondary_color=tpl.get("secondary_color", "#F5F5F5"),
            )
            generator.generate_pdf(gen_payload, save_path)

            if getattr(self, "open_after_generate", False):
                try:
                    if os.name == "nt":
                        os.startfile(save_path)
                    else:
                        webbrowser.open("file://" + os.path.abspath(save_path))
                except Exception:
                    pass

            QMessageBox.information(self, "PDF creado", f"Factura guardada en:\n{save_path}")

            self._handle_upload(save_path, inv)

        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Error generando PDF:\n{e}")

    # ---------------------------------------------------------------- upload
    def _handle_upload(self, save_path, inv_data):
        """Lógica para subir a Storage (Firebase u otro)."""
        try:
            logic = getattr(self.parent(), "logic", None)
            if not logic:
                return

            comp = self._last_payload.get("COMPANY", {})
            safe_comp = "".join(
                c for c in (comp.get("name") or "empresa") if c.isalnum()
            ).strip()
            year = (inv_data.get("date") or datetime.now().strftime("%Y-%m-%d"))[:4]
            storage_path = f"factura/{safe_comp}/{year}/{os.path.basename(save_path)}"

            upload_url = None
            if hasattr(logic, "upload_file_to_storage"):
                upload_url = logic.upload_file_to_storage(save_path, storage_path)
            elif hasattr(logic, "data_access") and hasattr(
                logic.data_access, "upload_file_to_storage"
            ):
                upload_url = logic.data_access.upload_file_to_storage(
                    save_path, storage_path
                )

            if upload_url:
                if self.parent() and hasattr(self.parent(), "_preview_pdf_info"):
                    self.parent()._preview_pdf_info = {
                        "storage_path": storage_path,
                        "url": upload_url,
                        "company_id": comp.get("id"),
                        "expires_at": (datetime.utcnow() + timedelta(days=7)).isoformat(),
                    }
                self._show_uploaded_link_actions(upload_url)

        except Exception as e:
            print(f"[UPLOAD ERROR] {e}")

    def _show_uploaded_link_actions(self, upload_url: str):
        try:
            if not upload_url:
                return
            msg = QMessageBox(self)
            msg.setWindowTitle("PDF subido")
            msg.setText("El PDF fue subido correctamente. ¿Qué deseas hacer?")
            open_btn = msg.addButton("Abrir enlace", QMessageBox.ButtonRole.AcceptRole)
            copy_btn = msg.addButton("Copiar enlace", QMessageBox.ButtonRole.ActionRole)
            msg.addButton("Cerrar", QMessageBox.ButtonRole.RejectRole)
            msg.exec()

            clicked = msg.clickedButton()
            if clicked is open_btn:
                webbrowser.open(upload_url)
            elif clicked is copy_btn:
                from PyQt6.QtGui import QGuiApplication

                QGuiApplication.clipboard().setText(upload_url)
        except Exception:
            pass

    # ---------------------------------------------------------------- Excel
    def _on_export_excel(self):
        """
        Exportación a Excel. Puedes llamarla manualmente desde tu código si la necesitas;
        no hay botón en UI porque no mostramos un diálogo completo.
        """
        try:
            payload = getattr(self, "_last_payload", {}) or {}
            comp = payload.get("COMPANY", {})
            tpl = payload.get("TEMPLATE", {})
            inv = payload.get("INVOICE", {})

            company_name = (comp.get("name") or "EMPRESA").strip()
            display_number = (inv.get("display_number") or inv.get("number") or "FACT").strip()

            base = f"FACT_{display_number}_{company_name}"
            safe = re.sub(r"[^A-Za-z0-9._\\-]+", "_", base).strip("_")
            suggested = f"{safe}.xlsx"

            fn, _ = QFileDialog.getSaveFileName(
                self,
                "Guardar Excel",
                suggested,
                "Excel Files (*.xlsx)",
            )
            if not fn:
                return
            save_path = fn if fn.lower().endswith(".xlsx") else fn + ".xlsx"

            try:
                from utils.quotation_templates import generate_invoice_excel as gen_invoice_xlsx
            except Exception:
                gen_invoice_xlsx = None

            if not callable(gen_invoice_xlsx):
                QMessageBox.warning(self, "Excel", "No se encontró exportador Excel.")
                return

            items_src = inv.get("items") or []
            items = []
            for it in items_src:
                items.append(
                    {
                        "code": it.get("code", ""),
                        "description": it.get("description", ""),
                        "unit": it.get("unit", ""),
                        "quantity": float(it.get("quantity", 0)),
                        "unit_price": float(it.get("unit_price", 0)),
                        "discount_pct": float(it.get("discount_pct", 0)),
                    }
                )

            invoice_data = {
                "company_id": comp.get("id"),
                "company_name": company_name,
                "invoice_date": inv.get("date"),
                "due_date": inv.get("due_date"),
                "ncf_number": inv.get("ncf"),
                "client_name": inv.get("client_name"),
                "client_rnc": inv.get("client_rnc"),
                "currency": inv.get("currency"),
                "apply_itbis": bool(inv.get("apply_itbis", True)),
                "itbis_rate": float(tpl.get("itbis_rate", 0.18)),
            }

            gen_invoice_xlsx(invoice_data, items, save_path, company_name, template=tpl)
            QMessageBox.information(self, "Excel", f"Excel generado:\n{save_path}")
        except Exception as e:
            QMessageBox.warning(self, "Excel", f"Error excel: {e}")

    # ---------------------------------------------------------------- HTML opcional
    def _on_save_html(self):
        """
        Solo si quieres guardar el HTML con el JSON inyectado (no se usa para preview).
        """
        try:
            company, tpl, invoice = self._build_injectable_payloads()
            if build_html_with_json_block:
                html = build_html_with_json_block(self.template_path, company, tpl, invoice)
            else:
                html = _local_build_html_with_json_block(self.template_path, company, tpl, invoice)

            fn, _ = QFileDialog.getSaveFileName(
                self, "Guardar HTML", "invoice.html", "HTML Files (*.html)"
            )
            if fn:
                with open(fn, "w", encoding="utf-8") as f:
                    f.write(html)
                QMessageBox.information(self, "HTML", f"Guardado en: {fn}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))