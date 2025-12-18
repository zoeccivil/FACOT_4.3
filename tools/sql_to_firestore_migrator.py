from __future__ import annotations

import os
import sys
import sqlite3
from typing import Dict, List, Any, Optional, TYPE_CHECKING

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFileDialog, QComboBox, QListWidget, QListWidgetItem, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QSplitter, QFormLayout,
    QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt

# Tipos sólo para chequeo estático (evita que Pylance considere variables como tipos)
if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient  # type: ignore

# Firestore (service account) - import dinámico en runtime
try:
    from google.cloud import firestore  # runtime client
    from google.oauth2 import service_account
except Exception:
    firestore = None  # type: ignore
    service_account = None  # type: ignore


class MappingDialog(QDialog):
    """
    Diálogo para configurar el mapeo tabla -> colección y seleccionar columnas a migrar.
    """
    def __init__(self, table_name: str, columns: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Configurar mapeo de '{table_name}'")
        self.resize(700, 500)

        self.table_name = table_name
        self.columns = columns[:]
        self.collection_edit = QLineEdit()
        self.collection_edit.setPlaceholderText("Nombre de colección destino (Firestore)")

        self.doc_id_combo = QComboBox()
        self.doc_id_combo.addItem("(auto-generar)")
        for c in self.columns:
            self.doc_id_combo.addItem(c)

        self.columns_list = QListWidget()
        self.columns_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        for c in self.columns:
            item = QListWidgetItem(c)
            item.setCheckState(Qt.CheckState.Checked)
            self.columns_list.addItem(item)

        self.upsert_checkbox = QCheckBox("Si existe documento con mismo ID, sustituir (upsert)")
        self.upsert_checkbox.setChecked(True)

        self.preview_table = QTableWidget(0, 2)
        self.preview_table.setHorizontalHeaderLabels(["Campo (Firestore)", "Columna (SQL)"])
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._refresh_preview()

        self.columns_list.itemChanged.connect(self._refresh_preview)
        self.doc_id_combo.currentIndexChanged.connect(self._refresh_preview)

        form = QFormLayout()
        form.addRow("Colección destino:", self.collection_edit)
        form.addRow("Columna para Document ID:", self.doc_id_combo)

        top = QHBoxLayout()
        top.addLayout(form)
        top.addStretch(1)

        mid = QSplitter(Qt.Orientation.Horizontal)
        left_box = QWidget()
        left_lay = QVBoxLayout(left_box)
        left_lay.addWidget(QLabel("Columnas a migrar (marca para incluir):"))
        left_lay.addWidget(self.columns_list)
        mid.addWidget(left_box)

        right_box = QWidget()
        right_lay = QVBoxLayout(right_box)
        right_lay.addWidget(QLabel("Previsualización de mapeo (campo:columna):"))
        right_lay.addWidget(self.preview_table)
        mid.addWidget(right_box)
        mid.setSizes([300, 400])

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.upsert_checkbox)
        root.addWidget(mid)
        root.addWidget(buttons)

    def _refresh_preview(self):
        selected_columns = []
        for i in range(self.columns_list.count()):
            item = self.columns_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_columns.append(item.text())

        doc_id_col = self.doc_id_combo.currentText()
        self.preview_table.setRowCount(0)
        for col in selected_columns:
            r = self.preview_table.rowCount()
            self.preview_table.insertRow(r)
            self.preview_table.setItem(r, 0, QTableWidgetItem(col))
            self.preview_table.setItem(r, 1, QTableWidgetItem(col))

        if doc_id_col != "(auto-generar)" and doc_id_col not in selected_columns:
            r = self.preview_table.rowCount()
            self.preview_table.insertRow(r)
            warn = QTableWidgetItem(f"[ADVERTENCIA] DocID usa columna '{doc_id_col}' no incluida. Se usará sólo para ID.")
            warn.setForeground(Qt.GlobalColor.red)
            self.preview_table.setItem(r, 0, warn)
            self.preview_table.setItem(r, 1, QTableWidgetItem(""))

    def get_mapping(self) -> Dict[str, Any]:
        selected_columns = []
        for i in range(self.columns_list.count()):
            item = self.columns_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_columns.append(item.text())
        return {
            "table_name": self.table_name,
            "collection": self.collection_edit.text().strip(),
            "doc_id_column": None if self.doc_id_combo.currentText() == "(auto-generar)" else self.doc_id_combo.currentText(),
            "columns": selected_columns,
            "upsert": self.upsert_checkbox.isChecked(),
        }


class SQLToFirestoreMigrator(QWidget):
    """
    Migrador interactivo:
      - Elegir base SQLite y credenciales JSON (service account).
      - Listar tablas y seleccionar cuál migrar.
      - Configurar mapeo: tabla -> colección, columnas -> campos, doc_id.
      - Upsert: sustituir si existe documento con mismo ID.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Migrador SQL -> Firestore")
        self.resize(900, 600)

        self.sql_conn: Optional[sqlite3.Connection] = None
        # Evita el error de Pylance usando una forward reference a un tipo definido sólo en TYPE_CHECKING
        self.fs: Optional["FirestoreClient"] = None  # type: ignore[name-defined]

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

        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("SQLite DB:"))
        src_row.addWidget(self.db_path_edit)
        src_row.addWidget(btn_db)
        src_row.addSpacing(12)
        src_row.addWidget(QLabel("Firebase JSON:"))
        src_row.addWidget(self.creds_path_edit)
        src_row.addWidget(btn_creds)
        src_row.addStretch(1)
        src_row.addWidget(connect_btn)

        self.tables_list = QListWidget()
        self.tables_list.itemDoubleClicked.connect(self._configure_mapping)

        self.status_label = QLabel("Selecciona DB y credenciales, luego conecta.")
        self.status_label.setWordWrap(True)

        self.btn_configure = QPushButton("Configurar mapeo…")
        self.btn_configure.setEnabled(False)
        self.btn_configure.clicked.connect(self._configure_mapping)

        self.btn_migrate = QPushButton("Migrar tabla seleccionada")
        self.btn_migrate.setEnabled(False)
        self.btn_migrate.clicked.connect(self._migrate_selected_table)

        self.log_table = QTableWidget(0, 3)
        self.log_table.setHorizontalHeaderLabels(["Evento", "Detalle", "Estado"])
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        top = QVBoxLayout()
        top.addLayout(src_row)
        top.addWidget(self.status_label)

        mid_split = QSplitter(Qt.Orientation.Horizontal)
        left_box = QWidget()
        left_lay = QVBoxLayout(left_box)
        left_lay.addWidget(QLabel("Tablas en SQLite:"))
        left_lay.addWidget(self.tables_list)
        act_row = QHBoxLayout()
        act_row.addWidget(self.btn_configure)
        act_row.addWidget(self.btn_migrate)
        act_row.addStretch(1)
        left_lay.addLayout(act_row)

        right_box = QWidget()
        right_lay = QVBoxLayout(right_box)
        right_lay.addWidget(QLabel("Log de migración:"))
        right_lay.addWidget(self.log_table)

        mid_split.addWidget(left_box)
        mid_split.addWidget(right_box)
        mid_split.setSizes([300, 600])

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(mid_split)

        self.table_mappings: Dict[str, Dict[str, Any]] = {}

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
            # El tipo real en runtime es firestore.Client; la anotación usa FirestoreClient (TYPE_CHECKING)
            self.fs = firestore.Client(credentials=creds, project=creds.project_id)  # type: ignore[call-arg]
        except Exception as e:
            QMessageBox.critical(self, "Firebase", f"No se pudo inicializar Firestore:\n{e}")
            return

        try:
            tables = self._list_tables(self.sql_conn)
            self.tables_list.clear()
            for t in tables:
                self.tables_list.addItem(t)
            self.status_label.setText(f"Conectado. {len(tables)} tablas encontradas.")
            self.btn_configure.setEnabled(True)
            self.btn_migrate.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "SQLite", f"No se pudieron listar tablas:\n{e}")

    def _list_tables(self, conn: sqlite3.Connection) -> List[str]:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        return [r[0] for r in cur.fetchall()]

    def _get_columns_for_table(self, table_name: str) -> List[str]:
        cur = self.sql_conn.cursor()
        cur.execute(f"PRAGMA table_info('{table_name}')")
        cols = []
        for row in cur.fetchall():
            cols.append(row[1])
        return cols

    def _configure_mapping(self):
        item = self.tables_list.currentItem()
        if not item:
            QMessageBox.information(self, "Configurar", "Selecciona una tabla primero.")
            return
        table_name = item.text()
        columns = self._get_columns_for_table(table_name)
        dlg = MappingDialog(table_name, columns, self)
        if table_name in self.table_mappings:
            prev = self.table_mappings[table_name]
            dlg.collection_edit.setText(prev.get("collection", ""))
            doc_id_col = prev.get("doc_id_column")
            if doc_id_col:
                idx = dlg.doc_id_combo.findText(doc_id_col)
                if idx >= 0:
                    dlg.doc_id_combo.setCurrentIndex(idx)
            dlg.upsert_checkbox.setChecked(bool(prev.get("upsert", True)))
            for i in range(dlg.columns_list.count()):
                it = dlg.columns_list.item(i)
                it.setCheckState(Qt.CheckState.Checked if it.text() in prev.get("columns", []) else Qt.CheckState.Unchecked)

        if dlg.exec():
            mapping = dlg.get_mapping()
            if not mapping["collection"]:
                QMessageBox.warning(self, "Configurar", "Debes indicar la colección destino.")
                return
            self.table_mappings[table_name] = mapping
            self._log("Configurar", f"Tabla '{table_name}' -> colección '{mapping['collection']}'", "OK")

    def _migrate_selected_table(self):
        item = self.tables_list.currentItem()
        if not item:
            QMessageBox.information(self, "Migrar", "Selecciona una tabla primero.")
            return
        table_name = item.text()
        mapping = self.table_mappings.get(table_name)
        if not mapping:
            QMessageBox.information(self, "Migrar", "Configura el mapeo de la tabla antes de migrar.")
            return

        coll_name = mapping["collection"]
        doc_id_col = mapping["doc_id_column"]
        cols = mapping["columns"] or []
        upsert = mapping["upsert"]

        if not cols:
            QMessageBox.warning(self, "Migrar", "Selecciona al menos una columna para migrar.")
            return

        try:
            cur = self.sql_conn.cursor()
            select_cols = cols + ([doc_id_col] if doc_id_col and doc_id_col not in cols else [])
            cur.execute(f"SELECT {', '.join(select_cols)} FROM '{table_name}'")
            rows = cur.fetchall()
        except Exception as e:
            QMessageBox.critical(self, "SQLite", f"No se pudo leer la tabla:\n{e}")
            return

        try:
            batch = self.fs.batch()  # type: ignore[union-attr]
            col_ref = self.fs.collection(coll_name)  # type: ignore[union-attr]
            count = 0
            for r in rows:
                row_dict = {}
                for ci, c in enumerate(cols):
                    row_dict[c] = r[ci]
                if doc_id_col:
                    if doc_id_col in cols:
                        doc_id_val = r[cols.index(doc_id_col)]
                    else:
                        doc_id_val = r[len(cols)]
                    doc_id = str(doc_id_val) if doc_id_val is not None else ""
                    doc_ref = col_ref.document(doc_id) if doc_id else col_ref.document()
                else:
                    doc_ref = col_ref.document()
                if upsert:
                    batch.set(doc_ref, row_dict, merge=True)
                else:
                    batch.set(doc_ref, row_dict, merge=False)
                count += 1
                if count % 400 == 0:
                    batch.commit()
                    batch = self.fs.batch()  # type: ignore[union-attr]
            batch.commit()
            self._log("Migrar", f"Migración completada: {count} documentos a '{coll_name}'", "OK")
            QMessageBox.information(self, "Migrar", f"Migración completada:\n{count} documentos a '{coll_name}'")
        except Exception as e:
            msg = str(e)
            self._log("Migrar", msg, "Error")
            hint = ""
            if "Quota exceeded" in msg or "429" in msg:
                hint = "\n\nSugerencia: se alcanzó la cuota. Vuelve a intentar más tarde o considera el plan Blaze."
            QMessageBox.critical(self, "Migrar", f"Ocurrió un error:\n{msg}{hint}")

    def _log(self, evt: str, det: str, status: str):
        r = self.log_table.rowCount()
        self.log_table.insertRow(r)
        self.log_table.setItem(r, 0, QTableWidgetItem(evt))
        self.log_table.setItem(r, 1, QTableWidgetItem(det))
        st_item = QTableWidgetItem(status)
        if status.lower() == "error":
            st_item.setForeground(Qt.GlobalColor.red)
        elif status.lower() == "ok":
            st_item.setForeground(Qt.GlobalColor.darkGreen)
        self.log_table.setItem(r, 2, st_item)


def run_sql_to_firestore_migrator():
    app = QApplication.instance() or QApplication(sys.argv)
    w = SQLToFirestoreMigrator()
    w.show()
    return app.exec()