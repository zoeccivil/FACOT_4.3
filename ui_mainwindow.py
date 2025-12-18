from __future__ import annotations

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QMessageBox,
    QMenuBar, QMenu, QFileDialog, QStatusBar, QPushButton, QFrame, QStackedWidget,
    QSizePolicy, QSpacerItem
)
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt6.QtCore import QUrl, Qt
import os, sys

import facot_config
from logic import LogicController

# Firebase imports (required for Firebase-only enforcement)
from data_access import get_data_access, DataAccessMode
from firebase import get_firebase_client

# Tabs modulares
from tabs.invoice_tab import InvoiceTab
import sys
# Fuerza recarga de módulos
if 'tabs.quotation_tab' in sys.modules:
    del sys.modules['tabs.quotation_tab']
from tabs.quotation_tab import QuotationTab
from tabs.invoice_history_tab import InvoiceHistoryTab
from tabs.quotation_history_tab import QuotationHistoryTab
from tabs.dashboard_tab import DashboardTab

# Ventanas secundarias
from settings_window import SettingsWindow
from company_management_window import CompanyManagementWindow
from items_management_window import ItemsManagementWindow

# Dialog para editar plantillas (botón/menú)
from dialogs.template_editor_dialog import TemplateEditorDialog

# Custom widgets
from widgets.connection_status_bar import ConnectionStatusBar

# -*- coding: utf-8 -*-

# Color palette (matching React/Tailwind reference)
COLORS = {
    "sidebar_bg": "#0f172a",      # slate-900
    "sidebar_text": "#94a3b8",    # slate-400
    "sidebar_text_active": "#ffffff",
    "sidebar_hover": "#1e293b",   # slate-800
    "background": "#f8fafc",      # slate-50
    "primary": "#4f46e5",         # indigo-600
    "primary_hover": "#4338ca",   # indigo-700
    "header_bg": "#ffffff",
    "header_border": "#e2e8f0",   # slate-200
    "text_main": "#1e293b",       # slate-800
    "text_muted": "#64748b",      # slate-500
    "card_bg": "#ffffff",
    "card_border": "#e2e8f0",
}

class HybridLogicWrapper:
    """
    Wrapper híbrido que combina logic (SQLite) y data_access (Firebase).
    
    Intercepta llamadas de atributos y las redirige al backend correcto:
    - Si data_access tiene el método, lo usa (Firebase)
    - Si no, delega a logic (SQLite)
    
    Esto permite que tabs existentes funcionen con ambos backends
    sin modificar su código.
    """
    
    def __init__(self, logic, data_access=None):
        self._logic = logic
        self._data_access = data_access
        self._use_firebase = data_access is not None
        
        # Para debugging
        if self._use_firebase:
            print(f"[HYBRID] Created hybrid wrapper with Firebase backend")
        else:
            print(f"[HYBRID] Created hybrid wrapper with SQLite only")
    
    def __getattr__(self, name):
        """
        Intercepta acceso a atributos/métodos.
        
        Prioridad:
        1. Si data_access existe y tiene el método -> usar Firebase
        2. Sino -> usar logic (SQLite)
        """
        # Si tenemos data_access y tiene el método, usarlo
        if self._use_firebase and self._data_access and hasattr(self._data_access, name):
            attr = getattr(self._data_access, name)
            # Si es callable, retornar función que logguea
            if callable(attr):
                def logged_call(*args, **kwargs):
                    # print(f"[HYBRID] Using Firebase for: {name}")
                    return attr(*args, **kwargs)
                return logged_call
            return attr
        
        # Sino, delegar a logic
        if hasattr(self._logic, name):
            attr = getattr(self._logic, name)
            if callable(attr):
                def logged_call(*args, **kwargs):
                    # print(f"[HYBRID] Using SQLite for: {name}")
                    return attr(*args, **kwargs)
                return logged_call
            return attr
        
        # Si no existe en ninguno, error estándar
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
    
    # Propiedades que deben accederse directamente
    @property
    def conn(self):
        """Retorna conexión SQLite para compatibilidad."""
        return self._logic.conn if hasattr(self._logic, 'conn') else None

from logic import LogicController
import facot_config
class MainWindow(QMainWindow):
    # CAMBIO AQUÍ: Añadir el parámetro logic_controller=None
    def __init__(self, logic_controller=None):
        super().__init__()
        
        # CAMBIO AQUÍ: Usar el controlador inyectado o crear uno legacy si falla
        if logic_controller:
            self.logic = logic_controller
            print("[MainWindow] Usando LogicController inyectado (Firebase/Proxy)")
        else:
            self.logic = LogicController(facot_config.get_db_path())
            print("[MainWindow] Creando LogicController local (Legacy SQLite)")
        self.setWindowTitle("Gestión de Facturas y Cotizaciones")
        self.resize(1100, 790)
        self.data_access = None  # Will hold DataAccess instance
        self.current_access_mode = "SQLITE"  # Track current mode
        self.hybrid_logic = None  # Will hold HybridLogicWrapper
        self._init_db()
        self._setup_ui()
        self._setup_menu()
        self._setup_connection_status()
        self._check_online_status()
        self._detect_and_set_connection_mode()

    def _initialize_firebase(self):
        """
        Helper method to initialize Firebase data access.
        
        Returns:
            bool: True if Firebase was successfully initialized, False otherwise
        """
        try:
            # Get or refresh Firebase client
            firebase_client = get_firebase_client()
            
            # Force FIREBASE mode (no AUTO fallback to SQLite)
            self.data_access = get_data_access(user_id=None, mode=DataAccessMode.FIREBASE)
            self.current_access_mode = "FIREBASE"
            
            # Create hybrid wrapper with Firebase as primary
            self.hybrid_logic = HybridLogicWrapper(self.logic, self.data_access)
            
            return True
        except Exception as e:
            print(f"[MAIN] Firebase initialization failed: {e}")
            return False
    
    def _init_db(self):
        """
        Initialize database connection.
        
        FIREBASE-FIRST POLICY:
        - SQLite is initialized only for backwards compatibility and migration tools
        - Main runtime MUST use Firebase for data operations
        - If Firebase is not configured, user is prompted to configure it
        """
        db_path = facot_config.get_db_path()
        if not db_path or not os.path.isfile(db_path):
            filename, _ = QFileDialog.getOpenFileName(self, "Selecciona tu archivo de base de datos", "", "Database Files (*.db);;Todos los archivos (*)")
            if filename:
                facot_config.set_db_path(filename); db_path = filename
            else:
                QMessageBox.critical(self, "Error", "No se seleccionó una base de datos. El programa se cerrará.")
                sys.exit(1)
        
        # Initialize SQLite (for migration tools and backwards compatibility only)
        self.logic = LogicController(db_path)
        
        # ===== FIREBASE-ONLY ENFORCEMENT =====
        # The application now REQUIRES Firebase for main runtime operations
        firebase_initialized = False
        firebase_error = None
        
        try:
            # Check if Firebase is available
            firebase_client = get_firebase_client()
            if not firebase_client.is_available():
                raise RuntimeError(
                    "Firebase no está configurado. La aplicación requiere Firebase para funcionar.\n\n"
                    "Por favor, configure Firebase desde: Herramientas > Configurar Firebase..."
                )
            
            # Initialize Firebase using helper method
            print(f"[MAIN] Enforcing FIREBASE-ONLY mode")
            firebase_initialized = self._initialize_firebase()
            
            if firebase_initialized:
                print(f"[MAIN] Firebase initialized successfully - using Firebase for all data operations")
            else:
                raise RuntimeError("Failed to initialize Firebase")
            
        except Exception as e:
            firebase_error = str(e)
            print(f"[MAIN] ERROR: Firebase initialization failed: {e}")
            
            # Show error dialog with option to configure
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("Firebase Requerido")
            msg.setText(
                "La aplicación requiere Firebase para funcionar.\n\n"
                f"Error: {firebase_error}\n\n"
                "¿Desea configurar Firebase ahora?"
            )
            msg.setStandardButtons(
                QMessageBox.StandardButton.Yes | 
                QMessageBox.StandardButton.No
            )
            msg.setDefaultButton(QMessageBox.StandardButton.Yes)
            
            result = msg.exec()
            
            if result == QMessageBox.StandardButton.Yes:
                # Open Firebase configuration dialog
                try:
                    from dialogs.firebase_config_dialog import FirebaseConfigDialog
                    config_dialog = FirebaseConfigDialog(self)
                    if config_dialog.exec():
                        # Try to initialize Firebase again using helper method
                        firebase_initialized = self._initialize_firebase()
                        
                        if firebase_initialized:
                            QMessageBox.information(
                                self,
                                "Firebase Configurado",
                                "Firebase se ha configurado correctamente.\n"
                                "La aplicación ahora usará Firebase para todas las operaciones."
                            )
                        else:
                            QMessageBox.critical(
                                self,
                                "Error",
                                "Firebase sigue sin estar disponible.\n\n"
                                "La aplicación se cerrará."
                            )
                            sys.exit(1)
                    else:
                        QMessageBox.warning(
                            self,
                            "Configuración Cancelada",
                            "Firebase no fue configurado. La aplicación se cerrará."
                        )
                        sys.exit(1)
                except ImportError as import_error:
                    QMessageBox.critical(
                        self,
                        "Error",
                        f"No se pudo abrir el diálogo de configuración:\n{import_error}\n\n"
                        "La aplicación se cerrará."
                    )
                    sys.exit(1)
            else:
                QMessageBox.warning(
                    self,
                    "Firebase Requerido",
                    "La aplicación requiere Firebase para funcionar.\n"
                    "La aplicación se cerrará."
                )
                sys.exit(1)
        
        # Final check: Ensure Firebase is initialized
        if not firebase_initialized:
            QMessageBox.critical(
                self,
                "Error Fatal",
                "No se pudo inicializar Firebase.\n"
                "La aplicación no puede continuar."
            )
            sys.exit(1)
        
        print(f"[MAIN] Database initialization complete - Mode: {self.current_access_mode}")

    def _setup_ui(self):
        """
        Build the modern dashboard-style UI with:
        - Left Sidebar (navigation)
        - Right Main Content (Header + QStackedWidget)
        """
        # Apply global stylesheet
        self._apply_global_stylesheet()
        
        # Central widget with horizontal layout
        central = QWidget()
        central.setObjectName("centralWidget")
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.setCentralWidget(central)
        
        # === SIDEBAR ===
        self.sidebar = self._create_sidebar()
        main_layout.addWidget(self.sidebar)
        
        # === MAIN CONTENT AREA ===
        content_area = QWidget()
        content_area.setObjectName("contentArea")
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # Header
        self.header = self._create_header()
        content_layout.addWidget(self.header)
        
        # Content (QStackedWidget)
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("contentStack")
        content_layout.addWidget(self.content_stack)
        
        main_layout.addWidget(content_area, 1)  # Stretch factor 1
        
        # === CREATE TABS / PAGES ===
        self._populate_companies()
        self.company_selector.currentIndexChanged.connect(self._on_company_change)
        
        # Function to get current company (tabs use injected get_current_company)
        get_company = lambda: self.companies.get(self.company_selector.currentText())
        
        # Use hybrid_logic instead of direct logic
        # This allows tabs to use Firebase or SQLite transparently
        logic_to_pass = self.hybrid_logic if self.hybrid_logic else self.logic
        
        # Create tab widgets
        self.dashboard_tab = DashboardTab(logic_to_pass, get_company)
        self.invoice_tab = InvoiceTab(logic_to_pass, get_company)
        self.quotation_tab = QuotationTab(logic_to_pass, get_company)
        self.invoice_history_tab = InvoiceHistoryTab(logic_to_pass, get_company)
        self.quotation_history_tab = QuotationHistoryTab(logic_to_pass, get_company)
        
        # Set main window reference for history tabs (for Edit functionality)
        self.invoice_history_tab.main_window = self
        self.quotation_history_tab.main_window = self
        
        # Connections: refresh history on save
        self.invoice_tab.invoice_saved.connect(lambda _id: self.invoice_history_tab.refresh())
        self.invoice_tab.invoice_saved.connect(lambda _id: self.dashboard_tab.refresh())
        self.quotation_tab.quotation_saved.connect(lambda _id: self.quotation_history_tab.refresh())
        self.quotation_tab.quotation_saved.connect(lambda _id: self.dashboard_tab.refresh())
        
        # Add pages to stack (order must match sidebar buttons)
        self.content_stack.addWidget(self.dashboard_tab)        # Index 0
        self.content_stack.addWidget(self.invoice_tab)          # Index 1
        self.content_stack.addWidget(self.quotation_tab)        # Index 2
        self.content_stack.addWidget(self.invoice_history_tab)  # Index 3
        self.content_stack.addWidget(self.quotation_history_tab) # Index 4
        
        # Set initial page
        self._navigate_to(0)
    
    def _create_sidebar(self) -> QFrame:
        """Create the sidebar navigation panel."""
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(256)
        sidebar.setStyleSheet(f"""
            QFrame#sidebar {{
                background-color: {COLORS['sidebar_bg']};
            }}
        """)
        
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Logo / App Title
        logo_container = QFrame()
        logo_container.setFixedHeight(64)
        logo_container.setStyleSheet(f"background-color: {COLORS['sidebar_bg']};")
        logo_layout = QHBoxLayout(logo_container)
        logo_layout.setContentsMargins(24, 0, 24, 0)
        
        logo_label = QLabel("FacturaPro")
        logo_label.setStyleSheet(f"""
            color: {COLORS['sidebar_text_active']};
            font-size: 18px;
            font-weight: bold;
        """)
        logo_layout.addWidget(logo_label)
        layout.addWidget(logo_container)
        
        # Navigation buttons container
        nav_container = QWidget()
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(12, 16, 12, 16)
        nav_layout.setSpacing(4)
        
        # Store nav buttons for state management
        self.nav_buttons = []
        
        # Navigation items: (icon, label, page_index)
        nav_items = [
            ("📊", "Dashboard", 0),
            ("📄", "Facturas", 1),
            ("📝", "Cotizaciones", 2),
            ("📋", "Historial Facturas", 3),
            ("📚", "Historial Cotizaciones", 4),
        ]
        
        for icon, label, page_index in nav_items:
            btn = self._create_nav_button(icon, label, page_index)
            nav_layout.addWidget(btn)
            self.nav_buttons.append(btn)
        
        nav_layout.addStretch(1)
        layout.addWidget(nav_container, 1)
        
        return sidebar
    
    def _create_nav_button(self, icon: str, label: str, page_index: int) -> QPushButton:
        """Create a styled navigation button for the sidebar."""
        btn = QPushButton(f"  {icon}  {label}")
        btn.setObjectName(f"navButton_{page_index}")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(44)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLORS['sidebar_text']};
                border: none;
                border-radius: 8px;
                text-align: left;
                padding-left: 16px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {COLORS['sidebar_hover']};
                color: {COLORS['sidebar_text_active']};
            }}
            QPushButton[active="true"] {{
                background-color: {COLORS['primary']};
                color: {COLORS['sidebar_text_active']};
            }}
        """)
        btn.clicked.connect(lambda: self._navigate_to(page_index))
        return btn
    
    def _create_header(self) -> QFrame:
        """Create the top header bar with company selector."""
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(64)
        header.setStyleSheet(f"""
            QFrame#header {{
                background-color: {COLORS['header_bg']};
                border-bottom: 1px solid {COLORS['header_border']};
            }}
        """)
        
        layout = QHBoxLayout(header)
        layout.setContentsMargins(32, 0, 32, 0)
        layout.setSpacing(16)
        
        # Left side: Page title (will be updated on navigation)
        self.page_title = QLabel("Dashboard")
        self.page_title.setStyleSheet(f"""
            color: {COLORS['text_main']};
            font-size: 20px;
            font-weight: 600;
        """)
        layout.addWidget(self.page_title)
        
        layout.addStretch(1)
        
        # Right side: Company selector
        company_label = QLabel("Empresa:")
        company_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 13px;")
        layout.addWidget(company_label)
        
        self.company_selector = QComboBox()
        self.company_selector.setMinimumWidth(200)
        self.company_selector.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLORS['background']};
                border: 1px solid {COLORS['header_border']};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
                color: {COLORS['text_main']};
            }}
            QComboBox:hover {{
                border-color: {COLORS['primary']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
        """)
        layout.addWidget(self.company_selector)
        
        return header
    
    def _navigate_to(self, page_index: int):
        """Navigate to a specific page in the content stack."""
        # Update stack
        self.content_stack.setCurrentIndex(page_index)
        
        # Update nav button states
        for i, btn in enumerate(self.nav_buttons):
            is_active = (i == page_index)
            btn.setProperty("active", "true" if is_active else "false")
            # Force style refresh
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        
        # Update page title
        titles = ["Dashboard", "Facturas", "Cotizaciones", "Historial de Facturas", "Historial de Cotizaciones"]
        if 0 <= page_index < len(titles):
            self.page_title.setText(titles[page_index])
    
    def _apply_global_stylesheet(self):
        """Apply global styles to the application."""
        self.setStyleSheet(f"""
            /* Main Window Background */
            QMainWindow {{
                background-color: {COLORS['background']};
            }}
            
            /* Content Area */
            QWidget#contentArea {{
                background-color: {COLORS['background']};
            }}
            
            /* Content Stack */
            QStackedWidget#contentStack {{
                background-color: {COLORS['background']};
            }}
            
            /* Card Style */
            QFrame.Card, QGroupBox {{
                background-color: {COLORS['card_bg']};
                border: 1px solid {COLORS['card_border']};
                border-radius: 12px;
            }}
            
            /* Primary Button */
            QPushButton[class="primary"] {{
                background-color: {COLORS['primary']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton[class="primary"]:hover {{
                background-color: {COLORS['primary_hover']};
            }}
            
            /* Default Input Styling */
            QLineEdit, QTextEdit, QDateEdit, QSpinBox, QDoubleSpinBox {{
                background-color: white;
                border: 1px solid {COLORS['card_border']};
                border-radius: 6px;
                padding: 6px 12px;
                color: {COLORS['text_main']};
            }}
            QLineEdit:focus, QTextEdit:focus, QDateEdit:focus {{
                border-color: {COLORS['primary']};
            }}
            
            /* Table Styling */
            QTableWidget {{
                background-color: white;
                border: 1px solid {COLORS['card_border']};
                border-radius: 8px;
                gridline-color: {COLORS['header_border']};
            }}
            QHeaderView::section {{
                background-color: {COLORS['background']};
                color: {COLORS['text_muted']};
                padding: 10px;
                border: none;
                border-bottom: 1px solid {COLORS['header_border']};
                font-weight: bold;
                font-size: 11px;
                text-transform: uppercase;
            }}
            
            /* Scrollbar */
            QScrollBar:vertical {{
                background: {COLORS['background']};
                width: 8px;
                margin: 0;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {COLORS['header_border']};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {COLORS['text_muted']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

    def _setup_menu(self):
        menu_bar = QMenuBar(self); self.setMenuBar(menu_bar)
        archivo_menu = QMenu("&Archivo", self); menu_bar.addMenu(archivo_menu)

        abrir_base_action = QAction("Abrir Base de Datos...", self)
        abrir_base_action.triggered.connect(self._abrir_base_de_datos)
        archivo_menu.addAction(abrir_base_action)

        crear_base_action = QAction("Crear Nueva Base de Datos...", self)
        crear_base_action.triggered.connect(self._crear_nueva_base_de_datos)
        archivo_menu.addAction(crear_base_action)

        backup_action = QAction("Hacer Backup...", self)
        backup_action.triggered.connect(self._hacer_backup)
        archivo_menu.addAction(backup_action)

        archivo_menu.addSeparator()
        salir_action = QAction("Salir", self); salir_action.triggered.connect(self.close)
        archivo_menu.addAction(salir_action)

        # Menú Reportes (placeholders)
        reportes_menu = QMenu("&Reportes", self); menu_bar.addMenu(reportes_menu)
        reporte_ventas_action = QAction("📊 Reporte de Ventas", self)
        reporte_ventas_action.triggered.connect(self._abrir_reporte_ventas)
        reportes_menu.addAction(reporte_ventas_action)
        reporte_clientes_action = QAction("👥 Reporte por Cliente", self)
        reporte_clientes_action.triggered.connect(self._abrir_reporte_clientes)
        reportes_menu.addAction(reporte_clientes_action)

        # Menú Herramientas
        herramientas_menu = QMenu("&Herramientas", self); menu_bar.addMenu(herramientas_menu)
        migrar_firebase_action = QAction("🔄 Migrar a Firebase...", self)
        migrar_firebase_action.setShortcut("Ctrl+Shift+M")
        migrar_firebase_action.setToolTip("Migrar datos de SQLite a Firebase")
        migrar_firebase_action.triggered.connect(self._abrir_dialogo_migracion)
        herramientas_menu.addAction(migrar_firebase_action)
        
        ncf_config_action = QAction("🔢 Configurar Secuencias NCF...", self)
        ncf_config_action.setShortcut("Ctrl+Shift+N")
        ncf_config_action.setToolTip("Configurar secuencias de NCF por empresa y tipo de comprobante")
        ncf_config_action.triggered.connect(self._abrir_configuracion_ncf)
        herramientas_menu.addAction(ncf_config_action)
        
        herramientas_menu.addSeparator()
        
        firebase_config_action = QAction("🔥 Configurar Firebase...", self)
        firebase_config_action.setShortcut("Ctrl+Shift+F")
        firebase_config_action.setToolTip("Configurar credenciales de Firebase")
        firebase_config_action.triggered.connect(self._abrir_configuracion_firebase)
        herramientas_menu.addAction(firebase_config_action)

        # Menú Opciones
        opciones_menu = QMenu("&Opciones", self); menu_bar.addMenu(opciones_menu)
        config_rutas_action = QAction("Configurar Rutas...", self)
        config_rutas_action.triggered.connect(self._abrir_configuracion)
        opciones_menu.addAction(config_rutas_action)

        gestionar_empresas_action = QAction("Gestionar Empresas...", self)
        gestionar_empresas_action.triggered.connect(self._abrir_gestion_empresas)
        opciones_menu.addAction(gestionar_empresas_action)

        gestion_items_action = QAction("Gestionar Ítems...", self)
        gestion_items_action.triggered.connect(self._abrir_gestion_items)
        opciones_menu.addAction(gestion_items_action)

        # Acción: Editar plantilla (abre el editor de plantillas para la empresa seleccionada)
        action_edit_template = QAction("Editar plantilla...", self)
        action_edit_template.setStatusTip("Editar plantilla para la empresa seleccionada")
        action_edit_template.triggered.connect(self._menu_edit_template)
        opciones_menu.addAction(action_edit_template)
    
    def _abrir_configuracion_firebase(self):
        """Abre el diálogo de configuración de Firebase."""
        try:
            from dialogs.firebase_config_dialog import FirebaseConfigDialog
            
            dialog = FirebaseConfigDialog(self)
            if dialog.exec():
                # Configuración guardada, intentar re-inicializar
                QMessageBox.information(
                    self,
                    "Firebase Configurado",
                    "La configuración de Firebase se ha guardado.\n\n"
                    "Por favor, reinicie la aplicación para aplicar los cambios."
                )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo abrir la configuración de Firebase:\n{e}")
    
    def _abrir_reporte_ventas(self):
        """Abre el diálogo de reporte de ventas (nuevo UI)."""
        try:
            from ui.report_sales_dialog import SalesReportDialog
            dialog = SalesReportDialog(self.hybrid_logic or self.logic, self)
            dialog.exec()
        except ImportError:
            QMessageBox.information(
                self,
                "Reporte de Ventas",
                "El módulo de reportes está en desarrollo.\n\n"
                "Próximamente podrá generar reportes de ventas por período."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error abriendo reporte de ventas: {e}")

    def _abrir_reporte_clientes(self):
        """Abre el diálogo de reporte por cliente (nuevo UI)."""
        try:
            from ui.report_clients_dialog import ClientsReportDialog
            dialog = ClientsReportDialog(self.hybrid_logic or self.logic, self)
            dialog.exec()
        except ImportError:
            QMessageBox.information(
                self,
                "Reporte por Cliente",
                "El módulo de reportes está en desarrollo.\n\n"
                "Próximamente podrá generar reportes por cliente."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error abriendo reporte de clientes: {e}")
            
    # --------- Menu handlers ----------
    def _abrir_base_de_datos(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Abrir Base de Datos", "", "Database Files (*.db);;Todos los archivos (*)")
        if filename:
            facot_config.set_db_path(filename)
            self.logic = LogicController(filename)
            self._populate_companies()
            # Reinyectar lógica en tabs
            get_company = lambda: self.companies.get(self.company_selector.currentText())
            self.dashboard_tab.logic = self.logic
            self.invoice_tab.logic = self.logic; self.quotation_tab.logic = self.logic
            self.invoice_history_tab.logic = self.logic; self.quotation_history_tab.logic = self.logic
            self._on_company_change()
            QMessageBox.information(self, "Base de Datos", "Base de datos abierta correctamente.")

    def _crear_nueva_base_de_datos(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Crear Nueva Base de Datos", "", "Database Files (*.db);;Todos los archivos (*)")
        if filename:
            facot_config.set_db_path(filename)
            self.logic = LogicController(filename)
            self._populate_companies()
            self._on_company_change()
            QMessageBox.information(self, "Base de Datos", "Nueva base de datos creada correctamente.")

    def _hacer_backup(self):
        import shutil
        db_path = self.logic.db_path
        backup_path, _ = QFileDialog.getSaveFileName(self, "Guardar Backup de la Base de Datos", "", "Database Files (*.db);;Todos los archivos (*)")
        if backup_path:
            shutil.copy2(db_path, backup_path)
            QMessageBox.information(self, "Backup", f"Backup guardado en:\n{backup_path}")

    def _abrir_configuracion(self):
        dlg = SettingsWindow(self.logic, self); dlg.exec()

    def _abrir_gestion_empresas(self):
        dlg = CompanyManagementWindow(self, self.logic); dlg.exec()
        # Si cambian empresas, repoblar
        self._populate_companies()
        self._on_company_change()

    def _abrir_gestion_items(self):
        dlg = ItemsManagementWindow(self); dlg.exec()

    def _abrir_dialogo_migracion(self):
        """Abre el diálogo de migración SQLite → Firebase"""
        from dialogs.migration_dialog import MigrationDialog
        
        dialog = MigrationDialog(self)
        dialog.exec()
    

    # --------- Empresas ----------
    def _populate_companies(self):
        self.company_selector.clear()
        
        # Use data_access if available, otherwise fallback to logic
        if self.data_access:
            companies = self.data_access.get_all_companies()
        else:
            companies = self.logic.get_all_companies()
        
        self.companies = {str(c['name']): c for c in companies}
        self.company_selector.addItems(self.companies.keys())

    def _on_company_change(self):
        # Notifica a las pestañas
        self.dashboard_tab.on_company_change()
        self.invoice_tab.on_company_change()
        self.quotation_tab.on_company_change()
        self.invoice_history_tab.refresh()
        self.quotation_history_tab.refresh()

    # Helper para obtener la empresa actual desde cualquier lugar
    def get_current_company(self):
        return self.companies.get(self.company_selector.currentText())

    # --- Compatibilidad: algunos diálogos llaman MainWindow.get_all_companies() ---
    def get_all_companies(self):
        """
        Delegado de compatibilidad para obtener empresas desde la ventana principal.
        Intenta híbrido, luego data_access, luego logic.
        """
        try:
            if self.hybrid_logic and hasattr(self.hybrid_logic, "get_all_companies"):
                return self.hybrid_logic.get_all_companies() or []
        except Exception as e:
            print(f"[MainWindow] hybrid get_all_companies error: {e}")
        try:
            if self.data_access and hasattr(self.data_access, "get_all_companies"):
                return self.data_access.get_all_companies() or []
        except Exception as e:
            print(f"[MainWindow] data_access get_all_companies error: {e}")
        try:
            if self.logic and hasattr(self.logic, "get_all_companies"):
                return self.logic.get_all_companies() or []
        except Exception as e:
            print(f"[MainWindow] logic get_all_companies error: {e}")
        return []

    # Menú: abrir editor de plantillas para la empresa seleccionada
    def _menu_edit_template(self):
        company = self.get_current_company()
        if not company:
            QMessageBox.warning(self, "Plantilla", "Seleccione primero una empresa válida.")
            return

        company_id = company.get("id") or company.get("company_id") or company.get("pk")
        if not company_id:
            QMessageBox.warning(self, "Plantilla", "La empresa seleccionada no tiene identificador.")
            return

        try:
            dlg = TemplateEditorDialog(company_id=company_id, parent=self)
            if dlg.exec():
                QMessageBox.information(self, "Plantilla", "Plantilla guardada correctamente.")
        except Exception as e:
            QMessageBox.critical(self, "Plantilla", f"No se pudo abrir el editor de plantillas:\n{e}")
            
    def _setup_connection_status(self):
        """Configura la barra de estado de conexión."""
        # Crear barra de estado
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        
        # Crear widget de estado de conexión
        self.connection_status = ConnectionStatusBar(self)
        
        # Configurar estado inicial (SQLite por defecto)
        db_path = facot_config.get_db_path()
        self.connection_status.set_mode("SQLITE", db_path)
        
        # Conectar señales
        self.connection_status.database_changed.connect(self._on_database_changed)
        self.connection_status.mode_changed.connect(self._on_connection_mode_changed)
        
        # Agregar a la barra de estado
        status_bar.addPermanentWidget(self.connection_status)
    
    def _check_online_status(self):
        """Verifica si hay conexión a internet."""
        # Crear network manager
        self.network_manager = QNetworkAccessManager(self)
        self.network_manager.finished.connect(self._on_network_check_finished)
        
        # Hacer request a un servidor confiable
        request = QNetworkRequest(QUrl("https://www.google.com"))
        request.setTransferTimeout(3000)  # 3 segundos timeout
        self.network_manager.get(request)
    
    def _on_network_check_finished(self, reply):
        """Callback cuando se completa la verificación de red."""
        is_online = (reply.error() == 0)
        self.connection_status.set_online_status(is_online)
        reply.deleteLater()
    
    def _detect_and_set_connection_mode(self):
        """
        Detecta si se está usando Firebase y actualiza el widget de estado.
        """
        try:
            from data_access import get_current_mode, DataAccessMode
            from firebase import get_firebase_client
            
            # Verificar si data_access es realmente FirebaseDataAccess
            is_using_firebase = (
                self.data_access is not None and 
                "Firebase" in type(self.data_access).__name__
            )
            
            # Verificar si Firebase está disponible
            firebase_client = get_firebase_client()
            firebase_available = firebase_client.is_available()
            
            if is_using_firebase and firebase_available:
                self.current_access_mode = "FIREBASE"
                self.connection_status.set_mode("FIREBASE")
                self.connection_status.set_online_status(True)
                print("[MAIN] Detected Firebase mode - updating status bar")
            else:
                self.current_access_mode = "SQLITE"
                db_path = facot_config.get_db_path()
                self.connection_status.set_mode("SQLITE", db_path)
                print(f"[MAIN] Using SQLite mode: {db_path}")
                
        except Exception as e:
            print(f"[MAIN] Error detecting connection mode: {e}")
            # Fallback to SQLite
            self.current_access_mode = "SQLITE"
            db_path = facot_config.get_db_path()
            self.connection_status.set_mode("SQLITE", db_path)
    
    def _on_database_changed(self, new_db_path: str):
        """
        Callback cuando el usuario cambia la base de datos.
        
        Args:
            new_db_path: Ruta a la nueva base de datos
        """
        try:
            # Actualizar configuración
            facot_config.set_db_path(new_db_path)
            
            # Recrear LogicController con nueva base
            self.logic = LogicController(new_db_path)
            
            # Recreate data_access with new logic controller
            from data_access import get_data_access, DataAccessMode
            self.data_access = get_data_access(logic_controller=self.logic, mode=DataAccessMode.SQLITE)
            self.current_access_mode = "SQLITE"
            
            # Actualizar companies
            self._populate_companies()
            
            # Reinyectar lógica en tabs
            self.dashboard_tab.logic = self.logic
            self.invoice_tab.logic = self.logic
            self.quotation_tab.logic = self.logic
            self.invoice_history_tab.logic = self.logic
            self.quotation_history_tab.logic = self.logic
            
            # Refrescar
            self.dashboard_tab.on_company_change()
            self.invoice_tab.on_company_change()
            self.quotation_tab.on_company_change()
            self.invoice_history_tab.refresh()
            self.quotation_history_tab.refresh()
            
            QMessageBox.information(
                self,
                "Base de Datos",
                f"Base de datos cambiada exitosamente:\n{os.path.basename(new_db_path)}"
            )
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"No se pudo cambiar la base de datos:\n{str(e)}"
            )
    
    def _on_connection_mode_changed(self, new_mode: str):
        """
        Callback cuando el usuario cambia el modo de conexión.
        
        Args:
            new_mode: Nuevo modo (SQLITE, FIREBASE, AUTO)
        """
        try:
            from data_access import set_data_access_mode, DataAccessMode, get_data_access
            
            # Mapear string a enum
            mode_map = {
                "SQLITE": DataAccessMode.SQLITE,
                "FIREBASE": DataAccessMode.FIREBASE,
                "AUTO": DataAccessMode.AUTO
            }
            
            mode = mode_map.get(new_mode.upper())
            if mode:
                set_data_access_mode(mode)
                self.current_access_mode = new_mode.upper()
                
                # Recreate data_access with new mode
                try:
                    if mode == DataAccessMode.SQLITE:
                        self.data_access = get_data_access(logic_controller=self.logic, mode=mode)
                    elif mode == DataAccessMode.FIREBASE:
                        self.data_access = get_data_access(user_id=None, mode=mode)
                    else:  # AUTO
                        self.data_access = get_data_access(logic_controller=self.logic, user_id=None, mode=mode)
                    
                    # Reload companies with new data access
                    self._populate_companies()
                    
                    # Update connection status display
                    self._detect_and_set_connection_mode()
                    
                    QMessageBox.information(
                        self,
                        "Modo de Conexión",
                        f"Modo de conexión cambiado a: {new_mode}\n\n"
                        f"La aplicación ahora usará {new_mode} para acceder a los datos."
                    )
                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "Error",
                        f"No se pudo cambiar al modo {new_mode}:\n{str(e)}\n\n"
                        "Revirtiendo a SQLite."
                    )
                    # Revert to SQLite
                    set_data_access_mode(DataAccessMode.SQLITE)
                    self.data_access = get_data_access(logic_controller=self.logic, mode=DataAccessMode.SQLITE)
                    self.current_access_mode = "SQLITE"
                    self._detect_and_set_connection_mode()
                
                # Si se cambió a Firebase o AUTO, verificar que esté configurado
                if new_mode in ["FIREBASE", "AUTO"]:
                    self._check_firebase_availability()
        
        except ImportError:
            QMessageBox.warning(
                self,
                "Modo de Conexión",
                "El módulo de Firebase no está disponible.\n"
                "Solo se puede usar SQLite."
            )
    
    def _check_firebase_availability(self):
        """Verifica si Firebase está disponible y configurado."""
        try:
            from firebase import get_firebase_client
            
            client = get_firebase_client()
            if not client.is_available():
                QMessageBox.warning(
                    self,
                    "Firebase",
                    "Firebase no está disponible o no está configurado correctamente.\n\n"
                    "Verifique que:\n"
                    "1. firebase-admin esté instalado (pip install firebase-admin)\n"
                    "2. El archivo de credenciales exista\n"
                    "3. Las credenciales sean válidas\n\n"
                    "La aplicación usará SQLite como fallback."
                )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Firebase",
                f"Error al verificar Firebase:\n{str(e)}\n\n"
                "La aplicación usará SQLite como fallback."
            )

    def _abrir_configuracion_ncf(self):
        """Abre el diálogo de configuración de secuencias NCF"""
        from dialogs.ncf_config_dialog import NCFConfigDialog
        
        # PASAR EL BACKEND CORRECTO (híbrido si existe)
        backend = self.hybrid_logic if self.hybrid_logic else self.logic
        dialog = NCFConfigDialog(backend, self)
        result = dialog.exec()
        # Si el usuario guardó/aceptó, refrescar inmediatamente en InvoiceTab:
        try:
            if result == 1:  # Accepted
                if hasattr(self, "invoice_tab") and hasattr(self.invoice_tab, "refresh_after_ncf_config"):
                    self.invoice_tab.refresh_after_ncf_config()
        except Exception as e:
            print(f"[MAIN] Error al refrescar InvoiceTab tras NCFConfig: {e}")