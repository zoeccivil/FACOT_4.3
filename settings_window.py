# (reemplaza el archivo settings_window.py por este)
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton, QFileDialog,
    QHBoxLayout, QMessageBox, QGroupBox, QTabWidget, QWidget
)
from PyQt6.QtCore import Qt
import facot_config

# Intentional safe import: CompanyManagementWindow may exist or not
try:
    from company_management_window import CompanyManagementWindow
except Exception:
    CompanyManagementWindow = None


class SettingsWindow(QDialog):
    def __init__(self, backend, parent=None):
        """
        backend: puede ser LogicController (SQLite), FirebaseDataAccess, o HybridLogicWrapper.
                 Se asume que provee get_all_companies() y get_company_details(company_id).
        """
        super().__init__(parent)
        self.setWindowTitle("Configuración")
        self.setMinimumSize(700, 650)
        self.backend = backend  # puede ser logic o hybrid wrapper

        # Build UI and load initial data
        self._build_ui()
        self._load_companies()
        self._load_settings_for_selected_company()

    def _build_ui(self):
        """Build UI with tabs for organization"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Tabs for better organization
        tabs = QTabWidget()

        # Tab 1: Apariencia
        appearance_tab = self._build_appearance_tab()
        tabs.addTab(appearance_tab, "Apariencia")

        # Tab 2: Empresa (light summary + launcher to full manager)
        company_tab = self._build_company_tab()
        tabs.addTab(company_tab, "Empresa")

        # Tab 3: Rutas y Archivos
        paths_tab = self._build_paths_tab()
        tabs.addTab(paths_tab, "Rutas y Archivos")

        # Tab 4: Backups y Firebase
        advanced_tab = self._build_advanced_tab()
        tabs.addTab(advanced_tab, "Avanzado")

        layout.addWidget(tabs)

        # Botones de acción
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("Guardar")
        btn_save.clicked.connect(self._save_settings)
        btn_row.addWidget(btn_save)

        layout.addLayout(btn_row)

    def _build_appearance_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Theme selector
        theme_group = QGroupBox("Tema de la Aplicación")
        theme_layout = QVBoxLayout(theme_group)

        desc_label = QLabel("Selecciona el tema visual de FACOT:")
        desc_label.setProperty("muted", True)
        theme_layout.addWidget(desc_label)

        self.theme_selector = QComboBox()
        self.theme_selector.setMinimumWidth(300)

        # FACOT Professional theme is now the only theme (applied globally in main.py)
        # Keeping selector for future multi-theme support
        try:
            # Add FACOT Professional theme
            self.theme_selector.addItem("FACOT Professional", "facot-professional")
            self.theme_selector.setCurrentIndex(0)
            
            # Disable selector since we only have one theme now
            self.theme_selector.setEnabled(False)
            
            # Note: Theme changes will require app restart to take effect
            # Connect change handler for future use
            self.theme_selector.currentIndexChanged.connect(self._on_theme_changed)

        except Exception as e:
            QMessageBox.warning(self, "Advertencia", f"No se pudieron cargar los temas: {e}")
            self.theme_selector.setEnabled(False)

        theme_layout.addWidget(QLabel("Tema:"))
        theme_layout.addWidget(self.theme_selector)

        themes_info = QLabel(
            "<b>Modern Midnight:</b> Tema oscuro moderno para uso prolongado<br>"
            "<b>FACOT Light Pro:</b> Tema claro profesional para ambientes iluminados"
        )
        themes_info.setProperty("muted", True)
        themes_info.setWordWrap(True)
        theme_layout.addWidget(themes_info)

        layout.addWidget(theme_group)
        layout.addStretch(1)

        return widget

    def _build_company_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Company selector
        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("Empresa:"))
        self.company_selector = QComboBox()
        self.company_selector.currentIndexChanged.connect(self._load_settings_for_selected_company)
        sel_row.addWidget(self.company_selector)
        layout.addLayout(sel_row)

        # Basic info (read-only summary)
        info_row1 = QHBoxLayout()
        info_row1.addWidget(QLabel("Nombre:"))
        self.summary_name = QLineEdit()
        self.summary_name.setReadOnly(True)
        info_row1.addWidget(self.summary_name)
        info_row1.addWidget(QLabel("RNC:"))
        self.summary_rnc = QLineEdit()
        self.summary_rnc.setReadOnly(True)
        info_row1.addWidget(self.summary_rnc)
        layout.addLayout(info_row1)

        info_row2 = QHBoxLayout()
        info_row2.addWidget(QLabel("Teléfono:"))
        self.summary_phone = QLineEdit()
        self.summary_phone.setReadOnly(True)
        info_row2.addWidget(self.summary_phone)
        info_row2.addWidget(QLabel("Email:"))
        self.summary_email = QLineEdit()
        self.summary_email.setReadOnly(True)
        info_row2.addWidget(self.summary_email)
        layout.addLayout(info_row2)

        # Invoice due date summary
        info_row3 = QHBoxLayout()
        info_row3.addWidget(QLabel("Vencimiento fijo (facturas):"))
        self.summary_due = QLineEdit()
        self.summary_due.setReadOnly(True)
        info_row3.addWidget(self.summary_due)
        layout.addLayout(info_row3)

        # Buttons: open full manager and refresh
        btn_row = QHBoxLayout()
        btn_open_mgr = QPushButton("Abrir gestor completo de empresas")
        btn_open_mgr.clicked.connect(self._open_company_manager_full)
        btn_row.addWidget(btn_open_mgr)

        btn_refresh = QPushButton("Refrescar empresas")
        btn_refresh.clicked.connect(self._load_companies)
        btn_row.addWidget(btn_refresh)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        layout.addStretch(1)
        return widget

    def _build_paths_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Plantilla de factura
        self.template_edit = QLineEdit()
        btn_template = QPushButton("Seleccionar")
        btn_template.clicked.connect(self._select_template)

        template_row = QHBoxLayout()
        template_row.addWidget(QLabel("Ruta de plantilla:"))
        template_row.addWidget(self.template_edit, 1)
        template_row.addWidget(btn_template)
        layout.addLayout(template_row)

        # Carpeta de salida
        self.output_edit = QLineEdit()
        btn_output = QPushButton("Seleccionar")
        btn_output.clicked.connect(self._select_output)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Carpeta de salida:"))
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(btn_output)
        layout.addLayout(output_row)

        # Carpeta de descargas (origen)
        self.downloads_edit = QLineEdit()
        btn_downloads = QPushButton("Seleccionar")
        btn_downloads.clicked.connect(self._select_downloads)

        downloads_row = QHBoxLayout()
        downloads_row.addWidget(QLabel("Carpeta de descargas:"))
        downloads_row.addWidget(self.downloads_edit, 1)
        downloads_row.addWidget(btn_downloads)
        layout.addLayout(downloads_row)

        # Carpeta de anexos (destino)
        self.attachments_edit = QLineEdit()
        btn_attachments = QPushButton("Seleccionar")
        btn_attachments.clicked.connect(self._select_attachments)

        attachments_row = QHBoxLayout()
        attachments_row.addWidget(QLabel("Carpeta de anexos:"))
        attachments_row.addWidget(self.attachments_edit, 1)
        attachments_row.addWidget(btn_attachments)
        layout.addLayout(attachments_row)

        layout.addStretch(1)
        return widget

    def _build_advanced_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Backups
        backup_group = QGroupBox("Backups")
        backup_layout = QVBoxLayout(backup_group)

        btn_backup_now = QPushButton("Crear backup ahora")
        btn_backup_now.clicked.connect(self._create_backup_now)
        backup_layout.addWidget(btn_backup_now)

        btn_open_backups = QPushButton("Abrir carpeta de backups")
        btn_open_backups.clicked.connect(self._open_backups_folder)
        backup_layout.addWidget(btn_open_backups)

        layout.addWidget(backup_group)

        # Firebase
        firebase_group = QGroupBox("Firebase")
        firebase_layout = QVBoxLayout(firebase_group)

        btn_firebase_config = QPushButton("Configurar Firebase")
        btn_firebase_config.clicked.connect(self._configure_firebase)
        firebase_layout.addWidget(btn_firebase_config)

        layout.addWidget(firebase_group)
        layout.addStretch(1)

        return widget

    # -------------------------
    # Event handlers / helpers
    # -------------------------
    def _on_theme_changed(self, index):
        # Theme is now applied globally in main.py
        # Changes here would require app restart to take effect
        theme_id = self.theme_selector.itemData(index)
        if theme_id:
            try:
                # Save theme preference to config for next app start
                import facot_config
                if hasattr(facot_config, 'set_theme'):
                    facot_config.set_theme(theme_id)
                    QMessageBox.information(
                        self, 
                        "Tema Actualizado", 
                        "El tema se aplicará al reiniciar la aplicación."
                    )
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Error al guardar tema: {e}")

    def _load_companies(self):
        companies = []
        try:
            if self.backend and hasattr(self.backend, 'get_all_companies'):
                companies = self.backend.get_all_companies() or []
            else:
                # fallback: try global facot_config logic (rare)
                companies = []
        except Exception as e:
            print(f"[SettingsWindow] get_all_companies error: {e}")
            companies = []

        self.companies = {}
        self.company_selector.blockSignals(True)
        self.company_selector.clear()
        for c in companies:
            name = c.get("name") or c.get("nombre") or ""
            cid = c.get("id") or c.get("pk") or c.get("company_id")
            if name:
                self.companies[name] = cid
                self.company_selector.addItem(name)
        self.company_selector.blockSignals(False)

        # Select active company if configured
        empresa_activa = facot_config.get_empresa_activa()
        if empresa_activa:
            for idx, name in enumerate(self.companies.keys()):
                if str(self.companies[name]) == str(empresa_activa):
                    self.company_selector.setCurrentIndex(idx)
                    break

    def _load_settings_for_selected_company(self):
        name = self.company_selector.currentText() if hasattr(self, 'company_selector') else ""
        company_id = self.companies.get(name) if getattr(self, 'companies', None) else None
        if not company_id:
            try:
                self.summary_name.setText("")
                self.summary_rnc.setText("")
                self.summary_phone.setText("")
                self.summary_email.setText("")
                self.summary_due.setText("")
            except Exception:
                pass
            return

        # Attempt to read minimal details; prefer get_company_details if available
        try:
            details = {}
            if self.backend and hasattr(self.backend, "get_company_details"):
                details = self.backend.get_company_details(company_id) or {}
            else:
                # fallback: attempt to glean from get_all_companies
                for c in (self.backend.get_all_companies() if self.backend and hasattr(self.backend, 'get_all_companies') else []):
                    if str(c.get("id")) == str(company_id):
                        details = c
                        break
        except Exception as e:
            print(f"[SettingsWindow] Error obteniendo detalles empresa: {e}")
            details = {}

        # Normalize
        name_val = details.get("name") or details.get("nombre") or ""
        rnc_val = details.get("rnc") or details.get("rnc_number") or ""
        phone_val = details.get("phone") or details.get("telefono") or ""
        email_val = details.get("email") or details.get("correo") or ""
        due_val = details.get("invoice_due_date") or details.get("invoice_due") or details.get("due_date") or ""

        try:
            self.summary_name.setText(name_val)
            self.summary_rnc.setText(rnc_val)
            self.summary_phone.setText(phone_val)
            self.summary_email.setText(email_val)
            self.summary_due.setText(due_val or "N/A")
        except Exception:
            pass

    def _open_company_manager_full(self):
        if CompanyManagementWindow is None:
            QMessageBox.warning(self, "Empresas", "No se encontró CompanyManagementWindow en este entorno.")
            return

        try:
            # open with this dialog as parent so modal relationship is clear
            # Pass the same backend to the manager so it can persist using the same backend
            dlg = CompanyManagementWindow(self, self.backend)
            dlg.exec()
        except TypeError:
            try:
                dlg = CompanyManagementWindow(self, self.backend)
                dlg.exec()
            except Exception as e:
                QMessageBox.critical(self, "Empresas", f"No se pudo abrir gestión de empresas:\n{e}")
                return
        except Exception as e:
            QMessageBox.critical(self, "Empresas", f"No se pudo abrir gestión de empresas:\n{e}")
            return

        # After manager closed, refresh list and selection
        try:
            self._load_companies()
            self._load_settings_for_selected_company()
        except Exception:
            pass

    # Path selectors used by paths tab
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

    def _save_settings(self):
        # Theme - save preference for next app start
        try:
            theme_id = self.theme_selector.itemData(self.theme_selector.currentIndex())
            if theme_id:
                import facot_config
                if hasattr(facot_config, 'set_theme'):
                    facot_config.set_theme(theme_id)
        except Exception:
            pass

        # Paths
        try:
            if hasattr(facot_config, 'set_template_path'):
                facot_config.set_template_path(self.template_edit.text().strip())
            if hasattr(facot_config, 'set_output_folder'):
                facot_config.set_output_folder(self.output_edit.text().strip())
            if hasattr(facot_config, 'set_downloads_folder_path'):
                facot_config.set_downloads_folder_path(self.downloads_edit.text().strip())
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudieron guardar rutas: {e}")
            return

        QMessageBox.information(self, "Configuración", "Configuración guardada correctamente.")
        self.accept()

    def _create_backup_now(self):
        try:
            from utils.backups import create_backup
            result = create_backup()

            if result['success']:
                QMessageBox.information(self, "Backup completado", f"Backup creado exitosamente.\n\nUbicación: {result.get('backup_path', 'N/A')}")
            else:
                QMessageBox.warning(self, "Backup con errores", f"El backup se completó con algunos errores:\n\n{', '.join(result.get('errors', ['Error desconocido']))}")
        except Exception as e:
            QMessageBox.critical(self, "Error de backup", f"No se pudo crear el backup:\n\n{str(e)}")

    def _open_backups_folder(self):
        import os, subprocess, platform
        backup_dir = facot_config.get_backup_config().get('backup_dir', './backups')
        backup_path = os.path.abspath(backup_dir)
        os.makedirs(backup_path, exist_ok=True)
        try:
            if platform.system() == 'Windows':
                os.startfile(backup_path)
            elif platform.system() == 'Darwin':
                subprocess.run(['open', backup_path])
            else:
                subprocess.run(['xdg-open', backup_path])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo abrir la carpeta:\n{backup_path}\n\nError: {e}")

    def _configure_firebase(self):
        try:
            from dialogs.firebase_config_dialog import FirebaseConfigDialog
            dialog = FirebaseConfigDialog(self)
            result = dialog.exec()
            if result == 1:  # Accepted
                QMessageBox.information(self, "Firebase configurado", "La configuración de Firebase se ha guardado.\nLos cambios tomarán efecto la próxima vez que inicie la aplicación.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo abrir la configuración de Firebase:\n\n{str(e)}")