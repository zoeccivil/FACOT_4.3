from __future__ import annotations

import os
import sys
import sqlite3
from typing import Optional, TYPE_CHECKING

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QMessageBox, QFormLayout, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt

# Declaración de tipo sólo para comprobación estática (Pylance/MyPy)
if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient  # type: ignore

# Firestore (service account) - import dinámico en runtime
try:
    from google.cloud import firestore  # runtime client
    from google.oauth2 import service_account
except Exception:
    firestore = None  # type: ignore
    service_account = None  # type: ignore


class EmitidasCounterWidget(QWidget):
    """
    Herramienta para contar transacciones/facturas 'EMITIDA' por company_id:
      - Cuenta en SQLite: SELECT COUNT(*) FROM invoices WHERE company_id=? AND UPPER(invoice_type)='EMITIDA'
      - Cuenta en Firestore: collection('invoices').where('company_id','==',company_id).where('invoice_type','==','EMITIDA')
        Si requiere índice compuesto y falla, hace fallback: consulta solo por company_id y filtra en cliente.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Contador de 'EMITIDA' por empresa (SQL vs Firestore)")
        self.resize(700, 350)

        self.sql_conn: Optional[sqlite3.Connection] = None
        # Usa anotación genérica para evitar el error de Pylance cuando firestore == None
        self.fs: Optional["FirestoreClient"] = None  # type: ignore[name-defined]

        # Selección de fuentes
        self.db_path_edit = QLineEdit()
        self.db_path_edit.setPlaceholderText("Selecciona archivo SQLite (*.db)")
        self.creds_path_edit = QLineEdit()
        self.creds_path_edit.setPlaceholderText("Selecciona credenciales Firebase (JSON)")

        btn_db = QPushButton("Buscar DB…")
        btn_db.clicked.connect(self._pick_db)
        btn_creds = QPushButton("Buscar credenciales…")
        btn_creds.clicked.connect(self._pick_creds)

        connect_btn = QPushButton("Conectar")
        connect_btn.clicked.connect(self._connect)

        # company_id input
        self.company_id_edit = QLineEdit()
        self.company_id_edit.setPlaceholderText("ID de empresa (company_id)")

        # acciones
        self.btn_count = QPushButton("Contar EMITIDA")
        self.btn_count.setEnabled(False)
        self.btn_count.clicked.connect(self._count_emitidas)

        # resultados
        self.result_table = QTableWidget(0, 3)
        self.result_table.setHorizontalHeaderLabels(["Fuente", "company_id", "EMITIDA (count)"])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # layout
        top = QFormLayout()
        db_row = QHBoxLayout()
        db_row.addWidget(self.db_path_edit); db_row.addWidget(btn_db)
        top.addRow("SQLite DB:", db_row)
        creds_row = QHBoxLayout()
        creds_row.addWidget(self.creds_path_edit); creds_row.addWidget(btn_creds)
        top.addRow("Firebase JSON:", creds_row)

        connect_row = QHBoxLayout()
        connect_row.addStretch(1)
        connect_row.addWidget(connect_btn)

        cid_row = QHBoxLayout()
        cid_row.addWidget(QLabel("Empresa (ID):"))
        cid_row.addWidget(self.company_id_edit)
        cid_row.addStretch(1)
        cid_row.addWidget(self.btn_count)

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addLayout(connect_row)
        root.addSpacing(6)
        root.addLayout(cid_row)
        root.addSpacing(8)
        root.addWidget(self.result_table)

    def _pick_db(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Seleccionar base de datos SQLite", "", "SQLite (*.db *.sqlite *.sqlite3);;Todos (*.*)")
        if fn:
            self.db_path_edit.setText(fn)

    def _pick_creds(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Seleccionar credenciales Firebase (JSON)", "", "JSON (*.json);;Todos (*.*)")
        if fn:
            self.creds_path_edit.setText(fn)

    def _connect(self):
        db_path = self.db_path_edit.text().strip()
        creds_path = self.creds_path_edit.text().strip()

        if not db_path or not os.path.exists(db_path):
            QMessageBox.critical(self, "SQLite", "Selecciona una base de datos válida.")
            return
        if firestore is None or service_account is None:
            QMessageBox.critical(self, "Firebase", "Paquetes google-cloud-firestore no disponibles.\nInstala: pip install google-cloud-firestore")
            return
        if not creds_path or not os.path.exists(creds_path):
            QMessageBox.critical(self, "Firebase", "Selecciona un archivo de credenciales JSON válido.")
            return

        try:
            self.sql_conn = sqlite3.connect(db_path)
            self.sql_conn.row_factory = sqlite3.Row
        except Exception as e:
            QMessageBox.critical(self, "SQLite", f"No se pudo abrir DB:\n{e}")
            return

        try:
            creds = service_account.Credentials.from_service_account_file(creds_path)
            # Nota: el tipo real en runtime lo provee google.cloud.firestore.Client
            self.fs = firestore.Client(credentials=creds, project=creds.project_id)  # type: ignore[call-arg]
        except Exception as e:
            QMessageBox.critical(self, "Firebase", f"No se pudo inicializar Firestore:\n{e}")
            return

        self.btn_count.setEnabled(True)
        QMessageBox.information(self, "Conectado", "Listo. Introduce un company_id y pulsa 'Contar EMITIDA'.")

    def _count_emitidas_sql(self, company_id: str) -> int:
        try:
            cur = self.sql_conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM invoices WHERE company_id = ? AND UPPER(invoice_type) = 'EMITIDA';",
                (company_id,)
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
        except Exception as e:
            QMessageBox.critical(self, "SQLite", f"Error contando en SQL:\n{e}")
            return 0

    def _count_emitidas_fb(self, company_id: str) -> int:
        """
        Intenta filtrar en Firestore (company_id ==, invoice_type == 'EMITIDA').
        Si requiere índice y falla, fallback: filtra solo company_id y luego en cliente por invoice_type.
        """
        count = 0
        try:
            base = self.fs.collection("invoices").where("company_id", "==", company_id)  # type: ignore[union-attr]

            try:
                q = base.where("invoice_type", "==", "EMITIDA")
                docs = q.stream()
                for _ in docs:
                    count += 1
                return count
            except Exception as e:
                # Fallback sin índice compuesto
                msg = str(e)
                idx_url = None
                for token in msg.split():
                    if token.startswith("http://") or token.startswith("https://"):
                        idx_url = token.strip().rstrip(").,")
                        break
                hint = "La consulta requiere un índice compuesto (company_id + invoice_type)."
                if idx_url:
                    hint += f"\nCrea el índice aquí:\n{idx_url}"
                QMessageBox.information(self, "Firestore (fallback)", hint)

                docs = base.stream()
                for d in docs:
                    data = d.to_dict()
                    if (data.get("invoice_type") or "").strip().upper() == "EMITIDA":
                        count += 1
                return count

        except Exception as e:
            QMessageBox.critical(self, "Firebase", f"Error contando en Firestore:\n{e}")
            return 0

    def _count_emitidas(self):
        company_id = (self.company_id_edit.text() or "").strip()
        if not company_id:
            QMessageBox.information(self, "Contar", "Introduce un company_id.")
            return

        sql_count = self._count_emitidas_sql(company_id)
        fb_count = self._count_emitidas_fb(company_id)

        self._append_result("SQLite", company_id, sql_count)
        self._append_result("Firestore", company_id, fb_count)

        diff = sql_count - fb_count
        QMessageBox.information(self, "Resultado",
            f"Company ID: {company_id}\nSQL EMITIDA: {sql_count}\nFirestore EMITIDA: {fb_count}\nDiferencia (SQL - Firestore): {diff}")

    def _append_result(self, source: str, company_id: str, count: int):
        r = self.result_table.rowCount()
        self.result_table.insertRow(r)
        self.result_table.setItem(r, 0, QTableWidgetItem(source))
        self.result_table.setItem(r, 1, QTableWidgetItem(company_id))
        self.result_table.setItem(r, 2, QTableWidgetItem(str(count)))


def run_emitidas_counter_tool():
    app = QApplication.instance() or QApplication(sys.argv)
    w = EmitidasCounterWidget()
    w.show()
    return app.exec()