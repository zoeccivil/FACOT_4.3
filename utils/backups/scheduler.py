"""
Scheduler - Programador de backups automáticos.

Ejecuta backups diarios a una hora configurada usando threading.
También ejecuta limpieza de backups antiguos.
"""

from __future__ import annotations
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Callable

from .backup_runner import BackupRunner
from .retention import cleanup_old_backups

# Hora por defecto para backups (02:00)
DEFAULT_BACKUP_HOUR = "02:00"


class BackupScheduler:
    """
    Programador de backups automáticos.
    
    Ejecuta backups diarios en segundo plano a la hora configurada.
    También limpia backups antiguos según política de retención.
    """
    
    _instance: Optional[BackupScheduler] = None
    
    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Configuración
        self.backup_dir = os.getenv("BACKUP_DIR", "./backups")
        self.backup_hour = os.getenv("BACKUP_HOUR", DEFAULT_BACKUP_HOUR)
        self.retention_days = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
        
        # Callbacks opcionales
        self.on_backup_complete: Optional[Callable] = None
        self.on_backup_error: Optional[Callable] = None
    
    def _parse_time(self, time_str: str) -> tuple:
        """
        Parsea una hora en formato HH:MM.
        
        Returns:
            Tuple (hour, minute)
        """
        try:
            parts = time_str.split(':')
            return (int(parts[0]), int(parts[1]))
        except Exception:
            return (2, 0)  # Default 02:00
    
    def _next_backup_time(self) -> datetime:
        """
        Calcula la próxima hora de backup.
        
        Returns:
            datetime de la próxima ejecución
        """
        hour, minute = self._parse_time(self.backup_hour)
        now = datetime.now()
        
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        if next_run <= now:
            # Ya pasó la hora hoy, programar para mañana
            next_run += timedelta(days=1)
        
        return next_run
    
    def _run_backup(self) -> bool:
        """
        Ejecuta el backup y la limpieza de retención.
        
        Returns:
            True si el backup fue exitoso
        """
        print(f"[SCHEDULER] Iniciando backup programado: {datetime.now()}")
        
        try:
            # Ejecutar backup
            runner = BackupRunner(self.backup_dir)
            result = runner.run_backup()
            
            if result['success']:
                print(f"[SCHEDULER] Backup completado: {result.get('backup_path')}")
                
                # Ejecutar limpieza de retención
                cleanup_result = cleanup_old_backups(
                    self.backup_dir, 
                    self.retention_days
                )
                
                print(f"[SCHEDULER] Limpieza: {len(cleanup_result['deleted'])} backups eliminados")
                
                if self.on_backup_complete:
                    self.on_backup_complete(result)
                
                return True
            else:
                print(f"[SCHEDULER] Backup fallido: {result.get('errors')}")
                
                if self.on_backup_error:
                    self.on_backup_error(result)
                
                return False
                
        except Exception as e:
            print(f"[SCHEDULER] Error en backup programado: {e}")
            
            if self.on_backup_error:
                self.on_backup_error({'error': str(e)})
            
            return False
    
    def _scheduler_loop(self):
        """Loop principal del scheduler."""
        print(f"[SCHEDULER] Iniciado. Próximo backup a las {self.backup_hour}")
        
        while not self._stop_event.is_set():
            try:
                # Verificar si falta backup del día
                runner = BackupRunner(self.backup_dir)
                today = datetime.now().strftime("%Y-%m-%d")
                
                if not runner.backup_exists_for_date(today):
                    # No hay backup de hoy, verificar si es hora
                    next_time = self._next_backup_time()
                    now = datetime.now()
                    
                    if next_time.date() == now.date():
                        # Backup programado para hoy, esperar hasta la hora
                        wait_seconds = (next_time - now).total_seconds()
                        
                        if wait_seconds <= 0:
                            # Es hora de ejecutar
                            self._run_backup()
                        else:
                            # Esperar en intervalos de 60 segundos
                            wait_seconds = min(wait_seconds, 60)
                            self._stop_event.wait(timeout=wait_seconds)
                    else:
                        # Ya pasó la hora de hoy, ejecutar ahora
                        self._run_backup()
                else:
                    # Ya hay backup de hoy, esperar hasta mañana
                    next_time = self._next_backup_time()
                    wait_seconds = min((next_time - datetime.now()).total_seconds(), 3600)
                    self._stop_event.wait(timeout=max(wait_seconds, 60))
                
            except Exception as e:
                print(f"[SCHEDULER] Error en loop: {e}")
                self._stop_event.wait(timeout=60)
        
        print("[SCHEDULER] Detenido")
    
    def start(self):
        """Inicia el scheduler en segundo plano."""
        if self._running:
            print("[SCHEDULER] Ya está corriendo")
            return
        
        self._running = True
        self._stop_event.clear()
        
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.start()
        
        print("[SCHEDULER] Iniciado")
    
    def stop(self):
        """Detiene el scheduler."""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=5)
        
        print("[SCHEDULER] Detenido")
    
    def is_running(self) -> bool:
        """Retorna True si el scheduler está corriendo."""
        return self._running
    
    def run_now(self) -> bool:
        """
        Ejecuta un backup inmediatamente.
        
        Returns:
            True si fue exitoso
        """
        return self._run_backup()
    
    def get_status(self) -> dict:
        """
        Obtiene el estado del scheduler.
        
        Returns:
            Dict con información de estado
        """
        runner = BackupRunner(self.backup_dir)
        today = datetime.now().strftime("%Y-%m-%d")
        
        return {
            'running': self._running,
            'backup_hour': self.backup_hour,
            'backup_dir': self.backup_dir,
            'retention_days': self.retention_days,
            'next_backup': self._next_backup_time().isoformat(),
            'today_backup_exists': runner.backup_exists_for_date(today),
            'total_backups': len(runner.list_backups())
        }


# Instancia global
_scheduler: Optional[BackupScheduler] = None


def get_backup_scheduler() -> BackupScheduler:
    """Obtiene la instancia global del scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackupScheduler()
    return _scheduler


def start_backup_scheduler():
    """Inicia el scheduler de backups."""
    scheduler = get_backup_scheduler()
    scheduler.start()


def stop_backup_scheduler():
    """Detiene el scheduler de backups."""
    scheduler = get_backup_scheduler()
    scheduler.stop()
