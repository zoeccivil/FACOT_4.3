"""
Test for audit logging functionality.

Verifies that the audit logger correctly logs CRUD operations.
"""
import pytest
import os
import tempfile
from pathlib import Path
from utils.logger import AuditLogger, get_audit_logger, log_create, log_delete


def test_audit_logger_singleton():
    """Test that AuditLogger follows singleton pattern."""
    logger1 = get_audit_logger()
    logger2 = get_audit_logger()
    assert logger1 is logger2


def test_log_create():
    """Test logging create operations."""
    logger = get_audit_logger()
    
    # Should not raise exception
    logger.log_create('Invoice', 123, {'type': 'emitida', 'total': 5000.0})
    logger.log_create('Quotation', 456)


def test_log_update():
    """Test logging update operations."""
    logger = get_audit_logger()
    
    # Should not raise exception
    logger.log_update('Invoice', 123, {'total': 6000.0})


def test_log_delete():
    """Test logging delete operations."""
    logger = get_audit_logger()
    
    # Should not raise exception
    logger.log_delete('Invoice', 123, {'type': 'emitida'})


def test_log_invoice_created():
    """Test convenience method for invoice creation logging."""
    logger = get_audit_logger()
    
    # Should not raise exception
    logger.log_invoice_created(
        invoice_id=105,
        invoice_type='emitida',
        total=5000.0,
        company_id=1,
        client='ABC Corp'
    )


def test_log_error():
    """Test logging errors."""
    logger = get_audit_logger()
    
    try:
        raise ValueError("Test error")
    except Exception as e:
        # Should not raise exception
        logger.log_error('test_operation', e, {'context': 'test'})


def test_convenience_functions():
    """Test convenience wrapper functions."""
    # Should not raise exceptions
    log_create('Invoice', 999, {'test': True})
    log_delete('Invoice', 999, {'test': True})


def test_log_file_created():
    """Test that log file is created."""
    logger = get_audit_logger()
    
    # Log something to ensure file is created
    logger.log_info("Test message")
    
    # Check that log directory exists
    log_dir = Path.home() / ".facot" / "logs"
    assert log_dir.exists()
    
    # Check that log file exists
    log_file = log_dir / "facot_audit.log"
    assert log_file.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
