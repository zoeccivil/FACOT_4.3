"""
BackupRunner - Exporta colecciones de Firestore a archivos locales.

Soporta formato JSON (por defecto) para los backups.
"""

from __future__ import annotations
import os
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Colecciones principales a respaldar
DEFAULT_COLLECTIONS = [
    'invoices',
    'quotations',
    'clients',
    'items',
    'companies',
    'ncf_sequence_configs',
    'third_parties',
]


class BackupRunner:
    """
    Ejecutor de backups de Firestore a archivos locales.
    
    Exporta colecciones a archivos JSON organizados por fecha.
    """
    
    def __init__(
        self, 
        backup_dir: Optional[str] = None,
        collections: Optional[List[str]] = None
    ):
        """
        Inicializa el runner de backups.
        
        Args:
            backup_dir: Directorio base para backups (default: ./backups)
            collections: Lista de colecciones a respaldar
        """
        self.backup_dir = Path(backup_dir or os.getenv("BACKUP_DIR", "./backups"))
        self.collections = collections or DEFAULT_COLLECTIONS
        self.db = None
        
        # Intentar obtener cliente Firestore
        self._init_firestore()
    
    def _init_firestore(self):
        """Inicializa el cliente de Firestore."""
        try:
            from firebase.firebase_client import get_firebase_client
            client = get_firebase_client()
            self.db = client.get_firestore()
        except Exception as e:
            print(f"[BACKUP] Error obteniendo Firestore: {e}")
    
    def _ensure_backup_dir(self, date_str: str) -> Path:
        """
        Asegura que exista el directorio de backup para la fecha.
        
        Args:
            date_str: Fecha en formato YYYY-MM-DD
        
        Returns:
            Path del directorio de backup
        """
        backup_path = self.backup_dir / date_str
        backup_path.mkdir(parents=True, exist_ok=True)
        return backup_path
    
    def _serialize_document(self, doc) -> Dict[str, Any]:
        """
        Serializa un documento de Firestore a dict.
        
        Args:
            doc: DocumentSnapshot de Firestore
        
        Returns:
            Dict con los datos del documento
        """
        data = doc.to_dict()
        data['_id'] = doc.id
        
        # Convertir tipos especiales
        for key, value in data.items():
            # Convertir Timestamp a ISO string
            if hasattr(value, 'isoformat'):
                data[key] = value.isoformat()
            elif hasattr(value, '_seconds'):  # Firestore Timestamp
                data[key] = datetime.fromtimestamp(value._seconds).isoformat()
        
        return data
    
    def _export_collection(self, collection_name: str) -> List[Dict[str, Any]]:
        """
        Exporta una colección completa.
        
        Args:
            collection_name: Nombre de la colección
        
        Returns:
            Lista de documentos como dicts
        """
        if not self.db:
            print(f"[BACKUP] Firestore no disponible, no se puede exportar {collection_name}")
            return []
        
        try:
            collection_ref = self.db.collection(collection_name)
            docs = []
            
            for doc in collection_ref.stream():
                doc_data = self._serialize_document(doc)
                
                # Exportar subcolecciones conocidas
                if collection_name == 'invoices':
                    items_ref = doc.reference.collection('items')
                    items = [self._serialize_document(item) for item in items_ref.stream()]
                    doc_data['_items'] = items
                elif collection_name == 'quotations':
                    items_ref = doc.reference.collection('items')
                    items = [self._serialize_document(item) for item in items_ref.stream()]
                    doc_data['_items'] = items
                
                docs.append(doc_data)
            
            print(f"[BACKUP] Exportados {len(docs)} documentos de {collection_name}")
            return docs
            
        except Exception as e:
            print(f"[BACKUP] Error exportando {collection_name}: {e}")
            return []
    
    def run_backup(self, date_str: Optional[str] = None) -> Dict[str, Any]:
        """
        Ejecuta un backup completo.
        
        Args:
            date_str: Fecha del backup (default: hoy)
        
        Returns:
            Dict con resultado del backup
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        
        result = {
            'date': date_str,
            'success': True,
            'collections': {},
            'errors': [],
            'backup_path': None
        }
        
        if not self.db:
            result['success'] = False
            result['errors'].append("Firestore no disponible")
            return result
        
        try:
            backup_path = self._ensure_backup_dir(date_str)
            result['backup_path'] = str(backup_path)
            
            for collection_name in self.collections:
                try:
                    docs = self._export_collection(collection_name)
                    
                    # Guardar en archivo JSON
                    file_path = backup_path / f"{collection_name}.json"
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(docs, f, ensure_ascii=False, indent=2, default=str)
                    
                    result['collections'][collection_name] = {
                        'count': len(docs),
                        'file': str(file_path)
                    }
                    
                except Exception as e:
                    error_msg = f"Error en {collection_name}: {str(e)}"
                    result['errors'].append(error_msg)
                    print(f"[BACKUP] {error_msg}")
            
            # Crear archivo de metadata
            metadata = {
                'backup_date': date_str,
                'backup_time': datetime.now().isoformat(),
                'collections': list(result['collections'].keys()),
                'total_documents': sum(c['count'] for c in result['collections'].values()),
                'errors': result['errors']
            }
            
            metadata_path = backup_path / "_metadata.json"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            if result['errors']:
                result['success'] = len(result['errors']) < len(self.collections)
            
            print(f"[BACKUP] Backup completado: {backup_path}")
            
        except Exception as e:
            result['success'] = False
            result['errors'].append(str(e))
            print(f"[BACKUP] Error en backup: {e}")
        
        return result
    
    def backup_exists_for_date(self, date_str: str) -> bool:
        """
        Verifica si ya existe un backup para la fecha.
        
        Args:
            date_str: Fecha en formato YYYY-MM-DD
        
        Returns:
            True si existe un backup válido
        """
        backup_path = self.backup_dir / date_str
        metadata_path = backup_path / "_metadata.json"
        return metadata_path.exists()
    
    def get_backup_info(self, date_str: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene información de un backup.
        
        Args:
            date_str: Fecha del backup
        
        Returns:
            Dict con metadata del backup o None
        """
        backup_path = self.backup_dir / date_str
        metadata_path = backup_path / "_metadata.json"
        
        if not metadata_path.exists():
            return None
        
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    
    def list_backups(self) -> List[Dict[str, Any]]:
        """
        Lista todos los backups disponibles.
        
        Returns:
            Lista de backups con su metadata
        """
        backups = []
        
        if not self.backup_dir.exists():
            return backups
        
        for item in sorted(self.backup_dir.iterdir(), reverse=True):
            if item.is_dir() and not item.name.startswith('.'):
                metadata = self.get_backup_info(item.name)
                if metadata:
                    metadata['path'] = str(item)
                    backups.append(metadata)
                else:
                    # Backup sin metadata, crear info básica
                    files = list(item.glob('*.json'))
                    backups.append({
                        'backup_date': item.name,
                        'path': str(item),
                        'files': len(files),
                        'has_metadata': False
                    })
        
        return backups


def create_backup(backup_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Función de conveniencia para crear un backup.
    
    Args:
        backup_dir: Directorio de backups (opcional)
    
    Returns:
        Resultado del backup
    """
    runner = BackupRunner(backup_dir)
    return runner.run_backup()
