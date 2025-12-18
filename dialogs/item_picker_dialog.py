from __future__ import annotations

import sqlite3
from typing import List, Dict, Tuple, Optional, Any
import os

from PyQt6.QtCore import Qt, QSettings, QMimeData, QByteArray
from PyQt6.QtGui import QDoubleValidator, QFontMetrics, QDrag, QAction
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QWidget, QHeaderView, QMessageBox, QGroupBox, QFormLayout, QSplitter,
    QComboBox, QStyledItemDelegate, QSizePolicy, QDialogButtonBox, QMenu, QAbstractItemView
)

import facot_config
from items_management_window import ItemsManagementWindow

def get_db_path() -> str:
    return facot_config.get_db_path() or ""


class NumericItemDelegate(QStyledItemDelegate):
    """Delegate numérico para edición de celdas (float)."""
    def __init__(self, decimals: int = 4, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.decimals = decimals

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setValidator(QDoubleValidator(0.0, 1e12, self.decimals, parent))
        return editor

    def setEditorData(self, editor, index):
        text = index.data() or ""
        editor.setText(text)

    def setModelData(self, editor, model, index):
        try:
            val = float((editor.text() or "0").replace(",", ""))
        except Exception:
            val = 0.0
        model.setData(index, f"{val:.2f}")


class ResultsTable(QTableWidget):
    """
    Tabla de resultados que soporta arrastrar filas (drag) hacia un carrito (drop).
    Emite mime data con key 'application/x-item-code' conteniendo el código del ítem.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Enable row drag
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setDragEnabled(True)
        self.viewport().setAcceptDrops(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def startDrag(self, supportedActions):
        sel = self.selectedIndexes()
        if not sel:
            return
        row = sel[0].row()
        code_item = self.item(row, 0)
        if not code_item:
            return
        code = code_item.text() or ""
        mime = QMimeData()
        mime.setData("application/x-item-code", QByteArray(code.encode("utf-8")))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class CartTable(QTableWidget):
    """
    Tabla carrito que acepta drops desde ResultsTable. Añade la fila arrastrada (código)
    usando callback add_callback(code: str) para delegar la lógica de agregar.
    """
    def __init__(self, add_callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_callback = add_callback
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat("application/x-item-code"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat("application/x-item-code"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat("application/x-item-code"):
            data = mime.data("application/x-item-code")
            try:
                code = bytes(data).decode("utf-8")
            except Exception:
                code = str(data)
            # Delegate adding to provided callback
            try:
                self.add_callback(code)
                event.acceptProposedAction()
            except Exception as e:
                QMessageBox.warning(self, "Drag&Drop", f"No se pudo agregar el ítem: {e}")
                event.ignore()
        else:
            event.ignore()


class ItemEditDialog(QDialog):
    """
    Editor rápido de un ítem (código, nombre, unidad, precio y categoría).
    Carga/guarda directamente desde la BD SQLite.
    """
    def __init__(self, code: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Editar Ítem - {code}")
        self.setModal(True)
        self._original_code = code
        self._item_id: Optional[int] = None
        self._categories: List[Tuple[int, str]] = []  # (id, name)
        self._build_ui()
        ok = self._load_item(code)
        if not ok:
            QMessageBox.critical(self, "Ítem", f"No se encontró el ítem con código '{code}'.")
            self.reject()

    def _build_ui(self):
        lay = QVBoxLayout(self)

        form = QFormLayout()
        self.code_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.unit_edit = QLineEdit()
        self.price_edit = QLineEdit()
        self.price_edit.setValidator(QDoubleValidator(0.0, 1e12, 4, self))

        self.category_combo = QComboBox()
        self._load_categories()

        form.addRow("Código:", self.code_edit)
        form.addRow("Nombre:", self.name_edit)
        form.addRow("Unidad:", self.unit_edit)
        form.addRow("Precio:", self.price_edit)
        form.addRow("Categoría:", self.category_combo)

        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)


    def _load_categories(self):
        self._categories.clear()
        self.category_combo.clear()
        db = get_db_path()
        if not db:
            return
        with sqlite3.connect(db) as conn:
            rows = conn.execute("SELECT id, IFNULL(name,'') FROM categories ORDER BY name").fetchall()
        for cid, name in rows:
            self._categories.append((cid, name))
            self.category_combo.addItem(name, cid)

    def _load_item(self, code: str) -> bool:
        db = get_db_path()
        if not db:
            return False
        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT id, code, IFNULL(name,''), IFNULL(unit,''), IFNULL(price,0), IFNULL(category_id, NULL) "
                "FROM items WHERE code = ?",
                (code,)
            ).fetchone()
        if not row:
            return False
        self._item_id = int(row[0])
        self.code_edit.setText(row[1] or "")
        self.name_edit.setText(row[2] or "")
        self.unit_edit.setText(row[3] or "")
        self.price_edit.setText(f"{float(row[4] or 0.0):.2f}")
        cat_id = row[5]
        if cat_id is not None:
            idx = self.category_combo.findData(cat_id)
            if idx >= 0:
                self.category_combo.setCurrentIndex(idx)
        return True

    def _on_save(self):
        code = (self.code_edit.text() or "").strip()
        name = (self.name_edit.text() or "").strip()
        unit = (self.unit_edit.text() or "").strip()
        try:
            price = float((self.price_edit.text() or "0").replace(",", ""))
        except Exception:
            price = 0.0
        cat_id = self.category_combo.currentData()

        if not code or not name:
            QMessageBox.warning(self, "Validación", "Código y Nombre son obligatorios.")
            return
        if self._item_id is None:
            QMessageBox.critical(self, "Ítem", "No hay ID de ítem para guardar.")
            return

        db = get_db_path()
        try:
            with sqlite3.connect(db) as conn:
                conn.execute(
                    "UPDATE items SET code = ?, name = ?, unit = ?, price = ?, category_id = ? WHERE id = ?",
                    (code, name, unit, price, cat_id, self._item_id)
                )
                conn.commit()
            self.accept()
        except sqlite3.IntegrityError as e:
            QMessageBox.critical(self, "Guardar", f"No se pudo guardar el ítem (código duplicado?):\n{e}")
        except Exception as e:
            QMessageBox.critical(self, "Guardar", f"Error al guardar:\n{e}")

    def get_result(self) -> Dict:
        return {
            "original_code": self._original_code,
            "code": (self.code_edit.text() or "").strip(),
            "name": (self.name_edit.text() or "").strip(),
            "unit": (self.unit_edit.text() or "").strip(),
            "price": float((self.price_edit.text() or "0").replace(",", "")) if (self.price_edit.text() or "").strip() else 0.0,
            "category_id": self.category_combo.currentData(),
        }


class ItemPickerDialog(QDialog):
    """
    Diálogo para buscar ítems, agregarlos con cantidad y precio a un 'carrito'
    y devolverlos al tab de Factura/Cotización.

    Cambios:
    - Lee ítems desde backend si está disponible (self.logic / parent.hybrid_logic etc.)
    - Soporta drag & drop: arrastrar fila de resultados al carrito
    """
    def __init__(self, parent=None, title: str = "Agregar ítems"):
        super().__init__(parent)
        self.setWindowTitle(title)

        # Detect backend (logic / hybrid_logic / data_access) from parent chain
        self.logic = None
        p = parent
        while p is not None:
            if hasattr(p, "hybrid_logic") and p.hybrid_logic:
                self.logic = p.hybrid_logic
                break
            if hasattr(p, "logic") and p.logic:
                self.logic = p.logic
                break
            if hasattr(p, "data_access") and p.data_access:
                self.logic = p.data_access
                break
            p = getattr(p, "parent", lambda: None)()
            if p is None:
                break

        # Habilitar maximizar/minimizar y expansión
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowFlags(self.windowFlags()
                            | Qt.WindowType.WindowMinMaxButtonsHint
                            | Qt.WindowType.WindowMaximizeButtonHint)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setSizeGripEnabled(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.resize(980, 600)

        self._updating_cart = False
        self.categories: List[Tuple[int, str, str]] = []

        self._build_ui()
        self._load_categories()
        self._search_items()
        self._restore_geometry()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)
        root.addWidget(splitter, stretch=1)

        # Panel izquierdo
        left = QWidget(); left_lay = QVBoxLayout(left)
        left.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        filters_box = QGroupBox("Buscar ítems")
        filters_lay = QHBoxLayout(filters_box)
        self.category_filter = QComboBox(); self.category_filter.currentIndexChanged.connect(self._search_items)
        self.category_filter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.search_edit = QLineEdit(); self.search_edit.setPlaceholderText("Escribe código o nombre…")
        self.search_edit.textChanged.connect(self._search_items)
        btn_refresh = QPushButton("Refrescar"); btn_refresh.clicked.connect(self._search_items)

        filters_lay.addWidget(QLabel("Categoría:"))
        filters_lay.addWidget(self.category_filter, stretch=2)
        filters_lay.addWidget(QLabel("Texto:"))
        filters_lay.addWidget(self.search_edit, stretch=3)
        filters_lay.addWidget(btn_refresh)
        left_lay.addWidget(filters_box)

        # Results table (uses ResultsTable to support drag)
        self.results_table = ResultsTable(0, 5)
        self.results_table.setHorizontalHeaderLabels(["Código", "Nombre", "Unidad", "Precio", "Categoría"])
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.results_table.setColumnHidden(4, True)
        self.results_table.itemDoubleClicked.connect(self._on_result_double_clicked)
        self.results_table.currentCellChanged.connect(self._on_results_current_changed)
        self.results_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(self._on_results_context_menu)
        self._apply_results_column_layout()
        left_lay.addWidget(self.results_table, stretch=1)

        # Panel derecho
        right = QWidget(); right_lay = QVBoxLayout(right)
        right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        controls_box = QGroupBox("Detalle de selección")
        controls_form = QFormLayout(controls_box)
        self.qty_edit = QLineEdit("1"); self.qty_edit.setValidator(QDoubleValidator(0.0, 1e9, 4, self))
        self.price_edit = QLineEdit(""); self.price_edit.setValidator(QDoubleValidator(0.0, 1e12, 4, self))
        btn_add = QPushButton("Agregar al carrito"); btn_add.clicked.connect(self._add_selected_to_cart)
        btn_manage = QPushButton("Gestionar Ítems…"); btn_manage.clicked.connect(self._open_items_management)
        row_btns = QHBoxLayout(); row_btns.addWidget(btn_add); row_btns.addWidget(btn_manage)
        controls_form.addRow("Cantidad:", self.qty_edit)
        controls_form.addRow("Precio:", self.price_edit)
        controls_form.addRow(row_btns)
        right_lay.addWidget(controls_box)

        cart_box = QGroupBox("Ítems seleccionados")
        cart_lay = QVBoxLayout(cart_box)
        # CartTable accepts drops and delegates to self._add_item_by_code
        self.cart_table = CartTable(self._add_item_by_code, 0, 6)
        self.cart_table.setHorizontalHeaderLabels(["Código", "Descripción", "Unidad", "Cantidad", "Precio Unitario", "Subtotal"])
        cart_header = self.cart_table.horizontalHeader()
        cart_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        cart_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.cart_table.verticalHeader().setVisible(False)
        self.cart_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cart_table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.SelectedClicked)
        self.cart_table.setItemDelegateForColumn(3, NumericItemDelegate(4, self.cart_table))
        self.cart_table.setItemDelegateForColumn(4, NumericItemDelegate(4, self.cart_table))
        self.cart_table.itemChanged.connect(self._on_cart_item_changed)
        self.cart_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        cart_lay.addWidget(self.cart_table)
        self._apply_cart_column_layout()

        cart_bottom = QHBoxLayout()
        self.cart_total_label = QLabel("Total carrito: 0.00")
        cart_bottom.addWidget(self.cart_total_label)
        cart_bottom.addStretch(1)
        btn_remove = QPushButton("Quitar seleccionado"); btn_remove.clicked.connect(self._remove_selected_cart)
        btn_clear = QPushButton("Vaciar carrito"); btn_clear.clicked.connect(self._clear_cart)
        cart_bottom.addWidget(btn_remove); cart_bottom.addWidget(btn_clear)
        cart_lay.addLayout(cart_bottom)
        right_lay.addWidget(cart_box, stretch=1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # Botonera pie
        actions = QHBoxLayout()
        actions.addStretch(1)
        ok = QPushButton("Aceptar"); ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancelar"); cancel.clicked.connect(self.reject)
        actions.addWidget(ok); actions.addWidget(cancel)
        root.addLayout(actions)

    # ------- Ajuste de columnas -------
    def _apply_results_column_layout(self):
        fm = QFontMetrics(self.results_table.font())
        code_w = fm.horizontalAdvance("999999") + 24
        unit_w = fm.horizontalAdvance("UNID") + 24
        price_w = fm.horizontalAdvance("9,999,999.99") + 28

        header = self.results_table.horizontalHeader()
        header.resizeSection(0, max(80, code_w))
        header.resizeSection(2, max(60, unit_w))
        header.resizeSection(3, max(110, price_w))
        self.results_table.setColumnHidden(4, True)

    def _apply_cart_column_layout(self):
        fm = QFontMetrics(self.cart_table.font())
        code_w = fm.horizontalAdvance("999999") + 24
        unit_w = fm.horizontalAdvance("UNID") + 24
        qty_w = fm.horizontalAdvance("9999.99") + 24
        price_w = fm.horizontalAdvance("9,999,999.99") + 28
        subtotal_w = price_w + 10

        header = self.cart_table.horizontalHeader()
        header.resizeSection(0, max(80, code_w))
        header.resizeSection(2, max(60, unit_w))
        header.resizeSection(3, max(80, qty_w))
        header.resizeSection(4, max(110, price_w))
        header.resizeSection(5, max(120, subtotal_w))

    # ------- Persistencia de geometría -------
    def _restore_geometry(self):
        s = QSettings("FACOT", "ItemPickerDialog")
        geom = s.value("geometry", None)
        if geom:
            try:
                self.restoreGeometry(geom)
            except Exception:
                pass

    def _save_geometry(self):
        s = QSettings("FACOT", "ItemPickerDialog")
        s.setValue("geometry", self.saveGeometry())

    def accept(self):
        self._save_geometry()
        super().accept()

    def reject(self):
        self._save_geometry()
        super().reject()

    # ------- Datos auxiliares -------
    def _load_categories(self):
        self.categories.clear()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("Todas", None)

        # Try to load categories from backend if available
        loaded = False
        try:
            if self.logic and hasattr(self.logic, "get_all_categories"):
                cats = self.logic.get_all_categories() or []
                for c in cats:
                    cid = c.get("id")
                    name = c.get("name") or c.get("nombre") or ""
                    prefix = c.get("code_prefix") or c.get("prefix") or ""
                    self.categories.append((cid, name, prefix))
                    self.category_filter.addItem(f"{name} ({prefix})", cid)
                loaded = True
        except Exception:
            loaded = False

        if not loaded:
            db = get_db_path()
            if db:
                with sqlite3.connect(db) as conn:
                    rows = conn.execute(
                        "SELECT id, IFNULL(name,''), IFNULL(code_prefix,'') FROM categories ORDER BY name"
                    ).fetchall()
                for cid, name, prefix in rows:
                    self.categories.append((cid, name, prefix))
                    self.category_filter.addItem(f"{name} ({prefix})", cid)

        self.category_filter.blockSignals(False)

    # ------- Acciones -------
    def _open_items_management(self):
        # Pass backend if ItemsManagementWindow supports it (it does in your repo)
        try:
            if self.logic:
                dlg = ItemsManagementWindow(self, backend=self.logic)
            else:
                dlg = ItemsManagementWindow(self)
        except TypeError:
            dlg = ItemsManagementWindow(self)
        dlg.exec()
        current_cid = self.category_filter.currentData()
        self._load_categories()
        if current_cid:
            idx = self.category_filter.findData(current_cid)
            if idx >= 0:
                self.category_filter.setCurrentIndex(idx)
        self._search_items()

    def _search_items(self):
        text_raw = (self.search_edit.text() or "").strip()
        text = text_raw.lower()
        sel_cid = self.category_filter.currentData()  # Puede ser None

        rows: List[Tuple[str, str, str, float, str]] = []  # (code, name, unit, price, category_name)
        backend_items: List[Dict[str, Any]] = []
        used_backend = False

        # 1) Intentar backend
        try:
            if self.logic and hasattr(self.logic, "get_items_like"):
                # get_items_like(query, limit) — algunos backends no filtran por categoría
                backend_items = self.logic.get_items_like(text_raw or "", limit=500) or []
                used_backend = True
            elif self.logic and hasattr(self.logic, "get_all_items"):
                backend_items = self.logic.get_all_items() or []
                used_backend = True
        except Exception as e:
            print(f"[ItemPicker] Backend error get_items: {e}")
            backend_items = []
            used_backend = False

        def _norm_item_dict(it: Dict[str, Any]) -> Dict[str, Any]:
            # Normaliza campos del backend a un esquema común
            return {
                "code": (it.get("code") or it.get("codigo") or "").strip(),
                "name": (it.get("name") or it.get("nombre") or "").strip(),
                "unit": (it.get("unit") or it.get("unidad") or "").strip(),
                "price": float(it.get("price") or it.get("precio") or 0.0),
                "category_id": it.get("category_id") if "category_id" in it else it.get("categoria_id"),
                "category_name": (it.get("category_name") or it.get("nombre_categoria") or "").strip(),
            }

        # 2) Si hubo backend, construir rows y aplicar filtros client-side si es necesario
        if used_backend and backend_items:
            normalized = [_norm_item_dict(it) for it in backend_items]

            # Filtro por texto (code, name, category_name)
            if text:
                normalized = [
                    it for it in normalized
                    if (it["code"].lower().find(text) != -1)
                    or (it["name"].lower().find(text) != -1)
                    or (it["category_name"].lower().find(text) != -1)
                ]

            # Filtro por categoría si tenemos ID
            if sel_cid is not None:
                normalized = [
                    it for it in normalized
                    if (it["category_id"] == sel_cid)
                ]

            # Map a tu tabla
            rows = [(it["code"], it["name"], it["unit"], it["price"], it["category_name"]) for it in normalized]

        # 3) Si no hay rows del backend, usar SQLite con filtro server-side
        if not rows:
            db = get_db_path()
            if not db:
                QMessageBox.warning(self, "Base de datos", "No hay base de datos seleccionada.")
                return
            try:
                with sqlite3.connect(db) as conn:
                    cur = conn.cursor()
                    base_q = """
                        SELECT i.code, IFNULL(i.name,''), IFNULL(i.unit,''), IFNULL(i.price,0), IFNULL(c.name,'')
                        FROM items i
                        LEFT JOIN categories c ON c.id = i.category_id
                        WHERE 1=1
                    """
                    params: List[Any] = []
                    if text:
                        base_q += " AND (LOWER(i.code) LIKE ? OR LOWER(i.name) LIKE ? OR LOWER(IFNULL(c.name,'')) LIKE ?)"
                        like = f"%{text}%"
                        params.extend([like, like, like])
                    if sel_cid is not None:
                        base_q += " AND i.category_id = ?"
                        params.append(sel_cid)
                    base_q += " ORDER BY i.name LIMIT 500"
                    cur.execute(base_q, params)
                    rows = cur.fetchall()
            except Exception as e:
                QMessageBox.critical(self, "BD", f"Error consultando ítems:\n{e}")
                return

        # 4) Poblar la tabla de resultados
        self.results_table.setRowCount(0)
        for r, row in enumerate(rows):
            self.results_table.insertRow(r)
            for c, val in enumerate(row):
                if c == 3:
                    # precio formateado
                    try:
                        val = f"{float(val or 0.0):.2f}"
                    except Exception:
                        val = "0.00"
                self.results_table.setItem(r, c, QTableWidgetItem(str(val)))

        self._apply_results_column_layout()


    def _on_result_double_clicked(self, item: QTableWidgetItem):
        if not item:
            return
        r = item.row()
        code_it = self.results_table.item(r, 0)
        if not code_it:
            return
        old_code = code_it.text()
        dlg = ItemEditDialog(old_code, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            updated = dlg.get_result()
            self._search_items()
            self._reselect_result_by_code(updated.get("code") or old_code)
            self._update_cart_rows_after_edit(updated.get("original_code") or old_code, updated)

    def _reselect_result_by_code(self, code: str):
        if not code:
            return
        for r in range(self.results_table.rowCount()):
            it = self.results_table.item(r, 0)
            if it and it.text() == code:
                self.results_table.selectRow(r)
                self._on_results_current_changed(r, 0, -1, -1)
                break

    def _on_results_current_changed(self, cur_row: int, cur_col: int, prev_row: int, prev_col: int):
        try:
            if cur_row < 0:
                return
            price_cell = self.results_table.item(cur_row, 3)
            price_def = float(price_cell.text()) if price_cell and price_cell.text() else 0.0
            self.price_edit.setText(f"{price_def:.2f}")
            self.qty_edit.setText("1")
        except Exception:
            pass

    def _add_selected_to_cart_quick(self, row: int, col: int):
        self._add_selected_to_cart(default_qty=True)

    def _add_selected_to_cart(self, default_qty: bool = False):
        r = self.results_table.currentRow()
        if r < 0:
            QMessageBox.information(self, "Selección", "Selecciona un ítem en la lista de resultados.")
            return
        code = self.results_table.item(r, 0).text()
        self._add_item_by_code(code, default_qty=default_qty)

    def _add_item_by_code(self, code: str, default_qty: bool = False):
        """
        Agrega al carrito el ítem con código dado. Si el source table has price/unit,
        usamos esos valores; else, consultamos backend or sqlite for full item details.
        """
        if not code:
            return
        # Try to find the item in results_table first (fast)
        found = None
        for r in range(self.results_table.rowCount()):
            it = self.results_table.item(r, 0)
            if it and it.text() == code:
                name = self.results_table.item(r, 1).text() if self.results_table.item(r, 1) else ""
                unit = self.results_table.item(r, 2).text() if self.results_table.item(r, 2) else ""
                try:
                    price = float(self.results_table.item(r, 3).text().replace(",", "")) if self.results_table.item(r, 3) else 0.0
                except Exception:
                    price = 0.0
                found = {"code": code, "name": name, "unit": unit, "price": price}
                break

        # If not found in table, try backend lookups
        if not found:
            try:
                if self.logic and hasattr(self.logic, "get_item_by_code"):
                    it = self.logic.get_item_by_code(code)
                    if it:
                        found = {
                            "code": it.get("code") or it.get("codigo") or "",
                            "name": it.get("name") or it.get("nombre") or "",
                            "unit": it.get("unit") or it.get("unidad") or "",
                            "price": float(it.get("price") or it.get("precio") or 0.0)
                        }
                elif self.logic and hasattr(self.logic, "get_items_like"):
                    # search exact
                    its = self.logic.get_items_like(code, limit=5) or []
                    for it in its:
                        if (it.get("code") or "").upper() == code.upper():
                            found = {
                                "code": it.get("code") or "",
                                "name": it.get("name") or "",
                                "unit": it.get("unit") or "",
                                "price": float(it.get("price") or 0.0)
                            }
                            break
            except Exception:
                found = None

        # Fallback to sqlite
        if not found:
            db = get_db_path()
            if db:
                with sqlite3.connect(db) as conn:
                    row = conn.execute(
                        "SELECT code, IFNULL(name,''), IFNULL(unit,''), IFNULL(price,0) FROM items WHERE code = ?",
                        (code,)
                    ).fetchone()
                if row:
                    found = {"code": row[0], "name": row[1], "unit": row[2], "price": float(row[3] or 0.0)}

        if not found:
            QMessageBox.warning(self, "Ítem", f"No se encontró el ítem con código '{code}'.")
            return

        # Determine qty and price
        try:
            qty = 1.0 if default_qty else float(self.qty_edit.text().replace(",", ".") or "1")
            price_input = (self.price_edit.text() or "").replace(",", ".")
            price = found.get("price", 0.0)
            if not default_qty and price_input.strip() != "":
                price = float(price_input)
        except Exception:
            QMessageBox.warning(self, "Validación", "Cantidad y Precio deben ser numéricos.")
            return

        if qty <= 0:
            QMessageBox.warning(self, "Validación", "La cantidad debe ser mayor a cero.")
            return
        if price < 0:
            QMessageBox.warning(self, "Validación", "El precio no puede ser negativo.")
            return

        code = found.get("code", "")
        name = found.get("name", "")
        unit = found.get("unit", "")

        # Merge into cart (same code as original)
        found_row = -1
        for i in range(self.cart_table.rowCount()):
            it = self.cart_table.item(i, 0)
            if it and it.text() == code:
                found_row = i
                break
        if found_row >= 0:
            old_qty = float(self.cart_table.item(found_row, 3).text().replace(",", ""))
            new_qty = old_qty + qty
            self._updating_cart = True
            self.cart_table.setItem(found_row, 3, QTableWidgetItem(f"{new_qty:.2f}"))
            self.cart_table.setItem(found_row, 4, QTableWidgetItem(f"{price:.2f}"))
            self.cart_table.setItem(found_row, 5, QTableWidgetItem(f"{new_qty * price:.2f}"))
            self._updating_cart = False
        else:
            row = self.cart_table.rowCount()
            self.cart_table.insertRow(row)
            self.cart_table.setItem(row, 0, QTableWidgetItem(code))
            self.cart_table.setItem(row, 1, QTableWidgetItem(name))
            self.cart_table.setItem(row, 2, QTableWidgetItem(unit))
            self.cart_table.setItem(row, 3, QTableWidgetItem(f"{qty:.2f}"))
            self.cart_table.setItem(row, 4, QTableWidgetItem(f"{price:.2f}"))
            self.cart_table.setItem(row, 5, QTableWidgetItem(f"{qty * price:.2f}"))

        self.qty_edit.setText("1")
        self._update_cart_total()

    def _on_cart_item_changed(self, item: QTableWidgetItem):
        if self._updating_cart:
            return
        row = item.row()
        col = item.column()
        if col not in (3, 4):
            return
        try:
            qty = float(self.cart_table.item(row, 3).text().replace(",", "")) if self.cart_table.item(row, 3) else 0.0
            price = float(self.cart_table.item(row, 4).text().replace(",", "")) if self.cart_table.item(row, 4) else 0.0
        except Exception:
            qty = 0.0; price = 0.0
        qty = max(0.0, qty); price = max(0.0, price)
        self._updating_cart = True
        self.cart_table.setItem(row, 3, QTableWidgetItem(f"{qty:.2f}"))
        self.cart_table.setItem(row, 4, QTableWidgetItem(f"{price:.2f}"))
        self.cart_table.setItem(row, 5, QTableWidgetItem(f"{qty * price:.2f}"))
        self._updating_cart = False
        self._update_cart_total()

    def _remove_selected_cart(self):
        r = self.cart_table.currentRow()
        if r >= 0:
            self.cart_table.removeRow(r)
            self._update_cart_total()

    def _clear_cart(self):
        self.cart_table.setRowCount(0)
        self._update_cart_total()

    def _update_cart_total(self):
        total = 0.0
        for r in range(self.cart_table.rowCount()):
            try:
                val = float(self.cart_table.item(r, 5).text().replace(",", "")) if self.cart_table.item(r, 5) else 0.0
            except Exception:
                val = 0.0
            total += val
        self.cart_total_label.setText(f"Total carrito: {total:,.2f}")

    def _update_cart_rows_after_edit(self, old_code: str, updated: Dict):
        if not updated:
            return
        new_code = updated.get("code", old_code)
        new_name = updated.get("name", "")
        new_unit = updated.get("unit", "")
        new_price = float(updated.get("price", 0.0) or 0.0)

        for r in range(self.cart_table.rowCount()):
            code_it = self.cart_table.item(r, 0)
            if not code_it:
                continue
            if code_it.text() == old_code:
                self.cart_table.setItem(r, 0, QTableWidgetItem(new_code))
                if new_name:
                    self.cart_table.setItem(r, 1, QTableWidgetItem(new_name))
                if new_unit:
                    self.cart_table.setItem(r, 2, QTableWidgetItem(new_unit))
                if new_price >= 0:
                    try:
                        qty = float(self.cart_table.item(r, 3).text().replace(",", ""))
                    except Exception:
                        qty = 0.0
                    self.cart_table.setItem(r, 4, QTableWidgetItem(f"{new_price:.2f}"))
                    self.cart_table.setItem(r, 5, QTableWidgetItem(f"{qty * new_price:.2f}"))
        self._update_cart_total()

    def get_selected_items(self) -> List[Dict]:
        items: List[Dict] = []
        for r in range(self.cart_table.rowCount()):
            code = self.cart_table.item(r, 0).text()
            name = self.cart_table.item(r, 1).text()
            unit = self.cart_table.item(r, 2).text()
            qty = float(self.cart_table.item(r, 3).text().replace(",", ""))
            price = float(self.cart_table.item(r, 4).text().replace(",", ""))
            subtotal = float(self.cart_table.item(r, 5).text().replace(",", ""))
            items.append({
                "code": code,
                "name": name,
                "unit": unit,
                "quantity": qty,
                "unit_price": price,
                "subtotal": subtotal,
            })
        return items

    def _on_results_context_menu(self, pos):
        index = self.results_table.indexAt(pos)
        if not index.isValid():
            return

        row = index.row()
        try:
            self.results_table.selectRow(row)
            self.results_table.setCurrentCell(row, 0)
            self._on_results_current_changed(row, 0, -1, -1)
        except Exception:
            pass

        menu = QMenu(self)
        act_add = QAction("Agregar al carrito", self)
        act_edit = QAction("Editar ítem…", self)

        act_add.triggered.connect(lambda: self._add_selected_to_cart(default_qty=True))
        act_edit.triggered.connect(self._edit_selected_result)

        menu.addAction(act_add)
        menu.addSeparator()
        menu.addAction(act_edit)

        global_pos = self.results_table.viewport().mapToGlobal(pos)
        menu.exec(global_pos)

    def _edit_selected_result(self):
        r = self.results_table.currentRow()
        if r < 0:
            QMessageBox.information(self, "Selección", "Selecciona un ítem para editar.")
            return
        code_it = self.results_table.item(r, 0)
        if not code_it:
            return

        old_code = code_it.text()
        dlg = ItemEditDialog(old_code, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            updated = dlg.get_result()
            self._search_items()
            self._reselect_result_by_code(updated.get("code") or old_code)
            self._update_cart_rows_after_edit(updated.get("original_code") or old_code, updated)