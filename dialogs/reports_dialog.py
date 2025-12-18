"""
Diálogos de Reportes para FACOT.

Proporciona diálogos para generar reportes de ventas y clientes.
"""

from __future__ import annotations
import os
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDateEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QGroupBox, QFileDialog,
    QMessageBox, QHeaderView, QProgressBar
)
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QFont


class BaseReportDialog(QDialog):
    """Clase base para diálogos de reportes."""
    
    def __init__(self, data_access, parent=None):
        super().__init__(parent)
        self.data_access = data_access
        self.dataset: List[Dict[str, Any]] = []
        self.setMinimumSize(800, 600)
    
    def _create_date_filters(self, layout: QVBoxLayout) -> tuple:
        """Crea los filtros de fecha."""
        date_group = QGroupBox("Período")
        date_layout = QHBoxLayout()
        
        # Fecha inicio
        date_layout.addWidget(QLabel("Desde:"))
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate().addMonths(-1))
        date_layout.addWidget(self.start_date)
        
        # Fecha fin
        date_layout.addWidget(QLabel("Hasta:"))
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())
        date_layout.addWidget(self.end_date)
        
        # Botones de período rápido
        btn_month = QPushButton("Este Mes")
        btn_month.clicked.connect(self._set_this_month)
        date_layout.addWidget(btn_month)
        
        btn_year = QPushButton("Este Año")
        btn_year.clicked.connect(self._set_this_year)
        date_layout.addWidget(btn_year)
        
        date_group.setLayout(date_layout)
        layout.addWidget(date_group)
        
        return self.start_date, self.end_date
    
    def _set_this_month(self):
        """Establece el período al mes actual."""
        today = QDate.currentDate()
        self.start_date.setDate(QDate(today.year(), today.month(), 1))
        self.end_date.setDate(today)
    
    def _set_this_year(self):
        """Establece el período al año actual."""
        today = QDate.currentDate()
        self.start_date.setDate(QDate(today.year(), 1, 1))
        self.end_date.setDate(today)
    
    def _get_date_range(self) -> tuple:
        """Obtiene el rango de fechas seleccionado."""
        start = self.start_date.date().toPyDate()
        end = self.end_date.date().toPyDate()
        return start, end
    
    def _create_table(self, headers: List[str], layout: QVBoxLayout) -> QTableWidget:
        """Crea la tabla de resultados."""
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        
        header = table.horizontalHeader()
        for i in range(len(headers)):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        layout.addWidget(table)
        return table
    
    def _create_action_buttons(self, layout: QVBoxLayout):
        """Crea los botones de acción."""
        btn_layout = QHBoxLayout()
        
        btn_generate = QPushButton("🔄 Generar Reporte")
        btn_generate.clicked.connect(self._generate_report)
        btn_layout.addWidget(btn_generate)
        
        btn_csv = QPushButton("📄 Exportar CSV")
        btn_csv.clicked.connect(self._export_csv)
        btn_layout.addWidget(btn_csv)
        
        btn_html = QPushButton("🌐 Vista Previa HTML")
        btn_html.clicked.connect(self._export_html)
        btn_layout.addWidget(btn_html)
        
        btn_layout.addStretch()
        
        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.close)
        btn_layout.addWidget(btn_close)
        
        layout.addLayout(btn_layout)
    
    def _generate_report(self):
        """Genera el reporte (a implementar en subclases)."""
        raise NotImplementedError
    
    def _export_csv(self):
        """Exporta a CSV (a implementar en subclases)."""
        raise NotImplementedError
    
    def _export_html(self):
        """Exporta a HTML (a implementar en subclases)."""
        raise NotImplementedError


from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDateEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from datetime import datetime
import os

class SalesReportDialog(BaseReportDialog):
    """Diálogo para reporte de ventas."""

    def __init__(self, data_access, parent=None):
        super().__init__(data_access, parent)
        self.setWindowTitle("📊 Reporte de Ventas")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Reporte de Ventas por Período")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._create_date_filters(layout)

        group_layout = QHBoxLayout()
        group_layout.addWidget(QLabel("Agrupar por:"))

        self.group_by = QComboBox()
        self.group_by.addItems(["Día", "Mes", "Producto"])
        group_layout.addWidget(self.group_by)
        group_layout.addStretch()

        layout.addLayout(group_layout)

        headers = ["Período", "Facturas", "Total", "Promedio", "Primer Fecha", "Última Fecha"]
        self.table = self._create_table(headers, layout)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-weight: bold; padding: 10px;")
        layout.addWidget(self.summary_label)

        self._create_action_buttons(layout)

    def _current_company_id(self):
        try:
            if self.parent and hasattr(self.parent, "get_current_company_id"):
                return self.parent.get_current_company_id()
        except Exception:
            return None
        return None

    def _generate_report(self):
        """Genera el reporte de ventas."""
        try:
            from services.reporting_service import ReportingService

            start, end = self._get_date_range()
            company_id = self._current_company_id()

            group_map = {"Día": "day", "Mes": "month", "Producto": "product"}
            group_by = group_map.get(self.group_by.currentText(), "day")

            service = ReportingService(self.data_access)
            self.dataset = service.sales_by_period(start, end, company_id=company_id, group_by=group_by)

            self.table.setRowCount(0)
            total_invoices = 0
            total_amount = 0.0

            for row_data in self.dataset:
                row = self.table.rowCount()
                self.table.insertRow(row)

                self.table.setItem(row, 0, QTableWidgetItem(str(row_data.get('key', ''))))
                self.table.setItem(row, 1, QTableWidgetItem(str(row_data.get('count_invoices', 0))))
                self.table.setItem(row, 2, QTableWidgetItem(f"{row_data.get('total_amount', 0):,.2f}"))
                self.table.setItem(row, 3, QTableWidgetItem(f"{row_data.get('avg_amount', 0):,.2f}"))
                self.table.setItem(row, 4, QTableWidgetItem(str(row_data.get('first_date', ''))))
                self.table.setItem(row, 5, QTableWidgetItem(str(row_data.get('last_date', ''))))

                total_invoices += row_data.get('count_invoices', 0)
                total_amount += row_data.get('total_amount', 0)

            self.summary_label.setText(
                f"Total: {total_invoices} facturas | Monto total: {total_amount:,.2f}"
            )

            if not self.dataset:
                QMessageBox.information(self, "Sin datos", "No se encontraron facturas en el período seleccionado.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error generando reporte: {e}")

    def _export_csv(self):
        if not self.dataset:
            QMessageBox.warning(self, "Sin datos", "Primero genere el reporte.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Guardar CSV",
            f"ventas_{datetime.now().strftime('%Y%m%d')}.csv",
            "CSV Files (*.csv)"
        )

        if file_path:
            try:
                from services.reporting_service import export_sales_csv
                if export_sales_csv(self.dataset, file_path):
                    QMessageBox.information(self, "Exportado", f"Reporte guardado en:\n{file_path}")
                else:
                    QMessageBox.warning(self, "Error", "No se pudo exportar el reporte.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error exportando: {e}")

    def _export_html(self):
        if not self.dataset:
            QMessageBox.warning(self, "Sin datos", "Primero genere el reporte.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Guardar HTML",
            f"ventas_{datetime.now().strftime('%Y%m%d')}.html",
            "HTML Files (*.html)"
        )

        if file_path:
            try:
                from services.reporting_service import export_report_html
                headers = ["key", "count_invoices", "total_amount", "avg_amount", "first_date", "last_date"]
                if export_report_html(self.dataset, "Reporte de Ventas", headers, file_path):
                    QMessageBox.information(self, "Exportado", f"Reporte guardado en:\n{file_path}")
                    import webbrowser
                    webbrowser.open(f"file://{os.path.abspath(file_path)}")
                else:
                    QMessageBox.warning(self, "Error", "No se pudo exportar el reporte.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error exportando: {e}")


class ClientsReportDialog(BaseReportDialog):
    """Diálogo para reporte por cliente."""

    def __init__(self, data_access, parent=None):
        super().__init__(data_access, parent)
        self.setWindowTitle("👥 Reporte por Cliente")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Reporte por Cliente")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._create_date_filters(layout)

        headers = ["RNC/ID", "Cliente", "Facturas", "Total", "Última Factura"]
        self.table = self._create_table(headers, layout)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-weight: bold; padding: 10px;")
        layout.addWidget(self.summary_label)

        self._create_action_buttons(layout)

    def _current_company_id(self):
        try:
            if self.parent and hasattr(self.parent, "get_current_company_id"):
                return self.parent.get_current_company_id()
        except Exception:
            return None
        return None

    def _generate_report(self):
        """Genera el reporte por cliente."""
        try:
            from services.reporting_service import ReportingService

            start, end = self._get_date_range()
            company_id = self._current_company_id()

            service = ReportingService(self.data_access)
            self.dataset = service.clients_by_period(start, end, company_id=company_id)

            self.table.setRowCount(0)
            total_clients = len(self.dataset)
            total_invoices = 0
            total_amount = 0.0

            for row_data in self.dataset:
                row = self.table.rowCount()
                self.table.insertRow(row)

                self.table.setItem(row, 0, QTableWidgetItem(str(row_data.get('client_id', ''))))
                self.table.setItem(row, 1, QTableWidgetItem(str(row_data.get('client_name', ''))))
                self.table.setItem(row, 2, QTableWidgetItem(str(row_data.get('invoices_count', 0))))
                self.table.setItem(row, 3, QTableWidgetItem(f"{row_data.get('total_amount', 0):,.2f}"))
                self.table.setItem(row, 4, QTableWidgetItem(str(row_data.get('last_invoice_date', ''))))

                total_invoices += row_data.get('invoices_count', 0)
                total_amount += row_data.get('total_amount', 0)

            self.summary_label.setText(
                f"Total: {total_clients} clientes | {total_invoices} facturas | Monto: {total_amount:,.2f}"
            )

            if not self.dataset:
                QMessageBox.information(self, "Sin datos", "No se encontraron facturas en el período seleccionado.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error generando reporte: {e}")

    def _export_csv(self):
        if not self.dataset:
            QMessageBox.warning(self, "Sin datos", "Primero genere el reporte.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Guardar CSV",
            f"clientes_{datetime.now().strftime('%Y%m%d')}.csv",
            "CSV Files (*.csv)"
        )

        if file_path:
            try:
                from services.reporting_service import export_clients_csv
                if export_clients_csv(self.dataset, file_path):
                    QMessageBox.information(self, "Exportado", f"Reporte guardado en:\n{file_path}")
                else:
                    QMessageBox.warning(self, "Error", "No se pudo exportar el reporte.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error exportando: {e}")

    def _export_html(self):
        if not self.dataset:
            QMessageBox.warning(self, "Sin datos", "Primero genere el reporte.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Guardar HTML",
            f"clientes_{datetime.now().strftime('%Y%m%d')}.html",
            "HTML Files (*.html)"
        )

        if file_path:
            try:
                from services.reporting_service import export_report_html
                headers = ["client_id", "client_name", "invoices_count", "total_amount", "last_invoice_date"]
                if export_report_html(self.dataset, "Reporte por Cliente", headers, file_path):
                    QMessageBox.information(self, "Exportado", f"Reporte guardado en:\n{file_path}")
                    import webbrowser
                    webbrowser.open(f"file://{os.path.abspath(file_path)}")
                else:
                    QMessageBox.warning(self, "Error", "No se pudo exportar el reporte.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error exportando: {e}")