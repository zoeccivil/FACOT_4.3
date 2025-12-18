from __future__ import annotations
from datetime import datetime, timedelta
import os
import datetime
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QPushButton,
    QDateEdit, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox, QComboBox,
    QHeaderView, QGroupBox, QToolButton, QCheckBox, QDialog, QGridLayout
)
from PyQt6.QtCore import QDate, Qt, pyqtSignal, QSize

from dialogs.item_picker_dialog import ItemPickerDialog
from dialogs.template_editor_dialog import TemplateEditorDialog
from dialogs.quotation_preview_dialog import QuotationPreviewDialog

from utils.template_manager import load_template, get_data_root
from utils.template_integration import (
    export_quotation_excel_with_template,
    export_quotation_pdf_with_template,
)
from constants import DEFAULT_CURRENCY, ITBIS_RATE
from utils.asset_paths import resolve_logo_uri
from dialogs.invoice_preview_dialog import InvoicePreviewDialog
from utils.app_paths import resource_path
DEFAULT_UNIT_FALLBACK = "UND"


class ItemsLookupMixin:
    def _normalize_name(self, s: str) -> str:
        s = (s or "").strip().upper()
        return " ".join(s.split())

    def _lookup_unit_by_code_or_name(self, code: str, name: str) -> str:
        print(f"[HIT] _lookup_unit_by_code_or_name code='{code}' name='{name}'")

        if code and hasattr(self.logic, "get_item_by_code"):
            try:
                found = self.logic.get_item_by_code(code) or {}
                u = (found.get("unit") or "").strip()
                if u:
                    return u
            except Exception:
                pass

        if name and hasattr(self.logic, "get_items_like"):
            try:
                target = self._normalize_name(name)
                cands = self.logic.get_items_like(name, limit=25) or []
                for c in cands:
                    if self._normalize_name(c.get("name")) == target:
                        u = (c.get("unit") or "").strip()
                        if u:
                            return u
            except Exception:
                pass

        return ""


class QuotationTab(QWidget, ItemsLookupMixin):
    quotation_saved = pyqtSignal(int)

    def __init__(self, logic, get_current_company_callable, parent=None):
        super().__init__(parent)
        self.logic = logic
        self.get_current_company = get_current_company_callable

        try:
            print(f"[LOAD] QuotationTab module: {__file__}")
        except Exception:
            pass

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.setStyleSheet("""
        QGroupBox {
            border: 1px solid #555; border-radius: 6px; margin-top: 10px;
            padding: 8px 10px;
        }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
        """)

        # 1. Datos de la Cotización + Datos del Cliente (unificado)
        datos_cliente_box = QGroupBox("1. Datos de la Cotización  ·  Datos del Cliente")
        g = QGridLayout(datos_cliente_box)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(6)

        # Fecha
        self.quotation_date = QDateEdit(QDate.currentDate()); self.quotation_date.setCalendarPopup(True)
        self.quotation_date.setFixedWidth(120)
        self.quotation_date.setObjectName("infoField")

        # Moneda
        self.quotation_currency = QLineEdit(DEFAULT_CURRENCY)
        self.quotation_currency.setFixedWidth(90)
        self.quotation_currency.setObjectName("infoField")

        # Vence (solo lectura)
        self.quotation_due_display = QLineEdit()
        self.quotation_due_display.setReadOnly(True)
        self.quotation_due_display.setPlaceholderText("N/A")
        self.quotation_due_display.setToolTip("Vencimiento automático = Fecha de emisión + 30 días")
        self.quotation_due_display.setFixedWidth(120)
        self.quotation_due_display.setObjectName("infoField")

        # Cliente
        self.quotation_client_rnc = QLineEdit(); self.quotation_client_rnc.setPlaceholderText("Buscar RNC/Cédula…")
        self.quotation_client_rnc.setFixedWidth(140); self.quotation_client_rnc.setObjectName("infoFieldSmall")

        self.quotation_client_name = QLineEdit(); self.quotation_client_name.setPlaceholderText("Buscar nombre/razón social…")
        self.quotation_client_name.setObjectName("infoField")

        self.quotation_suggestion_combo = QComboBox(); self.quotation_suggestion_combo.hide(); self.quotation_suggestion_combo.setEditable(False)

        # Ubicar widgets
        g.addWidget(QLabel("Fecha:"), 0, 0); g.addWidget(self.quotation_date, 0, 1)
        g.addWidget(QLabel("Moneda:"), 0, 2); g.addWidget(self.quotation_currency, 0, 3)
        g.addWidget(QLabel("Vence:"), 0, 4); g.addWidget(self.quotation_due_display, 0, 5)

        g.addWidget(QLabel("RNC/Cédula:"), 1, 0); g.addWidget(self.quotation_client_rnc, 1, 1)
        g.addWidget(QLabel("Nombre/Razón Social:"), 1, 2); g.addWidget(self.quotation_client_name, 1, 3, 1, 3)
        g.addWidget(self.quotation_suggestion_combo, 1, 6)

        g.setColumnStretch(3, 6); g.setColumnStretch(4, 0); g.setColumnStretch(5, 0)
        layout.addWidget(datos_cliente_box)

        # Botón editar plantilla
        btn_row = QHBoxLayout()
        self.edit_template_btn = QPushButton("Editar plantilla")
        self.edit_template_btn.setToolTip("Editar plantilla para la empresa seleccionada")
        btn_row.addWidget(self.edit_template_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        self.edit_template_btn.clicked.connect(self._on_edit_template)

        # Notas (colapsable)
        notes_toggle_row = QHBoxLayout()
        self.notes_toggle = QToolButton()
        self.notes_toggle.setText("Notas (opcional)")
        self.notes_toggle.setCheckable(True)
        self.notes_toggle.setChecked(False)
        self.notes_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.notes_toggle.toggled.connect(self._toggle_notes)
        notes_toggle_row.addWidget(self.notes_toggle)
        notes_toggle_row.addStretch(1)
        layout.addLayout(notes_toggle_row)

        self.notes_box = QGroupBox()
        notes_lay = QVBoxLayout(self.notes_box)
        self.quotation_notes = QTextEdit()
        self.quotation_notes.setPlaceholderText("Notas para la cotización…")
        self.quotation_notes.setMinimumHeight(80)
        notes_lay.addWidget(self.quotation_notes)
        self.notes_box.setVisible(False)
        layout.addWidget(self.notes_box)

        # 2. Detalles
        detalles_box = QGroupBox("2. Detalles de la Cotización")
        detalles_layout = QVBoxLayout(detalles_box)
        actions = QHBoxLayout()
        btn_add_items = QPushButton("Agregar ítems…")
        btn_add_items.clicked.connect(self._open_item_picker)
        btn_remove_item = QPushButton("Eliminar detalle seleccionado")
        btn_remove_item.clicked.connect(self._remove_item_row)
        actions.addWidget(btn_add_items)
        actions.addWidget(btn_remove_item)
        actions.addStretch(1)
        detalles_layout.addLayout(actions)

        self.quotation_items_table = QTableWidget(0, 7)
        self.quotation_items_table.setHorizontalHeaderLabels(["#", "Código", "Descripción", "Unidad", "Cantidad", "Precio Unitario", "Subtotal"])
        self.quotation_items_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.quotation_items_table.verticalHeader().setVisible(False)
        detalles_layout.addWidget(self.quotation_items_table)

        totals_row = QHBoxLayout()
        totals_row.addStretch(1)
        self.apply_itbis_checkbox = QCheckBox("Aplicar ITBIS (18%)")
        self.apply_itbis_checkbox.setChecked(True)
        self.apply_itbis_checkbox.stateChanged.connect(self._recalculate_totals)
        self.quotation_subtotal_label = QLabel("Subtotal: RD$ 0.00")
        self.quotation_itbis_label = QLabel("ITBIS: RD$ 0.00")
        self.quotation_total_label = QLabel("Total: RD$ 0.00")
        totals_row.addWidget(self.apply_itbis_checkbox)
        totals_row.addSpacing(12)
        totals_row.addWidget(self.quotation_subtotal_label)
        totals_row.addSpacing(8)
        totals_row.addWidget(self.quotation_itbis_label)
        totals_row.addSpacing(8)
        totals_row.addWidget(self.quotation_total_label)
        detalles_layout.addLayout(totals_row)

        layout.addWidget(detalles_box)

        footer_row = QHBoxLayout()
        footer_row.addStretch(1)
        btn_preview_html = QPushButton("Vista Previa / PDF")
        btn_preview_html.setToolTip("Abrir vista previa HTML y exportar a PDF (WYSIWYG)")
        btn_preview_html.clicked.connect(self._preview_quotation)
        btn_save_quotation = QPushButton("Guardar en Base de Datos")
        btn_save_quotation.clicked.connect(self._save_quotation)
        footer_row.addWidget(btn_preview_html)
        footer_row.addWidget(btn_save_quotation)
        layout.addLayout(footer_row)

        self.quotation_date.dateChanged.connect(lambda _d: self._refresh_due_date_label())
        self.quotation_client_rnc.textChanged.connect(lambda: self._suggest_third_party('rnc'))
        self.quotation_client_name.textChanged.connect(lambda: self._suggest_third_party('name'))
        self.quotation_suggestion_combo.activated.connect(self._select_suggestion)

        self._refresh_due_date_label()

    def _toggle_notes(self, checked: bool):
        self.notes_toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self.notes_box.setVisible(checked)

    def _open_item_picker(self):
        dlg = ItemPickerDialog(self, title="Agregar ítems a la Cotización")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        items = dlg.get_selected_items()
        for it in items:
            self._append_row(it.get("codigo"), it.get("nombre"), it.get("unidad"), it.get("cantidad"), it.get("precio"), it.get("subtotal"))
        self._recalculate_totals()

    def _append_row(self, code, name, unit, qty, price, subtotal=None):
        if subtotal is None:
            try:
                subtotal = float(qty) * float(price)
            except Exception:
                subtotal = 0.0
        row = self.quotation_items_table.rowCount()
        self.quotation_items_table.insertRow(row)
        self.quotation_items_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.quotation_items_table.setItem(row, 1, QTableWidgetItem(code or ""))
        self.quotation_items_table.setItem(row, 2, QTableWidgetItem(name or ""))
        self.quotation_items_table.setItem(row, 3, QTableWidgetItem(unit or DEFAULT_UNIT_FALLBACK))
        self.quotation_items_table.setItem(row, 4, QTableWidgetItem(f"{float(qty):.2f}" if qty is not None else "0.00"))
        self.quotation_items_table.setItem(row, 5, QTableWidgetItem(f"{float(price):.2f}" if price is not None else "0.00"))
        self.quotation_items_table.setItem(row, 6, QTableWidgetItem(f"{float(subtotal):,.2f}" if subtotal is not None else "0.00"))

    def on_company_change(self):
        self._clear_form()

    def _suggest_third_party(self, search_by):
        query = self.quotation_client_rnc.text() if search_by == "rnc" else self.quotation_client_name.text()
        if len(query) < 2:
            self.quotation_suggestion_combo.hide(); return
        results = self.logic.search_third_parties(query, search_by=search_by) if hasattr(self.logic, "search_third_parties") else []
        self.quotation_suggestion_combo.clear()
        for item in results:
            self.quotation_suggestion_combo.addItem(f"{item['rnc']} - {item['name']}")
        self.quotation_suggestion_combo.setVisible(bool(results))

    def _select_suggestion(self, idx):
        val = self.quotation_suggestion_combo.currentText()
        if " - " in val:
            rnc, name = val.split(" - ", 1)
            self.quotation_client_rnc.setText(rnc); self.quotation_client_name.setText(name)
        self.quotation_suggestion_combo.hide()

    def _remove_item_row(self):
        r = self.quotation_items_table.currentRow()
        if r < 0:
            QMessageBox.warning(self, "Sin Selección", "Selecciona un detalle para eliminar."); return
        self.quotation_items_table.removeRow(r)
        for i in range(self.quotation_items_table.rowCount()):
            self.quotation_items_table.setItem(i, 0, QTableWidgetItem(str(i+1)))
        self._recalculate_totals()

    def _recalculate_totals(self):
        subtotal = 0.0
        for r in range(self.quotation_items_table.rowCount()):
            cell = self.quotation_items_table.item(r, 6)
            try:
                subtotal += float((cell.text() if cell else "0").replace(",", ""))
            except Exception:
                pass
        itbis = subtotal * ITBIS_RATE if getattr(self, "apply_itbis_checkbox", None) and self.apply_itbis_checkbox.isChecked() else 0.0
        total = subtotal + itbis
        try:
            self.quotation_subtotal_label.setText(f"Subtotal: RD$ {subtotal:,.2f}")
            self.quotation_itbis_label.setText(f"ITBIS ({ITBIS_RATE*100:.0f}%): RD$ {itbis:,.2f}")
            self.quotation_total_label.setText(f"Total: RD$ {total:,.2f}")
        except Exception:
            pass

    def _on_edit_template(self):
        try:
            company = self.get_current_company()
        except Exception:
            company = None

        if not company:
            QMessageBox.warning(self, "Plantilla", "Seleccione primero una empresa válida.")
            return

        company_id = company.get("id") or company.get("company_id") or company.get("pk")
        if not company_id:
            QMessageBox.warning(self, "Plantilla", "La empresa seleccionada no tiene identificador.")
            return

        try:
            dlg = TemplateEditorDialog(company_id=company_id, parent=self)
            if dlg.exec():
                QMessageBox.information(self, "Plantilla", "Plantilla guardada correctamente.")
        except Exception as e:
            QMessageBox.critical(self, "Plantilla", f"No se pudo abrir el editor de plantillas:\n{e}")

    def _qdate_to_str(self, qdate) -> str:
        try:
            return f"{qdate.year():04d}-{qdate.month():02d}-{qdate.day():02d}"
        except Exception:
            return ""

    def _compute_quotation_due_date(self, quotation_date_str: str) -> str:
        if not quotation_date_str:
            return ""
        try:
            d = datetime.strptime(quotation_date_str[:10], "%Y-%m-%d")
            return (d + timedelta(days=30)).strftime("%Y-%m-%d")
        except Exception as e:
            print(f"[QTAB-DUE] error parse base: {e}")
            return ""

    def _refresh_due_date_label(self) -> None:
        try:
            if not hasattr(self, "quotation_date") or not hasattr(self, "quotation_due_display"):
                return
            base_str = self._qdate_to_str(self.quotation_date.date())
            due_str = self._compute_quotation_due_date(base_str)
            if due_str:
                qd = QDate.fromString(due_str, "yyyy-MM-dd")
                pretty = qd.toString("dd/MM/yyyy") if qd.isValid() else due_str
            else:
                pretty = "N/A"
            self.quotation_due_display.setText(pretty)
            self.quotation_due_display.setProperty("raw_due_date", due_str)
            print(f"[QTAB-DUE] UI updated: base={base_str} -> due={due_str} (display={pretty})")
        except Exception as e:
            print(f"[QTAB-DUE] _refresh_due_date_label error: {e}")

    def _preview_quotation(self):
        import os, datetime
        from utils.app_paths import get_resource_path as resource_path
        from dialogs.quotation_preview_dialog import QuotationPreviewDialog as DocumentPreviewDialog
        from dialogs.invoice_preview_dialog import InvoicePreviewDialog

        company = self.get_current_company()
        if not company:
            QMessageBox.warning(self, "Empresa", "Seleccione una empresa válida")
            return

        company_data, tpl = self._get_company_payload_for_preview()

        items = self._collect_items_for_export()
        if not items:
            QMessageBox.warning(self, "Ítems", "Agrega al menos un ítem a la cotización antes de previsualizar.")
            return

        try:
            quotation_date_str = self.quotation_date.date().toString("yyyy-MM-dd")
        except Exception:
            quotation_date_str = datetime.date.today().strftime("%Y-%m-%d")

        due_auto = self._compute_quotation_due_date(quotation_date_str)

        def _safe_text(name: str) -> str:
            w = getattr(self, name, None)
            if w is None: return ""
            if hasattr(w, "currentText"): return (w.currentText() or "").strip()
            if hasattr(w, "text"):        return (w.text() or "").strip()
            if hasattr(w, "toPlainText"): return (w.toPlainText() or "").strip()
            return ""

        subtotal = 0.0
        for it in items:
            try:
                subtotal += float(it.get("quantity", 0)) * float(it.get("unit_price", 0))
            except Exception:
                pass
        itbis_amount = subtotal * ITBIS_RATE if getattr(self, "apply_itbis_checkbox", None) and self.apply_itbis_checkbox.isChecked() else 0.0
        total_amount = subtotal + itbis_amount

        quotation_data = {
            "type": "COTIZACIÓN",
            "invoice_category": "Cotización",
            "company_id": company_data.get("id"),
            "number": "",
            "ncf": "",
            "date": quotation_date_str,
            "due_date": due_auto,
            "client_name": _safe_text("quotation_client_name"),
            "client_rnc":  _safe_text("quotation_client_rnc"),
            "currency":       _safe_text("quotation_currency"),
            "items": items,
            "notes": (self.quotation_notes.toPlainText() if getattr(self, "notes_box", None) and self.notes_box.isVisible() else _safe_text("quotation_notes")),
            "apply_itbis": (getattr(self, "apply_itbis_checkbox", None) and self.apply_itbis_checkbox.isChecked()),
            "subtotal": round(subtotal, 2),
            "itbis": round(itbis_amount, 2),
            "total_amount": round(total_amount, 2),
        }

        template_path = resource_path("templates", "quotation_template.html")

        if InvoicePreviewDialog is None:
            QMessageBox.critical(self, "Vista Previa", "DocumentPreviewDialog no está disponible.")
            return

        try:
            dlg = InvoicePreviewDialog(
                company=company_data,
                template=tpl,
                invoice=quotation_data,
                parent=self,
                template_path=template_path,
                debug=False,
            )
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Vista Previa", f"No se pudo abrir la vista previa:\n{e}")

    def _save_quotation(self):
        company = self.get_current_company()
        if not company:
            QMessageBox.warning(self, "Empresa", "Seleccione una empresa válida"); return

        subtotal = 0.0
        items = []
        for r in range(self.quotation_items_table.rowCount()):
            sub = self.quotation_items_table.item(r, 6)
            try:
                subtotal += float(sub.text().replace(",", "")) if sub and sub.text().strip() else 0.0
            except Exception:
                pass
        itbis = subtotal * ITBIS_RATE if getattr(self, "apply_itbis_checkbox", None) and self.apply_itbis_checkbox.isChecked() else 0.0
        total = subtotal + itbis

        data = {
            "company_id": company['id'],
            "quotation_date": self.quotation_date.date().toString("yyyy-MM-dd"),
            "client_name": self.quotation_client_name.text(),
            "client_rnc": self.quotation_client_rnc.text(),
            "notes": self.quotation_notes.toPlainText() if getattr(self, "notes_box", None) and self.notes_box.isVisible() else "",
            "currency": self.quotation_currency.text(),
            "apply_itbis": bool(getattr(self, "apply_itbis_checkbox", None) and self.apply_itbis_checkbox.isChecked()),
            "subtotal": round(subtotal, 2),
            "itbis": round(itbis, 2),
            "total_amount": round(total, 2),
            "excel_path": "",
            "pdf_path": "",
        }

        for r in range(self.quotation_items_table.rowCount()):
            desc = self.quotation_items_table.item(r, 2)
            qty = self.quotation_items_table.item(r, 4)
            price = self.quotation_items_table.item(r, 5)
            code = self.quotation_items_table.item(r, 1)
            unit = self.quotation_items_table.item(r, 3)
            try:
                qty_val = float(qty.text().replace(",", "")) if qty and qty.text().strip() else 0.0
                price_val = float(price.text().replace(",", "")) if price and price.text().strip() else 0.0
            except Exception:
                qty_val = 0.0; price_val = 0.0
            items.append({
                "code": code.text() if code else "",
                "description": desc.text() if desc else "",
                "unit": unit.text() if unit else DEFAULT_UNIT_FALLBACK,
                "quantity": qty_val,
                "unit_price": price_val,
                "line_total": round(qty_val * price_val, 2)
            })

        quotation_id = None
        try:
            quotation_id = self.logic.add_quotation(data, items)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo guardar la cotización:\n{e}")
            return

        QMessageBox.information(self, "Cotización", f"Cotización creada (ID: {quotation_id})")
        self._clear_form()
        if quotation_id:
            self.quotation_saved.emit(quotation_id)

    def _clear_form(self):
        try:
            self.quotation_date.setDate(QDate.currentDate())
            self.quotation_client_name.clear(); self.quotation_client_rnc.clear()
            self.quotation_notes.clear()
            self.notes_box.setVisible(False)
            self.notes_toggle.setChecked(False)
            self.notes_toggle.setArrowType(Qt.ArrowType.RightArrow)
            self.quotation_currency.setText(DEFAULT_CURRENCY)
            self.quotation_items_table.setRowCount(0)
            self.quotation_subtotal_label.setText("Subtotal: RD$ 0.00")
            self.quotation_itbis_label.setText("ITBIS: RD$ 0.00")
            self.quotation_total_label.setText("Total: RD$ 0.00")
            if getattr(self, "apply_itbis_checkbox", None):
                self.apply_itbis_checkbox.setChecked(True)
        except Exception:
            pass

    def _get_company_payload_for_preview(self):
        company_min = self.get_current_company() or {}
        company_id = company_min.get("id")

        if not company_id:
            print("[QuotationTab] ERROR: No se pudo obtener company_id")
            return {}, {}

        details_db = {}
        try:
            if hasattr(self.logic, "get_company_details"):
                details_db = self.logic.get_company_details(company_id) or {}
                print(f"[QuotationTab] get_company_details({company_id}) RESULTADO COMPLETO: {details_db}")
            else:
                print("[QuotationTab] ERROR: self.logic no tiene el método get_company_details")
        except Exception as e:
            print(f"[QuotationTab] ERROR en get_company_details: {e}")
            details_db = {}

        details = {**company_min, **details_db}

        a1 = (details.get("address_line1") or "").strip()
        a2 = (details.get("address_line2") or "").strip()
        addr = (details.get("address") or "").strip()
        if a1 or a2:
            address_full = f"{a1} {a2}".strip()
        else:
            address_full = addr or "Dirección no especificada"

        signature = (details.get("signature_name") or "").strip()
        logo_rel = (details.get("logo_path") or "").strip()

        payload = {
            "id": company_id,
            "name": details.get("name", "N/A"),
            "rnc": details.get("rnc", "N/A"),
            "address_line1": a1,
            "address_line2": a2,
            "address": address_full,
            "phone": details.get("phone", ""),
            "email": details.get("email", ""),
            "signature_name": signature,
            "authorized_name": signature,
            "logo_path": logo_rel,
        }

        tpl = {}
        try:
            tpl = load_template(int(company_id)) or {}
        except Exception:
            tpl = {}

        print(f"[QuotationTab] company_payload_for_preview FINAL: {payload}")

        return payload, tpl

    def _collect_items_for_export(self):
        print("[HIT] _collect_items_for_export (QUOTATION)")
        return self._collect_items_for_export_from_table(self.quotation_items_table)

    def _collect_items_for_export_from_table(self, table):
        DEFAULT_UNIT_FALLBACK = "UND"
        items = []

        row_count = table.rowCount() if table else 0
        for r in range(row_count):
            code_item = table.item(r, 1)
            desc_item = table.item(r, 2)
            unit_item = table.item(r, 3)
            qty_item  = table.item(r, 4)
            price_item= table.item(r, 5)

            code = (code_item.text().strip() if code_item and code_item.text() else "")
            desc = (desc_item.text().strip() if desc_item and desc_item.text() else "")

            unit_master = ""
            try:
                if code and hasattr(self.logic, "get_item_by_code"):
                    found = self.logic.get_item_by_code(code) or {}
                    unit_master = (found.get("unit") or "").strip()
            except Exception as e:
                print(f"[QUOTATION] get_item_by_code error: {e}")

            if not unit_master and desc:
                try:
                    if hasattr(self.logic, "conn") and self.logic.conn:
                        cur = self.logic.conn.cursor()
                        cur.execute("SELECT unit FROM items WHERE name = ? LIMIT 1", (desc,))
                        row = cur.fetchone()
                        if row:
                            unit_master = (row["unit"] if isinstance(row, dict) else row[0]) or ""
                            unit_master = unit_master.strip()
                except Exception as e:
                    print(f"[QUOTATION] lookup unit by exact name error: {e}")

            resolved_unit = unit_master or DEFAULT_UNIT_FALLBACK

            try:
                from PyQt6.QtWidgets import QTableWidgetItem
                current_unit = (unit_item.text().strip() if unit_item and unit_item.text() else "")
                if resolved_unit != current_unit:
                    table.setItem(r, 3, QTableWidgetItem(resolved_unit))
            except Exception:
                pass

            try:
                qty = float((qty_item.text() if qty_item else "0").replace(",", "").strip() or 0)
            except Exception:
                qty = 0.0
            try:
                price = float((price_item.text() if price_item else "0").replace(",", "").strip() or 0)
            except Exception:
                price = 0.0

            print(f"[QUOTATION] row={r} code='{code}' desc='{desc}' unit_master='{unit_master}' unit_final='{resolved_unit}'")

            items.append({
                "code": code,
                "description": desc,
                "unit": resolved_unit,
                "quantity": qty,
                "unit_price": price,
            })

        return items