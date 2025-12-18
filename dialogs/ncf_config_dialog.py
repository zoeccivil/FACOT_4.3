"""
Diálogo de configuración de secuencias NCF y vencimiento de facturas.
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView, QDateEdit,
    QGroupBox, QGridLayout, QComboBox
)
from PyQt6.QtCore import Qt, QDate

logger = logging.getLogger(__name__)

# Prefijos NCF soportados
NCF_PREFIXES = ["B01", "B02", "B14", "B15", "B16", "E31"]

# Mapeo de prefijo a nombre descriptivo
PREFIX_NAMES = {
    "B01": "Crédito Fiscal",
    "B02": "Consumidor Final",
    "B14": "Régimen Especial",
    "B15": "Gubernamental",
    "B16": "Exportación",
    "E31": "e-CF Consumidor Final"
}


class NCFConfigDialog(QDialog):
    """
    Diálogo para configurar:
    - Secuencias NCF por empresa y prefijo
    - Vencimiento fijo de facturas por empresa
    """
    
    def __init__(self, logic, parent=None):
        super().__init__(parent)
        self.logic = logic
        self.current_company_id = None
        self.setWindowTitle("Configuración de NCF y Vencimientos")
        self.setMinimumSize(800, 600)
        self._build_ui()
        self._load_companies()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        # Selector de empresa
        company_group = QGroupBox("Empresa")
        company_layout = QHBoxLayout(company_group)
        company_layout.addWidget(QLabel("Seleccionar empresa:"))
        self.company_combo = QComboBox()
        self.company_combo.currentIndexChanged.connect(self._on_company_changed)
        company_layout.addWidget(self.company_combo, 1)
        layout.addWidget(company_group)
        
        # Vencimiento fijo
        due_group = QGroupBox("Vencimiento Fijo de Facturas")
        due_layout = QGridLayout(due_group)
        due_layout.addWidget(QLabel("Fecha de vencimiento fija (opcional):"), 0, 0)
        self.due_date_edit = QDateEdit()
        self.due_date_edit.setCalendarPopup(True)
        self.due_date_edit.setDate(QDate.currentDate())
        self.due_date_edit.setSpecialValueText("Sin fecha fija")
        due_layout.addWidget(self.due_date_edit, 0, 1)
        
        btn_clear_due = QPushButton("Limpiar")
        btn_clear_due.clicked.connect(lambda: self.due_date_edit.setDate(QDate()))
        due_layout.addWidget(btn_clear_due, 0, 2)
        
        btn_save_due = QPushButton("Guardar Vencimiento")
        btn_save_due.clicked.connect(self._save_due_date)
        due_layout.addWidget(btn_save_due, 0, 3)
        
        layout.addWidget(due_group)
        
        # Tabla de secuencias NCF
        seq_group = QGroupBox("Secuencias NCF")
        seq_layout = QVBoxLayout(seq_group)
        
        seq_layout.addWidget(QLabel("Configure el último número asignado para cada tipo de comprobante:"))
        
        self.seq_table = QTableWidget(0, 4)
        self.seq_table.setHorizontalHeaderLabels(["Prefijo", "Descripción", "Última Secuencia", "Próximo NCF (Preview)"])
        self.seq_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.seq_table.verticalHeader().setVisible(False)
        seq_layout.addWidget(self.seq_table)
        
        btn_row = QHBoxLayout()
        btn_save_seq = QPushButton("Guardar Secuencias")
        btn_save_seq.clicked.connect(self._save_sequences)
        btn_row.addStretch()
        btn_row.addWidget(btn_save_seq)
        seq_layout.addLayout(btn_row)
        
        layout.addWidget(seq_group)
        
        # Botón cerrar
        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)
    
    def _load_companies(self):
        """Carga la lista de empresas."""
        self.company_combo.clear()
        try:
            companies = []
            if hasattr(self.logic, 'get_all_companies'):
                companies = self.logic.get_all_companies()
            elif hasattr(self.logic, 'data_access') and self.logic.data_access:
                companies = self.logic.data_access.get_all_companies()
            
            for comp in companies:
                comp_id = comp.get('id')
                comp_name = comp.get('name', f'Empresa {comp_id}')
                self.company_combo.addItem(comp_name, comp_id)
        except Exception as e:
            logger.exception("Error cargando empresas: %s", e)
            QMessageBox.warning(self, "Error", f"No se pudieron cargar las empresas:\n{e}")
    
    def _on_company_changed(self, index):
        """Se ejecuta cuando cambia la empresa seleccionada."""
        if index < 0:
            self.current_company_id = None
            return
        
        self.current_company_id = self.company_combo.itemData(index)
        company_name = self.company_combo.currentText()
        print(f"[NCF-CONFIG] Empresa cambiada: id={self.current_company_id}, nombre={company_name}")
        
        # Cargar datos de la empresa
        self._load_company_data()
    
    def _load_company_data(self):
        """Carga vencimiento y secuencias de la empresa actual."""
        if not self.current_company_id:
            return
        
        # Cargar vencimiento fijo
        try:
            due_date_str = ""
            if hasattr(self.logic, 'get_company_due_date'):
                due_date_str = self.logic.get_company_due_date(self.current_company_id)
            elif hasattr(self.logic, 'get_company_invoice_due_date'):
                due_date_str = self.logic.get_company_invoice_due_date(self.current_company_id)
            
            if due_date_str:
                try:
                    parts = due_date_str.split('-')
                    if len(parts) == 3:
                        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                        self.due_date_edit.setDate(QDate(y, m, d))
                except Exception:
                    pass
        except Exception as e:
            logger.exception("Error cargando vencimiento: %s", e)
        
        # Cargar secuencias NCF
        self._load_sequences()
    
    def _load_sequences(self):
        """Carga las secuencias NCF actuales."""
        self.seq_table.setRowCount(0)

        if not self.current_company_id:
            return

        # Asegurar company_id numérico cuando sea posible
        try:
            cid = int(self.current_company_id)
        except Exception:
            cid = self.current_company_id

        for prefix in NCF_PREFIXES:
            row = self.seq_table.rowCount()
            self.seq_table.insertRow(row)

            # Prefijo
            self.seq_table.setItem(row, 0, QTableWidgetItem(prefix))

            # Descripción
            desc = PREFIX_NAMES.get(prefix, prefix)
            self.seq_table.setItem(row, 1, QTableWidgetItem(desc))

            # Última secuencia (si el backend devuelve None/str, normalizar a int)
            last_seq = 0
            try:
                if hasattr(self.logic, 'get_ncf_last_seq'):
                    try:
                        val = self.logic.get_ncf_last_seq(cid, prefix)
                        # val puede venir como int o str; intentar normalizar
                        if val is None or val == "":
                            last_seq = 0
                        else:
                            try:
                                last_seq = int(val)
                            except Exception:
                                # intentar extraer últimos dígitos con regex
                                import re
                                m = re.search(r"(\d+)$", str(val))
                                last_seq = int(m.group(1)) if m else 0
                    except Exception as e:
                        logger.exception("Error obteniendo secuencia para %s: %s", prefix, e)
                        last_seq = 0
            except Exception as e:
                logger.exception("Error obteniendo secuencia wrapper para %s: %s", prefix, e)
                last_seq = 0

            seq_item = QTableWidgetItem(str(last_seq))
            seq_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            # permitir edición por el usuario
            seq_item.setFlags(seq_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.seq_table.setItem(row, 2, seq_item)

            # Preview del próximo NCF
            preview = ""
            try:
                if hasattr(self.logic, 'get_ncf_preview'):
                    try:
                        preview = self.logic.get_ncf_preview(cid, prefix) or ""
                    except Exception as e:
                        logger.exception("Error obteniendo preview para %s: %s", prefix, e)
                        preview = ""
            except Exception as e:
                logger.exception("Error en preview wrapper para %s: %s", prefix, e)
                preview = ""

            preview_item = QTableWidgetItem(preview)
            preview_item.setFlags(preview_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            preview_item.setForeground(Qt.GlobalColor.darkGray)
            self.seq_table.setItem(row, 3, preview_item)
        
    def _save_due_date(self):
        """Guarda el vencimiento fijo de facturas."""
        if not self.current_company_id:
            QMessageBox.warning(self, "Empresa", "Seleccione una empresa primero.")
            return
        
        due_date = self.due_date_edit.date()
        if not due_date.isValid() or due_date.isNull():
            due_str = ""
        else:
            due_str = due_date.toString("yyyy-MM-dd")
        
        try:
            print(f"[NCF-CONFIG] Intentando guardar vencimiento: empresa={self.current_company_id}, fecha={due_str}")
            
            success = False
            if hasattr(self.logic, 'set_company_due_date'):
                success = self.logic.set_company_due_date(self.current_company_id, due_str)
                print(f"[NCF-CONFIG] set_company_due_date: OK={success}")
            elif hasattr(self.logic, 'update_company_fields'):
                self.logic.update_company_fields(self.current_company_id, {"invoice_due_date": due_str})
                success = True
                print(f"[NCF-CONFIG] update_company_fields: OK=True")
            
            if success:
                QMessageBox.information(self, "Vencimiento", "Fecha de vencimiento guardada correctamente.")
            else:
                QMessageBox.warning(self, "Vencimiento", "No se pudo guardar la fecha de vencimiento.")
        except Exception as e:
            logger.exception("Error guardando vencimiento: %s", e)
            QMessageBox.critical(self, "Error", f"Error al guardar vencimiento:\n{e}")
    
    def _save_sequences(self):
            """Guarda las secuencias NCF forzando commit de editores y validando tipos."""
            if not self.current_company_id:
                QMessageBox.warning(self, "Empresa", "Seleccione una empresa primero.")
                return

            cid = self.current_company_id

            # 1. FORZAR COMMIT: Quitar foco y cerrar editores activos para que el valor pase al modelo
            self.seq_table.setFocus() 
            current_item = self.seq_table.currentItem()
            if current_item:
                self.seq_table.closePersistentEditor(current_item)
            self.seq_table.setCurrentCell(-1, -1) # Deseleccionar todo fuerza commit

            try:
                any_changed = False
                for row in range(self.seq_table.rowCount()):
                    prefix_item = self.seq_table.item(row, 0)
                    seq_item = self.seq_table.item(row, 2)

                    if not prefix_item or not seq_item:
                        continue

                    prefix = (prefix_item.text() or "").strip()
                    seq_text = (seq_item.text() or "").strip()

                    # Limpieza robusta de input (por si pegan texto)
                    import re
                    nums = re.findall(r'\d+', seq_text)
                    if not nums:
                        # Si está vacío o es inválido, ignorar o asumir 0 si se desea
                        continue
                    
                    # Tomamos el último grupo de dígitos (útil si pegaron B010000100)
                    seq_val_int = int(nums[-1]) 

                    # Guardar en Backend
                    if hasattr(self.logic, 'set_ncf_last_seq'):
                        # Asegurar que cid es int si el backend lo requiere así
                        try:
                            cid_int = int(cid)
                        except:
                            cid_int = cid 
                            
                        result = self.logic.set_ncf_last_seq(cid_int, prefix, seq_val_int)
                        if result:
                            any_changed = True
                            print(f"[NCF-CONFIG] Guardado OK: {cid_int} {prefix} -> {seq_val_int}")
                        else:
                            print(f"[NCF-CONFIG] Falló guardado: {cid_int} {prefix}")

                if any_changed:
                    QMessageBox.information(self, "Secuencias", "Secuencias guardadas correctamente.")
                    self._load_sequences() # Recargar para verificar persistencia visualmente
                    
                    # Notificar a la app principal si es posible para refrescar pestañas
                    try:
                        main_window = self.parent()
                        if hasattr(main_window, 'invoice_tab') and main_window.invoice_tab:
                            main_window.invoice_tab.refresh_after_ncf_config()
                    except:
                        pass
                else:
                    QMessageBox.information(self, "Secuencias", "No se detectaron cambios o error al guardar.")

            except Exception as e:
                logger.exception("Error guardando secuencias: %s", e)
                QMessageBox.critical(self, "Error", f"Excepción al guardar:\n{e}")