from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton, QFileDialog,
    QHBoxLayout, QListWidget, QMessageBox, QInputDialog
)
import facot_config

class SettingsWindow(QDialog):
    def __init__(self, logic, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración por Empresa")
        self.setMinimumSize(600, 600)
        self.logic = logic  # Debe ser instancia de LogicController

        self._build_ui()
        self._load_companies()
        self._load_settings_for_active_company()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Selector de empresa
        self.company_selector = QComboBox()
        self.company_selector.currentIndexChanged.connect(self._load_settings_for_selected_company)
        layout.addWidget(QLabel("Empresa:"))
        layout.addWidget(self.company_selector)

        # Datos básicos
        self.name_edit = QLineEdit()
        self.rnc_edit = QLineEdit()
        self.address_edit = QLineEdit()
        layout.addWidget(QLabel("Nombre:")); layout.addWidget(self.name_edit)
        layout.addWidget(QLabel("RNC:")); layout.addWidget(self.rnc_edit)
        layout.addWidget(QLabel("Dirección:")); layout.addWidget(self.address_edit)

        # Plantilla de factura
        self.template_edit = QLineEdit()
        btn_template = QPushButton("Seleccionar plantilla")
        btn_template.clicked.connect(self._select_template)
        hlayout_template = QHBoxLayout()
        hlayout_template.addWidget(QLabel("Ruta de plantilla:"))
        hlayout_template.addWidget(self.template_edit)
        hlayout_template.addWidget(btn_template)
        layout.addLayout(hlayout_template)

        # Carpeta de salida
        self.output_edit = QLineEdit()
        btn_output = QPushButton("Seleccionar carpeta salida")
        btn_output.clicked.connect(self._select_output)
        hlayout_output = QHBoxLayout()
        hlayout_output.addWidget(QLabel("Carpeta de salida:"))
        hlayout_output.addWidget(self.output_edit)
        hlayout_output.addWidget(btn_output)
        layout.addLayout(hlayout_output)

        # Carpeta de descargas (origen)
        self.downloads_edit = QLineEdit()
        btn_downloads = QPushButton("Seleccionar carpeta descargas")
        btn_downloads.clicked.connect(self._select_downloads)
        hlayout_downloads = QHBoxLayout()
        hlayout_downloads.addWidget(QLabel("Carpeta de descargas:"))
        hlayout_downloads.addWidget(self.downloads_edit)
        hlayout_downloads.addWidget(btn_downloads)
        layout.addLayout(hlayout_downloads)

        # Carpeta de anexos (destino)
        self.attachments_edit = QLineEdit()
        btn_attachments = QPushButton("Seleccionar carpeta anexos")
        btn_attachments.clicked.connect(self._select_attachments)
        hlayout_attachments = QHBoxLayout()
        hlayout_attachments.addWidget(QLabel("Carpeta de anexos:"))
        hlayout_attachments.addWidget(self.attachments_edit)
        hlayout_attachments.addWidget(btn_attachments)
        layout.addLayout(hlayout_attachments)

        # Monedas por empresa
        layout.addWidget(QLabel("Monedas permitidas para esta empresa:"))
        self.currency_list = QListWidget()
        layout.addWidget(self.currency_list)
        btn_add_currency = QPushButton("Añadir moneda")
        btn_add_currency.clicked.connect(self._add_currency)
        btn_remove_currency = QPushButton("Eliminar moneda seleccionada")
        btn_remove_currency.clicked.connect(self._remove_currency)
        layout.addWidget(btn_add_currency)
        layout.addWidget(btn_remove_currency)

        # Sección de Backups y Firebase
        layout.addWidget(QLabel(""))  # Espaciador
        layout.addWidget(QLabel("Backups y Firebase:"))
        
        hlayout_backups = QHBoxLayout()
        btn_backup_now = QPushButton("📦 Crear backup ahora")
        btn_backup_now.clicked.connect(self._create_backup_now)
        hlayout_backups.addWidget(btn_backup_now)
        
        btn_open_backups = QPushButton("📂 Abrir carpeta de backups")
        btn_open_backups.clicked.connect(self._open_backups_folder)
        hlayout_backups.addWidget(btn_open_backups)
        
        btn_firebase_config = QPushButton("🔥 Configurar Firebase")
        btn_firebase_config.clicked.connect(self._configure_firebase)
        hlayout_backups.addWidget(btn_firebase_config)
        
        layout.addLayout(hlayout_backups)

        # Botones de acción
        btn_save = QPushButton("Guardar configuración")
        btn_save.clicked.connect(self._save_settings)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        hlayout_action = QHBoxLayout()
        hlayout_action.addWidget(btn_cancel)
        hlayout_action.addWidget(btn_save)
        layout.addLayout(hlayout_action)

    def _load_companies(self):
        companies = self.logic.get_all_companies()
        self.companies = {}
        self.company_selector.clear()
        for c in companies:
            name = c["name"]
            rnc = c["rnc"]
            self.companies[name] = rnc
            self.company_selector.addItem(name)
        # Selecciona la empresa activa si existe
        empresa_activa = facot_config.get_empresa_activa()
        if empresa_activa:
            for idx, name in enumerate(self.companies):
                if self.companies[name] == empresa_activa:
                    self.company_selector.setCurrentIndex(idx)
                    break

    def _load_settings_for_selected_company(self):
        name = self.company_selector.currentText()
        company_id = self.companies.get(name)
        if not company_id:
            return
        empresa_cfg = facot_config.get_empresa_config(company_id)
        self.name_edit.setText(empresa_cfg.get("nombre", name))
        self.rnc_edit.setText(company_id)
        self.address_edit.setText(empresa_cfg.get("direccion", ""))
        self.template_edit.setText(empresa_cfg.get("ruta_plantilla", ""))
        self.output_edit.setText(empresa_cfg.get("carpeta_salida", ""))
        self.downloads_edit.setText(empresa_cfg.get("carpeta_origen", ""))
        self.attachments_edit.setText(empresa_cfg.get("carpeta_destino", ""))
        self.currency_list.clear()
        for moneda in empresa_cfg.get("monedas", []):
            self.currency_list.addItem(moneda)

    def _load_settings_for_active_company(self):
        # Solo para iniciar con la empresa activa
        self._load_settings_for_selected_company()

    def _select_template(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Selecciona la plantilla de factura", "", "Archivos Excel (*.xlsx);;Todos los archivos (*)")
        if filename:
            self.template_edit.setText(filename)

    def _select_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Selecciona la carpeta de salida")
        if folder:
            self.output_edit.setText(folder)

    def _select_downloads(self):
        folder = QFileDialog.getExistingDirectory(self, "Selecciona la carpeta de descargas")
        if folder:
            self.downloads_edit.setText(folder)

    def _select_attachments(self):
        folder = QFileDialog.getExistingDirectory(self, "Selecciona la carpeta de anexos")
        if folder:
            self.attachments_edit.setText(folder)

    def _add_currency(self):
        moneda, ok = QInputDialog.getText(self, "Añadir moneda", "Introduce el símbolo de la moneda:")
        if ok and moneda and moneda.strip():
            if moneda.upper() not in [self.currency_list.item(i).text() for i in range(self.currency_list.count())]:
                self.currency_list.addItem(moneda.upper())

    def _remove_currency(self):
        selected = self.currency_list.currentRow()
        if selected >= 0:
            self.currency_list.takeItem(selected)

    def _save_settings(self):
        name = self.company_selector.currentText()
        company_id = self.companies.get(name)
        if not company_id:
            QMessageBox.warning(self, "Error", "No se pudo determinar la empresa activa.")
            return
        empresa_cfg = {
            "nombre": self.name_edit.text(),
            "direccion": self.address_edit.text(),
            "ruta_plantilla": self.template_edit.text(),
            "carpeta_salida": self.output_edit.text(),
            "carpeta_origen": self.downloads_edit.text(),
            "carpeta_destino": self.attachments_edit.text(),
            "monedas": [self.currency_list.item(i).text() for i in range(self.currency_list.count())]
        }
        facot_config.set_empresa_config(company_id, empresa_cfg)
        facot_config.set_empresa_activa(company_id)
        QMessageBox.information(self, "Configuración", "Configuración guardada correctamente.")
        self.accept()

    def _create_backup_now(self):
        """Crea un backup manual ahora."""
        try:
            from utils.backups import create_backup
            result = create_backup()
            
            if result['success']:
                QMessageBox.information(
                    self,
                    "Backup completado",
                    f"Backup creado exitosamente.\n\n"
                    f"Ubicación: {result.get('backup_path', 'N/A')}\n"
                    f"Colecciones: {len(result.get('collections', {}))}"
                )
            else:
                QMessageBox.warning(
                    self,
                    "Backup con errores",
                    f"El backup se completó con algunos errores:\n\n"
                    f"{', '.join(result.get('errors', ['Error desconocido']))}"
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error de backup",
                f"No se pudo crear el backup:\n\n{str(e)}"
            )

    def _open_backups_folder(self):
        """Abre la carpeta de backups en el explorador de archivos."""
        import os
        import subprocess
        import platform
        
        backup_dir = facot_config.get_backup_config().get('backup_dir', './backups')
        backup_path = os.path.abspath(backup_dir)
        
        # Crear la carpeta si no existe
        os.makedirs(backup_path, exist_ok=True)
        
        try:
            if platform.system() == 'Windows':
                os.startfile(backup_path)
            elif platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', backup_path])
            else:  # Linux
                subprocess.run(['xdg-open', backup_path])
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error",
                f"No se pudo abrir la carpeta:\n{backup_path}\n\nError: {str(e)}"
            )

    def _configure_firebase(self):
        """Abre el diálogo de configuración de Firebase."""
        try:
            from dialogs.firebase_config_dialog import FirebaseConfigDialog
            
            dialog = FirebaseConfigDialog(self)
            result = dialog.exec()
            
            if result == 1:  # Accepted
                QMessageBox.information(
                    self,
                    "Firebase configurado",
                    "La configuración de Firebase se ha guardado.\n"
                    "Los cambios tomarán efecto la próxima vez que inicie la aplicación."
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"No se pudo abrir la configuración de Firebase:\n\n{str(e)}"
            )