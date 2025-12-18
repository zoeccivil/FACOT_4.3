from __future__ import annotations

import os
import logging
from typing import List, Dict, Any, Tuple, Set, Optional

from datetime import datetime, timedelta
import webbrowser

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHBoxLayout, QWidget as QWidgetAlias, QFileDialog, QMessageBox, QHeaderView,
    QMenu
)
from PyQt6.QtCore import QSize, Qt, QDate, QPoint

logger = logging.getLogger(__name__)

# Tipos de categoría/tipo de factura que se consideran "ingresos" (ventas)
INVOICE_TYPE_INGRESOS: Set[str] = {
    "INGRESO",
    "FACTURA",
    "FACTURA PRIVADA",
    "EMITIDA",
    "VENTA",
    "CREDITO FISCAL",
    "CONSUMIDOR FINAL",
    "GUBERNAMENTAL",
    "REGIMEN ESPECIAL",
    "EXPORTACION",
}

# Prefijos NCF que corresponden a comprobantes de venta/ingreso
NCF_PREFIX_INGRESOS: Set[str] = {"B01", "B02", "B14", "B15", "B16"}
INGRESO_TYPES: Set[str] = INVOICE_TYPE_INGRESOS | NCF_PREFIX_INGRESOS

# Optional dependencies with safe fallbacks
InvoicePreviewDialog = None
try:
    from dialogs.invoice_preview_dialog import InvoicePreviewDialog
except Exception as e:
    logger.debug("Aviso: InvoicePreviewDialog no disponible: %s", e)
    InvoicePreviewDialog = None

try:
    from utils.template_manager import load_template
except Exception as e:
    logger.debug("Aviso: utils.template_manager.load_template no disponible: %s", e)
    def load_template(company_id: int):
        return {}

try:
    from utils.asset_paths import resolve_logo_uri
except Exception as e:
    logger.debug("Aviso: utils.asset_paths.resolve_logo_uri no disponible: %s", e)
    def resolve_logo_uri(p): return p or ""

try:
    from utils.template_integration import export_invoice_pdf_with_template, export_invoice_excel_with_template
except Exception as e:
    logger.debug("Aviso: utils.template_integration no disponible: %s", e)
    def export_invoice_pdf_with_template(*args, **kwargs):
        raise RuntimeError("export_invoice_pdf_with_template no disponible")
    def export_invoice_excel_with_template(*args, **kwargs):
        raise RuntimeError("export_invoice_excel_with_template no disponible")


class InvoiceHistoryTab(QWidget):
    def __init__(self, logic, get_current_company_callable, parent=None):
        super().__init__(parent)
        self.logic = logic
        self.get_current_company = get_current_company_callable
        self._records: List[Dict[str, Any]] = []  # caché de registros mostrados
        self._build_ui()
        try:
            self.refresh()
        except Exception as e:
            logger.exception("Error al refrescar InvoiceHistoryTab en init: %s", e)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title_label = QLabel("Historial de Facturas")
        title_label.setProperty("heading", True)
        layout.addWidget(title_label)

        from PyQt6.QtWidgets import QDateEdit, QLineEdit
        self.filter_widget = QWidget()
        self.filter_widget.setProperty("filterRow", True)
        filter_layout = QHBoxLayout(self.filter_widget)
        filter_layout.setContentsMargins(12, 8, 12, 8)

        filter_layout.addWidget(QLabel("Desde:"))
        self.filter_date_from = QDateEdit()
        self.filter_date_from.setCalendarPopup(True)
        self.filter_date_from.setDate(QDate.currentDate().addMonths(-1))
        self.filter_date_from.dateChanged.connect(self.refresh)
        filter_layout.addWidget(self.filter_date_from)

        filter_layout.addWidget(QLabel("Hasta:"))
        self.filter_date_to = QDateEdit()
        self.filter_date_to.setCalendarPopup(True)
        self.filter_date_to.setDate(QDate.currentDate())
        self.filter_date_to.dateChanged.connect(self.refresh)
        filter_layout.addWidget(self.filter_date_to)

        filter_layout.addWidget(QLabel("Cliente:"))
        self.filter_client = QLineEdit()
        self.filter_client.setPlaceholderText("Buscar por nombre...")
        self.filter_client.textChanged.connect(self.refresh)
        filter_layout.addWidget(self.filter_client)

        filter_layout.addStretch(1)
        btn_clear_filters = QPushButton("Limpiar filtros")
        btn_clear_filters.setProperty("flat", True)
        btn_clear_filters.clicked.connect(self._clear_filters)
        filter_layout.addWidget(btn_clear_filters)
        layout.addWidget(self.filter_widget)

        # --- TOOLBAR (history actions: Abrir PDF / Regenerar enlace) ---
        tool_row = QHBoxLayout()
        self.btn_open_pdf = QPushButton("Abrir PDF")
        self.btn_open_pdf.setToolTip("Abrir PDF de la factura seleccionada (usa pdf_url guardado en Firestore)")
        self.btn_open_pdf.clicked.connect(self._open_selected_pdf)
        tool_row.addWidget(self.btn_open_pdf)

        self.btn_regen_pdf_link = QPushButton("Regenerar enlace")
        self.btn_regen_pdf_link.setToolTip("Generar nuevo signed URL para el PDF de la factura seleccionada")
        self.btn_regen_pdf_link.clicked.connect(self._regenerate_selected_pdf_link)
        tool_row.addWidget(self.btn_regen_pdf_link)

        tool_row.addStretch(1)
        layout.addLayout(tool_row)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["ID", "Fecha", "NCF", "Cliente", "RNC", "Moneda", "Total", "Acciones"])
        header = self.table.horizontalHeader()

        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(80)
        self.table.setMinimumWidth(400)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        actions_col = self.table.columnCount() - 1
        header.setSectionResizeMode(actions_col, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(actions_col, 120)

        self._apply_initial_column_widths(self.table)

        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setSortingEnabled(True)

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._on_table_double_click)

        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("Refrescar Historial")
        btn_refresh.clicked.connect(self.refresh)
        btn_row.addWidget(btn_refresh)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    def _apply_initial_column_widths(self, table: QTableWidget):
        try:
            viewport_w = table.viewport().width()
            actions_w = 120
            other_w = max(0, viewport_w - actions_w - 12)
            proportions = {0: 0.08, 1: 0.12, 2: 0.18, 3: 0.28, 4: 0.14, 5: 0.08, 6: 0.12}
            for col, frac in proportions.items():
                w = int(other_w * frac)
                table.setColumnWidth(col, max(w, 80))
            table.setColumnWidth(table.columnCount() - 1, actions_w)
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_initial_column_widths(self.table)

    def _clear_filters(self):
        self.filter_date_from.setDate(QDate.currentDate().addMonths(-1))
        self.filter_date_to.setDate(QDate.currentDate())
        self.filter_client.clear()
        self.refresh()

    def toggle_filters(self):
        if hasattr(self, 'filter_widget'):
            self.filter_widget.setVisible(not self.filter_widget.isVisible())

    def _filter_emitidas_only(self, facturas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        filtered = []
        for inv in facturas:
            invoice_type = (inv.get('invoice_type') or inv.get('type') or '').strip().lower()
            if invoice_type == "emitida":
                filtered.append(inv)
        return filtered

    def _parse_date_str(self, value: Any) -> str:
        if not value:
            return ""
        try:
            if isinstance(value, str):
                s = value.strip()
                return s[:10] if len(s) >= 10 else s
            try:
                return value.strftime("%Y-%m-%d")
            except Exception:
                return str(value)[:10]
        except Exception:
            return ""

    def _fetch_emitidas(self, company_id, full_scan: bool = False) -> List[Dict[str, Any]]:
        def _norm_company_match(d: Dict[str, Any], cid: Any) -> bool:
            v = d.get("company_id")
            return str(v) == str(cid)

        fs = getattr(self.logic, "firestore", None)
        if fs:
            try:
                col = fs.collection("invoices")
                docs = []
                try:
                    from google.cloud.firestore_v1 import FieldFilter
                    q1 = col.where(filter=FieldFilter("company_id", "==", company_id))
                    docs = list(q1.stream())
                    if not docs:
                        q2 = col.where(filter=FieldFilter("company_id", "==", str(company_id)))
                        docs = list(q2.stream())
                except Exception:
                    try:
                        q1 = col.where("company_id", "==", company_id)
                        docs = list(q1.stream())
                    except Exception:
                        q2 = col.where("company_id", "==", str(company_id))
                        docs = list(q2.stream())
                out = []
                for d in docs:
                    data = d.to_dict() or {}
                    data['id'] = d.id
                    if not _norm_company_match(data, company_id):
                        continue
                    itype = (data.get('invoice_type') or data.get('type') or '').strip().lower()
                    if itype == 'emitida':
                        out.append(data)
                return out
            except Exception as e:
                logger.error("Error leyendo Firestore en _fetch_emitidas: %s", e)

        try:
            if hasattr(self.logic, "get_facturas"):
                raw = self.logic.get_facturas(company_id, only_issued=False)
            elif hasattr(self.logic, "get_invoices"):
                raw = self.logic.get_invoices(company_id)
            else:
                raw = []
            return self._filter_emitidas_only(raw)
        except Exception as e:
            logger.error("Error en fallback logic: %s", e)
            return []

    def _populate_table(self, records: List[Dict[str, Any]]):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for f in records:
            row = self.table.rowCount()
            self.table.insertRow(row)

            id_str = str(f.get('id', ''))
            it_id = QTableWidgetItem(id_str)
            try:
                it_id.setData(Qt.ItemDataRole.UserRole, int(f.get('id')))
            except Exception:
                it_id.setData(Qt.ItemDataRole.UserRole, id_str)
            self.table.setItem(row, 0, it_id)

            date_str = self._parse_date_str(f.get("invoice_date") or f.get("date") or f.get("created_at") or f.get("issued_at") or "")
            it_date = QTableWidgetItem(date_str)
            it_date.setData(Qt.ItemDataRole.UserRole, date_str)
            self.table.setItem(row, 1, it_date)

            it_ncf = QTableWidgetItem(f.get('invoice_number', '') or f.get('ncf', ''))
            self.table.setItem(row, 2, it_ncf)

            client_name = (f.get("third_party_name") or f.get("client_name") or "").strip()
            it_client = QTableWidgetItem(client_name)
            self.table.setItem(row, 3, it_client)

            it_rnc = QTableWidgetItem(f.get('rnc', '') or f.get('client_rnc', ''))
            self.table.setItem(row, 4, it_rnc)

            it_cur = QTableWidgetItem(f.get('currency', ''))
            self.table.setItem(row, 5, it_cur)

            total = f.get('total_amount', f.get('total', 0.0)) or 0.0
            it_total = QTableWidgetItem(f"{float(total):,.2f}")
            it_total.setData(Qt.ItemDataRole.UserRole, float(total))
            self.table.setItem(row, 6, it_total)

            try:
                self._add_invoice_action_buttons(row, f)
            except Exception:
                logger.exception("Error añadiendo boton de acciones para factura id=%s", f.get('id'))

        self.table.setSortingEnabled(True)
        self._apply_initial_column_widths(self.table)

    def refresh(self):
        company = self.get_current_company()
        if not company:
            return
        try:
            company_id = company['id']
        except Exception:
            company_id = company.get('id')
        if not company_id:
            return

        facturas = self._fetch_emitidas(company_id)

        client_q = (self.filter_client.text() or "").strip().lower()
        from_date = self.filter_date_from.date().toString("yyyy-MM-dd")
        to_date = self.filter_date_to.date().toString("yyyy-MM-dd")

        filtered: List[Dict[str, Any]] = []
        for f in facturas:
            date_str = self._parse_date_str(f.get("invoice_date") or f.get("date") or f.get("created_at") or f.get("issued_at") or "")
            date_ok = True
            if date_str:
                try:
                    date_ok = (date_str >= from_date and date_str <= to_date)
                except Exception:
                    date_ok = True

            client_name = (f.get("third_party_name") or f.get("client_name") or "").strip()
            client_ok = True
            if client_q:
                client_ok = client_q in client_name.lower()

            if date_ok and client_ok:
                filtered.append(f)

        self._records = filtered[:]
        self._populate_table(self._records)

    def _add_invoice_action_buttons(self, row: int, record: Dict[str, Any]):
        widget = QWidgetAlias()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_preview = QPushButton()
        btn_preview.setObjectName("actionButton")
        btn_preview.setToolTip("Ver detalle / Vista previa")
        btn_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_preview.setFixedSize(32, 32)
        eye_icon = os.path.join(os.getcwd(), "assets", "icons", "eye.svg")
        if os.path.exists(eye_icon):
            from PyQt6.QtGui import QIcon
            btn_preview.setIcon(QIcon(eye_icon)); btn_preview.setIconSize(QSize(20, 20))
        else:
            btn_preview.setText("👁")
        btn_preview.clicked.connect(lambda _, rec=record: self._open_invoice_preview(rec))
        layout.addWidget(btn_preview)

        widget.setLayout(layout)
        self.table.setRowHeight(row, 44)
        actions_col = self.table.columnCount() - 1
        try:
            self.table.setCellWidget(row, actions_col, widget)
        except Exception:
            for c in range(self.table.columnCount()):
                header_item = self.table.horizontalHeaderItem(c)
                if header_item and header_item.text().strip().lower() == "acciones":
                    self.table.setCellWidget(row, c, widget)
                    break

    def _resolve_company_and_template(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        company = self.get_current_company() or {}
        tpl = {}
        try:
            tpl = load_template(int(company.get('id')))
        except Exception:
            tpl = {}
        company_data = {
            "id": company.get('id'),
            "name": company.get('name'),
            "rnc": company.get('rnc') or company.get('rnc_number') or "",
            "address_line1": company.get('address') or company.get('address_line1') or "",
            "address_line2": company.get('address_line2') or "",
            "phone": company.get('phone') or company.get('telefono') or "",
            "email": company.get('email') or company.get('correo') or "",
            "logo_path": ""
        }
        logo_rel = tpl.get("logo_path") or company.get("logo_path") or ""
        company_data["logo_path"] = resolve_logo_uri(logo_rel) or ""
        return company_data, tpl

    def _get_record_items(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = record.get('items') or record.get('details') or []
        if not items and hasattr(self.logic, "get_invoice_items"):
            try:
                items = self.logic.get_invoice_items(record.get('id'))
            except Exception:
                items = []
        normalized = []
        for it in items:
            normalized.append({
                "code": it.get("code") or it.get("item_code") or it.get("codigo") or "",
                "description": it.get("description") or it.get("descripcion") or "",
                "unit": it.get("unit") or it.get("unidad") or "",
                "quantity": float(it.get("quantity", it.get("cantidad", 0)) or 0),
                "unit_price": float(it.get("unit_price", it.get("precio", 0)) or 0)
            })
        return normalized

    def _build_display_invoice_number(self, company: Dict[str, Any], ncf: str, prefix_label: str = "FACT", last_digits: int = 6) -> str:
        initials = self._company_initials(company.get('name', 'COMPANY'))
        digits = ''.join(ch for ch in (ncf or "") if ch.isdigit())
        tail = digits[-last_digits:] if digits else ''
        if tail:
            return f"{prefix_label}-{initials}-{tail}"
        return f"{prefix_label}-{initials}-{ncf or ''}"

    def _company_initials(self, company_name: str, max_chars: int = 6) -> str:
        if not company_name:
            return "COMP"
        parts = [p for p in company_name.replace(',', ' ').split() if p]
        if len(parts) == 1:
            s = parts[0][:max_chars].upper()
            return ''.join([c for c in s if c.isalnum()])[:max_chars]
        initials = ''.join([p[0].upper() for p in parts[:3]])
        return initials[:max_chars]

    def _open_invoice_preview(self, record: Dict[str, Any]):
        company_data, tpl = self._resolve_company_and_template()
        inv_type = record.get("invoice_type") or record.get("type") or "FACTURA"
        if isinstance(inv_type, str) and inv_type.lower() == "emitida":
            inv_type = "FACTURA"
        ncf_val = record.get("invoice_number") or record.get("ncf") or ""
        display_number = self._build_display_invoice_number(company_data, ncf_val, prefix_label="FACT", last_digits=6)
        apply_itbis = record.get("apply_itbis")
        if apply_itbis is None:
            try:
                total = float(record.get("total_amount", 0) or 0)
                itbis = float(record.get("itbis", 0) or 0)
                apply_itbis = (itbis > 0.01)
            except Exception:
                apply_itbis = True
        invoice_payload = {
            "company_id": record.get("company_id", company_data.get("id")),
            "number": record.get("invoice_number") or record.get("number") or ncf_val,
            "ncf": ncf_val,
            "date": (record.get("invoice_date") or record.get("date") or "")[:10],
            "client_name": record.get("third_party_name") or record.get("client_name") or "",
            "client_rnc": record.get("rnc") or record.get("client_rnc") or "",
            "currency": record.get("currency") or "",
            "items": self._get_record_items(record),
            "notes": record.get("notes", "") or "",
            "type": inv_type,
            "display_number": display_number,
            "apply_itbis": apply_itbis,
        }
        if InvoicePreviewDialog is None:
            QMessageBox.warning(self, "Vista Previa", "InvoicePreviewDialog no disponible.")
            return
        template_path = os.path.join(os.getcwd(), "templates", "invoice_template.html")
        dlg = InvoicePreviewDialog(company=company_data, template=tpl, invoice=invoice_payload, parent=self, template_path=template_path, debug=False)
        dlg.exec()

    def _find_invoice_tab_in_window(self):
        try:
            win = self.window()
            if win is None:
                return None
            if hasattr(win, "invoice_tab"):
                return getattr(win, "invoice_tab")
            for attr in ("invoice_tab", "tab_invoice", "main_invoice_tab"):
                if hasattr(win, attr):
                    return getattr(win, attr)
        except Exception:
            pass
        p = self.parent()
        safety = 0
        while p is not None and safety < 12:
            if hasattr(p, "invoice_tab"):
                return getattr(p, "invoice_tab")
            p = p.parent() if callable(getattr(p, "parent", None)) else None
            safety += 1
        return None

    def _edit_invoice(self, record: Dict[str, Any]):
        iid = record.get('id')
        if not iid:
            QMessageBox.warning(self, "Editar", "ID de factura no disponible.")
            return

        itab = self._find_invoice_tab_in_window()
        if itab:
            handled = False
            for m in ("load_invoice", "edit_invoice", "load_invoice_by_id", "_load_invoice", "open_invoice"):
                fn = getattr(itab, m, None)
                if callable(fn):
                    try:
                        fn(iid)
                        try:
                            win = self.window()
                            sw = getattr(win, "stacked_widget", None)
                            if sw is not None:
                                for i in range(sw.count()):
                                    if sw.widget(i) is itab:
                                        sw.setCurrentIndex(i)
                                        break
                        except Exception:
                            pass
                        handled = True
                        break
                    except Exception as e:
                        logger.exception("Error calling %s on invoice_tab: %s", m, e)
            if handled:
                return

        QMessageBox.information(self, "Editar", "No se pudo abrir la factura en modo edición automáticamente.\nCompruebe que exista un editor integrado (invoice_tab).")

    def _delete_invoice(self, inv_id_or_record):
        """
        Borra una factura. inv_id_or_record puede ser:
        - un id (int o str)
        - un dict con key 'id' o 'invoice_id' o 'documentId'
        """
        # Extraer id del argumento
        inv_id = None
        try:
            if isinstance(inv_id_or_record, dict):
                inv_id = inv_id_or_record.get("id") or inv_id_or_record.get("invoice_id") or inv_id_or_record.get("doc_id") or inv_id_or_record.get("documentId")
            else:
                inv_id = inv_id_or_record
            # Normalizar a string/entero según convenga
            if inv_id is None:
                QMessageBox.warning(self, "Eliminar", f"No se encontró ID de la factura a eliminar: {repr(inv_id_or_record)}")
                return
            # Mostrar confirmación con el ID legible
            reply = QMessageBox.question(self, "Eliminar",
                                        f"¿Estás seguro de borrar la factura {inv_id} permanentemente?",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
            # Intentar convertir a entero si es posible (backends que usan ints)
            inv_id_to_use = inv_id
            try:
                inv_id_to_use = int(inv_id)
            except Exception:
                # dejar tal cual (string)
                inv_id_to_use = inv_id

            res = False
            if hasattr(self.logic, "delete_factura"):
                try:
                    res = self.logic.delete_factura(inv_id_to_use)
                except Exception as e:
                    print(f"[INV-DELETE] logic.delete_factura raised: {e}")
                    try:
                        # Fallback: pasar string
                        res = self.logic.delete_factura(str(inv_id_to_use))
                    except Exception as e2:
                        print(f"[INV-DELETE] fallback delete_factura error: {e2}")
                        res = False
            elif hasattr(self.logic, "data_access") and hasattr(self.logic.data_access, "delete_factura"):
                try:
                    res = self.logic.data_access.delete_factura(inv_id_to_use)
                except Exception:
                    try:
                        res = self.logic.data_access.delete_factura(str(inv_id_to_use))
                    except Exception:
                        res = False

            if res:
                QMessageBox.information(self, "Eliminado", "Factura eliminada.")
                self.refresh()
            else:
                QMessageBox.critical(self, "Error", "No se pudo eliminar (ver log).")
        except Exception as e:
            logger.exception("Error en _delete_invoice: %s", e)
            QMessageBox.critical(self, "Error", f"No se pudo eliminar la factura:\n{e}")




    def _export_invoice_pdf(self, record: Dict[str, Any]):
        company = self.get_current_company()
        if not company:
            QMessageBox.warning(self, "Empresa", "Seleccione una empresa válida"); return

        apply_itbis = record.get("apply_itbis")
        if apply_itbis is None:
            try:
                itbis = float(record.get("itbis", 0) or 0)
                apply_itbis = (itbis > 0.01)
            except Exception:
                apply_itbis = True

        invoice_payload = {
            "company_id": record.get("company_id", company.get('id')),
            "company_name": company.get('name', ''),
            "invoice_date": record.get("invoice_date", ""),
            "invoice_number": record.get("invoice_number") or record.get("ncf") or "",
            "client_name": record.get("third_party_name") or record.get("client_name") or "",
            "client_rnc": record.get("rnc") or record.get("client_rnc") or "",
            "apply_itbis": apply_itbis,
        }
        items = self._get_record_items(record)
        fn, _ = QFileDialog.getSaveFileName(self, "Guardar Factura como PDF", f"factura_{invoice_payload.get('invoice_number','')}.pdf", "PDF Files (*.pdf)")
        if not fn:
            return
        save_path = fn if fn.lower().endswith(".pdf") else fn + ".pdf"
        try:
            export_invoice_pdf_with_template(invoice_payload, items, save_path, company_name=company.get('name',''))
            QMessageBox.information(self, "PDF", f"Factura guardada como PDF en:\n{save_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo exportar la factura a PDF:\n{e}")

    def _export_invoice_excel(self, record: Dict[str, Any]):
        company = self.get_current_company()
        if not company:
            QMessageBox.warning(self, "Empresa", "Seleccione una empresa válida"); return

        apply_itbis = record.get("apply_itbis")
        if apply_itbis is None:
            try:
                itbis = float(record.get("itbis", 0) or 0)
                apply_itbis = (itbis > 0.01)
            except Exception:
                apply_itbis = True

        invoice_payload = {
            "company_id": record.get("company_id", company.get('id')),
            "company_name": company.get('name', ''),
            "invoice_date": record.get("invoice_date", ""),
            "invoice_number": record.get("invoice_number") or record.get("ncf") or "",
            "client_name": record.get("third_party_name") or record.get("client_name") or "",
            "client_rnc": record.get("rnc") or record.get("client_rnc") or "",
            "apply_itbis": apply_itbis,
        }
        items = self._get_record_items(record)
        fn, _ = QFileDialog.getSaveFileName(self, "Guardar Factura como Excel", f"factura_{invoice_payload.get('invoice_number','')}.xlsx", "Excel Files (*.xlsx)")
        if not fn:
            return
        save_path = fn if fn.lower().endswith(".xlsx") else fn + ".xlsx"
        try:
            export_invoice_excel_with_template(invoice_payload, items, save_path, company_name=company.get('name',''))
            QMessageBox.information(self, "Excel", f"Factura guardada como Excel en:\n{save_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo exportar la factura a Excel:\n{e}")

    def _show_context_menu(self, position: QPoint):
        row = self.table.rowAt(position.y())
        if row < 0:
            return
        record = self._record_by_row(row)
        if not record:
            return

        menu = QMenu(self)

        preview_action = menu.addAction("👁 Vista Previa")
        preview_action.triggered.connect(lambda: self._open_invoice_preview(record))

        edit_action = menu.addAction("✏️ Editar")
        edit_action.triggered.connect(lambda: self._edit_invoice(record))

        menu.addSeparator()

        pdf_action = menu.addAction("📄 Exportar PDF")
        pdf_action.triggered.connect(lambda: self._export_invoice_pdf(record))

        excel_action = menu.addAction("📊 Exportar Excel")
        excel_action.triggered.connect(lambda: self._export_invoice_excel(record))

        menu.addSeparator()

        open_pdf_action = menu.addAction("Abrir PDF")
        open_pdf_action.triggered.connect(lambda: self._open_selected_pdf())

        regen_action = menu.addAction("Regenerar enlace")
        regen_action.triggered.connect(lambda: self._regenerate_selected_pdf_link())

        menu.addSeparator()

        delete_action = menu.addAction("🗑 Eliminar")
        delete_action.triggered.connect(lambda: self._delete_invoice(record))

        menu.exec(self.table.viewport().mapToGlobal(position))

    def _on_table_double_click(self, index):
        row = index.row()
        record = self._record_by_row(row)
        if record:
            self._open_invoice_preview(record)

    def _record_by_row(self, row: int) -> Dict[str, Any]:
        try:
            id_item = self.table.item(row, 0)
            if not id_item:
                return {}
            id_val = id_item.text()
            for rec in self._records:
                if str(rec.get('id')) == id_val:
                    return rec
        except Exception:
            pass
        return {}

    # --- Methods added/modified for PDF open and regeneration (history) ---

    def _get_selected_invoice_id(self) -> Optional[str]:
        """Returns the ID (text) of the currently selected table row, or None."""
        try:
            r = self.table.currentRow()
            if r < 0:
                return None
            item = self.table.item(r, 0)
            if not item:
                return None
            return item.text()
        except Exception:
            return None

    def _open_selected_pdf(self):
        """Open the signed/public URL for the selected invoice in the user's browser."""
        invoice_id = self._get_selected_invoice_id()
        if not invoice_id:
            QMessageBox.information(self, "Abrir PDF", "Seleccione una factura primero.")
            return
        try:
            inv = None
            if hasattr(self.logic, 'get_invoice_by_id'):
                inv = self.logic.get_invoice_by_id(invoice_id) or {}
            else:
                QMessageBox.information(self, "Abrir PDF", "El backend no soporta obtener factura por ID.")
                return
            pdf_url = (inv or {}).get('pdf_url') or (inv or {}).get('pdfUrl') or None
            if not pdf_url:
                QMessageBox.information(self, "Abrir PDF", "No se encontró URL del PDF para esta factura.")
                return
            webbrowser.open(pdf_url)
        except Exception as e:
            QMessageBox.warning(self, "Abrir PDF", f"No se pudo abrir el enlace:\n{e}")

    def _regenerate_selected_pdf_link(self):
        """
        Generate a new signed URL for the selected invoice's storage path and persist it.
        Uses logic.generate_signed_url_for_path(...) or falls back to data_access helper.
        """
        try:
            invoice_id = self._get_selected_invoice_id()
            if not invoice_id:
                QMessageBox.information(self, "Regenerar enlace", "Seleccione una factura primero.")
                return

            inv = None
            if hasattr(self.logic, 'get_invoice_by_id'):
                inv = self.logic.get_invoice_by_id(invoice_id) or {}
            else:
                QMessageBox.information(self, "Regenerar enlace", "El backend no soporta obtener factura por ID.")
                return

            storage_path = inv.get('pdf_storage_path') or inv.get('pdfPath') or None
            if not storage_path:
                QMessageBox.information(self, "Regenerar enlace", "No se encontró storage_path para esta factura.")
                return

            # determine days (configurable)
            days = 7
            try:
                import facot_config
                days = int(getattr(facot_config, "PDF_SIGNED_URL_DAYS", 7) or 7)
            except Exception:
                days = 7

            url = None
            if hasattr(self.logic, "generate_signed_url_for_path"):
                url = self.logic.generate_signed_url_for_path(storage_path, days=days)
            elif hasattr(self.logic, "data_access") and hasattr(self.logic.data_access, "generate_signed_url_for_path"):
                url = self.logic.data_access.generate_signed_url_for_path(storage_path, days=days)
            else:
                QMessageBox.warning(self, "Regenerar enlace", "El backend no soporta generar signed URLs bajo demanda.")
                return

            if not url:
                QMessageBox.warning(self, "Regenerar enlace", "No se pudo generar un nuevo enlace firmado.")
                return

            expires_at = (datetime.utcnow() + timedelta(days=min(days, 7))).isoformat()

            # persist in backend
            if hasattr(self.logic, "set_invoice_pdf_info"):
                try:
                    self.logic.set_invoice_pdf_info(invoice_id, storage_path, url, expires_at=expires_at)
                except TypeError:
                    # older signature: (invoice_id, storage_path, url)
                    self.logic.set_invoice_pdf_info(invoice_id, storage_path, url)
            elif hasattr(self.logic, "data_access") and hasattr(self.logic.data_access, "set_invoice_pdf_info"):
                try:
                    self.logic.data_access.set_invoice_pdf_info(invoice_id, storage_path, url, expires_at=expires_at)
                except TypeError:
                    self.logic.data_access.set_invoice_pdf_info(invoice_id, storage_path, url)

            QMessageBox.information(self, "Regenerar enlace", f"Nuevo enlace generado y guardado.\nExpira: {expires_at}")
            try:
                self.refresh()
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, "Regenerar enlace", f"No se pudo generar el enlace:\n{e}")