"""
Diálogo de Configuración de Firebase para FACOT.

Permite al usuario seleccionar el archivo de credenciales JSON de Firebase
y configurar el bucket de Storage.
"""

import os
import json
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QFileDialog, QMessageBox, QGroupBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class FirebaseConfigDialog(QDialog):
    """
    Diálogo para configurar las credenciales de Firebase.
    
    Permite:
    - Seleccionar archivo JSON de credenciales (service account)
    - Configurar el bucket de Storage
    - Validar credenciales antes de guardar
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración de Firebase")
        self.setModal(True)
        self.setMinimumWidth(550)
        self.setMinimumHeight(300)
        
        self._credentials_path = ""
        self._storage_bucket = ""
        
        self._init_ui()
        self._load_existing_config()
    
    def _init_ui(self):
        """Construye la interfaz del diálogo."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Título
        title = QLabel("🔥 Configuración de Firebase")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Descripción
        desc = QLabel(
            "Para conectar FACOT con Firebase, necesitas un archivo de credenciales\n"
            "(Service Account JSON) de tu proyecto Firebase."
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)
        
        # Grupo de credenciales
        cred_group = QGroupBox("Credenciales")
        cred_layout = QVBoxLayout()
        
        # Ruta del archivo JSON
        cred_label = QLabel("Archivo de credenciales (JSON):")
        cred_layout.addWidget(cred_label)
        
        cred_row = QHBoxLayout()
        self.cred_edit = QLineEdit()
        self.cred_edit.setPlaceholderText("Selecciona el archivo firebase-credentials.json")
        self.cred_edit.setReadOnly(True)
        cred_row.addWidget(self.cred_edit)
        
        btn_browse = QPushButton("📂 Seleccionar...")
        btn_browse.clicked.connect(self._browse_credentials)
        cred_row.addWidget(btn_browse)
        cred_layout.addLayout(cred_row)
        
        cred_group.setLayout(cred_layout)
        layout.addWidget(cred_group)
        
        # Grupo de Storage
        storage_group = QGroupBox("Storage")
        storage_layout = QVBoxLayout()
        
        bucket_label = QLabel("Bucket de Storage:")
        storage_layout.addWidget(bucket_label)
        
        self.bucket_edit = QLineEdit()
        self.bucket_edit.setPlaceholderText("proyecto-id.firebasestorage.app")
        storage_layout.addWidget(self.bucket_edit)
        
        bucket_hint = QLabel(
            "💡 Se autocompleta al seleccionar las credenciales. "
            "Formato: {project_id}.firebasestorage.app"
        )
        bucket_hint.setProperty("muted", True)
        bucket_hint.setWordWrap(True)
        storage_layout.addWidget(bucket_hint)
        
        storage_group.setLayout(storage_layout)
        layout.addWidget(storage_group)
        
        # Botones de acción
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        btn_cancel = QPushButton("❌ Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        
        btn_test = QPushButton("🔍 Validar conexión")
        btn_test.clicked.connect(self._test_connection)
        btn_layout.addWidget(btn_test)
        
        btn_save = QPushButton("💾 Guardar y conectar")
        btn_save.clicked.connect(self._save_and_accept)
        btn_save.setDefault(True)
        btn_layout.addWidget(btn_save)
        
        layout.addLayout(btn_layout)
    
    def _load_existing_config(self):
        """Carga la configuración existente si la hay."""
        try:
            import facot_config
            if hasattr(facot_config, 'get_firebase_config'):
                cred_path, bucket = facot_config.get_firebase_config()
                if cred_path:
                    self.cred_edit.setText(cred_path)
                    self._credentials_path = cred_path
                if bucket:
                    self.bucket_edit.setText(bucket)
                    self._storage_bucket = bucket
        except Exception:
            pass
    
    def _browse_credentials(self):
        """Abre diálogo para seleccionar archivo de credenciales."""
        start_dir = os.path.expanduser("~")
        if self._credentials_path and os.path.exists(os.path.dirname(self._credentials_path)):
            start_dir = os.path.dirname(self._credentials_path)
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar credenciales de Firebase",
            start_dir,
            "Archivos JSON (*.json);;Todos los archivos (*.*)"
        )
        
        if file_path:
            self.cred_edit.setText(file_path)
            self._credentials_path = file_path
            
            # Intentar extraer project_id y autocompletar bucket
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    cred_data = json.load(f)
                    project_id = cred_data.get('project_id', '')
                    
                    if project_id:
                        suggested_bucket = f"{project_id}.firebasestorage.app"
                        if not self.bucket_edit.text():
                            self.bucket_edit.setText(suggested_bucket)
                            self._storage_bucket = suggested_bucket
                        
                        QMessageBox.information(
                            self,
                            "Credenciales detectadas",
                            f"Proyecto: {project_id}\n"
                            f"Bucket sugerido: {suggested_bucket}"
                        )
            except json.JSONDecodeError:
                QMessageBox.warning(
                    self, 
                    "Archivo inválido", 
                    "El archivo seleccionado no es un JSON válido."
                )
            except Exception as e:
                print(f"[FIREBASE] Error leyendo credenciales: {e}")
    
    def _test_connection(self):
        """Valida la conexión con Firebase."""
        cred_path = self.cred_edit.text().strip()
        bucket = self.bucket_edit.text().strip()
        
        if not cred_path:
            QMessageBox.warning(self, "Error", "Selecciona un archivo de credenciales.")
            return
        
        if not os.path.exists(cred_path):
            QMessageBox.warning(self, "Error", "El archivo de credenciales no existe.")
            return
        
        if not bucket:
            QMessageBox.warning(self, "Error", "Ingresa el nombre del bucket de Storage.")
            return
        
        try:
            # Intentar cargar las credenciales
            with open(cred_path, 'r', encoding='utf-8') as f:
                cred_data = json.load(f)
            
            # Validar campos requeridos
            required_fields = ['type', 'project_id', 'private_key', 'client_email']
            missing = [f for f in required_fields if f not in cred_data]
            
            if missing:
                QMessageBox.warning(
                    self,
                    "Credenciales incompletas",
                    f"El archivo de credenciales no contiene los campos requeridos:\n"
                    f"{', '.join(missing)}\n\n"
                    "Asegúrate de usar un archivo de Service Account válido."
                )
                return
            
            if cred_data.get('type') != 'service_account':
                QMessageBox.warning(
                    self,
                    "Tipo de credencial inválido",
                    "El archivo debe ser de tipo 'service_account'.\n"
                    "Descarga las credenciales desde Firebase Console > "
                    "Configuración > Service accounts > Generate new private key."
                )
                return
            
            QMessageBox.information(
                self,
                "✓ Credenciales válidas",
                f"Las credenciales parecen correctas.\n\n"
                f"Proyecto: {cred_data.get('project_id')}\n"
                f"Email: {cred_data.get('client_email')}"
            )
            
        except json.JSONDecodeError:
            QMessageBox.critical(self, "Error", "El archivo no es un JSON válido.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al validar credenciales:\n{str(e)}")
    
    def _save_and_accept(self):
        """Guarda la configuración y cierra el diálogo."""
        cred_path = self.cred_edit.text().strip()
        bucket = self.bucket_edit.text().strip()
        
        if not cred_path:
            QMessageBox.warning(self, "Error", "Selecciona un archivo de credenciales.")
            return
        
        if not os.path.exists(cred_path):
            QMessageBox.warning(self, "Error", "El archivo de credenciales no existe.")
            return
        
        if not bucket:
            QMessageBox.warning(self, "Error", "Ingresa el nombre del bucket de Storage.")
            return
        
        self._credentials_path = cred_path
        self._storage_bucket = bucket
        
        # Guardar en config
        try:
            import facot_config
            if hasattr(facot_config, 'set_firebase_config'):
                facot_config.set_firebase_config(cred_path, bucket)
        except Exception as e:
            print(f"[FIREBASE] Error guardando configuración: {e}")
        
        self.accept()
    
    def get_credentials_path(self) -> str:
        """Retorna la ruta del archivo de credenciales."""
        return self._credentials_path
    
    def get_storage_bucket(self) -> str:
        """Retorna el nombre del bucket de Storage."""
        return self._storage_bucket


def show_firebase_config_dialog(parent=None) -> bool:
    """
    Muestra el diálogo de configuración de Firebase.
    
    Args:
        parent: Widget padre
    
    Returns:
        True si el usuario aceptó y guardó la configuración
    """
    dialog = FirebaseConfigDialog(parent)
    result = dialog.exec()
    return result == QDialog.DialogCode.Accepted
