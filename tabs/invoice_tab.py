from __future__ import annotations
import os
import logging
from typing import Dict, Any, List, Any as AnyType, Optional
from datetime import datetime as dt, timedelta
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton,
    QDateEdit, QCheckBox, QTableWidget, QTableWidgetItem, QMessageBox, QFileDialog,
    QHeaderView, QGroupBox, QGridLayout, QDialog, QInputDialog
)
from PyQt6.QtCore import QDate, Qt, pyqtSignal, QRegularExpression
from PyQt6.QtGui import QRegularExpressionValidator

from constants import NCF_TYPES, ITBIS_RATE, DEFAULT_CURRENCY

from utils.quotation_templates import (
    generate_quotation_excel as generate_invoice_excel,
    generate_quotation_pdf as generate_invoice_pdf,
)

from dialogs.item_picker_dialog import ItemPickerDialog
from dialogs.template_editor_dialog import TemplateEditorDialog

from utils.template_integration import (
    export_invoice_excel_with_template,
    export_invoice_pdf_with_template,
)

try:
    from utils.template_manager import load_template, get_data_root
except Exception:
    def load_template(company_id: int):
        return {}
    def get_data_root():
        return os.getcwd()

try:
    from dialogs.invoice_preview_dialog import InvoicePreviewDialog
except Exception:
    InvoicePreviewDialog = None

from utils.asset_paths import resolve_logo_uri

try:
    from company_management_window import CompanyManagementWindow
except Exception:
    CompanyManagementWindow = None

try:
    import config_facot
except Exception:
    class _Cfg:
        QUOTATION_DUE_DAYS = 30
        INVOICE_DUE_DAYS = 30
        INVOICE_FIXED_DUE_DATE = ""
        COMPANY_LOGOS = {}
        DEFAULT_LOGO_PATH = ""
    config_facot = _Cfg()

CATEGORY_TO_PREFIX = {
    "FACTURA PRIVADA": "B01",
    "FACTURA GUBERNAMENTAL": "B15",
    "FACTURA GUBERMAMENTAL": "B15",
    "FACTURA CONSUMIDOR FINAL": "B02",
    "FACTURA EXENTA": "B14",
    "FACTURA EXENTA (REGIMEN ESPECIAL)": "B14",
    "FACTURA EXCENTA (REGIMEN ESPECIAL)": "B14",
}
DEFAULT_UNIT_FALLBACK = "UND"


NCF_CATEGORY_MAP = {
    'B01': 'Factura Privada',
    'B02': 'Consumidor Final',
    'B04': 'Nota de Crédito',
    'B14': 'Factura Gubernamental',
    'B15': 'Factura Exenta',
    'B16': 'Gubernamental Exenta',
    'E31': 'Factura Privada (e-CF)',
    'E32': 'Consumidor Final (e-CF)',
    'E33': 'Nota de Débito (e-CF)',
    'E34': 'Nota de Crédito (e-CF)',
}

def _derive_invoice_category_from_ncf(ncf: str) -> str:
    if not ncf:
        return ""
    return NCF_CATEGORY_MAP.get((ncf or "").strip().upper()[:3], "")
# Logger
logger = logging.getLogger(__name__)


class InvoiceTab(QWidget):
    """
    Pestaña de Facturas:
    - Secuencias NCF persistentes (preview vs consumo)
    - Ítems con unidad desde maestro
    - Exportación y vista previa
    """
    invoice_saved = pyqtSignal(int)

    def __init__(self, logic, get_current_company_callable, parent=None):
        super().__init__(parent)
        self.logic = logic
        self.get_current_company = get_current_company_callable
        # Contenedor temporal para PDF subidos en modo preview (antes de crear invoice)
        # Estructura: {'storage_path': str, 'url': str, 'company_id': int, 'ncf_or_number': str, 'expires_at': str}
        # Usamos dos nombres por compatibilidad con distintos lugares del código
        self._preview_pdf_info = None
        self._preview_pdf_info_invoice = None
        try:
            print(f"[LOAD] InvoiceTab module: {__file__}")
        except Exception:
            pass
        self._build_ui()



    # -------------------------
    # UI principal
    # -------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Top action row
        top_btn_row = QHBoxLayout()
        self.edit_template_btn = QPushButton("Editar plantilla")
        self.edit_template_btn.clicked.connect(self._on_edit_template)
        top_btn_row.addWidget(self.edit_template_btn)

        self.edit_company_btn = QPushButton("Editar empresa")
        self.edit_company_btn.clicked.connect(self._open_company_manager)
        top_btn_row.addWidget(self.edit_company_btn)

        self.btn_next_ncf = QPushButton("Siguiente NCF")
        self.btn_next_ncf.setToolTip("Asignar y consumir el siguiente NCF real")
        self.btn_next_ncf.clicked.connect(self._on_next_ncf_clicked)
        top_btn_row.addWidget(self.btn_next_ncf)

        top_btn_row.addStretch(1)
        layout.addLayout(top_btn_row)

        # COMBINED BLOCK: Datos de Factura + Datos del Cliente (compact)
        datos_cliente_box = QGroupBox("1. Datos de la Factura  ·  Datos del Cliente")
        g = QGridLayout(datos_cliente_box)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(6)

        # NCF asignado (read-only for user, programmatically writable)
        self.ncf_number_edit = QLineEdit()
        self.ncf_number_edit.setClearButtonEnabled(True)
        self._setup_ncf_validator()
        self.ncf_number_edit.setReadOnly(True)
        self.ncf_number_edit.setFixedWidth(180)
        self.ncf_number_edit.setObjectName("infoField")

        # invoice category (keeps prefix mapping)
        self.invoice_kind_combo = QComboBox()
        self.invoice_kind_combo.addItems([
            "FACTURA PRIVADA",
            "FACTURA GUBERNAMENTAL",
            "FACTURA CONSUMIDOR FINAL",
            "FACTURA EXENTA",
        ])

        # dates
        self.invoice_date = QDateEdit(QDate.currentDate()); self.invoice_date.setCalendarPopup(True)
        self.invoice_due_date = QDateEdit(QDate.currentDate()); self.invoice_due_date.setCalendarPopup(True)
        self.invoice_date.setFixedWidth(120); self.invoice_date.setObjectName("infoField")
        self.invoice_due_date.setFixedWidth(120); self.invoice_due_date.setObjectName("infoField")

        # currency
        self.currency_combo = QComboBox(); self.currency_combo.addItems(["RD$", "USD", "EUR"])
        try: self.currency_combo.setCurrentText(DEFAULT_CURRENCY)
        except Exception: pass
        self.currency_combo.setFixedWidth(90); self.currency_combo.setObjectName("infoField")

        self.exchange_rate_edit = QLineEdit("1.00"); self.exchange_rate_edit.setVisible(False)
        self.exchange_rate_edit.setFixedWidth(90); self.exchange_rate_edit.setObjectName("infoField")

        # client fields & suggest combo
        self.client_rnc = QLineEdit(); self.client_rnc.setPlaceholderText("RNC/Cédula…")
        self.client_rnc.setFixedWidth(140); self.client_rnc.setObjectName("infoFieldSmall")
        self.client_name = QLineEdit(); self.client_name.setPlaceholderText("Nombre / Razón Social…")
        self.client_name.setObjectName("infoField")
        self.suggestion_combo = QComboBox(); self.suggestion_combo.hide(); self.suggestion_combo.setEditable(False)
        self.client_rnc.textChanged.connect(lambda: self._suggest_third_party('rnc'))
        self.client_name.textChanged.connect(lambda: self._suggest_third_party('name'))
        self.suggestion_combo.activated.connect(self._select_suggestion)

        # refresh preview NCF button (small)
        self.btn_refresh_ncf = QPushButton("↻"); self.btn_refresh_ncf.setToolTip("Mostrar el próximo NCF (preview)")
        self.btn_refresh_ncf.clicked.connect(self._update_ncf_sequence)

        # Row 0: NCF | Refresh | Tipo Factura | Fecha | Vencimiento
        g.addWidget(QLabel("NCF Asignado:"), 0, 0); g.addWidget(self.ncf_number_edit, 0, 1)
        g.addWidget(self.btn_refresh_ncf, 0, 2)
        g.addWidget(QLabel("Tipo Factura:"), 0, 3); g.addWidget(self.invoice_kind_combo, 0, 4)
        g.addWidget(QLabel("Fecha:"), 0, 5); g.addWidget(self.invoice_date, 0, 6)
        g.addWidget(QLabel("Vencimiento:"), 0, 7); g.addWidget(self.invoice_due_date, 0, 8)

        # Row 1: Moneda | Tasa | RNC (small) | Nombre (large span)
        g.addWidget(QLabel("Moneda:"), 1, 0)
        g.addWidget(self.currency_combo, 1, 1)
        g.addWidget(QLabel("Tasa:"), 1, 2)
        g.addWidget(self.exchange_rate_edit, 1, 3)
        g.addWidget(QLabel("RNC/Cédula:"), 1, 4)
        g.addWidget(self.client_rnc, 1, 5)
        g.addWidget(QLabel("Nombre/Razón Social:"), 1, 6)
        g.addWidget(self.client_name, 1, 7, 1, 2)
        g.addWidget(self.suggestion_combo, 1, 9)

        # column stretches to allocate remaining space to 'Nombre'
        g.setColumnStretch(1, 0)
        g.setColumnStretch(3, 0)
        g.setColumnStretch(5, 0)
        g.setColumnStretch(7, 6)
        g.setColumnStretch(8, 2)
        layout.addWidget(datos_cliente_box)

        # Connections preserved
        self.invoice_kind_combo.currentIndexChanged.connect(self._update_ncf_sequence)
        self.invoice_date.dateChanged.connect(self._maybe_new_year_reset)
        self.currency_combo.currentIndexChanged.connect(self._on_currency_change)

        # 2. Detalles de la Factura (tabla) — includes Totals inline
        detalles_box = QGroupBox("2. Detalles de la Factura")
        detalles_layout = QVBoxLayout(detalles_box)

        actions = QHBoxLayout()
        btn_add_items = QPushButton("Agregar ítems…"); btn_add_items.clicked.connect(self._open_item_picker)
        btn_remove_item = QPushButton("Eliminar detalle seleccionado"); btn_remove_item.clicked.connect(self._remove_invoice_item_row)
        actions.addWidget(btn_add_items); actions.addWidget(btn_remove_item); actions.addStretch(1)
        detalles_layout.addLayout(actions)

        # Items table
        self.invoice_items_table = QTableWidget(0, 7)
        self.invoice_items_table.setHorizontalHeaderLabels(["#", "Código", "Descripción", "Unidad", "Cantidad", "Precio Unitario", "Subtotal"])
        self.invoice_items_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.invoice_items_table.verticalHeader().setVisible(False)
        detalles_layout.addWidget(self.invoice_items_table)

        # Totals inline inside detalles block (compact right-aligned)
        totals_row = QHBoxLayout()
        totals_row.addStretch(1)
        self.apply_itbis_checkbox = QCheckBox("Aplicar ITBIS (18%)"); self.apply_itbis_checkbox.setChecked(True)
        self.apply_itbis_checkbox.stateChanged.connect(self._recalculate_invoice_totals)
        self.subtotal_label = QLabel("Subtotal: RD$ 0.00")
        self.itbis_label = QLabel("ITBIS: RD$ 0.00")
        self.total_label = QLabel("Total: RD$ 0.00")

        totals_row.addWidget(self.apply_itbis_checkbox)
        totals_row.addSpacing(12)
        totals_row.addWidget(self.subtotal_label)
        totals_row.addSpacing(8)
        totals_row.addWidget(self.itbis_label)
        totals_row.addSpacing(8)
        totals_row.addWidget(self.total_label)

        detalles_layout.addLayout(totals_row)
        layout.addWidget(detalles_box)

        # Footer action buttons (kept simple)
        footer_actions = QHBoxLayout()
        footer_actions.addStretch(1)
        btn_preview_html = QPushButton("Vista Previa / PDF")
        btn_preview_html.setToolTip("Abrir vista previa HTML y exportar a PDF")
        btn_preview_html.clicked.connect(self._preview_invoice)

        btn_save_invoice = QPushButton("Guardar en Base de Datos")
        btn_save_invoice.setProperty("class", "primary")
        btn_save_invoice.clicked.connect(self._save_invoice)

        footer_actions.addWidget(btn_preview_html)
        footer_actions.addWidget(btn_save_invoice)
        
        layout.addLayout(footer_actions)

        # Initial population / hooks
        self._apply_default_due_date()
        self.invoice_date.dateChanged.connect(self._on_invoice_date_changed)
        self._update_ncf_sequence()

    # -------------------------
    # NCF helpers
    # -------------------------
    def _setup_ncf_validator(self):
        pattern = r"^(E[0-9]{13}|(?!E)[A-Z][0-9]{10})$"
        regex = QRegularExpression(pattern)
        self.ncf_number_edit.setValidator(QRegularExpressionValidator(regex, self.ncf_number_edit))
        try:
            self.ncf_number_edit.textEdited.connect(lambda _: self._enforce_upper(self.ncf_number_edit))
        except Exception:
            pass
        self.ncf_number_edit.setPlaceholderText("Formato: ETTSSSSSSSSSSS o LTTSSSSSSSS (E+13 / letra≠E+10)")

    def _enforce_upper(self, edit: QLineEdit):
        try:
            pos = edit.cursorPosition()
            edit.setText((edit.text() or "").upper())
            edit.setCursorPosition(pos)
        except Exception:
            pass

    def _category_prefix(self) -> str:
        cat = (self.invoice_kind_combo.currentText() or "").strip().upper()
        if cat in CATEGORY_TO_PREFIX:
            return CATEGORY_TO_PREFIX[cat]
        if isinstance(NCF_TYPES, dict):
            return next(iter(NCF_TYPES.keys()), "B01")
        return "B01"

    def _dedupe_ncf(self, ncf: str, prefix3: str) -> str:
        n = (ncf or "").upper()
        p = (prefix3 or "").upper()
        if len(n) >= 4 and len(p) == 3:
            if n[0] == n[1] and n[1:].startswith(p):
                return n[1:]
        return n

    def _update_ncf_sequence(self):
        company = self.get_current_company()
        if not company:
            self.ncf_number_edit.clear(); return
        prefix3 = self._category_prefix()
        preview = ""
        try:
            if hasattr(self.logic, "get_ncf_preview"):
                preview = self.logic.get_ncf_preview(int(company['id']), prefix3)
                print(f"[ITAB-NCF-PREVIEW] company_id={company['id']}, prefix3={prefix3}, preview={preview}")
            elif hasattr(self.logic, "get_next_ncf"):
                preview = self.logic.get_next_ncf(int(company['id']), prefix3)
                print(f"[ITAB-NCF-PREVIEW] company_id={company['id']}, prefix3={prefix3}, preview={preview} (via get_next_ncf)")
        except Exception as e:
            print(f"[NCF] Error preview: {e}")
        preview = self._dedupe_ncf(preview, prefix3)
        self.ncf_number_edit.setText(preview or "")

    def _on_next_ncf_clicked(self):
        comp = self.get_current_company()
        if not comp:
            QMessageBox.warning(self, "NCF", "Seleccione una empresa."); return
        prefix3 = self._category_prefix()
        
        # Obtener el valor antes (para logging)
        before_ncf = ""
        try:
            if hasattr(self.logic, "get_ncf_preview"):
                before_ncf = self.logic.get_ncf_preview(int(comp['id']), prefix3)
        except Exception as e:
            print(f"[ITAB-NCF-ALLOC] Error obteniendo preview: {e}")
        
        try:
            if hasattr(self.logic, "allocate_next_ncf"):
                next_ncf = self.logic.allocate_next_ncf(int(comp['id']), prefix3)
                print(f"[ITAB-NCF-ALLOC] company_id={comp['id']}, prefix3={prefix3}, before={before_ncf}, after={next_ncf}, assigned={next_ncf}")
            else:
                next_ncf = self.logic.get_next_ncf(int(comp['id']), prefix3)
                print(f"[ITAB-NCF-ALLOC] company_id={comp['id']}, prefix3={prefix3}, assigned={next_ncf} (via get_next_ncf)")
            next_ncf = self._dedupe_ncf(next_ncf, prefix3)
            self.ncf_number_edit.setText(next_ncf)
        except Exception as e:
            QMessageBox.critical(self, "NCF", f"No se pudo asignar el siguiente NCF:\n{e}")

    def _maybe_new_year_reset(self):
        self._update_ncf_sequence()

    def _validate_ncf_or_warn(self) -> bool:
        ncf = (self.ncf_number_edit.text() or "").strip().upper()
        if not hasattr(self.logic, "validate_ncf"):
            return True
        if not self.logic.validate_ncf(ncf):
            QMessageBox.critical(self, "NCF", "NCF inválido. Formatos válidos: E + 13 dígitos, o letra≠E + 10 dígitos.")
            return False
        return True

    def _ensure_ncf_assigned_and_mark(self, company: Dict[str, Any]):
        if not company:
            return None
        prefix = self._category_prefix()
        current = (self.ncf_number_edit.text() or "").strip().upper()
        try:
            if hasattr(self.logic, "get_ncf_preview"):
                preview = self.logic.get_ncf_preview(int(company['id']), prefix)
            else:
                preview = self.logic.get_next_ncf(int(company['id']), prefix)
        except Exception:
            preview = ""
        try:
            if not current or (preview and current == preview):
                if hasattr(self.logic, "allocate_next_ncf"):
                    assigned = self.logic.allocate_next_ncf(int(company['id']), prefix)
                else:
                    assigned = self.logic.get_next_ncf(int(company['id']), prefix)
                assigned = self._dedupe_ncf(assigned, prefix)
                if assigned:
                    self.ncf_number_edit.setText(assigned)
                    current = assigned
        except Exception as ex:
            print("[InvoiceTab] _ensure_ncf_assigned_and_mark error:", ex)
        return current

    # -------------------------
    # Moneda / fechas
    # -------------------------
    def _on_currency_change(self):
        moneda = self.currency_combo.currentText()
        if moneda != "RD$":
            self.exchange_rate_edit.setVisible(True)
            try:
                tasa, ok = QInputDialog.getDouble(
                    self, "Tasa de cambio",
                    f"Ingrese la tasa para {moneda} → RD$: ",
                    value=self._safe_float(self.exchange_rate_edit.text(), 1.0),
                    min=0.0001, decimals=4
                )
            except Exception:
                ok = False; tasa = 1.0
            self.exchange_rate_edit.setText(f"{tasa:.4f}" if ok else "1.00")
        else:
            self.exchange_rate_edit.setText("1.00"); self.exchange_rate_edit.setVisible(False)

    def _apply_default_due_date(self):
        fixed = getattr(config_facot, "INVOICE_FIXED_DUE_DATE", "") or ""
        days = int(getattr(config_facot, "INVOICE_DUE_DAYS", 0) or 0)
        if fixed:
            try:
                y, m, d = [int(x) for x in fixed.split("-")]
                self.invoice_due_date.setDate(QDate(y, m, d))
                return
            except Exception:
                pass
        if days > 0:
            base = self.invoice_date.date()
            self.invoice_due_date.setDate(base.addDays(days))

    def _on_invoice_date_changed(self, new_date: QDate):
        fixed = getattr(config_facot, "INVOICE_FIXED_DUE_DATE", "") or ""
        days = int(getattr(config_facot, "INVOICE_DUE_DAYS", 0) or 0)
        if fixed:
            return
        if days > 0:
            self.invoice_due_date.setDate(new_date.addDays(days))

    # -------------------------
    # Cliente / sugerencias
    # -------------------------
    def _suggest_third_party(self, search_by):
        query = self.client_rnc.text() if search_by == "rnc" else self.client_name.text()
        if len(query) < 2:
            self.suggestion_combo.hide(); return
        results = self.logic.search_third_parties(query, search_by=search_by) if hasattr(self.logic, "search_third_parties") else []
        self.suggestion_combo.clear()
        for item in results:
            self.suggestion_combo.addItem(f"{item['rnc']} - {item['name']}")
        self.suggestion_combo.setVisible(bool(results))

    def _select_suggestion(self, idx: int):
        try:
            text = self.suggestion_combo.currentText() or ""
            if " - " in text:
                rnc, name = text.split(" - ", 1)
                self.client_rnc.setText(rnc.strip())
                self.client_name.setText(name.strip())
            else:
                if text:
                    self.client_name.setText(text.strip())
            self.suggestion_combo.hide()
        except Exception:
            self.suggestion_combo.hide()

    # -------------------------
    # Ítems
    # -------------------------
    def _open_item_picker(self):
        dlg = ItemPickerDialog(self, title="Agregar ítems a la Factura")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        items = dlg.get_selected_items()
        for it in items:
            code = it.get("code") or it.get("codigo") or it.get("item_code") or ""
            name = it.get("name") or it.get("nombre") or it.get("description") or ""
            unit = it.get("unit") or it.get("unidad") or ""
            qty = it.get("quantity") or it.get("cantidad") or 0
            price = it.get("unit_price") or it.get("precio") or 0.0
            self._append_row(code, name, unit, qty, price)
        self._recalculate_invoice_totals()

    def _append_row(self, code, name, unit, qty, price, subtotal=None):
        if subtotal is None:
            try:
                subtotal = float(qty) * float(price)
            except Exception:
                subtotal = 0.0
        row = self.invoice_items_table.rowCount()
        self.invoice_items_table.insertRow(row)
        self.invoice_items_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.invoice_items_table.setItem(row, 1, QTableWidgetItem(code or ""))
        self.invoice_items_table.setItem(row, 2, QTableWidgetItem(name or ""))
        self.invoice_items_table.setItem(row, 3, QTableWidgetItem((unit or "").strip()))
        self.invoice_items_table.setItem(row, 4, QTableWidgetItem(f"{float(qty):.2f}" if qty is not None else "0.00"))
        self.invoice_items_table.setItem(row, 5, QTableWidgetItem(f"{float(price):.2f}" if price is not None else "0.00"))
        self.invoice_items_table.setItem(row, 6, QTableWidgetItem(f"{float(subtotal):,.2f}"))
        self._recalculate_invoice_totals()

    def _remove_invoice_item_row(self):
        r = self.invoice_items_table.currentRow()
        if r < 0:
            QMessageBox.warning(self, "Sin Selección", "Selecciona un detalle para eliminar."); return
        self.invoice_items_table.removeRow(r)
        for i in range(self.invoice_items_table.rowCount()):
            self.invoice_items_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
        self._recalculate_invoice_totals()

    def _recalculate_invoice_totals(self):
        subtotal = 0.0
        for r in range(self.invoice_items_table.rowCount()):
            cell = self.invoice_items_table.item(r, 6)
            if not cell:
                continue
            txt = (cell.text() or "").replace(",", "").strip()
            try:
                subtotal += float(txt) if txt else 0.0
            except Exception:
                pass
        itbis = subtotal * ITBIS_RATE if getattr(self, "apply_itbis_checkbox", None) and self.apply_itbis_checkbox.isChecked() else 0.0
        total = subtotal + itbis
        try:
            self.subtotal_label.setText(f"Subtotal: RD$ {subtotal:,.2f}")
            self.itbis_label.setText(f"ITBIS ({ITBIS_RATE*100:.0f}%): RD$ {itbis:,.2f}")
            self.total_label.setText(f"Total: RD$ {total:,.2f}")
        except Exception:
            pass

    # -------------------------
    # Vista previa / exportación
    # -------------------------
    def _collect_items_for_export(self) -> List[Dict[str, AnyType]]:
        items = []
        for r in range(self.invoice_items_table.rowCount()):
            desc_item = self.invoice_items_table.item(r, 2)
            code_item = self.invoice_items_table.item(r, 1)
            unit_item = self.invoice_items_table.item(r, 3)
            qty_item = self.invoice_items_table.item(r, 4)
            price_item = self.invoice_items_table.item(r, 5)
            try:
                qty_val = float(qty_item.text().replace(",", "")) if qty_item and qty_item.text().strip() else 0.0
            except Exception:
                qty_val = 0.0
            try:
                price_val = float(price_item.text().replace(",", "")) if price_item and price_item.text().strip() else 0.0
            except Exception:
                price_val = 0.0
            items.append({
                "code": code_item.text() if code_item else "",
                "description": desc_item.text() if desc_item else "",
                "unit": unit_item.text() if unit_item else DEFAULT_UNIT_FALLBACK,
                "quantity": qty_val,
                "unit_price": price_val
            })
        return items

    def _preview_invoice(self):
        company = self.get_current_company()
        if not company:
            QMessageBox.warning(self, "Empresa", "Seleccione una empresa válida")
            return

        company_data, tpl = self._get_company_payload_for_preview()
        self._ensure_ncf_assigned_and_mark(company)
        ncf_text = (self.ncf_number_edit.text() or "").strip().upper()

        items = self._collect_items_for_export()
        if not items:
            QMessageBox.warning(self, "Ítems", "Agrega al menos un ítem antes de previsualizar.")
            return

        invoice_data = {
            "company_id": company_data.get('id'),
            "number": f"INV-DRAFT-{dt.now().strftime('%y%m%d%H%M%S')}",
            "ncf": ncf_text,
            "date": self.invoice_date.date().toString("yyyy-MM-dd"),
            "due_date": self.invoice_due_date.date().toString("yyyy-MM-dd"),
            "client_name": self.client_name.text(),
            "client_rnc": self.client_rnc.text(),
            "currency": self.currency_combo.currentText(),
            "exchange_rate": self._safe_float(self.exchange_rate_edit.text(), 1.0),
            "items": items,
            "notes": "",
            "invoice_category": self.invoice_kind_combo.currentText(),
            "type": self.invoice_kind_combo.currentText(),
            "apply_itbis": getattr(self, "apply_itbis_checkbox", QCheckBox()).isChecked() if hasattr(self, "apply_itbis_checkbox") else False,
        }
        invoice_data["display_number"] = self._build_display_invoice_number(company_data, ncf_text, prefix_label="FACT", last_digits=6)

        template_path = os.path.join(get_data_root(), "templates", "quotation_template.html")

        if InvoicePreviewDialog is None:
            QMessageBox.critical(self, "Vista Previa", "InvoicePreviewDialog no está disponible.")
            return

        dlg = InvoicePreviewDialog(
            company=company_data,
            template=tpl,
            invoice=invoice_data,
            parent=self,
            template_path=template_path,
            debug=False
        )
        dlg.exec()

    def _generate_invoice_excel(self):
        company = self.get_current_company()
        if not company:
            QMessageBox.warning(self, "Empresa", "Seleccione una empresa válida")
            return

        items_for_export = []
        for r in range(self.invoice_items_table.rowCount()):
            desc = self.invoice_items_table.item(r, 2)
            qty = self.invoice_items_table.item(r, 4)
            price = self.invoice_items_table.item(r, 5)
            try:
                qty_val = float(qty.text().replace(",", "")) if qty and qty.text().strip() else 0.0
                price_val = float(price.text().replace(",", "")) if price and price.text().strip() else 0.0
            except Exception:
                qty_val = 0.0; price_val = 0.0
            items_for_export.append({"description": desc.text() if desc else "", "quantity": qty_val, "unit_price": price_val})

        data = {
            "company_id": int(company['id']),
            "invoice_date": self.invoice_date.date().toString("yyyy-MM-dd"),
            "invoice_number": (self.ncf_number_edit.text() or "").strip(),
            "invoice_type": "emitida",
            "invoice_category": self.invoice_kind_combo.currentText(),
            "client_name": self.client_name.text(),
            "client_rnc": self.client_rnc.text(),
            "currency": self.currency_combo.currentText(),
        }

        fn, _ = QFileDialog.getSaveFileName(self, "Guardar Factura como Excel", "", "Excel Files (*.xlsx)")
        if fn:
            save_path = fn if fn.endswith(".xlsx") else fn + ".xlsx"
            self._ensure_ncf_assigned_and_mark(company)
            generate_invoice_excel(data, items_for_export, save_path, company.get('name', ''))

    def _generate_invoice_pdf(self):
        company = self.get_current_company()
        if not company:
            QMessageBox.warning(self, "Empresa", "Seleccione una empresa válida")
            return

        items_for_export = []
        for r in range(self.invoice_items_table.rowCount()):
            desc = self.invoice_items_table.item(r, 2)
            qty = self.invoice_items_table.item(r, 4)
            price = self.invoice_items_table.item(r, 5)
            try:
                qty_val = float(qty.text().replace(",", "")) if qty and qty.text().strip() else 0.0
            except Exception:
                qty_val = 0.0
            try:
                price_val = float(price.text().replace(",", "")) if price and price.text().strip() else 0.0
            except Exception:
                price_val = 0.0
            items_for_export.append({"description": desc.text() if desc else "", "quantity": qty_val, "unit_price": price_val})

        data = {
            "company_id": int(company['id']),
            "invoice_date": self.invoice_date.date().toString("yyyy-MM-dd"),
            "invoice_number": (self.ncf_number_edit.text() or "").strip(),
            "invoice_type": "emitida",
            "invoice_category": self.invoice_kind_combo.currentText(),
            "client_name": self.client_name.text(),
            "client_rnc": self.client_rnc.text(),
            "currency": self.currency_combo.currentText(),
        }

        fn, _ = QFileDialog.getSaveFileName(self, "Guardar Factura como PDF", "", "PDF Files (*.pdf)")
        if not fn:
            return

        save_path = fn if fn.endswith(".pdf") else fn + ".pdf"
        # Ensure an NCF is assigned before generating/saving PDF
        try:
            self._ensure_ncf_assigned_and_mark(company)
        except Exception:
            pass

        self._ensure_ncf_assigned_and_mark(company)
        try:
            # Generar PDF localmente (template_integration delega al generador)
            export_invoice_pdf_with_template(data, items_for_export, save_path, company.get('name', ''))
        except Exception:
            # fallback al generador directo
            try:
                generate_invoice_pdf(data, items_for_export, save_path, company.get('name', ''))
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo generar el PDF:\n{e}")
                return

        # --- SUBIDA A FIREBASE STORAGE (si está disponible en backend) ---
        try:
            # Sanitizar nombre empresa para ruta
            company_name = (company.get('name') or '').strip()
            safe_company = ''.join(c for c in company_name if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_') or f"company_{company.get('id')}"
            ncf_or_num = (self.ncf_number_edit.text() or "").strip() or f"DRAFT-{dt.now().strftime('%Y%m%d%H%M%S')}"
            year = self.invoice_date.date().toString("yyyy")
            month = self.invoice_date.date().toString("MM")
            storage_path = f"factura/{safe_company}/{year}/{month}/{ncf_or_num}.pdf"

            upload_url = None
            # Hybrid wrapper o logic podría exponer upload_file_to_storage
            if hasattr(self.logic, "upload_file_to_storage"):
                upload_url = self.logic.upload_file_to_storage(save_path, storage_path)
            elif hasattr(self.logic, "data_access") and hasattr(self.logic.data_access, "upload_file_to_storage"):
                upload_url = self.logic.data_access.upload_file_to_storage(save_path, storage_path)

            expires_at = ""
            if upload_url:
                try:
                    import facot_config
                    days = int(getattr(facot_config, "PDF_SIGNED_URL_DAYS", 7) or 7)
                    days = min(days, 7)
                except Exception:
                    days = 7
                expires_at = (dt.utcnow() + timedelta(days=days)).isoformat()

            # Guardar metadata temporalmente en ambos atributos (compat)
            preview_meta = {
                "storage_path": storage_path,
                "url": upload_url,
                "company_id": int(company.get('id') or 0),
                "ncf_or_number": ncf_or_num,
                "expires_at": expires_at
            }
            self._preview_pdf_info = preview_meta
            self._preview_pdf_info_invoice = preview_meta

            if upload_url:
                print(f"[PDF-UPLOAD] tipo=factura storage_path={storage_path} url={upload_url}")
            else:
                print(f"[PDF-UPLOAD] Upload returned no url for {storage_path}")

        except Exception as e:
            print(f"[PDF-UPLOAD] ERROR during upload: {e}")
    # -------------------------
    # Utilidades numéricas / texto
    # -------------------------
    def _safe_float(self, txt: str, default: float = 0.0) -> float:
        try:
            return float((txt or "").replace(",", "").strip())
        except Exception:
            return default

    def _safe_text_attr(self, attr_name: str) -> str:
        w = getattr(self, attr_name, None)
        try:
            if w is None:
                return ""
            if hasattr(w, "text"):
                return (w.text() or "").strip()
            if hasattr(w, "toPlainText"):
                return (w.toPlainText() or "").strip()
        except Exception:
            pass
        return ""

    # -------------------------
    # Empresa / payload para preview
    # -------------------------
    def _company_display_address(self, details: Dict[str, Any], company_fallback: Dict[str, Any]) -> str:
        a1 = (details.get("address_line1") or company_fallback.get("address_line1") or "").strip()
        a2 = (details.get("address_line2") or company_fallback.get("address_line2") or "").strip()
        addr = (details.get("address") or company_fallback.get("address") or "").strip()
        if a1 or a2:
            parts = [p for p in [a1, a2] if p]
            return " ".join(parts)
        return addr or "Dirección no especificada"

    def _resolve_company_logo(self, company_id: AnyType, details: Dict[str, Any], company_fallback: Dict[str, Any]) -> str:
        cand = (details.get("logo_path") or company_fallback.get("logo_path") or "").strip()
        if not cand:
            logos = getattr(config_facot, "COMPANY_LOGOS", {}) or {}
            key_id = str(company_id) if company_id is not None else ""
            cand = logos.get(key_id) or logos.get(details.get("name") or company_fallback.get("name") or "", "")
        if not cand:
            cand = getattr(config_facot, "DEFAULT_LOGO_PATH", "") or ""
        return resolve_logo_uri(cand) or ""

    def _get_company_payload_for_preview(self):
        """
        Normaliza y devuelve (company_payload, tpl) para inyectar en InvoicePreviewDialog.
        Mejora:
        - Recupera detalles completos vía self.logic.get_company_details si hace falta.
        - Busca el nombre autorizado en múltiples claves posibles.
        - Intenta obtener invoice_due_date desde helpers del logic o desde el documento sequences/<id>_meta.
        - Aplica el invoice_due_date al widget usando _set_invoice_due_date_widget.
        """
        company_min = self.get_current_company() or {}
        company_id = company_min.get("id")
        if not company_id:
            print("[InvoiceTab] ERROR: No se pudo obtener company_id")
        details = {}
        try:
            if hasattr(self.logic, "get_company_details"):
                details = self.logic.get_company_details(company_id) or {}
            else:
                print("[InvoiceTab] ERROR: self.logic no tiene get_company_details")
        except Exception as e:
            print(f"[InvoiceTab] ERROR en get_company_details: {e}")
            details = {}

        # Merge: prefer details (detailed) but keep company_min fields as fallback
        merged = {**company_min, **(details or {})}

        # Normalize address
        a1 = (merged.get("address_line1") or "").strip()
        a2 = (merged.get("address_line2") or "").strip()
        addr = (merged.get("address") or "").strip()
        if a1 or a2:
            address_full = f"{a1} {a2}".strip()
        else:
            address_full = addr or "Dirección no especificada"

        # Resolve signature/authorized name robustly
        signature = ""
        for k in ("signature_name", "authorized_name", "firma", "signature", "authorized_signer", "authorized"):
            v = merged.get(k)
            if v and isinstance(v, str) and v.strip():
                signature = v.strip()
                break

        # Attempt to obtain invoice_due_date if missing from merged using helper methods on logic
        def _normalize_date(s):
            if not s:
                return ""
            try:
                s2 = str(s).strip()
                if len(s2) >= 10 and s2[4] == '-' and s2[7] == '-':
                    return s2[:10]
                from datetime import datetime
                d = datetime.fromisoformat(s2[:19])
                return d.strftime("%Y-%m-%d")
            except Exception:
                try:
                    parts = str(s2).replace("/", "-").split("-")
                    if len(parts) >= 3:
                        y, m, d = parts[0], parts[1], parts[2]
                        if len(y) == 4:
                            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
                except Exception:
                    pass
            return ""

        invoice_due = (merged.get("invoice_due_date") or "").strip()
        if not invoice_due:
            try:
                # try logic helper names
                for fn in ("get_company_due_date", "get_company_invoice_due_date", "get_company_due"):
                    try:
                        if hasattr(self.logic, fn):
                            val = getattr(self.logic, fn)(company_id)
                            vn = _normalize_date(val)
                            if vn:
                                invoice_due = vn
                                print(f"[InvoiceTab] Obtained invoice_due_date via {fn}: {vn}")
                                break
                    except Exception as e_fn:
                        print(f"[InvoiceTab] helper {fn} raised: {e_fn}")
                # fallback: try sequences/<id>_meta in data_access if available
                try:
                    da = getattr(self.logic, "data_access", None) or self.logic
                    if da and hasattr(da, "db"):
                        mid = f"{company_id}_meta"
                        try:
                            doc = da.db.collection("sequences").document(mid).get()
                            if doc and getattr(doc, "exists", False):
                                dd = doc.to_dict() or {}
                                v2 = dd.get("invoice_due_date") or dd.get("due_date") or ""
                                v2n = _normalize_date(v2)
                                if v2n:
                                    invoice_due = v2n
                                    print(f"[InvoiceTab] Obtained invoice_due_date from sequences/{mid}: {v2n}")
                        except Exception as e_doc:
                            print(f"[InvoiceTab] sequences meta check failed: {e_doc}")
                except Exception:
                    pass
            except Exception:
                pass

        # Logo relative path (as stored)
        logo_rel = (merged.get("logo_path") or "").strip()

        payload = {
            "id": company_id,
            "name": merged.get("name") or company_min.get("name", ""),
            "rnc": merged.get("rnc") or merged.get("rnc_number") or company_min.get("rnc", ""),
            "address_line1": a1,
            "address_line2": a2,
            "address": address_full,
            "phone": merged.get("phone") or merged.get("telefono") or company_min.get("phone", ""),
            "email": merged.get("email") or merged.get("correo") or company_min.get("email", ""),
            "signature_name": signature,
            "authorized_name": signature,
            "logo_path": logo_rel,
            "invoice_due_date": invoice_due or ""
        }

        # Apply the invoice due date to the widget so that UI and preview will be consistent
        try:
            self._set_invoice_due_date_widget(payload.get("invoice_due_date") or "")
        except Exception:
            pass

        tpl = {}
        try:
            tpl = load_template(int(company_id)) or {}
        except Exception as e:
            print(f"[InvoiceTab] ERROR al cargar template: {e}")
            tpl = {}

        print(f"[InvoiceTab] company_payload_for_preview FINAL: {payload}")
        return payload, tpl

    # -------------------------
    # Guardar factura
    # -------------------------
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

    def _save_invoice(self):
        """Guarda la factura asegurando NCF, vencimiento, moneda, terceros y metadata de PDF."""
        company = self.get_current_company()
        if not company:
            QMessageBox.warning(self, "Empresa", "Seleccione una empresa.")
            return

        # 1) ASEGURAR NCF (consumo real)
        try:
            current_ncf = self._ensure_ncf_assigned_and_mark(company) or (self.ncf_number_edit.text() or "").strip().upper()
        except Exception as e:
            print(f"[SAVE] Error allocating NCF: {e}")
            current_ncf = (self.ncf_number_edit.text() or "").strip().upper()

        # 2) RECOLECTAR ITEMS Y TOTALES
        items = self._collect_items_for_export()
        if not items:
            QMessageBox.warning(self, "Ítems", "Agrega al menos un ítem antes de guardar.")
            return

        subtotal = 0.0
        for it in items:
            try:
                subtotal += float(it.get("unit_price", 0) or 0) * float(it.get("quantity", 0) or 0)
            except Exception:
                pass
        itbis = subtotal * ITBIS_RATE if getattr(self, "apply_itbis_checkbox", None) and self.apply_itbis_checkbox.isChecked() else 0.0
        total = subtotal + itbis

        # 3) LEER METADATA DEL PREVIEW (si existe)
        pdf_meta = getattr(self, "_preview_pdf_info", {}) or {}

        # 4) NORMALIZAR MONEDA + TASA
        currency = (self.currency_combo.currentText() or "").strip() or DEFAULT_CURRENCY
        try:
            exchange_rate = float((self.exchange_rate_edit.text() or "1").replace(",", "").strip() or 1.0)
        except Exception:
            exchange_rate = 1.0

        # 5) CONSTRUIR PAYLOAD (asegurar keys esperadas por backend FACTURAS-PyQT6-GIT)
        invoice_date_str = self.invoice_date.date().toString("yyyy-MM-dd")
        imputation_date = invoice_date_str
        ncf_current = current_ncf or ""
        invoice_category = self.invoice_kind_combo.currentText() or ""
        if not invoice_category:
            invoice_category = _derive_invoice_category_from_ncf(ncf_current) or ""

        total_amount_rd = round(total * exchange_rate, 2)

        invoice_payload = {
            "company_id": int(company.get("id") or 0),

            # Compatibilidad FACTURAS-PyQT6-GIT
            "invoice_type": "emitida",
            "invoice_date": invoice_date_str,
            "imputation_date": imputation_date,
            "invoice_number": ncf_current,
            "invoice_category": invoice_category,
            "rnc": (self.client_rnc.text() or "").strip(),
            "third_party_name": (self.client_name.text() or "").strip(),
            "currency": currency,
            "itbis": round(itbis, 2),
            "total_amount": round(total, 2),
            "exchange_rate": exchange_rate,
            "total_amount_rd": total_amount_rd,
            "attachment_path": None,

            # Legacy / compat local
            "ncf": ncf_current,
            "due_date": self.invoice_due_date.date().toString("yyyy-MM-dd"),
            "client_name": (self.client_name.text() or "").strip(),  # espejo legacy
            "client_rnc": (self.client_rnc.text() or "").strip(),    # espejo legacy
            "subtotal": round(subtotal, 2),
            "items": items,
            "type": "emitida",
            "notes": "",

            # metadata del preview PDF (si existe)
            "pdf_storage_path": pdf_meta.get("storage_path", ""),
            "pdf_url": pdf_meta.get("url", ""),
            "pdf_expires_at": pdf_meta.get("expires_at", "")
        }

        # 5b) Registrar/actualizar el tercero en la colección third_parties
        rnc_val = (self.client_rnc.text() or "").strip()
        tp_name = (self.client_name.text() or "").strip()
        try:
            if rnc_val and tp_name and hasattr(self.logic, "add_or_update_third_party"):
                self.logic.add_or_update_third_party(rnc=rnc_val, name=tp_name)
        except Exception as e:
            print(f"[WARN] No se pudo registrar/actualizar tercero: {e}")

        # Debug: imprimir payload antes de guardar
        try:
            import json
            print("[INV-PAYLOAD] Final payload before add_invoice:", json.dumps(invoice_payload, ensure_ascii=False))
        except Exception:
            print("[INV-PAYLOAD] Final payload (non-serializable) ->", invoice_payload)

        # 6) LLAMAR AL BACKEND (add_invoice)
        try:
            if not hasattr(self.logic, "add_invoice"):
                QMessageBox.critical(self, "Error", "Método add_invoice no encontrado en logic.")
                return

            try:
                result = self.logic.add_invoice(invoice_payload, items)
            except TypeError:
                result = self.logic.add_invoice(invoice_payload)

            print("[INV-SAVE] add_invoice returned:", repr(result))

            # 7) EXTRAER invoice_id robustamente
            invoice_id = None
            try:
                if result is None:
                    invoice_id = None
                elif isinstance(result, (int, str)):
                    invoice_id = result
                elif isinstance(result, dict):
                    for k in ("id", "invoice_id", "doc_id", "inserted_id", "name"):
                        if k in result and result[k]:
                            invoice_id = result[k]
                            break
                    if invoice_id is None and result.get("success") and (result.get("id") or result.get("invoice_id")):
                        invoice_id = result.get("id") or result.get("invoice_id")
                    if invoice_id is None and len(result) == 1:
                        val = next(iter(result.values()))
                        if isinstance(val, (int, str)):
                            invoice_id = val
                else:
                    invoice_id = str(result)
            except Exception as e:
                print("[INV-SAVE] Error extrayendo invoice_id:", e)
                invoice_id = None

            # 8) PERSISTIR METADATA DEL PDF (si existe)
            if pdf_meta.get("url") and invoice_id:
                try:
                    if hasattr(self.logic, "set_invoice_pdf_info"):
                        try:
                            self.logic.set_invoice_pdf_info(invoice_id, pdf_meta.get("storage_path"), pdf_meta.get("url"), expires_at=pdf_meta.get("expires_at"))
                        except TypeError:
                            self.logic.set_invoice_pdf_info(invoice_id, pdf_meta.get("storage_path"), pdf_meta.get("url"))
                    elif hasattr(self.logic, "data_access") and hasattr(self.logic.data_access, "set_invoice_pdf_info"):
                        try:
                            self.logic.data_access.set_invoice_pdf_info(invoice_id, pdf_meta.get("storage_path"), pdf_meta.get("url"), expires_at=pdf_meta.get("expires_at"))
                        except TypeError:
                            self.logic.data_access.set_invoice_pdf_info(invoice_id, pdf_meta.get("storage_path"), pdf_meta.get("url"))
                    print(f"[INV-SAVE] Persisted PDF metadata for invoice_id={invoice_id}")
                except Exception as e:
                    print(f"[INV-SAVE] Error persisting pdf metadata: {e}")

            # 9) Mensaje final y limpieza
            try:
                display_id = invoice_id if invoice_id is not None else repr(result)
                QMessageBox.information(self, "Guardado", f"Factura {current_ncf} guardada (ID: {display_id}).")
            except Exception:
                pass

            try:
                self._clear_invoice_form()
                self._update_ncf_sequence()
                self._preview_pdf_info = None
                self._preview_pdf_info_invoice = None
            except Exception:
                pass

            try:
                if invoice_id is not None:
                    try:
                        iid = int(invoice_id)
                        self.invoice_saved.emit(iid)
                    except Exception:
                        pass
            except Exception:
                pass

        except Exception as e:
            logger.exception("Save failed")
            QMessageBox.critical(self, "Error", f"Error al guardar: {e}")


    def _set_invoice_due_date_widget(self, date_str):
        """Helper para actualizar el widget de fecha sin errores."""
        if not date_str: return
        try:
            from PyQt6.QtCore import QDate
            d = QDate.fromString(date_str[:10], "yyyy-MM-dd")
            if d.isValid():
                self.invoice_due_date.setDate(d)
        except: pass

    def _clear_invoice_form(self):
        try:
            self.invoice_date.setDate(QDate.currentDate())
            self.invoice_due_date.setDate(QDate.currentDate())
            self.ncf_number_edit.clear()
            self.client_rnc.clear(); self.client_name.clear()
            self.currency_combo.setCurrentText(DEFAULT_CURRENCY)
            self.exchange_rate_edit.setText("1.00"); self.exchange_rate_edit.setVisible(False)
            self.invoice_items_table.setRowCount(0)
            self.subtotal_label.setText("Subtotal: RD$ 0.00")
            self.itbis_label.setText("ITBIS: RD$ 0.00")
            self.total_label.setText("Total: RD$ 0.00")
        except Exception:
            pass
    
    def load_invoice_by_id(self, invoice_id: int):
        """
        Load an existing invoice into the form for editing.
        
        Args:
            invoice_id: ID of the invoice to load
        """
        try:
            # Get invoice data
            invoice = None
            if hasattr(self.logic, 'get_invoice_by_id'):
                invoice = self.logic.get_invoice_by_id(invoice_id)
            else:
                # Fallback: search in get_facturas
                company = self.get_current_company()
                if company and hasattr(self.logic, 'get_facturas'):
                    facturas = self.logic.get_facturas(company['id'])
                    for f in facturas:
                        if f.get('id') == invoice_id or str(f.get('id')) == str(invoice_id):
                            invoice = f
                            break
            
            if not invoice:
                QMessageBox.warning(self, "Error", f"No se encontró la factura con ID: {invoice_id}")
                return
            
            # Clear form first
            self._clear_invoice_form()
            
            # Load header data
            # Date
            date_str = invoice.get('invoice_date', '')
            if date_str:
                try:
                    from datetime import datetime
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    self.invoice_date.setDate(QDate(date_obj.year, date_obj.month, date_obj.day))
                except Exception:
                    pass
            
            # NCF
            ncf = invoice.get('invoice_number', '') or invoice.get('ncf', '')
            self.ncf_number_edit.setText(ncf)
            
            # Category
            category = invoice.get('invoice_category', '')
            if category:
                index = self.invoice_kind_combo.findText(category)
                if index >= 0:
                    self.invoice_kind_combo.setCurrentIndex(index)
            
            # Client data
            self.client_name.setText(invoice.get('third_party_name', '') or invoice.get('client_name', ''))
            self.client_rnc.setText(invoice.get('rnc', '') or invoice.get('client_rnc', ''))
            
            # Currency
            currency = invoice.get('currency', 'RD$')
            index = self.currency_combo.findText(currency)
            if index >= 0:
                self.currency_combo.setCurrentIndex(index)
            
            # Exchange rate
            exchange_rate = invoice.get('exchange_rate', 1.0) or 1.0
            self.exchange_rate_edit.setText(str(exchange_rate))
            if currency != 'RD$':
                self.exchange_rate_edit.setVisible(True)
            
            # Load items
            items = []
            if hasattr(self.logic, 'get_invoice_items'):
                items = self.logic.get_invoice_items(invoice_id)
            
            # Populate items table
            self.invoice_items_table.setRowCount(0)
            for item in items:
                code = item.get('item_code', item.get('code', ''))
                name = item.get('description', item.get('name', ''))
                unit = item.get('unit', 'UND')
                qty = item.get('quantity', 0.0)
                price = item.get('unit_price', item.get('price', 0.0))
                subtotal = qty * price
                self._append_row(code, name, unit, qty, price, subtotal)
            
            # Recalculate totals
            self._recalculate_invoice_totals()
            
            QMessageBox.information(self, "Cargar Factura", f"Factura ID: {invoice_id} cargada para edición")
            
        except Exception as e:
            logger.exception("Error al cargar factura: %s", e)
            QMessageBox.critical(self, "Error", f"No se pudo cargar la factura:\n{str(e)}")

    # -------------------------
    # Direcciones / vencimiento fijo
    # -------------------------
    def _compute_invoice_due_date(self, company_payload: dict, invoice_date_str: str) -> str:
        due = (company_payload or {}).get("invoice_due_date") or ""
        return (due or "").strip()

    def _set_invoice_due_date_widget(self, due_str: str) -> None:
        try:
            if not due_str: return
            y, m, d = [int(x) for x in due_str[:10].split("-")]
            self.invoice_due_date.setDate(QDate(y, m, d))
            print(f"[ITAB-DUE] Prefill widget invoice_due_date <- {due_str}")
        except Exception as e:
            print(f"[ITAB-DUE] error prefill widget: {e}")

    # -------------------------
    # Empresa / plantillas / gestión
    # -------------------------
    def _on_edit_template(self):
        """
        Abre CompanyManagementWindow para editar empresa/branding.
        Se retira TemplateEditorDialog (deprecated).
        """
        company = None
        try: company = self.get_current_company()
        except Exception: pass
        if not company:
            QMessageBox.warning(self, "Branding", "Seleccione primero una empresa válida.")
            return

        company_id = (company.get("id") or company.get("company_id") or company.get("pk"))
        if not company_id:
            QMessageBox.warning(self, "Branding", "Empresa sin identificador."); return

        if CompanyManagementWindow:
            try:
                dlg = CompanyManagementWindow(parent=self, logic_controller=self.logic)
                # Pre-seleccionar la empresa actual
                try:
                    dlg.selected_company_id = int(company_id)
                    if hasattr(dlg, '_load_companies'):
                        dlg._load_companies()
                    for row in range(dlg.company_table.rowCount()):
                        if dlg._companies_cache and row < len(dlg._companies_cache):
                            if dlg._companies_cache[row].get('id') == int(company_id):
                                dlg.company_table.selectRow(row)
                                dlg._on_select(row, 0)
                                break
                except Exception as e:
                    print(f"[ITAB] Error pre-selecting company in CompanyManagementWindow: {e}")

                dlg.exec()
                # Refresh after editing
                self._notify_companies_changed()
                try: self.on_company_change()
                except Exception: self._update_ncf_sequence()
                return
            except Exception as e:
                print(f"[ITAB] Error opening CompanyManagementWindow: {e}")
                QMessageBox.critical(self, "Branding", f"No se pudo abrir gestión de empresas:\n{e}")
        else:
            QMessageBox.warning(self, "Branding", "CompanyManagementWindow no disponible.")

    def _open_company_manager(self):
        if CompanyManagementWindow is None:
            QMessageBox.warning(self, "Empresas", "No se encontró CompanyManagementWindow."); return
        try:
            dlg = CompanyManagementWindow(parent=self, logic_controller=self.logic)
            dlg.exec()
        except TypeError:
            try:
                dlg = CompanyManagementWindow(self, self.logic); dlg.exec()
            except Exception as e:
                QMessageBox.critical(self, "Empresas", f"No se pudo abrir gestión de empresas:\n{e}")
                return
        except Exception as e:
            QMessageBox.critical(self, "Empresas", f"No se pudo abrir gestión de empresas:\n{e}")
            return
        self._notify_companies_changed()
        try: self.on_company_change()
        except Exception: self._update_ncf_sequence()

    def _notify_companies_changed(self):
        p = self.parent(); safety = 0
        while p is not None and safety < 12:
            if hasattr(p, "_populate_companies"):
                try: p._populate_companies()
                except Exception: pass
                break
            p = p.parent(); safety += 1

    def refresh_company_due_date(self):
        """Lee el vencimiento fijo desde backend y lo aplica al widget con logs."""
        try:
            company = self.get_current_company()
            if not company:
                return
            cid = int(company.get('id'))
            due = ""
            # Preferir métodos dedicados si existen: LogicController ya delega al backend
            if hasattr(self.logic, "get_company_due_date"):
                due = self.logic.get_company_due_date(cid) or ""
            elif hasattr(self.logic, "get_company_invoice_due_date"):
                due = self.logic.get_company_invoice_due_date(cid) or ""
            # Aplica al widget
            if due:
                self._set_invoice_due_date_widget(due)
            else:
                # Si está vacío, deja la fecha según la política actual
                # o limpia explícitamente si prefieres
                # self.invoice_due_date.setDate(QDate.currentDate())
                pass
            print(f"[ITAB-DUE] Refresh from backend for company_id={cid} -> {due or '(empty)'}")
        except Exception as e:
            print(f"[ITAB-DUE] Error refreshing due date: {e}")

    def refresh_after_ncf_config(self):
        """
        Refresca datos sensibles tras cerrar/guardar NCFConfigDialog:
        - NCF preview para la empresa seleccionada
        - Vencimiento fijo (invoice_due_date) leído desde backend
        """
        try:
            self._update_ncf_sequence()
        except Exception as e:
            print(f"[ITAB] Error refreshing NCF after config: {e}")
        try:
            self.refresh_company_due_date()
        except Exception as e:
            print(f"[ITAB] Error refreshing due date after config: {e}")

    def on_company_change(self):
        try: self.suggestion_combo.hide()
        except Exception: pass
        self._clear_invoice_form()
        self._apply_default_due_date()
        # Primero trae vencimiento fijo desde backend y lo aplica
        try:
            self.refresh_company_due_date()
        except Exception:
            pass
        # Luego actualiza secuencia NCF
        self._update_ncf_sequence()



