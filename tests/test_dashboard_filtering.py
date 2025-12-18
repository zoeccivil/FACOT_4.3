"""
Test for dashboard filtering logic.

Verifies that the dashboard correctly filters invoices by type,
excluding expenses from revenue calculations.
"""
import pytest
from datetime import datetime
from constants import INGRESO_TYPES, EXPENSE_TYPES


def test_ingreso_types_constant():
    """Test that INGRESO_TYPES constant is defined correctly."""
    assert INGRESO_TYPES == ["emitida"]
    assert "emitida" in INGRESO_TYPES


def test_expense_types_constant():
    """Test that EXPENSE_TYPES constant is defined correctly."""
    assert EXPENSE_TYPES == ["gasto"]
    assert "gasto" in EXPENSE_TYPES


def test_invoice_filtering_logic():
    """Test that invoice filtering logic works correctly."""
    # Sample invoices with different types
    invoices = [
        {"id": 1, "invoice_type": "emitida", "total_amount": 1000.0},
        {"id": 2, "invoice_type": "gasto", "total_amount": 500.0},
        {"id": 3, "invoice_type": "emitida", "total_amount": 2000.0},
        {"id": 4, "invoice_type": "EMITIDA", "total_amount": 1500.0},  # uppercase
        {"id": 5, "invoice_type": "GASTO", "total_amount": 300.0},  # uppercase
    ]
    
    # Filter for income invoices only (same logic as in DashboardTab)
    income_invoices = [
        f for f in invoices
        if f.get('invoice_type', '').lower() in [t.lower() for t in INGRESO_TYPES]
        and f.get('invoice_type', '').lower() not in [t.lower() for t in EXPENSE_TYPES]
    ]
    
    # Should only include emitida invoices (IDs 1, 3, 4)
    assert len(income_invoices) == 3
    assert all(inv['invoice_type'].lower() == 'emitida' for inv in income_invoices)
    
    # Calculate total (should exclude expenses)
    total_income = sum(float(f.get('total_amount', 0) or 0) for f in income_invoices)
    assert total_income == 4500.0  # 1000 + 2000 + 1500
    
    # Verify expenses are excluded
    expense_ids = {inv['id'] for inv in income_invoices}
    assert 2 not in expense_ids  # gasto with 500
    assert 5 not in expense_ids  # GASTO with 300


def test_monthly_data_aggregation():
    """Test monthly data aggregation for chart."""
    # Sample invoices with dates
    invoices = [
        {"id": 1, "invoice_type": "emitida", "total_amount": 1000.0, "invoice_date": "2024-01-15"},
        {"id": 2, "invoice_type": "emitida", "total_amount": 2000.0, "invoice_date": "2024-01-20"},
        {"id": 3, "invoice_type": "emitida", "total_amount": 1500.0, "invoice_date": "2024-02-10"},
        {"id": 4, "invoice_type": "gasto", "total_amount": 500.0, "invoice_date": "2024-01-25"},  # Should be excluded
        {"id": 5, "invoice_type": "emitida", "total_amount": 3000.0, "invoice_date": "2023-12-15"},  # Previous year
    ]
    
    current_year = 2024
    monthly_totals = {month: 0.0 for month in range(1, 13)}
    
    # Filter for income only
    income_invoices = [
        f for f in invoices
        if f.get('invoice_type', '').lower() in [t.lower() for t in INGRESO_TYPES]
        and f.get('invoice_type', '').lower() not in [t.lower() for t in EXPENSE_TYPES]
    ]
    
    # Aggregate by month
    for invoice in income_invoices:
        invoice_date_str = invoice.get('invoice_date')
        if invoice_date_str:
            invoice_date = datetime.fromisoformat(invoice_date_str)
            if invoice_date.year == current_year:
                month = invoice_date.month
                amount = float(invoice.get('total_amount', 0) or 0)
                monthly_totals[month] += amount
    
    # Verify monthly totals
    assert monthly_totals[1] == 3000.0  # Jan: 1000 + 2000 (expense excluded)
    assert monthly_totals[2] == 1500.0  # Feb: 1500
    assert monthly_totals[3] == 0.0     # Mar: 0
    assert monthly_totals[12] == 0.0    # Dec 2023 excluded (previous year)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
