"""
Retention - Gestión de retención de backups.

Elimina backups antiguos según política de retención configurada.
"""

from __future__ import annotations
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

# Retención por defecto: 30 días
DEFAULT_RETENTION_DAYS = 30


def cleanup_old_backups(
    backup_dir: Optional[str] = None,
    retention_days: Optional[int] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Elimina backups que excedan el período de retención.
    
    Args:
        backup_dir: Directorio de backups (default: ./backups)
        retention_days: Días de retención (default: 30)
        dry_run: Si True, solo reporta sin eliminar
    
    Returns:
        Dict con resultado de la limpieza
    """
    backup_path = Path(backup_dir or os.getenv("BACKUP_DIR", "./backups"))
    days = retention_days or int(os.getenv("BACKUP_RETENTION_DAYS", DEFAULT_RETENTION_DAYS))
    
    result = {
        'retention_days': days,
        'backup_dir': str(backup_path),
        'dry_run': dry_run,
        'deleted': [],
        'kept': [],
        'errors': []
    }
    
    if not backup_path.exists():
        result['errors'].append(f"Directorio no existe: {backup_path}")
        return result
    
    # Fecha límite
    cutoff_date = datetime.now() - timedelta(days=days)
    
    for item in backup_path.iterdir():
        if not item.is_dir() or item.name.startswith('.'):
            continue
        
        # Parsear fecha del nombre del directorio
        try:
            backup_date = datetime.strptime(item.name, "%Y-%m-%d")
        except ValueError:
            # Nombre no es fecha válida, ignorar
            continue
        
        backup_info = {
            'date': item.name,
            'path': str(item)
        }
        
        if backup_date < cutoff_date:
            # Backup antiguo, eliminar
            if dry_run:
                backup_info['action'] = 'would_delete'
                result['deleted'].append(backup_info)
            else:
                try:
                    shutil.rmtree(item)
                    backup_info['action'] = 'deleted'
                    result['deleted'].append(backup_info)
                    print(f"[RETENTION] Eliminado backup antiguo: {item.name}")
                except Exception as e:
                    backup_info['error'] = str(e)
                    result['errors'].append(backup_info)
                    print(f"[RETENTION] Error eliminando {item.name}: {e}")
        else:
            backup_info['action'] = 'kept'
            result['kept'].append(backup_info)
    
    print(f"[RETENTION] Limpieza completada: {len(result['deleted'])} eliminados, "
          f"{len(result['kept'])} conservados")
    
    return result


def get_backup_stats(backup_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Obtiene estadísticas de los backups.
    
    Args:
        backup_dir: Directorio de backups
    
    Returns:
        Dict con estadísticas
    """
    backup_path = Path(backup_dir or os.getenv("BACKUP_DIR", "./backups"))
    
    stats = {
        'backup_dir': str(backup_path),
        'exists': backup_path.exists(),
        'total_backups': 0,
        'oldest_backup': None,
        'newest_backup': None,
        'total_size_bytes': 0,
        'total_size_mb': 0,
        'backups_by_month': {}
    }
    
    if not backup_path.exists():
        return stats
    
    backup_dates = []
    
    for item in backup_path.iterdir():
        if not item.is_dir() or item.name.startswith('.'):
            continue
        
        try:
            datetime.strptime(item.name, "%Y-%m-%d")
            backup_dates.append(item.name)
            
            # Calcular tamaño
            size = sum(f.stat().st_size for f in item.rglob('*') if f.is_file())
            stats['total_size_bytes'] += size
            
            # Agrupar por mes
            month_key = item.name[:7]  # YYYY-MM
            if month_key not in stats['backups_by_month']:
                stats['backups_by_month'][month_key] = 0
            stats['backups_by_month'][month_key] += 1
            
        except ValueError:
            continue
    
    if backup_dates:
        backup_dates.sort()
        stats['total_backups'] = len(backup_dates)
        stats['oldest_backup'] = backup_dates[0]
        stats['newest_backup'] = backup_dates[-1]
        stats['total_size_mb'] = round(stats['total_size_bytes'] / (1024 * 1024), 2)
    
    return stats


def get_backups_to_delete(
    backup_dir: Optional[str] = None,
    retention_days: Optional[int] = None
) -> List[str]:
    """
    Lista los backups que serían eliminados según la política de retención.
    
    Args:
        backup_dir: Directorio de backups
        retention_days: Días de retención
    
    Returns:
        Lista de fechas de backups a eliminar
    """
    result = cleanup_old_backups(backup_dir, retention_days, dry_run=True)
    return [b['date'] for b in result['deleted']]
