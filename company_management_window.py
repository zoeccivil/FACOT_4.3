from __future__ import annotations

from typing import Dict, Any, Optional, List
import os
import re

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QLabel,
    QLineEdit, QPushButton, QFileDialog, QMessageBox, QWidget, QHeaderView, QDateEdit, QTextEdit, QTabWidget, QColorDialog
)
from PyQt6.QtCore import QDate, Qt

# Asegúrate de que este import funcione en tu estructura de carpetas
from utils.asset_paths import copy_logo_to_assets, relativize_if_under_assets

HEX_RE = re.compile(r"^#([0-9A-Fa-f]{6})$")

def _is_hex_color(s: str) -> bool:
    return bool(HEX_RE.match((s or "").strip()))

def _qcolor_to_hex(color) -> str:
    try:
        r = color.red()
        g = color.green()
        b = color.blue()
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return "#000000"

class CompanyManagementWindow(QDialog):
    """
    Ventana para gestionar empresas y branding (Opción A).
    Incluye color pickers para primary_color y secondary_color,
    subida de logo a Storage (URL pública) con fallback a assets.
    """

    SMALL_LINEHEIGHT = 24

    def __init__(self, parent, logic_controller):
        super().__init__(parent)
        self.setWindowTitle("Gestionar Empresas")
        self.resize(1000, 680)

        self.logic = logic_controller

        self.selected_company_id: Optional[int] = None
        self._pending_logo_source_abs: Optional[str] = None
        self._companies_cache: List[Dict[str, Any]] = []

        self._build_ui()
        self._load_companies()

    @staticmethod
    def _norm_full(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": row.get("id"),
            "name": row.get("name", ""),
            "rnc": row.get("rnc") or row.get("rnc_number", "") or "",
            "address_line1": row.get("address_line1") or row.get("address", "") or "",
            "address_line2": row.get("address_line2", "") or "",
            "phone": row.get("phone") or row.get("telefono", "") or "",
            "email": row.get("email") or row.get("correo") or "",
            "signature_name": row.get("signature_name", "") or row.get("authorized_name", "") or "",
            "logo_path": row.get("logo_path", "") or "",
            "invoice_due_date": row.get("invoice_due_date", "") or "",
            "primary_color": row.get("primary_color") or "#0087C3",
            "secondary_color": row.get("secondary_color") or "#F5F5F5",
            "font_name": row.get("font_name") or "Inter",
            "font_size": row.get("font_size") or 13,
            "layout": row.get("layout") or "default",
            "header_lines": row.get("header_lines") or ["", "", ""],
            "footer_lines": row.get("footer_lines") or [],
            "show_logo": True if row.get("show_logo") is None else bool(row.get("show_logo")),
        }

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)

        table_frame = QWidget()
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self.company_table = QTableWidget(0, 4)
        self.company_table.setHorizontalHeaderLabels(["Nombre de la Empresa", "RNC", "Teléfono", "Email"])
        header = self.company_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.company_table.verticalHeader().setVisible(False)
        self.company_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.company_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.company_table.cellClicked.connect(self._on_select)
        self.company_table.setStyleSheet("QTableWidget::item { padding: 4px 6px; }")
        table_layout.addWidget(self.company_table)
        main_layout.addWidget(table_frame, stretch=2)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, stretch=1)

        form_frame = QWidget()
        form_layout = QVBoxLayout(form_frame)
        form_layout.setSpacing(6)
        form_layout.setContentsMargins(4, 4, 4, 4)

        def compact_lineedit(placeholder: str = "") -> QLineEdit:
            le = QLineEdit()
            if placeholder:
                le.setPlaceholderText(placeholder)
            le.setMinimumHeight(self.SMALL_LINEHEIGHT)
            le.setMaximumHeight(self.SMALL_LINEHEIGHT + 2)
            return le

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Nombre:"))
        self.name_edit = compact_lineedit()
        row1.addWidget(self.name_edit, stretch=3)
        row1.addWidget(QLabel("RNC:"))
        self.rnc_edit = compact_lineedit()
        row1.addWidget(self.rnc_edit, stretch=1)
        form_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Dirección 1:"))
        self.address1_edit = compact_lineedit()
        row2.addWidget(self.address1_edit, stretch=3)
        row2.addWidget(QLabel("Dirección 2:"))
        self.address2_edit = compact_lineedit()
        row2.addWidget(self.address2_edit, stretch=2)
        form_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Teléfono:"))
        self.phone_edit = compact_lineedit()
        row3.addWidget(self.phone_edit, stretch=1)
        row3.addWidget(QLabel("Email:"))
        self.email_edit = compact_lineedit()
        row3.addWidget(self.email_edit, stretch=2)
        form_layout.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Firma autorizada (nombre):"))
        self.signature_edit = compact_lineedit()
        row4.addWidget(self.signature_edit, stretch=3)
        form_layout.addLayout(row4)

        row6 = QHBoxLayout()
        row6.addWidget(QLabel("Vencimiento fijo facturas:"))
        self.invoice_due_date_edit = QDateEdit()
        self.invoice_due_date_edit.setCalendarPopup(True)
        self.invoice_due_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.invoice_due_date_edit.setMinimumHeight(self.SMALL_LINEHEIGHT + 2)
        self.invoice_due_date_edit.setDate(QDate.currentDate())
        row6.addWidget(self.invoice_due_date_edit, stretch=1)
        btn_clear_due = QPushButton("Limpiar")
        btn_clear_due.setMinimumHeight(self.SMALL_LINEHEIGHT + 4)
        btn_clear_due.setToolTip("Deja el vencimiento vacío (N/A)")
        btn_clear_due.clicked.connect(lambda: self.invoice_due_date_edit.setDate(QDate.currentDate()))
        row6.addWidget(btn_clear_due)
        form_layout.addLayout(row6)

        self.tabs.addTab(form_frame, "Datos")

        brand_frame = QWidget()
        brand_layout = QVBoxLayout(brand_frame)
        brand_layout.setSpacing(6)
        brand_layout.setContentsMargins(4, 4, 4, 4)

        row_logo = QHBoxLayout()
        row_logo.addWidget(QLabel("Logo (URL pública):"))
        self.logo_path_edit = compact_lineedit()
        row_logo.addWidget(self.logo_path_edit, stretch=3)
        btn_logo = QPushButton("Elegir logo…")
        btn_logo.setMinimumHeight(self.SMALL_LINEHEIGHT + 4)
        btn_logo.clicked.connect(self._browse_logo)
        row_logo.addWidget(btn_logo)
        brand_layout.addLayout(row_logo)

        # Color primario con picker
        row_colors1 = QHBoxLayout()
        row_colors1.addWidget(QLabel("Color Primario (#RRGGBB):"))
        self.primary_color_edit = compact_lineedit("#0087C3")
        row_colors1.addWidget(self.primary_color_edit, stretch=1)
        btn_pick_primary = QPushButton("Elegir color…")
        btn_pick_primary.clicked.connect(lambda: self._pick_color(self.primary_color_edit))
        row_colors1.addWidget(btn_pick_primary)
        brand_layout.addLayout(row_colors1)

        # Color secundario con picker
        row_colors2 = QHBoxLayout()
        row_colors2.addWidget(QLabel("Color Secundario (#RRGGBB):"))
        self.secondary_color_edit = compact_lineedit("#F5F5F5")
        row_colors2.addWidget(self.secondary_color_edit, stretch=1)
        btn_pick_secondary = QPushButton("Elegir color…")
        btn_pick_secondary.clicked.connect(lambda: self._pick_color(self.secondary_color_edit))
        row_colors2.addWidget(btn_pick_secondary)
        brand_layout.addLayout(row_colors2)

        row_font = QHBoxLayout()
        row_font.addWidget(QLabel("Fuente:"))
        self.font_name_edit = compact_lineedit("Inter")
        row_font.addWidget(self.font_name_edit, stretch=1)
        row_font.addWidget(QLabel("Tamaño:"))
        self.font_size_edit = compact_lineedit("13")
        row_font.addWidget(self.font_size_edit, stretch=1)
        brand_layout.addLayout(row_font)

        row_layout = QHBoxLayout()
        row_layout.addWidget(QLabel("Layout:"))
        self.layout_edit = compact_lineedit("default")
        row_layout.addWidget(self.layout_edit, stretch=1)
        brand_layout.addLayout(row_layout)

        brand_layout.addWidget(QLabel("Encabezado (3 líneas):"))
        self.header1_edit = compact_lineedit()
        self.header2_edit = compact_lineedit()
        self.header3_edit = compact_lineedit()
        brand_layout.addWidget(self.header1_edit)
        brand_layout.addWidget(self.header2_edit)
        brand_layout.addWidget(self.header3_edit)

        brand_layout.addWidget(QLabel("Footer (múltiples líneas):"))
        self.footer_lines_edit = QTextEdit()
        self.footer_lines_edit.setFixedHeight(90)
        brand_layout.addWidget(self.footer_lines_edit)

        self.tabs.addTab(brand_frame, "Branding")

        btns = QHBoxLayout()
        btn_new = QPushButton("Nuevo")
        btn_new.setMinimumHeight(self.SMALL_LINEHEIGHT + 6)
        btn_new.clicked.connect(self._clear_fields)
        btns.addWidget(btn_new)

        btn_save = QPushButton("Guardar Cambios")
        btn_save.setMinimumHeight(self.SMALL_LINEHEIGHT + 6)
        btn_save.clicked.connect(self._save_company)
        btns.addWidget(btn_save)

        btn_del = QPushButton("Eliminar Empresa")
        btn_del.setMinimumHeight(self.SMALL_LINEHEIGHT + 6)
        btn_del.clicked.connect(self._delete_company)
        btns.addWidget(btn_del)

        main_layout.addLayout(btns)

    def _pick_color(self, target_line_edit: QLineEdit):
        """
        Abre QColorDialog y asigna el color seleccionado en formato #RRGGBB.
        """
        try:
            initial = target_line_edit.text().strip()
            if not _is_hex_color(initial):
                initial = "#FFFFFF"
            color = QColorDialog.getColor()
            if color and color.isValid():
                hexv = _qcolor_to_hex(color)
                target_line_edit.setText(hexv)
        except Exception as e:
            QMessageBox.warning(self, "Color", f"No se pudo abrir el selector de color:\n{e}")

    def _load_companies(self):
        self.company_table.setRowCount(0)
        if not hasattr(self.logic, "get_all_companies"):
            QMessageBox.critical(self, "Error", "El backend no tiene el método get_all_companies")
            return
        try:
            raw = self.logic.get_all_companies() or []
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al cargar empresas de Firebase:\n{e}")
            raw = []
        self._companies_cache = raw[:]
        for row, c in enumerate(self._companies_cache):
            name = c.get("name", "")
            rnc = c.get("rnc") or c.get("rnc_number", "")
            phone = c.get("phone") or c.get("telefono", "")
            email = c.get("email") or c.get("correo", "")
            self.company_table.insertRow(row)
            self.company_table.setItem(row, 0, QTableWidgetItem(str(name)))
            self.company_table.setItem(row, 1, QTableWidgetItem(str(rnc)))
            self.company_table.setItem(row, 2, QTableWidgetItem(str(phone)))
            self.company_table.setItem(row, 3, QTableWidgetItem(str(email)))
            self.company_table.setRowHeight(row, 22)

    def _on_select(self, row, _column):
        if row < 0 or row >= len(self._companies_cache):
            return
        cid = self._companies_cache[row].get("id")
        if not cid:
            return
        self.selected_company_id = cid
        try:
            det_raw = self.logic.get_company_details(int(cid)) or {}
        except Exception:
            det_raw = self._companies_cache[row]
        det = self._norm_full(det_raw)
        self.name_edit.setText(str(det["name"]))
        self.rnc_edit.setText(str(det["rnc"]))
        self.address1_edit.setText(str(det["address_line1"]))
        self.address2_edit.setText(str(det["address_line2"]))
        self.phone_edit.setText(str(det["phone"]))
        self.email_edit.setText(str(det["email"]))
        self.signature_edit.setText(str(det["signature_name"]))
        self._set_due_date_from_str(det.get("invoice_due_date") or "")
        self.logo_path_edit.setText(str(det["logo_path"]))
        self.primary_color_edit.setText(str(det["primary_color"]))
        self.secondary_color_edit.setText(str(det["secondary_color"]))
        self.font_name_edit.setText(str(det["font_name"]))
        self.font_size_edit.setText(str(det["font_size"]))
        self.layout_edit.setText(str(det["layout"]))
        hl = det.get("header_lines") or ["", "", ""]
        self.header1_edit.setText(hl[0] if len(hl) > 0 else "")
        self.header2_edit.setText(hl[1] if len(hl) > 1 else "")
        self.header3_edit.setText(hl[2] if len(hl) > 2 else "")
        self.footer_lines_edit.setPlainText("\n".join(det.get("footer_lines") or []))

    def _clear_fields(self):
        self.selected_company_id = None
        self._pending_logo_source_abs = None
        self.name_edit.clear()
        self.rnc_edit.clear()
        self.address1_edit.clear()
        self.address2_edit.clear()
        self.phone_edit.clear()
        self.email_edit.clear()
        self.signature_edit.clear()
        self.invoice_due_date_edit.setDate(QDate.currentDate())
        self.logo_path_edit.clear()
        self.primary_color_edit.setText("#0087C3")
        self.secondary_color_edit.setText("#F5F5F5")
        self.font_name_edit.setText("Inter")
        self.font_size_edit.setText("13")
        self.layout_edit.setText("default")
        self.header1_edit.clear(); self.header2_edit.clear(); self.header3_edit.clear()
        self.footer_lines_edit.clear()
        self.company_table.clearSelection()
        self.name_edit.setFocus()

    def _save_company(self):
        name = self.name_edit.text().strip()
        rnc = self.rnc_edit.text().strip()
        if not name or not rnc:
            QMessageBox.critical(self, "Error", "El Nombre y el RNC son obligatorios.")
            return

        address1 = self.address1_edit.text().strip()
        address2 = self.address2_edit.text().strip()
        phone = self.phone_edit.text().strip()
        email = self.email_edit.text().strip()
        signature_name = self.signature_edit.text().strip()
        fixed_due_date = self._dateedit_to_str(self.invoice_due_date_edit)

        logo_val = self.logo_path_edit.text().strip()
        primary_color = self.primary_color_edit.text().strip() or "#0087C3"
        secondary_color = self.secondary_color_edit.text().strip() or "#F5F5F5"
        font_name = self.font_name_edit.text().strip() or "Inter"
        font_size_txt = self.font_size_edit.text().strip() or "13"
        layout_val = self.layout_edit.text().strip() or "default"
        header_lines = [self.header1_edit.text().strip(), self.header2_edit.text().strip(), self.header3_edit.text().strip()]
        footer_lines = [l.strip() for l in (self.footer_lines_edit.toPlainText().splitlines()) if l.strip()]

        if not _is_hex_color(primary_color):
            QMessageBox.warning(self, "Color", "Color Primario inválido (#RRGGBB). Se mantendrá #0087C3.")
            primary_color = "#0087C3"
        if not _is_hex_color(secondary_color):
            QMessageBox.warning(self, "Color", "Color Secundario inválido (#RRGGBB). Se mantendrá #F5F5F5.")
            secondary_color = "#F5F5F5"

        try:
            font_size = int(font_size_txt)
        except Exception:
            font_size = 13

        is_new = self.selected_company_id is None

        try:
            if is_new:
                new_id = self.logic.add_company(name, rnc, address1)
                self.selected_company_id = new_id
                cid = new_id
            else:
                cid = int(self.selected_company_id)

            logo_public_or_rel = self._prepare_logo_to_save(logo_val, cid)

            payload = {
                "name": name,
                "rnc": rnc,
                "address_line1": address1,
                "address": address1,
                "address_line2": address2,
                "phone": phone,
                "email": email,
                "signature_name": signature_name,
                "invoice_due_date": fixed_due_date,
                "logo_path": logo_public_or_rel,
                "primary_color": primary_color,
                "secondary_color": secondary_color,
                "font_name": font_name,
                "font_size": font_size,
                "layout": layout_val,
                "header_lines": header_lines,
                "footer_lines": footer_lines,
                "show_logo": bool(logo_public_or_rel),
            }

            self.logic.update_company_fields(cid, payload)

            QMessageBox.information(self, "Éxito", "Empresa y branding guardados correctamente.")
            self._load_companies()
            self._reselect_by_id(cid)
            if hasattr(self.parent(), "_populate_companies"):
                try:
                    self.parent()._populate_companies()
                except Exception:
                    pass

        except Exception as e:
            QMessageBox.critical(self, "Error al guardar", f"Ocurrió un error:\n{e}")

    def _delete_company(self):
        if not self.selected_company_id:
            QMessageBox.warning(self, "Sin Selección", "Selecciona una empresa para eliminar.")
            return
        confirm = QMessageBox.question(
            self, "Confirmar",
            "¿Seguro que deseas eliminar esta empresa?\nEsta acción no se puede deshacer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            if hasattr(self.logic, "delete_company"):
                success, msg = self.logic.delete_company(self.selected_company_id)
                if success:
                    QMessageBox.information(self, "Eliminado", "Empresa eliminada.")
                    self._clear_fields()
                    self._load_companies()
                else:
                    QMessageBox.warning(self, "Error", f"No se pudo eliminar: {msg}")
            else:
                QMessageBox.critical(self, "Error", "El backend no soporta eliminación de empresas.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error técnico al eliminar:\n{e}")

    def _browse_logo(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Seleccionar Logo", "", "Imágenes (*.png *.jpg *.jpeg *.svg);;Todos los archivos (*)")
        if not fn:
            return
        print(f"[COMPANY-LOGO] Selected logo file: {fn}")
        if self.selected_company_id:
            try:
                cid = int(self.selected_company_id)
                ext = os.path.splitext(fn)[1].lower() or ".png"
                storage_path = f"logos/company_{cid}{ext}"

                url = None
                # Asegura que logic tiene upload_file_to_storage
                logic = self.logic
                if hasattr(logic, 'upload_file_to_storage'):
                    try:
                        url = logic.upload_file_to_storage(fn, storage_path)
                        if url:
                            print(f"[COMPANY-LOGO] Uploaded to storage: {url}")
                            self.logo_path_edit.setText(url)
                            QMessageBox.information(self, "Logo", f"Logo subido al storage.\n\nURL: {url}")
                            return
                        else:
                            print(f"[COMPANY-LOGO] upload_file_to_storage returned None, falling back")
                    except Exception as e:
                        print(f"[COMPANY-LOGO] upload_file_to_storage failed: {e}, falling back")
                else:
                    print("[COMPANY-LOGO] LogicController no tiene upload_file_to_storage (modo incorrecto)")

                rel = copy_logo_to_assets(fn, cid)
                self.logo_path_edit.setText(rel)
                QMessageBox.information(self, "Logo", f"Logo copiado a assets (ruta relativa):\n\n{rel}")
            except Exception as e:
                QMessageBox.warning(self, "Logo", f"No se pudo procesar el logo:\n{e}")
        else:
            self._pending_logo_source_abs = fn
            self.logo_path_edit.setText(os.path.basename(fn))
            print(f"[COMPANY-LOGO] Pending logo for new company: {fn}")

    def _prepare_logo_to_save(self, current_logo_value: str, company_id: int) -> str:
        print(f"[COMPANY-LOGO] _prepare_logo_to_save: current_value='{current_logo_value}', company_id={company_id}")
        if self._pending_logo_source_abs:
            local_path = self._pending_logo_source_abs
            ext = os.path.splitext(local_path)[1].lower() or ".png"
            storage_path = f"logos/company_{company_id}{ext}"
            self._pending_logo_source_abs = None
            if hasattr(self.logic, 'upload_file_to_storage'):
                try:
                    url = self.logic.upload_file_to_storage(local_path, storage_path)
                    if url:
                        print(f"[COMPANY-LOGO] Uploaded pending logo to storage: {url}")
                        return url
                except Exception as e:
                    print(f"[COMPANY-LOGO] Error uploading pending logo to storage: {e}")
            try:
                rel = copy_logo_to_assets(local_path, int(company_id))
                print(f"[COMPANY-LOGO] Copied pending logo to assets: {rel}")
                return rel
            except Exception as e:
                print(f"[COMPANY-LOGO] Error copying pending logo to assets: {e}")
                return ""
        if current_logo_value and current_logo_value.startswith(('http://', 'https://')):
            return current_logo_value
        if not current_logo_value:
            return ""
        val = current_logo_value
        if val.lower().startswith("file:///") or os.path.isabs(val):
            rel_try = relativize_if_under_assets(val)
            if rel_try != val:
                return rel_try
            abs_src = val[8:].replace("/", os.sep) if val.lower().startswith("file:///") else val
            if hasattr(self.logic, 'upload_file_to_storage') and os.path.exists(abs_src):
                ext = os.path.splitext(abs_src)[1].lower() or ".png"
                storage_path = f"logos/company_{company_id}{ext}"
                try:
                    url = self.logic.upload_file_to_storage(abs_src, storage_path)
                    if url:
                        print(f"[COMPANY-LOGO] Uploaded absolute path to storage: {url}")
                        return url
                except Exception as e:
                    print(f"[COMPANY-LOGO] Error uploading absolute path to storage: {e}")
            try:
                rel = copy_logo_to_assets(abs_src, int(company_id))
                print(f"[COMPANY-LOGO] Copied absolute path to assets: {rel}")
                return rel
            except Exception as e:
                print(f"[COMPANY-LOGO] Error copying absolute path to assets: {e}")
                return ""
        return val.replace("\\", "/")

    def _dateedit_to_str(self, de: QDateEdit) -> str:
        try:
            qd = de.date()
            return f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        except Exception:
            return ""

    def _set_due_date_from_str(self, s: str):
        if not s:
            self.invoice_due_date_edit.setDate(QDate.currentDate())
            return
        try:
            parts = s[:10].split("-")
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            self.invoice_due_date_edit.setDate(QDate(y, m, d))
        except Exception:
            self.invoice_due_date_edit.setDate(QDate.currentDate())

    def _reselect_by_id(self, company_id: Optional[int]):
        if not company_id:
            return
        for row, c in enumerate(self._companies_cache):
            if c.get("id") == company_id:
                self.company_table.selectRow(row)
                break