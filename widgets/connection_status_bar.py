"""
ConnectionStatusBar widget for showing database connection status.
Displays current mode (SQLite/Firebase), online status, and allows mode switching.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QMenu, QFileDialog
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QAction
import os


class ConnectionStatusBar(QWidget):
    """
    Status bar widget that displays current database connection info.
    
    Features:
    - Shows current mode (SQLITE, FIREBASE, AUTO)
    - Shows database path for SQLite mode
    - Shows online/offline status
    - Allows switching between modes
    - Allows changing database file
    """
    
    # Signals
    database_changed = pyqtSignal(str)  # Emitted when database path changes
    mode_changed = pyqtSignal(str)  # Emitted when connection mode changes
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_mode = "SQLITE"
        self._db_path = ""
        self._is_online = False
        self._setup_ui()
    
    def _setup_ui(self):
        """Build the status bar UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)
        
        # Mode indicator
        self.mode_label = QLabel("SQLite")
        self.mode_label.setStyleSheet("""
            QLabel {
                background-color: #e2e8f0;
                color: #334155;
                padding: 2px 8px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        layout.addWidget(self.mode_label)
        
        # Database path / info
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("""
            QLabel {
                color: #64748b;
                font-size: 11px;
            }
        """)
        layout.addWidget(self.info_label)
        
        # Online status indicator
        self.online_indicator = QLabel("●")
        self.online_indicator.setStyleSheet("color: #94a3b8;")  # Gray by default
        self.online_indicator.setToolTip("Offline")
        layout.addWidget(self.online_indicator)
        
        # Menu button for actions
        self.menu_btn = QPushButton("⚙")
        self.menu_btn.setFixedSize(24, 24)
        self.menu_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
                border-radius: 4px;
            }
        """)
        self.menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_btn.clicked.connect(self._show_menu)
        layout.addWidget(self.menu_btn)
        
        layout.addStretch()
    
    def set_mode(self, mode: str, db_path: str = ""):
        """
        Set the current connection mode.
        
        Args:
            mode: 'SQLITE', 'FIREBASE', or 'AUTO'
            db_path: Path to database file (for SQLite mode)
        """
        self._current_mode = mode.upper()
        self._db_path = db_path
        
        # Update mode label
        mode_styles = {
            "SQLITE": ("SQLite", "#e2e8f0", "#334155"),
            "FIREBASE": ("Firebase", "#fef3c7", "#92400e"),
            "AUTO": ("Auto", "#dbeafe", "#1e40af"),
        }
        
        label_text, bg_color, text_color = mode_styles.get(
            self._current_mode, ("Unknown", "#f1f5f9", "#64748b")
        )
        
        self.mode_label.setText(label_text)
        self.mode_label.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                padding: 2px 8px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }}
        """)
        
        # Update info label
        if self._current_mode == "SQLITE" and db_path:
            filename = os.path.basename(db_path)
            self.info_label.setText(filename)
            self.info_label.setToolTip(db_path)
        elif self._current_mode == "FIREBASE":
            self.info_label.setText("Cloud Database")
            self.info_label.setToolTip("Connected to Firebase Firestore")
        else:
            self.info_label.setText("")
            self.info_label.setToolTip("")
    
    def set_online_status(self, is_online: bool):
        """
        Set the online/offline status indicator.
        
        Args:
            is_online: True if online, False if offline
        """
        self._is_online = is_online
        
        if is_online:
            self.online_indicator.setStyleSheet("color: #22c55e;")  # Green
            self.online_indicator.setToolTip("Online")
        else:
            self.online_indicator.setStyleSheet("color: #94a3b8;")  # Gray
            self.online_indicator.setToolTip("Offline")
    
    def _show_menu(self):
        """Show the options menu."""
        menu = QMenu(self)
        
        # Mode selection submenu
        mode_menu = menu.addMenu("Connection Mode")
        
        sqlite_action = QAction("SQLite (Local)", self)
        sqlite_action.setCheckable(True)
        sqlite_action.setChecked(self._current_mode == "SQLITE")
        sqlite_action.triggered.connect(lambda: self._set_mode("SQLITE"))
        mode_menu.addAction(sqlite_action)
        
        firebase_action = QAction("Firebase (Cloud)", self)
        firebase_action.setCheckable(True)
        firebase_action.setChecked(self._current_mode == "FIREBASE")
        firebase_action.triggered.connect(lambda: self._set_mode("FIREBASE"))
        mode_menu.addAction(firebase_action)
        
        auto_action = QAction("Auto (Hybrid)", self)
        auto_action.setCheckable(True)
        auto_action.setChecked(self._current_mode == "AUTO")
        auto_action.triggered.connect(lambda: self._set_mode("AUTO"))
        mode_menu.addAction(auto_action)
        
        menu.addSeparator()
        
        # Change database action (only for SQLite)
        if self._current_mode == "SQLITE":
            change_db_action = QAction("Change Database...", self)
            change_db_action.triggered.connect(self._change_database)
            menu.addAction(change_db_action)
        
        # Show menu
        menu.exec(self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomLeft()))
    
    def _set_mode(self, mode: str):
        """Internal method to change mode and emit signal."""
        if mode != self._current_mode:
            self.mode_changed.emit(mode)
    
    def _change_database(self):
        """Open file dialog to change database."""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar Archivo de Base de Datos",
            "",
            "Base de Datos SQLite (*.db);;Todos los Archivos (*.*)"
        )
        if filename:
            self.database_changed.emit(filename)
            self.set_mode("SQLITE", filename)
