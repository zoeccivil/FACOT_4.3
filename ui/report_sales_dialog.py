from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDateEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QFont
from datetime import datetime
import os

from services.reporting_service import ReportingService

class SalesReportDialog(QDialog):
    def __init__(self, data_access, parent=None):
        super().__init__(parent)
        self.data_access = data_access
        self.setWindowTitle("📊 Reporte de Ventas")
        self.setMinimumSize(900, 600)
        self.dataset = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Reporte de Ventas por Período (Agrupado por Mes)")
        f = QFont()
        f.setPointSize(14)
        f.setBold(True)
        title.setFont(f)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Filtros
        filt = QHBoxLayout()
        filt.addWidget(QLabel("Desde:"))
        self.start_date = QDateEdit(calendarPopup=True)
        self.start_date.setDate(QDate.currentDate().addMonths(-1))
        filt.addWidget(self.start_date)

        filt.addWidget(QLabel("Hasta:"))
        self.end_date = QDateEdit(calendarPopup=True)
        self.end_date.setDate(QDate.currentDate())
        filt.addWidget(self.end_date)

        filt.addSpacing(20)
        filt.addWidget(QLabel("Empresa:"))
        self.company_cb = QComboBox()
        self.company_cb.addItem("Todas", userData=None)  # None = sin filtro
        # puedes poblarla desde parent si tiene empresas cargadas
        if parent := self.parent():
            if hasattr(parent, "get_companies_list"):
                for c in parent.get_companies_list() or []:
                    self.company_cb.addItem(str(c.get("name")), userData=c.get("id"))
        filt.addWidget(self.company_cb)

        filt.addStretch()
        layout.addLayout(filt)

        headers = ["Período (YYYY-MM)", "Facturas", "Total RD$", "Promedio RD$", "Primera Fecha", "Última Fecha", "Totales por Moneda"]
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        for i in range(len(headers)):
            self.table.horizontalHeader().setSectionResizeMode(i, self.table.horizontalHeader().ResizeMode.Stretch)
        layout.addWidget(self.table)

        self.summary = QLabel("")
        self.summary.setStyleSheet("font-weight: bold; padding: 8px;")
        layout.addWidget(self.summary)

        btns = QHBoxLayout()
        gen = QPushButton("Generar")
        gen.clicked.connect(self._generate)
        btns.addWidget(gen)

        pdf = QPushButton("Exportar PDF")
        pdf.clicked.connect(self._export_pdf)
        btns.addWidget(pdf)

        xls = QPushButton("Exportar Excel")
        xls.clicked.connect(self._export_excel)
        btns.addWidget(xls)

        btns.addStretch()
        close = QPushButton("Cerrar")
        close.clicked.connect(self.close)
        btns.addWidget(close)

        layout.addLayout(btns)

    def _current_company_id(self):
        return self.company_cb.currentData()

    def _generate(self):
        start = self.start_date.date().toPyDate()
        end = self.end_date.date().toPyDate()
        company_id = self._current_company_id()

        svc = ReportingService(self.data_access)
        self.dataset = svc.sales_by_period(start, end, company_id=company_id, group_by="month")

        self.table.setRowCount(0)
        total_invoices = 0
        total_rd = 0.0

        for row in self.dataset:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(str(row.get("key"))))
            self.table.setItem(r, 1, QTableWidgetItem(str(row.get("count_invoices", 0))))
            self.table.setItem(r, 2, QTableWidgetItem(f"{row.get('total_rd', 0):,.2f}"))
            self.table.setItem(r, 3, QTableWidgetItem(f"{row.get('avg_rd', 0):,.2f}"))
            self.table.setItem(r, 4, QTableWidgetItem(str(row.get("first_date", ""))))
            self.table.setItem(r, 5, QTableWidgetItem(str(row.get("last_date", ""))))
            self.table.setItem(r, 6, QTableWidgetItem(str(row.get("totals_by_currency", {}))))

            total_invoices += row.get("count_invoices", 0)
            total_rd += row.get("total_rd", 0.0)

        self.summary.setText(f"Total: {total_invoices} facturas | Monto RD$: {total_rd:,.2f}")

        if not self.dataset:
            QMessageBox.information(self, "Sin datos", "No se encontraron facturas en el período.")

    def _export_excel(self):
        if not self.dataset:
            QMessageBox.warning(self, "Sin datos", "Genera primero el reporte.")
            return
        fname, _ = QFileDialog.getSaveFileName(self, "Guardar Excel", "ventas.xlsx", "Excel Files (*.xlsx)")
        if not fname:
            return
        headers = ["key", "count_invoices", "total_rd", "avg_rd", "first_date", "last_date", "totals_by_currency"]
        svc = ReportingService(self.data_access)
        ok = svc.export_excel(self.dataset, headers, fname)
        if ok:
            QMessageBox.information(self, "Éxito", f"Guardado en:\n{fname}")
        else:
            QMessageBox.critical(self, "Error", "No se pudo exportar.")

    def _export_pdf(self):
        if not self.dataset:
            QMessageBox.warning(self, "Sin datos", "Genera primero el reporte.")
            return
        fname, _ = QFileDialog.getSaveFileName(self, "Guardar PDF", "ventas.pdf", "PDF Files (*.pdf)")
        if not fname:
            return
        svc = ReportingService(self.data_access)
        ok = svc.export_pdf(self.dataset, "Reporte de Ventas", fname)
        if ok:
            QMessageBox.information(self, "Éxito", f"PDF guardado en:\n{fname}")
        else:
            QMessageBox.warning(self, "Aviso", "Implementa el generador de PDF para exportar.")