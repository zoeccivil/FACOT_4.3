"""
Módulo de backups para FACOT.

Proporciona:
- backup_runner: Exportar colecciones de Firestore a archivos locales
- retention: Limpiar backups antiguos
- scheduler: Programar backups automáticos
"""

from .backup_runner import BackupRunner, create_backup
from .retention import cleanup_old_backups, get_backup_stats
from .scheduler import BackupScheduler, start_backup_scheduler, stop_backup_scheduler

__all__ = [
    'BackupRunner',
    'create_backup',
    'cleanup_old_backups',
    'get_backup_stats',
    'BackupScheduler',
    'start_backup_scheduler',
    'stop_backup_scheduler',
]
