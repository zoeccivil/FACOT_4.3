"""
Tests para el sistema de backups.
"""
import os
import json
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestBackupRunner:
    """Tests para BackupRunner."""
    
    @pytest.fixture
    def temp_backup_dir(self):
        """Crea directorio temporal para backups."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def mock_firestore(self):
        """Mock de cliente Firestore."""
        mock_db = Mock()
        
        # Mock de colección vacía
        mock_collection = Mock()
        mock_collection.stream.return_value = []
        mock_db.collection.return_value = mock_collection
        
        return mock_db
    
    def test_backup_runner_init(self, temp_backup_dir, mock_firestore):
        """Test de inicialización del runner."""
        from utils.backups.backup_runner import BackupRunner
        runner = BackupRunner(backup_dir=temp_backup_dir)
        runner.db = mock_firestore  # Override db
        
        assert runner.backup_dir == Path(temp_backup_dir)
        assert len(runner.collections) > 0
    
    def test_backup_creates_directory(self, temp_backup_dir, mock_firestore):
        """Test de que backup crea el directorio."""
        from utils.backups.backup_runner import BackupRunner
        runner = BackupRunner(backup_dir=temp_backup_dir)
        runner.db = mock_firestore  # Override db
        
        date_str = "2024-11-27"
        runner.run_backup(date_str)
        
        backup_path = Path(temp_backup_dir) / date_str
        assert backup_path.exists()
    
    def test_backup_creates_metadata(self, temp_backup_dir, mock_firestore):
        """Test de que backup crea metadata."""
        from utils.backups.backup_runner import BackupRunner
        runner = BackupRunner(backup_dir=temp_backup_dir)
        runner.db = mock_firestore  # Override db
        
        date_str = "2024-11-27"
        runner.run_backup(date_str)
        
        metadata_path = Path(temp_backup_dir) / date_str / "_metadata.json"
        assert metadata_path.exists()
        
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
            assert 'backup_date' in metadata
            assert 'backup_time' in metadata
    
    def test_backup_exists_for_date(self, temp_backup_dir, mock_firestore):
        """Test de verificación de backup existente."""
        from utils.backups.backup_runner import BackupRunner
        runner = BackupRunner(backup_dir=temp_backup_dir)
        runner.db = mock_firestore  # Override db
        
        date_str = "2024-11-27"
        
        # No existe aún
        assert runner.backup_exists_for_date(date_str) is False
        
        # Crear backup
        runner.run_backup(date_str)
        
        # Ahora existe
        assert runner.backup_exists_for_date(date_str) is True
    
    def test_list_backups(self, temp_backup_dir, mock_firestore):
        """Test de listar backups."""
        from utils.backups.backup_runner import BackupRunner
        runner = BackupRunner(backup_dir=temp_backup_dir)
        runner.db = mock_firestore  # Override db
        
        # Crear varios backups
        runner.run_backup("2024-11-25")
        runner.run_backup("2024-11-26")
        runner.run_backup("2024-11-27")
        
        backups = runner.list_backups()
        
        assert len(backups) == 3


class TestRetention:
    """Tests para el sistema de retención."""
    
    @pytest.fixture
    def temp_backup_dir(self):
        """Crea directorio temporal con backups de prueba."""
        temp_dir = tempfile.mkdtemp()
        
        # Crear backups de prueba
        today = datetime.now()
        for days_ago in [5, 15, 35, 45]:
            date = today - timedelta(days=days_ago)
            date_str = date.strftime("%Y-%m-%d")
            backup_path = Path(temp_dir) / date_str
            backup_path.mkdir(parents=True)
            
            # Crear metadata
            metadata = {"backup_date": date_str}
            with open(backup_path / "_metadata.json", 'w') as f:
                json.dump(metadata, f)
        
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_cleanup_old_backups(self, temp_backup_dir):
        """Test de limpieza de backups antiguos."""
        from utils.backups.retention import cleanup_old_backups
        
        result = cleanup_old_backups(
            backup_dir=temp_backup_dir,
            retention_days=30
        )
        
        # Backups de 35 y 45 días deberían ser eliminados
        assert len(result['deleted']) == 2
        # Backups de 5 y 15 días deberían conservarse
        assert len(result['kept']) == 2
    
    def test_cleanup_dry_run(self, temp_backup_dir):
        """Test de limpieza en modo simulación."""
        from utils.backups.retention import cleanup_old_backups
        
        result = cleanup_old_backups(
            backup_dir=temp_backup_dir,
            retention_days=30,
            dry_run=True
        )
        
        # Debería identificar pero no eliminar
        assert len(result['deleted']) == 2
        
        # Verificar que los archivos aún existen
        for backup in result['deleted']:
            assert Path(backup['path']).exists()
    
    def test_get_backup_stats(self, temp_backup_dir):
        """Test de estadísticas de backups."""
        from utils.backups.retention import get_backup_stats
        
        stats = get_backup_stats(backup_dir=temp_backup_dir)
        
        assert stats['exists'] is True
        assert stats['total_backups'] == 4
        assert stats['oldest_backup'] is not None
        assert stats['newest_backup'] is not None


class TestScheduler:
    """Tests para el scheduler de backups."""
    
    def test_scheduler_singleton(self):
        """Test de patrón singleton."""
        from utils.backups.scheduler import BackupScheduler
        
        s1 = BackupScheduler()
        s2 = BackupScheduler()
        
        assert s1 is s2
    
    def test_parse_time(self):
        """Test de parseo de hora."""
        from utils.backups.scheduler import BackupScheduler
        
        scheduler = BackupScheduler()
        
        hour, minute = scheduler._parse_time("02:00")
        assert hour == 2
        assert minute == 0
        
        hour, minute = scheduler._parse_time("14:30")
        assert hour == 14
        assert minute == 30
    
    def test_get_status(self):
        """Test de obtener estado del scheduler."""
        from utils.backups.scheduler import BackupScheduler
        
        scheduler = BackupScheduler()
        status = scheduler.get_status()
        
        assert 'running' in status
        assert 'backup_hour' in status
        assert 'backup_dir' in status
        assert 'retention_days' in status
