from __future__ import annotations

import sys
import os
import csv
import sqlite3
import webbrowser
from typing import List, Dict, Any, Optional

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QLineEdit,
    QDateEdit, QTabWidget, QMessageBox, QDialog, QFormLayout
)
from PyQt6.QtCore import Qt, QDate

# Opcional: Firestore con credenciales de servicio
try:
    from google.cloud import firestore
    from google.oauth2 import service_account
except Exception:
    firestore = None
    service_account = None


def normalize_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Map SQL/Firebase record into a common comparable schema."""
    return {
        "id": raw.get("id") or raw.get("doc_id") or raw.get("pk") or "",
        "invoice_number": raw.get("invoice_number") or raw.get("ncf") or raw.get("number") or "",
        "invoice_type": (raw.get("invoice_type") or raw.get("type") or "").strip().upper(),
        "invoice_date": (raw.get("invoice_date") or raw.get("date") or "").strip()[:10],
        "client_name": raw.get("client_name") or raw.get("third_party_name") or "",
        "client_rnc": raw.get("client_rnc") or raw.get("rnc") or "",
        "currency": raw.get("currency") or "",
        "total_amount": float(raw.get("total_amount", raw.get("total", 0.0)) or 0.0),
    }


class CompareSetupDialog(QDialog):
    """Diálogo para seleccionar la base SQLite y credenciales Firestore."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurar fuentes de datos")
        self.resize(600, 200)

        self.db_path_edit = QLineEdit()
        self.db_path_edit.setPlaceholderText("Ruta del archivo SQLite (*.db)")
        self.creds_path_edit = QLineEdit()
        self.creds_path_edit.setPlaceholderText("Archivo de credenciales JSON de Firebase")

        btn_browse_db = QPushButton("Buscar DB…")
        btn_browse_db.clicked.connect(self._browse_db)
        btn_browse_creds = QPushButton("Buscar credenciales…")
        btn_browse_creds.clicked.connect(self._browse_creds)

        form = QFormLayout()
        db_row = QHBoxLayout()
        db_row.addWidget(self.db_path_edit)
        db_row.addWidget(btn_browse_db)
        form.addRow("SQLite DB:", db_row)

        creds_row = QHBoxLayout()
        creds_row.addWidget(self.creds_path_edit)
        creds_row.addWidget(btn_browse_creds)
        form.addRow("Credenciales Firebase:", creds_row)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btn_ok = QPushButton("Iniciar comparador")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addLayout(btns)

    def _browse_db(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Seleccionar base de datos SQLite", "", "SQLite DB (*.db *.sqlite *.sqlite3);;Todos (*.*)")
        if fn:
            self.db_path_edit.setText(fn)

    def _browse_creds(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Seleccionar credenciales Firebase (JSON)", "", "JSON (*.json);;Todos (*.*)")
        if fn:
            self.creds_path_edit.setText(fn)

    def get_paths(self) -> Dict[str, str]:
        return {
            "db_path": self.db_path_edit.text().strip(),
            "creds_path": self.creds_path_edit.text().strip(),
        }


class CompareInvoicesWidget(QWidget):
    def __init__(self, sql_conn, firestore_client, parent=None):
        super().__init__(parent)
        self.sql_conn = sql_conn
        self.fs = firestore_client

        self.setWindowTitle("Comparación de invoices (SQLite vs Firebase)")
        self.resize(1100, 700)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Filtros básicos
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Empresa (ID):"))
        self.company_id_edit = QLineEdit()
        self.company_id_edit.setPlaceholderText("company_id (opcional)")
        filter_row.addWidget(self.company_id_edit)

        filter_row.addWidget(QLabel("Desde:"))
        self.date_from = QDateEdit(QDate.currentDate().addMonths(-3))
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        filter_row.addWidget(self.date_from)

        filter_row.addWidget(QLabel("Hasta:"))
        self.date_to = QDateEdit(QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        filter_row.addWidget(self.date_to)

        self.btn_load = QPushButton("Cargar y comparar")
        self.btn_load.clicked.connect(self.load_and_compare)
        filter_row.addStretch(1)
        filter_row.addWidget(self.btn_load)

        self.btn_export = QPushButton("Exportar resultados (CSV)")
        self.btn_export.clicked.connect(self.export_results)
        filter_row.addWidget(self.btn_export)

        layout.addLayout(filter_row)

        # Tabs para resultados
        self.tabs = QTabWidget()
        self.table_only_sql = self._make_table(["id", "invoice_number", "invoice_type", "invoice_date", "client_name", "client_rnc", "currency", "total_amount"])
        self.table_only_fb = self._make_table(["id", "invoice_number", "invoice_type", "invoice_date", "client_name", "client_rnc", "currency", "total_amount"])
        self.table_diff = self._make_table(["key", "field", "sql_value", "fb_value"])

        self.tabs.addTab(self.table_only_sql, "Solo en SQL")
        self.tabs.addTab(self.table_only_fb, "Solo en Firebase")
        self.tabs.addTab(self.table_diff, "Campos diferentes")
        layout.addWidget(self.tabs)

        # Estado
        self.status = QLabel("Listo.")
        layout.addWidget(self.status)

        # Cache de resultados para exportación
        self._result_only_sql: List[Dict[str, Any]] = []
        self._result_only_fb: List[Dict[str, Any]] = []
        self._result_diff: List[Dict[str, Any]] = []

    def _make_table(self, headers: List[str]) -> QTableWidget:
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        hdr = t.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(True)
        hdr.setMinimumSectionSize(100)
        t.setAlternatingRowColors(True)
        t.verticalHeader().setVisible(False)
        t.setSortingEnabled(True)
        t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return t

    def _load_sql_invoices(self, company_id: Optional[str], dfrom: str, dto: str) -> List[Dict[str, Any]]:
        out = []
        try:
            cur = self.sql_conn.cursor()
            if company_id:
                query = "SELECT id, invoice_number, invoice_type, invoice_date, client_name, client_rnc, currency, total_amount FROM invoices WHERE company_id=? AND date(invoice_date) BETWEEN ? AND ?"
                cur.execute(query, (company_id, dfrom, dto))
            else:
                query = "SELECT id, invoice_number, invoice_type, invoice_date, client_name, client_rnc, currency, total_amount FROM invoices WHERE date(invoice_date) BETWEEN ? AND ?"
                cur.execute(query, (dfrom, dto))
            rows = cur.fetchall()
            for r in rows:
                if isinstance(r, dict):
                    out.append(normalize_record(r))
                else:
                    out.append(normalize_record({
                        "id": r[0], "invoice_number": r[1], "invoice_type": r[2],
                        "invoice_date": r[3], "client_name": r[4], "client_rnc": r[5],
                        "currency": r[6], "total_amount": r[7],
                    }))
        except Exception as e:
            QMessageBox.critical(self, "SQLite", f"Error cargando invoices:\n{e}")
        return out

    def _load_fb_invoices(self, company_id: Optional[str], dfrom: str, dto: str) -> List[Dict[str, Any]]:
        """
        Intenta aplicar filtros en Firestore (company_id y rango de invoice_date).
        Si la consulta requiere un índice compuesto y falla, hace fallback:
        - Consulta solo por company_id (o toda la colección si no hay company_id)
        - Aplica el filtro de fechas en cliente
        Además, cuando se detecta el error de índice, muestra un diálogo amigable con un botón para abrir la URL del índice.
        """
        out = []
        if firestore is None:
            QMessageBox.critical(self, "Firebase", "El módulo google.cloud.firestore no está disponible.\nInstala: pip install google-cloud-firestore")
            return out
        try:
            col = self.fs.collection("invoices")
            q = col
            if company_id:
                q = q.where("company_id", "==", company_id)

            # Primero intentamos con rango de fechas directamente
            try:
                q_with_dates = q.where("invoice_date", ">=", dfrom).where("invoice_date", "<=", dto)
                docs = q_with_dates.stream()
                # Si llega aquí, no hubo error de índice; no necesitamos fallback.
                for doc in docs:
                    data = doc.to_dict()
                    data["doc_id"] = doc.id
                    out.append(normalize_record(data))
            except Exception as e:
                # Detectar si es error de índice requerido
                msg = str(e)
                index_url = self._extract_index_url(msg)
                self._show_index_hint_dialog(msg, index_url)

                # Fallback: consulta base sin fechas y filtra en cliente
                docs = q.stream()
                for doc in docs:
                    data = doc.to_dict()
                    data["doc_id"] = doc.id
                    rec = normalize_record(data)
                    date_str = (rec.get("invoice_date") or "")[:10]
                    if date_str and (date_str >= dfrom and date_str <= dto):
                        out.append(rec)
                    # Si no hay fecha, lo descartamos del rango

        except Exception as e:
            QMessageBox.critical(self, "Firebase", f"Error cargando invoices:\n{e}")
        return out

    def _extract_index_url(self, msg: str) -> Optional[str]:
        """
        Busca una URL de índice en el mensaje de error del SDK de Firestore.
        Generalmente incluye 'create_composite=...' o un enlace directo a la consola.
        """
        # Heurística sencilla: buscar 'https://' y cortar hasta un espacio
        if "http" not in msg:
            return None
        for token in msg.split():
            if token.startswith("http://") or token.startswith("https://"):
                # Limpiar posibles caracteres finales
                url = token.strip().rstrip(").,")
                return url
        return None

    def _show_index_hint_dialog(self, full_error_msg: str, index_url: Optional[str]):
        """
        Muestra un diálogo amigable cuando se detecta que la consulta necesita un índice.
        Incluye un botón para abrir la URL del índice en el navegador.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle("Firestore: índice requerido")
        dlg.resize(700, 260)
        lay = QVBoxLayout(dlg)
        info = QLabel("La consulta en Firestore requiere un índice compuesto para combinar filtros.\n\n"
                      "Opciones:\n"
                      "1) Presiona 'Abrir índice' para crear el índice sugerido en la consola.\n"
                      "2) Continúa con el comparador: se usará un modo fallback (filtrado por fecha en cliente).\n")
        info.setWordWrap(True)
        lay.addWidget(info)

        err_label = QLabel(f"Detalle: {full_error_msg}")
        err_label.setWordWrap(True)
        err_label.setStyleSheet("color:#c33;")
        lay.addWidget(err_label)

        btns = QHBoxLayout()
        btns.addStretch(1)

        btn_ok = QPushButton("Continuar (fallback)")
        btn_ok.clicked.connect(dlg.accept)
        btns.addWidget(btn_ok)

        if index_url:
            btn_open = QPushButton("Abrir índice")
            def _open():
                try:
                    webbrowser.open(index_url)
                except Exception:
                    QMessageBox.information(self, "Abrir índice", f"Abre manualmente:\n{index_url}")
            btn_open.clicked.connect(_open)
            btns.addWidget(btn_open)

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(dlg.reject)
        btns.addWidget(btn_cancel)

        lay.addLayout(btns)
        dlg.exec()

    def load_and_compare(self):
        company_id = (self.company_id_edit.text() or "").strip() or None
        dfrom = self.date_from.date().toString("yyyy-MM-dd")
        dto = self.date_to.date().toString("yyyy-MM-dd")

        self.status.setText("Cargando datos...")
        QApplication.processEvents()

        sql_list = self._load_sql_invoices(company_id, dfrom, dto)
        fb_list = self._load_fb_invoices(company_id, dfrom, dto)

        def key_of(rec: Dict[str, Any]) -> str:
            return str(rec.get("id") or "").strip() or str(rec.get("invoice_number") or "").strip()

        sql_map = {key_of(r): r for r in sql_list if key_of(r)}
        fb_map = {key_of(r): r for r in fb_list if key_of(r)}

        only_sql = []
        only_fb = []
        diffs = []

        all_keys = set(sql_map.keys()) | set(fb_map.keys())
        for k in sorted(all_keys):
            s = sql_map.get(k)
            f = fb_map.get(k)
            if s and not f:
                only_sql.append(s)
            elif f and not s:
                only_fb.append(f)
            else:
                for field in ("invoice_number", "invoice_type", "invoice_date", "client_name", "client_rnc", "currency", "total_amount"):
                    sv = s.get(field)
                    fv = f.get(field)
                    if isinstance(sv, float) or isinstance(fv, float):
                        try:
                            sv_f = float(sv or 0)
                            fv_f = float(fv or 0)
                            equal = abs(sv_f - fv_f) < 0.005
                        except Exception:
                            equal = (str(sv) == str(fv))
                    else:
                        equal = (str(sv) == str(fv))
                    if not equal:
                        diffs.append({
                            "key": k,
                            "field": field,
                            "sql_value": sv,
                            "fb_value": fv
                        })

        self._result_only_sql = only_sql
        self._result_only_fb = only_fb
        self._result_diff = diffs

        self._fill_table_records(self.table_only_sql, only_sql)
        self._fill_table_records(self.table_only_fb, only_fb)
        self._fill_table_diffs(self.table_diff, diffs)

        self.status.setText(f"Listo. SQL:{len(sql_list)} FB:{len(fb_list)} | Solo SQL:{len(only_sql)} Solo FB:{len(only_fb)} Diferencias:{len(diffs)}")

    def _fill_table_records(self, table: QTableWidget, rows: List[Dict[str, Any]]):
        table.setSortingEnabled(False)
        table.setRowCount(0)
        for r in rows:
            row = table.rowCount()
            table.insertRow(row)
            cols = ["id", "invoice_number", "invoice_type", "invoice_date", "client_name", "client_rnc", "currency", "total_amount"]
            for ci, key in enumerate(cols):
                val = r.get(key, "")
                if key == "total_amount":
                    item = QTableWidgetItem(f"{float(val):,.2f}")
                    item.setData(Qt.ItemDataRole.UserRole, float(val))
                else:
                    item = QTableWidgetItem(str(val))
                    if key == "invoice_date":
                        item.setData(Qt.ItemDataRole.UserRole, str(val)[:10])
                table.setItem(row, ci, item)
        table.setSortingEnabled(True)
        hdr = table.horizontalHeader()
        hdr.setStretchLastSection(True)
        for i in range(table.columnCount()-1):
            table.setColumnWidth(i, max(120, table.viewport().width() // (table.columnCount())))

    def _fill_table_diffs(self, table: QTableWidget, rows: List[Dict[str, Any]]):
        table.setSortingEnabled(False)
        table.setRowCount(0)
        for r in rows:
            row = table.rowCount()
            table.insertRow(row)
            for ci, key in enumerate(["key", "field", "sql_value", "fb_value"]):
                val = r.get(key, "")
                item = QTableWidgetItem("" if val is None else str(val))
                table.setItem(row, ci, item)
        table.setSortingEnabled(True)
        hdr = table.horizontalHeader()
        hdr.setStretchLastSection(True)
        for i in range(table.columnCount()-1):
            table.setColumnWidth(i, max(140, table.viewport().width() // (table.columnCount())))

    def export_results(self):
        fn, _ = QFileDialog.getSaveFileName(self, "Exportar resultados CSV", "comparacion_invoices.csv", "CSV Files (*.csv)")
        if not fn:
            return
        try:
            with open(fn, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Tipo", "id", "invoice_number", "invoice_type", "invoice_date", "client_name", "client_rnc", "currency", "total_amount"])
                for r in self._result_only_sql:
                    w.writerow(["solo_sql", r.get("id"), r.get("invoice_number"), r.get("invoice_type"), r.get("invoice_date"),
                                r.get("client_name"), r.get("client_rnc"), r.get("currency"), r.get("total_amount")])
                for r in self._result_only_fb:
                    w.writerow(["solo_fb", r.get("id"), r.get("invoice_number"), r.get("invoice_type"), r.get("invoice_date"),
                                r.get("client_name"), r.get("client_rnc"), r.get("currency"), r.get("total_amount")])
                w.writerow(["tipo", "key", "field", "sql_value", "fb_value", "", "", "", ""])
                for d in self._result_diff:
                    w.writerow(["diff", d.get("key"), d.get("field"), d.get("sql_value"), d.get("fb_value"), "", "", "", ""])
            QMessageBox.information(self, "Exportar", f"Resultados exportados en:\n{fn}")
        except Exception as e:
            QMessageBox.critical(self, "Exportar", f"No se pudo exportar:\n{e}")


def run_compare_tool_with_dialog():
    """Abre un diálogo para seleccionar DB y credenciales, luego lanza el comparador."""
    app = QApplication.instance() or QApplication(sys.argv)
    setup = CompareSetupDialog()
    if setup.exec() != QDialog.DialogCode.Accepted:
        return 0

    paths = setup.get_paths()
    db_path = paths.get("db_path")
    creds_path = paths.get("creds_path")

    # Validaciones básicas
    if not db_path or not os.path.exists(db_path):
        QMessageBox.critical(setup, "SQLite", "Selecciona una base de datos válida.")
        return 0

    if firestore is None or service_account is None:
        QMessageBox.critical(setup, "Firebase", "Paquetes de Google Cloud no disponibles.\nInstala: pip install google-cloud-firestore")
        return 0

    if not creds_path or not os.path.exists(creds_path):
        QMessageBox.critical(setup, "Firebase", "Selecciona un archivo de credenciales JSON válido.")
        return 0

    # Inicializar SQLite
    try:
        sql_conn = sqlite3.connect(db_path)
        sql_conn.row_factory = sqlite3.Row
    except Exception as e:
        QMessageBox.critical(setup, "SQLite", f"No se pudo abrir la base de datos:\n{e}")
        return 0

    # Inicializar Firestore con credenciales de servicio
    try:
        creds = service_account.Credentials.from_service_account_file(creds_path)
        fs_client = firestore.Client(credentials=creds, project=creds.project_id)
    except Exception as e:
        QMessageBox.critical(setup, "Firebase", f"No se pudo inicializar Firestore:\n{e}")
        return 0

    # Lanzar comparador
    w = CompareInvoicesWidget(sql_conn, fs_client)
    w.show()
    return app.exec()