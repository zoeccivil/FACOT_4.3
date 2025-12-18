from __future__ import annotations

import os
import logging
from typing import List, Dict, Any, Tuple, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHBoxLayout, QWidget as QWidgetAlias, QFileDialog, QMessageBox, QHeaderView, QSizePolicy,
    QComboBox, QLineEdit
)
from PyQt6.QtCore import QSize, Qt

logger = logging.getLogger(__name__)

# Dependencies that can fail — import defensivo y fallback
QuotationPreviewDialog = None
try:
    from dialogs.quotation_preview_dialog import QuotationPreviewDialog
except Exception as e:
    logger.debug("Aviso: QuotationPreviewDialog no disponible: %s", e)
    QuotationPreviewDialog = None

# Carga de plantilla
try:
    from utils.template_manager import load_template
except Exception as e:
    logger.debug("Aviso: utils.template_manager.load_template no disponible: %s", e)
    def load_template(company_id: int):
        return {}

# Resolver logo relativo -> file:///
try:
    from utils.asset_paths import resolve_logo_uri
except Exception as e:
    logger.debug("Aviso: utils.asset_paths.resolve_logo_uri no disponible: %s", e)
    def resolve_logo_uri(path):
        return path or ""

try:
    from utils.template_integration import export_quotation_pdf_with_template, export_quotation_excel_with_template
except Exception as e:
    logger.debug("Aviso: utils.template_integration funciones no disponibles: %s", e)
    def export_quotation_pdf_with_template(*args, **kwargs):
        raise RuntimeError("export_quotation_pdf_with_template no disponible")
    def export_quotation_excel_with_template(*args, **kwargs):
        raise RuntimeError("export_quotation_excel_with_template no disponible")

# IconManager fallback
IconManager = None
try:
    from icon_manager import IconManager
except Exception as e:
    logger.debug("Aviso: icon_manager no disponible: %s", e)
    IconManager = None

# Constants (puede lanzar si falta)
try:
    from constants import ITBIS_RATE
except Exception:
    ITBIS_RATE = 0.18

class QuotationHistoryTab(QWidget):
    def __init__(self, logic, get_current_company_callable, parent=None):
        super().__init__(parent)
        self.logic = logic
        self.get_current_company = get_current_company_callable
        self.main_window = None  # Will be set externally
        self.all_quotations = []  # Store all quotations for client-side filtering
        self._build_ui()
        # safe refresh: si falla, no rompa el import
        try:
            self.refresh()
        except Exception as e:
            logger.exception("Error al refrescar QuotationHistoryTab en init: %s", e)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Historial de Cotizaciones"))
        
        # === TOP FILTER BAR ===
        filter_bar = QHBoxLayout()
        
        # Date Filter - Month/Year
        filter_bar.addWidget(QLabel("Mes:"))
        self.month_combo = QComboBox()
        self.month_combo.addItem("Todos", None)
        months = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        for i, month in enumerate(months, 1):
            self.month_combo.addItem(month, i)
        self.month_combo.currentIndexChanged.connect(self._apply_filters)
        filter_bar.addWidget(self.month_combo)
        
        filter_bar.addWidget(QLabel("Año:"))
        self.year_combo = QComboBox()
        self.year_combo.addItem("Todos", None)
        from datetime import datetime
        current_year = datetime.now().year
        for year in range(current_year, current_year - 10, -1):
            self.year_combo.addItem(str(year), year)
        self.year_combo.currentIndexChanged.connect(self._apply_filters)
        filter_bar.addWidget(self.year_combo)
        
        # Search Bar - Client Name
        filter_bar.addWidget(QLabel("Buscar Cliente:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Nombre del cliente...")
        self.search_input.textChanged.connect(self._apply_filters)
        filter_bar.addWidget(self.search_input)
        
        filter_bar.addStretch()
        layout.addLayout(filter_bar)
        
        # --- TOOLBAR (History actions: Abrir PDF / Regenerar enlace) ---
        tool_row = QHBoxLayout()
        self.btn_open_pdf = QPushButton("Abrir PDF")
        self.btn_open_pdf.setToolTip("Abrir PDF de la cotización seleccionada (usa pdf_url guardado en Firestore)")
        self.btn_open_pdf.clicked.connect(self._open_selected_pdf)
        tool_row.addWidget(self.btn_open_pdf)

        self.btn_regen_pdf_link = QPushButton("Regenerar enlace")
        self.btn_regen_pdf_link.setToolTip("Generar nuevo signed URL para el PDF de la cotización seleccionada")
        self.btn_regen_pdf_link.clicked.connect(self._regenerate_selected_pdf_link)
        tool_row.addWidget(self.btn_regen_pdf_link)

        tool_row.addStretch(1)
        layout.addLayout(tool_row)
        
        # === TABLE ===
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["ID", "Fecha", "Cliente", "RNC", "Moneda", "Total", "Notas", "Acciones"])
        
        header = self.table.horizontalHeader()
        # Enable sorting
        self.table.setSortingEnabled(True)
        
        # Column resize strategy - fill entire width without gaps
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # ID
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)  # Fecha
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)      # Cliente
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)  # RNC
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)  # Moneda
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)  # Total
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)  # Notas
        
        # Actions column - fixed width
        actions_col = self.table.columnCount() - 1
        header.setSectionResizeMode(actions_col, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(actions_col, 200)

        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        
        # Context menu for table rows
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(self.table)
        
        # Refresh button
        btn_refresh = QPushButton("Refrescar Historial")
        btn_refresh.clicked.connect(self.refresh)
        layout.addWidget(btn_refresh)    


    def _get_selected_quotation_id(self) -> Optional[str]:
        """Retorna el ID (texto) de la fila seleccionada en la tabla o None."""
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


    def _show_context_menu(self, position):
        """Show context menu on right-click for a quotation row, adding open/regenerate actions."""
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction

        index = self.table.indexAt(position)
        if not index.isValid():
            return

        row = index.row()
        quotation_id_item = self.table.item(row, 0)
        if not quotation_id_item:
            return

        quotation_id = quotation_id_item.text()
        # try to find the record dict if needed
        record = None
        try:
            for q in self.all_quotations:
                if str(q.get('id')) == str(quotation_id):
                    record = q
                    break
        except Exception:
            record = None

        menu = QMenu(self)

        preview_action = QAction("👁 Vista Previa", self)
        preview_action.triggered.connect(lambda: self._open_quotation_preview(record) if record else None)
        menu.addAction(preview_action)

        edit_action = QAction("✏️ Editar", self)
        edit_action.triggered.connect(lambda: self._edit_quotation(quotation_id))
        menu.addAction(edit_action)

        menu.addSeparator()

        pdf_action = QAction("📄 Exportar PDF", self)
        pdf_action.triggered.connect(lambda: self._export_quotation_pdf(record) if record else None)
        menu.addAction(pdf_action)

        excel_action = QAction("📊 Exportar Excel", self)
        excel_action.triggered.connect(lambda: self._export_quotation_excel(record) if record else None)
        menu.addAction(excel_action)

        menu.addSeparator()

        open_pdf_action = QAction("Abrir PDF", self)
        open_pdf_action.triggered.connect(lambda: self._open_selected_pdf())
        menu.addAction(open_pdf_action)

        regen_action = QAction("Regenerar enlace", self)
        regen_action.triggered.connect(lambda: self._regenerate_selected_pdf_link())
        menu.addAction(regen_action)

        menu.addSeparator()

        delete_action = QAction("🗑️ Eliminar", self)
        delete_action.triggered.connect(lambda: self._delete_quotation(quotation_id))
        menu.addAction(delete_action)

        menu.exec(self.table.viewport().mapToGlobal(position))
    

    def _open_selected_pdf(self):
        """Open the signed/public URL for the selected quotation in the user's browser."""
        import webbrowser
        quotation_id = self._get_selected_quotation_id()
        if not quotation_id:
            QMessageBox.information(self, "Abrir PDF", "Seleccione una cotización primero.")
            return
        try:
            q = None
            if hasattr(self.logic, 'get_quotation_by_id'):
                q = self.logic.get_quotation_by_id(quotation_id) or {}
            else:
                QMessageBox.information(self, "Abrir PDF", "El backend no soporta obtener cotización por ID.")
                return
            pdf_url = (q or {}).get('pdf_url') or None
            if not pdf_url:
                QMessageBox.information(self, "Abrir PDF", "No se encontró URL del PDF para esta cotización.")
                return
            webbrowser.open(pdf_url)
        except Exception as e:
            QMessageBox.warning(self, "Abrir PDF", f"No se pudo abrir el enlace:\n{e}")

    def _regenerate_selected_pdf_link(self):
        """
        Generate a new signed URL for the selected quotation's storage path and persist it.
        This uses logic.generate_signed_url_for_path(...) or falls back to data_access helper.
        """
        from datetime import datetime, timedelta
        try:
            quotation_id = self._get_selected_quotation_id()
            if not quotation_id:
                QMessageBox.information(self, "Regenerar enlace", "Seleccione una cotización primero.")
                return

            q = None
            if hasattr(self.logic, 'get_quotation_by_id'):
                q = self.logic.get_quotation_by_id(quotation_id) or {}
            else:
                QMessageBox.information(self, "Regenerar enlace", "El backend no soporta obtener cotización por ID.")
                return

            storage_path = q.get('pdf_storage_path') or None
            if not storage_path:
                QMessageBox.information(self, "Regenerar enlace", "No se encontró storage_path para esta cotización.")
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
            if hasattr(self.logic, "set_quotation_pdf_info"):
                self.logic.set_quotation_pdf_info(quotation_id, storage_path, url, expires_at=expires_at)
            elif hasattr(self.logic, "data_access") and hasattr(self.logic.data_access, "set_quotation_pdf_info"):
                self.logic.data_access.set_quotation_pdf_info(quotation_id, storage_path, url, expires_at=expires_at)

            QMessageBox.information(self, "Regenerar enlace", f"Nuevo enlace generado y guardado.\nExpira: {expires_at}")
            try:
                self.refresh()
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, "Regenerar enlace", f"No se pudo generar el enlace:\n{e}")


    def _edit_quotation(self, quotation_id):
        """Edit a quotation by loading it in the quotation tab."""
        try:
            # Get main window reference
            if not self.main_window:
                # Try to find main window
                parent = self.parent()
                while parent:
                    if hasattr(parent, 'quotation_tab'):
                        self.main_window = parent
                        break
                    parent = parent.parent()
            
            if not self.main_window or not hasattr(self.main_window, 'quotation_tab'):
                QMessageBox.warning(self, "Error", "No se pudo acceder a la pestaña de cotizaciones")
                return
            
            # Load quotation in quotation tab
            if hasattr(self.main_window.quotation_tab, 'load_quotation_by_id'):
                self.main_window.quotation_tab.load_quotation_by_id(int(quotation_id))
                # Switch to quotation tab (index 2)
                if hasattr(self.main_window, 'content_stack'):
                    self.main_window.content_stack.setCurrentIndex(2)
                    self.main_window._navigate_to(2)
            else:
                QMessageBox.warning(self, "Error", "La funcionalidad de edición no está disponible")
        except Exception as e:
            logger.exception("Error al editar cotización: %s", e)
            QMessageBox.critical(self, "Error", f"No se pudo editar la cotización:\n{str(e)}")
    
    def _delete_quotation(self, quotation_id):
        """Delete a quotation after confirmation."""
        try:
            # Confirm deletion
            reply = QMessageBox.question(
                self,
                "Confirmar Eliminación",
                f"¿Está seguro que desea eliminar la cotización ID: {quotation_id}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            # Delete quotation
            if hasattr(self.logic, 'delete_quotation'):
                self.logic.delete_quotation(int(quotation_id))
                QMessageBox.information(self, "Éxito", "Cotización eliminada correctamente")
                # Refresh table
                self.refresh()
            else:
                QMessageBox.warning(self, "Error", "La funcionalidad de eliminación no está disponible")
        except Exception as e:
            logger.exception("Error al eliminar cotización: %s", e)
            QMessageBox.critical(self, "Error", f"No se pudo eliminar la cotización:\n{str(e)}")
    
    def _apply_filters(self):
        """Apply filters to the table based on selected month/year and search text."""
        # Disable sorting temporarily while updating
        self.table.setSortingEnabled(False)
        
        month = self.month_combo.currentData()
        year = self.year_combo.currentData()
        search_text = self.search_input.text().lower().strip()
        
        # Filter quotations
        filtered = []
        for q in self.all_quotations:
            # Date filter
            if month or year:
                date_str = q.get('quotation_date', '')
                if date_str:
                    try:
                        from datetime import datetime
                        # Parse date - handle multiple formats
                        date_obj = None
                        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                            try:
                                date_obj = datetime.strptime(date_str, fmt)
                                break
                            except ValueError:
                                continue
                        
                        if date_obj:
                            if month and date_obj.month != month:
                                continue
                            if year and date_obj.year != year:
                                continue
                        else:
                            continue  # Skip if date couldn't be parsed
                    except Exception:
                        continue
            
            # Search filter
            if search_text:
                client_name = q.get('client_name', '').lower()
                if search_text not in client_name:
                    continue
            
            filtered.append(q)
        
        # Update table
        self._populate_table(filtered)
        
        # Re-enable sorting
        self.table.setSortingEnabled(True)
    
    def _populate_table(self, quotations):
        """Populate table with quotations."""
        self.table.setRowCount(0)
        for q in quotations:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(q.get('id', ''))))
            self.table.setItem(row, 1, QTableWidgetItem(q.get('quotation_date', '')))
            self.table.setItem(row, 2, QTableWidgetItem(q.get('client_name', '')))
            self.table.setItem(row, 3, QTableWidgetItem(q.get('client_rnc', '')))
            self.table.setItem(row, 4, QTableWidgetItem(q.get('currency', '')))
            total = q.get('total_amount', q.get('total', 0.0)) or 0.0
            self.table.setItem(row, 5, QTableWidgetItem(f"{total:,.2f}"))
            self.table.setItem(row, 6, QTableWidgetItem(q.get('notes', '')))
            # actions
            try:
                self._add_quotation_action_buttons(row, q)
            except Exception:
                logger.exception("Error añadiendo boton de acciones para cotizacion id=%s", q.get('id'))

    def refresh(self):
        """Refresh quotation history."""
        company = self.get_current_company()
        if not company:
            return
        try:
            cotizaciones = self.logic.get_quotations(company['id']) if hasattr(self.logic, "get_quotations") else []
        except Exception as e:
            logger.exception("Error al obtener cotizaciones: %s", e)
            cotizaciones = []
        
        # Store all quotations for filtering
        self.all_quotations = cotizaciones
        
        # Log the fetch
        logger.info(f"Quotation History Fetch: Retrieved {len(cotizaciones)} quotations")
        
        # Populate table (will be filtered by date/search if applied)
        self._apply_filters()

    def _add_quotation_action_buttons(self, row: int, record: Dict[str, Any]):
            """
            Añade botones de acción modernos (solo icono) estilizados por QSS.
            """
            widget = QWidgetAlias()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(4, 2, 4, 2)
            layout.setSpacing(8)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Botón PREVIEW (Ojo)
            btn_preview = QPushButton()
            btn_preview.setObjectName("actionButton")  # ID para CSS (themes/style_template.qss)
            btn_preview.setToolTip("Ver detalle / Vista previa")
            btn_preview.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_preview.setFixedSize(32, 32)
            
            # Cargar Icono (Intenta SVG, fallback a texto unicode limpio)
            icon_path = os.path.join(os.getcwd(), "assets", "icons", "eye.svg")
            if os.path.exists(icon_path):
                from PyQt6.QtGui import QIcon
                btn_preview.setIcon(QIcon(icon_path))
                btn_preview.setIconSize(QSize(20, 20))
            else:
                btn_preview.setText("👁") # Fallback visual

            layout.addWidget(btn_preview)
            widget.setLayout(layout)

            # Ajustar altura fila para que el botón respire
            self.table.setRowHeight(row, 44)

            # Conectar acción
            btn_preview.clicked.connect(lambda _, rec=record: self._open_quotation_preview(rec))

            # Insertar en la última columna (Acciones)
            actions_col = self.table.columnCount() - 1
            try:
                self.table.setCellWidget(row, actions_col, widget)
            except Exception:
                # Fallback seguro por si la columna no es la última por alguna razón
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
        # Resolver logo relativo usando assets_root
        logo_rel = tpl.get("logo_path") or company.get("logo_path") or ""
        company_data["logo_path"] = resolve_logo_uri(logo_rel) or ""
        return company_data, tpl

    def _get_record_items(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = record.get('items') or record.get('details') or []
        if not items and hasattr(self.logic, "get_quotation_items"):
            try:
                items = self.logic.get_quotation_items(record.get('id'))
            except Exception:
                items = []
        normalized = []
        for it in items:
            normalized.append({
                "code": it.get("code") or it.get("codigo") or "",
                "description": it.get("description") or it.get("descripcion") or "",
                "unit": it.get("unit") or it.get("unidad") or "",
                "quantity": float(it.get("quantity", it.get("cantidad", 0)) or 0),
                "unit_price": float(it.get("unit_price", it.get("precio", 0)) or 0)
            })
        return normalized

    def _open_quotation_preview(self, record: Dict[str, Any]):
        company_data, tpl = self._resolve_company_and_template()

        # Detectar si la cotización original tenía ITBIS
        apply_itbis = record.get("apply_itbis")
        if apply_itbis is None:
            try:
                total = float(record.get("total_amount", 0) or 0)
                itbis = float(record.get("itbis", 0) or 0)
                apply_itbis = (itbis > 0.01)
            except Exception:
                apply_itbis = False  # Por defecto False en cotizaciones

        quotation_payload = {
            "id": record.get("id"),
            "number": record.get("quotation_number") or record.get("number") or "",
            "date": record.get("quotation_date") or record.get("date") or "",
            "client_name": record.get("client_name") or record.get("third_party_name") or "",
            "client_rnc": record.get("client_rnc") or record.get("rnc") or "",
            "currency": record.get("currency") or "",
            "items": self._get_record_items(record),
            "notes": record.get("notes", "") or "",
            "apply_itbis": apply_itbis,
        }

        if QuotationPreviewDialog is None:
            QMessageBox.warning(self, "Vista Previa", "QuotationPreviewDialog no disponible.")
            return

        template_path = os.path.join(os.getcwd(), "templates", "quotation_template.html")
        dlg = QuotationPreviewDialog(company=company_data, template=tpl, quotation=quotation_payload, parent=self, template_path=template_path, debug=False)
        dlg.exec()

    def _export_quotation_pdf(self, record: Dict[str, Any]):
        company = self.get_current_company()
        if not company:
            QMessageBox.warning(self, "Empresa", "Seleccione una empresa válida"); return

        apply_itbis = record.get("apply_itbis")
        if apply_itbis is None:
            try:
                itbis = float(record.get("itbis", 0) or 0)
                apply_itbis = (itbis > 0.01)
            except Exception:
                apply_itbis = False

        invoice_payload = {
            "company_id": record.get("company_id", company.get('id')),
            "company_name": company.get('name', ''),
            "quotation_date": record.get("quotation_date", ""),
            "quotation_number": record.get("quotation_number") or record.get("number") or "",
            "client_name": record.get("client_name") or record.get("third_party_name") or "",
            "client_rnc": record.get("client_rnc") or record.get("rnc") or "",
            "apply_itbis": apply_itbis,
            "itbis_rate": ITBIS_RATE
        }
        items = self._get_record_items(record)
        fn, _ = QFileDialog.getSaveFileName(self, "Guardar Cotización como PDF", f"cotizacion_{invoice_payload.get('quotation_number','')}.pdf", "PDF Files (*.pdf)")
        if not fn:
            return
        save_path = fn if fn.lower().endswith(".pdf") else fn + ".pdf"
        try:
            export_quotation_pdf_with_template(invoice_payload, items, save_path, company_name=company.get('name',''))
            QMessageBox.information(self, "PDF", f"Cotización guardada como PDF en:\n{save_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo exportar la cotización a PDF:\n{e}")

    def _export_quotation_excel(self, record: Dict[str, Any]):
        company = self.get_current_company()
        if not company:
            QMessageBox.warning(self, "Empresa", "Seleccione una empresa válida"); return

        apply_itbis = record.get("apply_itbis")
        if apply_itbis is None:
            try:
                itbis = float(record.get("itbis", 0) or 0)
                apply_itbis = (itbis > 0.01)
            except Exception:
                apply_itbis = False

        invoice_payload = {
            "company_id": record.get("company_id", company.get('id')),
            "company_name": company.get('name', ''),
            "quotation_date": record.get("quotation_date", ""),
            "quotation_number": record.get("quotation_number") or record.get("number") or "",
            "client_name": record.get("client_name") or record.get("third_party_name") or "",
            "client_rnc": record.get("client_rnc") or record.get("rnc") or "",
            "apply_itbis": apply_itbis,
            "itbis_rate": ITBIS_RATE
        }
        items = self._get_record_items(record)
        fn, _ = QFileDialog.getSaveFileName(self, "Guardar Cotización como Excel", f"cotizacion_{invoice_payload.get('quotation_number','')}.xlsx", "Excel Files (*.xlsx)")
        if not fn:
            return
        save_path = fn if fn.lower().endswith(".xlsx") else fn + ".xlsx"
        try:
            export_quotation_excel_with_template(invoice_payload, items, save_path, company_name=company.get('name',''))
            QMessageBox.information(self, "Excel", f"Cotización guardada como Excel en:\n{save_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo exportar la cotización a Excel:\n{e}")