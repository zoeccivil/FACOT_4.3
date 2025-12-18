# Constantes compartidas
NCF_TYPES = {
    "Crédito Fiscal (B01)": "B01",
    "Consumidor Final (B02)": "B02",
    "Gubernamental (B15)": "B15",
    "Régimen Especial (B14)": "B14",
    "Nota de Crédito (B04)": "B04",
}
ITBIS_RATE = 0.18
DEFAULT_CURRENCY = "RD$"

# Invoice Types - Centralized Definitions
# Used across the application for consistent filtering of income vs expense invoices

# Invoice type names that represent income/revenue (case-insensitive matching)
INVOICE_TYPE_INGRESOS = {
    "INGRESO",
    "FACTURA",
    "FACTURA PRIVADA",
    "EMITIDA",
    "VENTA",
    "CREDITO FISCAL",
    "CONSUMIDOR FINAL",
    "GUBERNAMENTAL",
    "REGIMEN ESPECIAL",
    "EXPORTACION",
}

# NCF prefixes that correspond to sales/income invoices
NCF_PREFIX_INGRESOS = {
    "B01",  # Crédito Fiscal
    "B02",  # Consumidor Final
    "B14",  # Régimen Especial
    "B15",  # Gubernamental
    "B16",  # Exportación
}

# Combined set for filtering (used by invoice history)
INGRESO_TYPES_FULL = INVOICE_TYPE_INGRESOS | NCF_PREFIX_INGRESOS

# Simplified list for database filtering (primary invoice type field)
# This is used for dashboard and revenue calculations where we filter by the invoice_type field
INGRESO_TYPES = ["emitida"]  # Primary income invoice type in database

# Expense invoice types (to explicitly exclude from revenue)
EXPENSE_TYPES = ["gasto"]  # Expense invoices should be excluded from revenue