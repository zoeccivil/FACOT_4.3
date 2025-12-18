"""
Centralized logging system for FACOT application.

Provides structured logging with timestamps and details for:
- Audit trail (CRUD operations)
- System events
- Error tracking

This log will be used for debugging and can help rebuild indices if needed.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import json


# Configure logging format
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Log file location
LOG_DIR = Path.home() / ".facot" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "facot_audit.log"


class AuditLogger:
    """
    Centralized audit logger for FACOT application.
    
    Logs all significant actions (Create, Read, Update, Delete) with timestamps
    and details for audit trail and system recovery.
    """
    
    _instance: Optional['AuditLogger'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the logger (singleton pattern)."""
        if self._initialized:
            return
        
        # Create logger
        self.logger = logging.getLogger("FACOT_AUDIT")
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid duplicates
        self.logger.handlers.clear()
        
        # File handler
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # Console handler (for debugging)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)  # Only warnings and errors to console
        console_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        self._initialized = True
        self.logger.info("Audit logger initialized")
    
    def _format_details(self, details: Dict[str, Any]) -> str:
        """Format details dictionary as JSON string."""
        try:
            return json.dumps(details, ensure_ascii=False, default=str)
        except Exception:
            return str(details)
    
    def log_create(self, entity_type: str, entity_id: Any, details: Optional[Dict[str, Any]] = None):
        """
        Log a CREATE operation.
        
        Args:
            entity_type: Type of entity (e.g., 'Invoice', 'Quotation', 'Company')
            entity_id: ID of created entity
            details: Additional details (e.g., {'total': 5000, 'client': 'ABC Corp'})
        """
        msg = f"CREATE {entity_type} ID: {entity_id}"
        if details:
            msg += f" | Details: {self._format_details(details)}"
        self.logger.info(msg)
    
    def log_read(self, entity_type: str, query: Optional[str] = None, count: Optional[int] = None):
        """
        Log a READ operation.
        
        Args:
            entity_type: Type of entity being read
            query: Optional query description
            count: Number of records returned
        """
        msg = f"READ {entity_type}"
        if query:
            msg += f" | Query: {query}"
        if count is not None:
            msg += f" | Count: {count}"
        self.logger.info(msg)
    
    def log_update(self, entity_type: str, entity_id: Any, changes: Optional[Dict[str, Any]] = None):
        """
        Log an UPDATE operation.
        
        Args:
            entity_type: Type of entity
            entity_id: ID of updated entity
            changes: Dictionary of changed fields
        """
        msg = f"UPDATE {entity_type} ID: {entity_id}"
        if changes:
            msg += f" | Changes: {self._format_details(changes)}"
        self.logger.info(msg)
    
    def log_delete(self, entity_type: str, entity_id: Any, details: Optional[Dict[str, Any]] = None):
        """
        Log a DELETE operation.
        
        Args:
            entity_type: Type of entity
            entity_id: ID of deleted entity
            details: Additional details about the deleted entity
        """
        msg = f"DELETE {entity_type} ID: {entity_id}"
        if details:
            msg += f" | Details: {self._format_details(details)}"
        self.logger.warning(msg)  # Use WARNING level for deletes
    
    def log_error(self, operation: str, error: Exception, context: Optional[Dict[str, Any]] = None):
        """
        Log an error.
        
        Args:
            operation: Operation that failed
            error: Exception that occurred
            context: Additional context information
        """
        msg = f"ERROR {operation} | Error: {str(error)}"
        if context:
            msg += f" | Context: {self._format_details(context)}"
        self.logger.error(msg, exc_info=True)
    
    def log_info(self, message: str, details: Optional[Dict[str, Any]] = None):
        """
        Log a general informational message.
        
        Args:
            message: Log message
            details: Optional additional details
        """
        msg = message
        if details:
            msg += f" | Details: {self._format_details(details)}"
        self.logger.info(msg)
    
    def log_invoice_created(self, invoice_id: Any, invoice_type: str, total: float, 
                           company_id: Optional[Any] = None, client: Optional[str] = None):
        """
        Convenience method to log invoice creation.
        
        Example: [2023-10-27 10:00:00] [INFO] Invoice created ID: 105, Type: EMITIDA, Total: 5000.00
        """
        details = {
            'type': invoice_type.upper(),
            'total': f"{total:.2f}",
        }
        if company_id:
            details['company_id'] = company_id
        if client:
            details['client'] = client
        
        self.log_create('Invoice', invoice_id, details)


# Global instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


# Convenience functions
def log_create(entity_type: str, entity_id: Any, details: Optional[Dict[str, Any]] = None):
    """Log a CREATE operation."""
    get_audit_logger().log_create(entity_type, entity_id, details)


def log_read(entity_type: str, query: Optional[str] = None, count: Optional[int] = None):
    """Log a READ operation."""
    get_audit_logger().log_read(entity_type, query, count)


def log_update(entity_type: str, entity_id: Any, changes: Optional[Dict[str, Any]] = None):
    """Log an UPDATE operation."""
    get_audit_logger().log_update(entity_type, entity_id, changes)


def log_delete(entity_type: str, entity_id: Any, details: Optional[Dict[str, Any]] = None):
    """Log a DELETE operation."""
    get_audit_logger().log_delete(entity_type, entity_id, details)


def log_error(operation: str, error: Exception, context: Optional[Dict[str, Any]] = None):
    """Log an error."""
    get_audit_logger().log_error(operation, error, context)


def log_info(message: str, details: Optional[Dict[str, Any]] = None):
    """Log a general informational message."""
    get_audit_logger().log_info(message, details)
