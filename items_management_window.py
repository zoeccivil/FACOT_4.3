from __future__ import annotations

import re
import traceback
from typing import Optional, Tuple, List, Dict, Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDoubleValidator, QAction, QFontMetrics
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView, QWidget, QFormLayout,
    QTextEdit, QSpinBox, QFileDialog, QSizePolicy, QProgressDialog, QMenu
)

# Excel (Opcional)
try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.worksheet.datavalidation import DataValidation
except Exception:
    Workbook = None
    load_workbook = None
    DataValidation = None

CODE_PAD = 4  # ABC0001

# -------------------- Utilidades UI -------------------- #
def _slug_letters(text: str, n: int = 3) -> str:
    letters = re.findall(r"[A-Za-z]", text)
    if not letters:
        return "CAT"
    return "".join(letters[:n]).upper().ljust(n, "X")

# -------------------- Diálogo de Categoría -------------------- #
class CategoryDialog(QDialog):
    def __init__(self, category: Optional[Dict]=None, parent: Optional[QWidget]=None):
        super().__init__(parent)
        self.setWindowTitle("Categoría")
        # category es un dict: {'id', 'name', 'code_prefix', 'next_seq', 'description'}
        self.category = category 
        self._build_ui()
        if category:
            self._load(category)

    def _build_ui(self):
        root = QVBoxLayout(self)

        # Barra de categorías
        cat_bar = QHBoxLayout()
        cat_bar.addWidget(QLabel("Categoría:"))

        self.cat_combo = QComboBox()
        self.cat_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cat_combo.currentIndexChanged.connect(self._on_category_changed)
        cat_bar.addWidget(self.cat_combo, stretch=6)

        self.btn_new_cat = QPushButton("Nueva")
        self.btn_edit_cat = QPushButton("Editar")
        self.btn_del_cat = QPushButton("Eliminar")
        self.btn_new_cat.clicked.connect(self._new_category)
        self.btn_edit_cat.clicked.connect(self._edit_category)
        self.btn_del_cat.clicked.connect(self._delete_category)
        cat_bar.addWidget(self.btn_new_cat)
        cat_bar.addWidget(self.btn_edit_cat)
        cat_bar.addWidget(self.btn_del_cat)
        root.addLayout(cat_bar)

        # Acciones de ítem
        actions = QHBoxLayout()
        self.btn_new_item = QPushButton("Nuevo Ítem")
        self.btn_edit_item = QPushButton("Editar Ítem")
        self.btn_del_item = QPushButton("Eliminar Ítem")
        self.btn_new_item.clicked.connect(self._new_item)
        self.btn_edit_item.clicked.connect(self._edit_item)
        self.btn_del_item.clicked.connect(self._delete_item)

        actions.addWidget(self.btn_new_item)
        actions.addWidget(self.btn_edit_item)
        actions.addWidget(self.btn_del_item)
        root.addLayout(actions)

        # Búsqueda
        search_bar = QHBoxLayout()
        search_bar.addWidget(QLabel("Buscar:"))
        self.search_edit = QLineEdit(); self.search_edit.setPlaceholderText("Código, nombre o categoría…")
        # Conectar de forma robusta: la señal textChanged emite el texto; aceptamos el parámetro en el filtro
        self.search_edit.textChanged.connect(self._filter_items_table) # _filter_items_table acepta arg opcional
        search_bar.addWidget(self.search_edit)
        root.addLayout(search_bar)

        # Tabla
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["#", "Código", "Nombre", "UD", "Costo", "Precio Venta", "Categoría", "Descripción"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # Mostrar descripción (antes la ocultabas); si quieres ocultarla pon True
        self.table.setColumnHidden(7, False)
        self.table.itemDoubleClicked.connect(lambda *_: self._edit_item())
        
        root.addWidget(self.table)

    def _on_name_change(self, text: str):
        # Sugerir prefijo solo si es nuevo y el campo está vacío
        if not self.category and not self.prefix_edit.text():
            self.prefix_edit.setText(_slug_letters(text, 3))

    def _load(self, cat):
        self.name_edit.setText(cat.get("name", ""))
        self.prefix_edit.setText(cat.get("code_prefix") or _slug_letters(cat.get("name", "")))
        self.seq_spin.setValue(int(cat.get("next_seq", 1)))
        self.desc_edit.setPlainText(cat.get("description", ""))

    def get_data(self) -> Optional[Dict]:
        name = self.name_edit.text().strip()
        prefix = self.prefix_edit.text().strip().upper()
        seq = int(self.seq_spin.value())
        desc = self.desc_edit.toPlainText().strip()
        
        if not name:
            QMessageBox.warning(self, "Validación", "El nombre es obligatorio.")
            return None
        if not re.fullmatch(r"[A-Z0-9]{2,6}", prefix or ""):
            QMessageBox.warning(self, "Validación", "El prefijo debe tener entre 2 y 6 caracteres alfanuméricos en mayúscula.")
            return None
            
        return {
            "name": name,
            "code_prefix": prefix,
            "next_seq": seq,
            "description": desc
        }

# -------------------- Diálogo de Ítem -------------------- #
class ItemDialog(QDialog):
    def __init__(self, categories: list, item: Optional[dict]=None, suggested_code: str=None, parent: Optional[QWidget]=None):
        super().__init__(parent)
        self.setWindowTitle("Ítem")
        self.categories = categories  # Lista de dicts o tuplas
        self.item = item
        self.suggested_code_func = None # Callback para pedir sugerencias dinámicas
        self.initial_suggestion = suggested_code
        self._build_ui()
        
        if item:
            self._load(item)
        else:
            self._update_code_preview()

    def _build_ui(self):
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.cat_combo = QComboBox()
        self.cat_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        # Llenar combo categorías
        for cat in self.categories:
            # cat puede ser dict o tuple, normalizamos
            if isinstance(cat, dict):
                cid = cat.get('id')
                name = cat.get('name')
                prefix = cat.get('code_prefix')
            else: # tuple (compatibilidad)
                cid, name, prefix, _, _ = cat
                
            self.cat_combo.addItem(f"{name} ({prefix})", cid)
            
        self.cat_combo.currentIndexChanged.connect(self._update_code_preview)

        self.auto_code = QComboBox()
        self.auto_code.addItems(["Automático", "Manual"])
        self.auto_code.currentIndexChanged.connect(self._on_code_mode_change)

        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("Código (si Manual)")
        self.code_edit.setEnabled(False)

        self.name_edit = QLineEdit()
        self.unit_combo = QComboBox()
        self.unit_combo.setEditable(True)
        self.unit_combo.addItems(["UND", "SERV", "HR", "M", "M2", "M3", "KG", "LT", "PAQ"])

        self.cost_edit = QLineEdit(); self.cost_edit.setValidator(QDoubleValidator(0.0, 1e12, 4))
        self.price_edit = QLineEdit(); self.price_edit.setValidator(QDoubleValidator(0.0, 1e12, 4))
        self.desc_edit = QTextEdit()

        self.next_code_label = QLabel("Siguiente código: -")

        code_row = QHBoxLayout()
        code_row.addWidget(self.auto_code)
        code_row.addWidget(self.code_edit)
        code_cont = QWidget(); code_cont.setLayout(code_row)

        form.addRow("Categoría:", self.cat_combo)
        form.addRow("Código:", code_cont)
        form.addRow("Sugerencia:", self.next_code_label)
        form.addRow("Nombre:", self.name_edit)
        form.addRow("Unidad:", self.unit_combo)
        form.addRow("Costo:", self.cost_edit)
        form.addRow("Precio:", self.price_edit)
        form.addRow("Descripción:", self.desc_edit)
        lay.addLayout(form)

        btns = QHBoxLayout()
        ok = QPushButton("Guardar"); ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancelar"); cancel.clicked.connect(self.reject)
        btns.addWidget(ok); btns.addWidget(cancel)
        lay.addLayout(btns)

    def _on_code_mode_change(self, idx: int):
        manual = (self.auto_code.currentText() == "Manual")
        self.code_edit.setEnabled(manual)
        self._update_code_preview()

    def _update_code_preview(self):
        # Esta lógica simplificada asume que el padre pasará el código si es nuevo
        # En una app real, aquí llamaríamos a un callback al backend
        suggestion = self.initial_suggestion if not self.item else "-"
        self.next_code_label.setText(f"Siguiente código (aprox): {suggestion or '-'}")
        
        if self.auto_code.currentText() == "Automático":
            self.code_edit.setText("")

    def _load(self, item: dict):
        idx = self.cat_combo.findData(item.get("category_id"))
        if idx >= 0:
            self.cat_combo.setCurrentIndex(idx)
            
        # Si ya tiene código, ponemos modo manual para mostrarlo, pero indicando que es fijo
        self.auto_code.setCurrentText("Manual") 
        self.code_edit.setEnabled(True) # Permitir editar si se desea cambiar (avanzado)
        self.code_edit.setText(item.get("code", ""))
        
        self.name_edit.setText(item.get("name", ""))
        
        unit = item.get("unit", "UND")
        uidx = self.unit_combo.findText(unit)
        if uidx >= 0:
            self.unit_combo.setCurrentIndex(uidx)
        else:
            self.unit_combo.setEditText(unit)
            
        self.cost_edit.setText(str(item.get("cost", 0)))
        self.price_edit.setText(str(item.get("price", 0)))
        self.desc_edit.setPlainText(item.get("description", ""))

    def get_data(self) -> Optional[dict]:
        cid = self.cat_combo.currentData()
        if not cid:
            QMessageBox.warning(self, "Validación", "Seleccione una categoría.")
            return None
            
        name = self.name_edit.text().strip()
        unit = self.unit_combo.currentText().strip().upper()
        try:
            cost = float(self.cost_edit.text().replace(",", ".") or 0)
            price = float(self.price_edit.text().replace(",", ".") or 0)
        except ValueError:
            QMessageBox.warning(self, "Validación", "Costo y Precio deben ser numéricos.")
            return None
            
        manual = (self.auto_code.currentText() == "Manual")
        code = self.code_edit.text().strip().upper()
        
        if manual and not code:
            QMessageBox.warning(self, "Validación", "Ingrese un código o use Automático.")
            return None
            
        return {
            "category_id": cid,
            "code": code if manual else None,
            "name": name,
            "unit": unit,
            "cost": cost,
            "price": price,
            "description": self.desc_edit.toPlainText().strip(),
            "manual_code": manual
        }

# -------------------- Ventana Principal -------------------- #
class ItemsManagementWindow(QDialog):
    def __init__(self, parent=None, backend: Optional[Any] = None):
        super().__init__(parent)
        print("\n[DEBUG-ITEMS] --- Inicializando ItemsManagementWindow ---")
        self.setWindowTitle("Gestión de Ítems y Categorías")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setSizeGripEnabled(True)
        self.setMinimumSize(1120, 640)

        # Resolver backend
        self.backend = backend
        if not self.backend:
             print("[DEBUG-ITEMS] Backend no proporcionado en constructor, buscando en padre...")
             # (Lógica simplificada de búsqueda en padre si es necesario, 
             #  pero idealmente se pasa desde el main/parent)
             if parent and hasattr(parent, 'logic'):
                 self.backend = parent.logic
        
        print(f"[DEBUG-ITEMS] Backend resuelto: {self.backend}")

        self._categories_cache = []
        self._items_cache = []

        self._build_ui()
        
        # Cargar datos iniciales
        self._load_categories()
        self._load_items()

    def _build_ui(self):
        root = QVBoxLayout(self)

        # Barra de categorías
        cat_bar = QHBoxLayout()
        cat_bar.addWidget(QLabel("Categoría:"))

        self.cat_combo = QComboBox()
        self.cat_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cat_combo.currentIndexChanged.connect(self._on_category_changed)
        cat_bar.addWidget(self.cat_combo, stretch=6)

        self.btn_new_cat = QPushButton("Nueva")
        self.btn_edit_cat = QPushButton("Editar")
        self.btn_del_cat = QPushButton("Eliminar")
        self.btn_new_cat.clicked.connect(self._new_category)
        self.btn_edit_cat.clicked.connect(self._edit_category)
        self.btn_del_cat.clicked.connect(self._delete_category)
        cat_bar.addWidget(self.btn_new_cat)
        cat_bar.addWidget(self.btn_edit_cat)
        cat_bar.addWidget(self.btn_del_cat)
        root.addLayout(cat_bar)

        # Acciones de ítem
        actions = QHBoxLayout()
        self.btn_new_item = QPushButton("Nuevo Ítem")
        self.btn_edit_item = QPushButton("Editar Ítem")
        self.btn_del_item = QPushButton("Eliminar Ítem")
        self.btn_new_item.clicked.connect(self._new_item)
        self.btn_edit_item.clicked.connect(self._edit_item)
        self.btn_del_item.clicked.connect(self._delete_item)

        actions.addWidget(self.btn_new_item)
        actions.addWidget(self.btn_edit_item)
        actions.addWidget(self.btn_del_item)
        root.addLayout(actions)

        # Búsqueda
        search_bar = QHBoxLayout()
        search_bar.addWidget(QLabel("Buscar:"))
        self.search_edit = QLineEdit(); self.search_edit.setPlaceholderText("Código, nombre o categoría…")
        self.search_edit.textChanged.connect(self._filter_items_table) # Filtrado local
        search_bar.addWidget(self.search_edit)
        root.addLayout(search_bar)

        # Tabla
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["#", "Código", "Nombre", "UD", "Costo", "Precio Venta", "Categoría", "Descripción"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setColumnHidden(7, True)
        self.table.itemDoubleClicked.connect(lambda *_: self._edit_item())
        
        root.addWidget(self.table)

    # -------------------------
    # Carga de Datos (FIREBASE/BACKEND ONLY)
    # -------------------------
    def _load_categories(self):
        print("[DEBUG-ITEMS] Cargando categorías desde backend...")
        if not self.backend or not hasattr(self.backend, 'get_all_categories'):
            print("[DEBUG-ITEMS] Backend no soporta get_all_categories")
            return

        try:
            raw_cats = self.backend.get_all_categories() or []
            print(f"[DEBUG-ITEMS] Categorías recibidas: {len(raw_cats)}")
            
            # Normalizar
            self._categories_cache = []
            for c in raw_cats:
                self._categories_cache.append({
                    "id": c.get('id'),
                    "name": c.get('name', ''),
                    "code_prefix": c.get('code_prefix', ''),
                    "next_seq": c.get('next_seq', 1),
                    "description": c.get('description', '')
                })
            
            # Actualizar combo
            self.cat_combo.blockSignals(True)
            self.cat_combo.clear()
            self.cat_combo.addItem("Todas", None)
            for c in self._categories_cache:
                self.cat_combo.addItem(f"{c['name']} ({c['code_prefix']})", c['id'])
            self.cat_combo.blockSignals(False)
            
        except Exception as e:
            print(f"[DEBUG-ITEMS] Error cargando categorías: {e}")
            traceback.print_exc()

    def _load_items(self):
        print("[DEBUG-ITEMS] Cargando ítems desde backend...")
        if not self.backend or not hasattr(self.backend, 'get_all_items'):
            print("[DEBUG-ITEMS] Backend no soporta get_all_items")
            return

        try:
            raw_items = self.backend.get_all_items() or []
            print(f"[DEBUG-ITEMS] Ítems recibidos: {len(raw_items)}")
            
            self._items_cache = []
            # Crear mapa de ID categoria -> Nombre
            cat_map = {c['id']: c['name'] for c in self._categories_cache}
            
            for it in raw_items:
                cat_id = it.get('category_id')
                cat_name = cat_map.get(cat_id, "Desconocida")
                
                self._items_cache.append({
                    "id": it.get('id'),
                    "code": it.get('code', ''),
                    "name": it.get('name', ''),
                    "unit": it.get('unit', ''),
                    "cost": float(it.get('cost', 0)),
                    "price": float(it.get('price', 0)),
                    "category_id": cat_id,
                    "category_name": cat_name,
                    "description": it.get('description', '')
                })
                
            self._filter_items_table()
            
        except Exception as e:
            print(f"[DEBUG-ITEMS] Error cargando ítems: {e}")
            traceback.print_exc()

    def _filter_items_table(self, _=None):
        """Filtra y repinta la tabla basándose en el cache local.
        Acepta un parámetro opcional porque textChanged emite el texto.
        """
        try:
            search = (self.search_edit.text() or "").lower().strip()
            cat_filter_id = self.cat_combo.currentData()  # None si es "Todas"
            
            self.table.setRowCount(0)
            
            filtered = []
            for it in self._items_cache:
                # Filtro por categoría - COMPARACIÓN ROBUSTA (Str vs Str)
                if cat_filter_id is not None:
                    # Convertimos ambos a string para asegurar coincidencia "1" == 1
                    if str(it.get('category_id', '')) != str(cat_filter_id):
                        continue
                
                # Filtro por texto
                if search:
                    txt = f"{it.get('code','')} {it.get('name','')} {it.get('category_name','')}".lower()
                    if search not in txt:
                        continue
                
                filtered.append(it)
            
            # Pintar
            for idx, it in enumerate(filtered, 1):
                row = self.table.rowCount()
                self.table.insertRow(row)
                
                # Guardamos el ID real en el item 0
                item_id_widget = QTableWidgetItem(str(idx))
                item_id_widget.setData(Qt.ItemDataRole.UserRole, it['id']) # ID real
                
                self.table.setItem(row, 0, item_id_widget)
                self.table.setItem(row, 1, QTableWidgetItem(it.get('code','') or ""))
                self.table.setItem(row, 2, QTableWidgetItem(it.get('name','') or ""))
                self.table.setItem(row, 3, QTableWidgetItem(it.get('unit','') or "UND"))
                try:
                    self.table.setItem(row, 4, QTableWidgetItem(f"{float(it.get('cost',0)):,.2f}"))
                except Exception:
                    self.table.setItem(row, 4, QTableWidgetItem("0.00"))
                try:
                    self.table.setItem(row, 5, QTableWidgetItem(f"{float(it.get('price',0)):,.2f}"))
                except Exception:
                    self.table.setItem(row, 5, QTableWidgetItem("0.00"))
                self.table.setItem(row, 6, QTableWidgetItem(it.get('category_name','') or ""))
                self.table.setItem(row, 7, QTableWidgetItem(it.get('description','') or ""))
        except Exception as e:
            print(f"[DEBUG-ITEMS] Error en _filter_items_table: {e}")
            traceback.print_exc()

    def _on_category_changed(self, idx):
        self._filter_items_table()

    # -------------------------
    # Operaciones CRUD (Delegando a Backend)
    # -------------------------
    def _new_category(self):
        dlg = CategoryDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if data and self.backend:
                try:
                    # Asumimos que el backend tiene add_category
                    if hasattr(self.backend, 'add_category'):
                        self.backend.add_category(data)
                        QMessageBox.information(self, "Éxito", "Categoría creada.")
                        self._load_categories()
                    else:
                        QMessageBox.warning(self, "Error", "El backend no soporta crear categorías.")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error al crear categoría: {e}")

    def _edit_category(self):
        cid = self.cat_combo.currentData()
        if not cid:
            return
            
        # Buscar datos en cache
        cat_data = next((c for c in self._categories_cache if str(c['id']) == str(cid)), None)
        if not cat_data:
            return

        dlg = CategoryDialog(category=cat_data, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if data and self.backend:
                try:
                    if hasattr(self.backend, 'update_category'):
                        self.backend.update_category(cid, data)
                        QMessageBox.information(self, "Éxito", "Categoría actualizada.")
                        self._load_categories()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error al actualizar: {e}")

    def _delete_category(self):
        cid = self.cat_combo.currentData()
        if not cid: return
        
        confirm = QMessageBox.question(self, "Confirmar", "¿Eliminar categoría?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.Yes and self.backend:
            try:
                if hasattr(self.backend, 'delete_category'):
                    self.backend.delete_category(cid)
                    self._load_categories()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error al eliminar: {e}")

    def _new_item(self):
        # Para el diálogo necesitamos las categorías
        cats = self._categories_cache
        dlg = ItemDialog(cats, parent=self)
        
        # Preseleccionar la categoría activa si hay una
        curr_cid = self.cat_combo.currentData()
        if curr_cid:
            idx = dlg.cat_combo.findData(curr_cid)
            if idx >= 0: dlg.cat_combo.setCurrentIndex(idx)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if data and self.backend:
                # Generación de código automática si es necesario
                if not data['code'] and hasattr(self.backend, 'generate_next_item_code'):
                    try:
                        data['code'] = self.backend.generate_next_item_code(data['category_id'])
                    except Exception as e:
                        print(f"Error generando código: {e}")
                        # Fallback simple
                        import time
                        data['code'] = f"GEN{int(time.time())}"

                try:
                    if hasattr(self.backend, 'add_item'):
                        self.backend.add_item(data)
                        self._load_items()
                    else:
                        QMessageBox.warning(self, "Error", "Backend no soporta crear ítems.")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error al crear ítem: {e}")

    def _edit_item(self):
        row = self.table.currentRow()
        if row < 0: return
        
        # Recuperar ID real del item
        item_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        # Buscar en cache
        item_data = next((i for i in self._items_cache if i['id'] == item_id), None)
        if not item_data: return

        dlg = ItemDialog(self._categories_cache, item=item_data, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if data and self.backend:
                try:
                    if hasattr(self.backend, 'update_item'):
                        self.backend.update_item(item_id, data)
                        self._load_items()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error al actualizar: {e}")

    def _delete_item(self):
        row = self.table.currentRow()
        if row < 0: return
        item_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        confirm = QMessageBox.question(self, "Confirmar", "¿Eliminar ítem?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.Yes and self.backend:
            try:
                if hasattr(self.backend, 'delete_item'):
                    self.backend.delete_item(item_id)
                    self._load_items()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error al eliminar: {e}")