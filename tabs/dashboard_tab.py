"""
DashboardTab - Modern dashboard view with summary cards and analytics.

Functional data sources:
- Invoices: logic.get_facturas(company_id) OR logic.list_invoices(company_id)
- Quotations: logic.get_quotations(company_id) OR logic.list_quotations(company_id)
- Third parties (clients): logic.get_third_parties(company_id) OR logic.list_third_parties(company_id)
- Recent activity: built from invoices and quotations timestamps

Filtering:
- Income invoices only: invoice_type/type in INGRESO_TYPES (e.g., 'emitida', 'ingreso')
- Exclude EXPENSE_TYPES (e.g., 'gasto', 'compra')
- Pending = status NOT in ('paid','pagada','cobrada')

The chart aggregates current-year monthly totals from income invoices only.
"""
from __future__ import annotations

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, date
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout,
    QScrollArea, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from constants import INGRESO_TYPES, EXPENSE_TYPES

# Try to import pyqtgraph for charts
try:
    import pyqtgraph as pg
    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False
    print("[DASHBOARD] pyqtgraph not available - using placeholder chart")


def _to_lower(s: Optional[str]) -> str:
    return str(s or "").strip().lower()


def _parse_date_any(dval: Any) -> Optional[datetime]:
    if not dval:
        return None
    if isinstance(dval, datetime):
        return dval
    if isinstance(dval, date):
        return datetime(dval.year, dval.month, dval.day)
    s = str(dval)
    # Try ISO (including 'Z')
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        pass
    # Common formats
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s[:10], fmt)
        except Exception:
            continue
    return None


class DashboardCard(QFrame):
    def __init__(self, title: str, value: str, icon: str = "", subtitle: str = "", color: str = "#4f46e5", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("DashboardCard")
        self._setup_ui(title, value, icon, subtitle, color)
        self._apply_styles()
    
    def _setup_ui(self, title: str, value: str, icon: str, subtitle: str, color: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)
        header = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setObjectName("cardTitle")
        self.title_label.setStyleSheet(f"color: #64748b; font-size: 13px; font-weight: 500;")
        header.addWidget(self.title_label)
        header.addStretch()
        if icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet(f"color: {color}; font-size: 24px;")
            header.addWidget(icon_label)
        layout.addLayout(header)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("cardValue")
        font = QFont(); font.setPointSize(24); font.setBold(True)
        self.value_label.setFont(font)
        self.value_label.setStyleSheet("color: #1e293b;")
        layout.addWidget(self.value_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
            layout.addWidget(subtitle_label)
        layout.addStretch()
    
    def _apply_styles(self):
        self.setStyleSheet("""
            DashboardCard, QFrame#DashboardCard {
                background-color: white;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    
    def set_value(self, value: str):
        self.value_label.setText(value)


class SalesChart(QFrame):
    def __init__(self, title: str = "Resumen de Ingresos", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("SalesChart")
        self._setup_ui(title)
    
    def _setup_ui(self, title: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #1e293b; font-size: 16px; font-weight: 600;")
        layout.addWidget(title_label)
        if HAS_PYQTGRAPH:
            pg.setConfigOptions(antialias=True)
            self.plot_widget = pg.PlotWidget()
            self.plot_widget.setBackground('w')
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
            self.plot_widget.setMinimumHeight(300)
            self.plot_widget.setLabel('left', 'Ingresos', units='$')
            self.plot_widget.setLabel('bottom', 'Mes')
            current_year = datetime.now().year
            ax = self.plot_widget.getAxis('bottom')
            ax.setTicks([[(i, datetime(current_year, i, 1).strftime('%b')) for i in range(1, 13)]])
            layout.addWidget(self.plot_widget, 1)
        else:
            placeholder = QLabel("📊 Instalar pyqtgraph para visualizar gráficos\n\npip install pyqtgraph")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("color: #94a3b8; font-size: 14px; padding: 40px;")
            layout.addWidget(placeholder, 1)
            self.plot_widget = None
        self.setStyleSheet("""
            QFrame#SalesChart {
                background-color: white;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        self.setMinimumHeight(256)
    
    def update_chart(self, monthly_data: Dict[int, float]):
        if not HAS_PYQTGRAPH or not self.plot_widget:
            return
        self.plot_widget.clear()
        months = list(range(1, 13))
        sales = [monthly_data.get(m, 0.0) for m in months]
        bargraph = pg.BarGraphItem(x=months, height=sales, width=0.6, brush='#4f46e5', pen='#4338ca')
        self.plot_widget.addItem(bargraph)
        max_sale = max(sales) if sales else 0
        if max_sale > 0:
            self.plot_widget.setYRange(0, max_sale * 1.1)
        else:
            self.plot_widget.setYRange(0, 100)
        self.plot_widget.setXRange(0, 13)


class ActivityList(QFrame):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("ActivityList")
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        title_label = QLabel("Actividad Reciente")
        title_label.setStyleSheet("color: #1e293b; font-size: 16px; font-weight: 600;")
        layout.addWidget(title_label)
        self.items_layout = QVBoxLayout()
        self.items_layout.setSpacing(8)
        layout.addLayout(self.items_layout)
        layout.addStretch()
        self.setStyleSheet("""
            QFrame#ActivityList {
                background-color: white;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
        """)
        self.setMinimumHeight(256)
    
    def _create_activity_item(self, icon: str, text: str, time: str) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        icon_label = QLabel(icon); icon_label.setStyleSheet("font-size: 18px;"); icon_label.setFixedWidth(24)
        layout.addWidget(icon_label)
        text_label = QLabel(text); text_label.setStyleSheet("color: #334155; font-size: 13px;")
        layout.addWidget(text_label, 1)
        time_label = QLabel(time); time_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(time_label)
        widget.setStyleSheet("""
            QWidget { background-color: #f8fafc; border-radius: 8px; }
            QWidget:hover { background-color: #f1f5f9; }
        """)
        return widget
    
    def clear(self):
        while self.items_layout.count() > 0:
            item = self.items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def add_activity(self, icon: str, text: str, time: str):
        item = self._create_activity_item(icon, text, time)
        self.items_layout.insertWidget(0, item)
        while self.items_layout.count() > 10:
            item = self.items_layout.takeAt(self.items_layout.count() - 1)
            if item.widget():
                item.widget().deleteLater()


class DashboardTab(QWidget):
    def __init__(self, logic=None, get_current_company_callable=None, parent=None):
        super().__init__(parent)
        self.logic = logic
        self.get_current_company = get_current_company_callable
        self._setup_ui()
        self._load_data()
    
    def _setup_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        content = QWidget(); content.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(24)
        cards_layout = QHBoxLayout(); cards_layout.setSpacing(16)
        self.card_ingresos = DashboardCard("Ingresos Totales", "$0.00", "💰", "Este mes", "#22c55e"); cards_layout.addWidget(self.card_ingresos)
        self.card_pendientes = DashboardCard("Facturas Pendientes", "$0.00", "📋", "Por cobrar", "#f59e0b"); cards_layout.addWidget(self.card_pendientes)
        self.card_cotizaciones = DashboardCard("Cotizaciones", "0", "📝", "Este mes", "#4f46e5"); cards_layout.addWidget(self.card_cotizaciones)
        self.card_clientes = DashboardCard("Clientes Activos", "0", "👥", "Total", "#06b6d4"); cards_layout.addWidget(self.card_clientes)
        layout.addLayout(cards_layout)
        bottom_layout = QHBoxLayout(); bottom_layout.setSpacing(24)
        self.chart = SalesChart("Resumen de Ingresos"); bottom_layout.addWidget(self.chart, 2)
        self.activity_list = ActivityList(); bottom_layout.addWidget(self.activity_list, 1)
        layout.addLayout(bottom_layout)
        layout.addStretch()
        scroll.setWidget(content)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)
    
    # ---------------- Data loading ----------------
    def _safe_list(self, method_name: str, *args, **kwargs) -> List[Dict[str, Any]]:
        if not self.logic:
            return []
        # Try preferred method, then common aliases
        for name in (method_name, f"get_{method_name}", f"list_{method_name}"):
            if hasattr(self.logic, name):
                try:
                    res = getattr(self.logic, name)(*args, **kwargs) or []
                    if isinstance(res, list):
                        return res
                except Exception as e:
                    print(f"[Dashboard] Error calling {name}: {e}")
        return []
    
    def _load_data(self):
        if not self.logic or not self.get_current_company:
            return
        try:
            company = self.get_current_company()
            if not company:
                return
            company_id = company.get('id')

            # Invoices
            all_invoices = self._safe_list("facturas", company_id)
            # Filter to income invoices only
            income_invoices = []
            for f in all_invoices:
                inv_type = _to_lower(f.get('invoice_type') or f.get('type'))
                if inv_type in EXPENSE_TYPES:
                    continue
                if inv_type in INGRESO_TYPES or inv_type == 'emitida':
                    income_invoices.append(f)
            print(f"[Dashboard] Filtered {len(income_invoices)} income invoices from {len(all_invoices)} total")

            # Totals
            total_ingresos = sum(float(f.get('total_amount') or f.get('total') or 0) for f in income_invoices)
            self.card_ingresos.set_value(f"${total_ingresos:,.2f}")

            pending_total = 0.0
            for f in income_invoices:
                status = _to_lower(f.get('status'))
                if status not in ('paid', 'pagada', 'cobrada'):
                    pending_total += float(f.get('total_amount') or f.get('total') or 0)
            self.card_pendientes.set_value(f"${pending_total:,.2f}")

            # Chart
            self._update_chart_data(income_invoices)

            # Quotations count (this month)
            quotations = self._safe_list("quotations", company_id)
            # Count only current month
            cur_y = datetime.now().year; cur_m = datetime.now().month
            q_this_month = 0
            for q in quotations:
                qdate = _parse_date_any(q.get('date') or q.get('quotation_date') or q.get('created_at'))
                if qdate and qdate.year == cur_y and qdate.month == cur_m:
                    q_this_month += 1
            self.card_cotizaciones.set_value(str(q_this_month))

            # Clients active (unique client names appearing in income invoices OR backend third parties)
            clients_list = self._safe_list("third_parties", company_id)
            if clients_list:
                self.card_clientes.set_value(str(len(clients_list)))
            else:
                # Derive from invoices
                names = set()
                for f in income_invoices:
                    name = (f.get('client_name') or f.get('third_party_name') or "").strip()
                    if name:
                        names.add(name)
                self.card_clientes.set_value(str(len(names)) if names else "0")

            # Recent activity
            self._load_recent_activity(company_id, income_invoices, quotations)

        except Exception as e:
            print(f"[DashboardTab] Error loading data: {e}")

    def _load_recent_activity(self, company_id: Any, invoices: List[Dict[str, Any]], quotations: List[Dict[str, Any]]):
        # Build recent items from invoices and quotations
        events: List[Tuple[datetime, str, str]] = []  # (time, icon, text)

        # Invoices: created/updated
        for inv in invoices:
            dt = _parse_date_any(inv.get('updated_at') or inv.get('created_at') or inv.get('date'))
            if dt:
                num = inv.get('ncf') or inv.get('number') or inv.get('display_number') or ""
                client = inv.get('client_name') or inv.get('third_party_name') or ""
                text = f"Factura {num} para {client}" if client else f"Factura {num}"
                icon = "📄" if _to_lower(inv.get('status')) not in ('paid','pagada','cobrada') else "✅"
                events.append((dt, icon, text))

        # Quotations: created/sent
        for qt in quotations:
            dt = _parse_date_any(qt.get('updated_at') or qt.get('created_at') or qt.get('date'))
            if dt:
                num = qt.get('number') or qt.get('display_number') or ""
                client = qt.get('client_name') or qt.get('third_party_name') or ""
                text = f"Cotización {num} para {client}" if client else f"Cotización {num}"
                icon = "📝"
                events.append((dt, icon, text))

        # Sort by time desc and take last 10
        events.sort(key=lambda x: x[0], reverse=True)
        events = events[:10]

        # Render
        self.activity_list.clear()
        now = datetime.now()
        for dt, icon, text in events:
            diff = now - dt
            mins = int(diff.total_seconds() // 60)
            if mins < 60:
                when = f"Hace {mins} minutos"
            else:
                hours = mins // 60
                if hours < 24:
                    when = f"Hace {hours} horas"
                else:
                    days = hours // 24
                    when = "Ayer" if days == 1 else f"Hace {days} días"
            self.activity_list.add_activity(icon, text, when)

    def _update_chart_data(self, invoices: List[Dict[str, Any]]):
        current_year = datetime.now().year
        monthly_totals = {m: 0.0 for m in range(1, 13)}
        for invoice in invoices:
            invoice_date = _parse_date_any(invoice.get('invoice_date') or invoice.get('date') or invoice.get('created_at'))
            if not invoice_date:
                continue
            if invoice_date.year == current_year:
                month = invoice_date.month
                amount = float(invoice.get('total_amount') or invoice.get('total') or 0)
                monthly_totals[month] += amount
        if hasattr(self.chart, 'update_chart'):
            self.chart.update_chart(monthly_totals)
    
    def refresh(self):
        self._load_data()
    
    def on_company_change(self):
        self._load_data()