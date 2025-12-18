"""
Servicio de NCF con transacciones Firestore.

Proporciona generación de NCF únicos y consistentes usando
transacciones Firestore con reintentos automáticos.

Estructura de colección ncf_sequence_configs:
- category: "FACTURA PRIVADA", "CONSUMIDOR FINAL", etc.
- company_id: int
- created_at, created_by
- effective_from
- last_assigned: "B0100000163" (último NCF emitido)
- next_sequence: 164 (siguiente correlativo numérico)
- notes
- prefix: "B01", "B02", etc.
- updated_at, updated_by
"""

from __future__ import annotations
import os
import re
import time
from datetime import datetime
from typing import Optional, Tuple, Dict, Any

# Configuración por defecto
DEFAULT_NCF_PADDING = 8  # Dígitos después del prefijo (ej: B01 + 8 dígitos = 11 chars)
DEFAULT_ECF_PADDING = 11  # Para E-CF (ej: E31 + 11 dígitos = 14 chars)
DEFAULT_MAX_RETRIES = 5

# Mapeo de categorías a prefijos
CATEGORY_TO_PREFIX = {
    "FACTURA PRIVADA": "B01",
    "Crédito Fiscal": "B01",
    "Crédito Fiscal (B01)": "B01",
    "CONSUMIDOR FINAL": "B02",
    "Consumidor Final": "B02",
    "Consumidor Final (B02)": "B02",
    "FACTURA EXENTA": "B14",
    "Regímenes Especiales": "B14",
    "Régimen Especial": "B14",
    "Régimen Especial (B14)": "B14",
    "FACTURA GUBERNAMENTAL": "B15",
    "Gubernamental": "B15",
    "Gubernamental (B15)": "B15",
    "FACTURA EXPORTACIÓN": "B16",
    "Exportaciones": "B16",
    "NOTA DE CRÉDITO": "B04",
    "Nota de Crédito": "B04",
    "Nota de Crédito (B04)": "B04",
    # E-CF
    "E-CF Consumidor Final": "E31",
    "E-CF Crédito Fiscal": "E32",
    "E-CF Nota de Débito": "E33",
    "E-CF Nota de Crédito": "E34",
}

# Regex para validación NCF
NCF_REGEX_STD = re.compile(r'^(?!E)[A-Z][0-9]{10}$')  # Letra≠E + 10 dígitos
NCF_REGEX_ECF = re.compile(r'^E[0-9]{13}$')  # E + 13 dígitos


class NCFFirestoreService:
    """
    Servicio de NCF usando Firestore con transacciones.
    
    Garantiza:
    - NCFs únicos por company_id + prefix/category
    - Consistencia bajo concurrencia
    - Reintentos automáticos ante contención
    """
    
    def __init__(self, db=None, max_retries: int = None):
        """
        Inicializa el servicio de NCF.
        
        Args:
            db: Cliente de Firestore (si None, se obtiene de FirebaseClient)
            max_retries: Máximo de reintentos para transacciones
        """
        self.db = db
        self.max_retries = max_retries or int(os.getenv("MAX_NCF_TX_RETRIES", DEFAULT_MAX_RETRIES))
        self.ncf_padding = int(os.getenv("NCF_PADDING", DEFAULT_NCF_PADDING))
        
        if self.db is None:
            try:
                from firebase.firebase_client import get_firebase_client
                client = get_firebase_client()
                self.db = client.get_firestore()
            except Exception as e:
                print(f"[NCF_FIRESTORE] Error obteniendo Firestore: {e}")
    
    def _get_padding(self, prefix: str) -> int:
        """Obtiene el padding correcto según el prefijo."""
        if prefix and prefix[0].upper() == 'E':
            return DEFAULT_ECF_PADDING
        return self.ncf_padding
    
    def _derive_prefix(self, category: str, prefix: Optional[str] = None) -> str:
        """
        Deriva el prefijo desde la categoría si no se proporciona.
        
        Args:
            category: Categoría del comprobante
            prefix: Prefijo explícito (si se proporciona, tiene prioridad)
        
        Returns:
            Prefijo de 3 caracteres (ej: "B01")
        """
        if prefix and len(prefix) >= 3:
            return prefix[:3].upper()
        
        # Buscar en mapeo
        if category in CATEGORY_TO_PREFIX:
            return CATEGORY_TO_PREFIX[category]
        
        # Buscar coincidencia parcial
        category_upper = category.upper()
        for key, value in CATEGORY_TO_PREFIX.items():
            if key.upper() in category_upper or category_upper in key.upper():
                return value
        
        # Default
        return "B01"
    
    def _parse_ncf(self, ncf: str) -> Tuple[str, int]:
        """
        Parsea un NCF extrayendo prefijo y número.
        
        Args:
            ncf: NCF completo (ej: "B0100000163")
        
        Returns:
            Tuple (prefix, sequence_number)
        """
        if not ncf or len(ncf) < 4:
            return ("B01", 0)
        
        prefix = ncf[:3].upper()
        try:
            seq = int(ncf[3:])
            return (prefix, seq)
        except ValueError:
            return (prefix, 0)
    
    def _format_ncf(self, prefix: str, sequence: int) -> str:
        """
        Formatea un NCF con el padding correcto.
        
        Args:
            prefix: Prefijo de 3 caracteres
            sequence: Número de secuencia
        
        Returns:
            NCF formateado (ej: "B0100000163")
        """
        padding = self._get_padding(prefix)
        return f"{prefix.upper()}{sequence:0{padding}d}"
    
    def _validate_ncf(self, ncf: str) -> bool:
        """Valida el formato de un NCF."""
        if not ncf:
            return False
        ncf = ncf.strip().upper()
        return bool(NCF_REGEX_STD.match(ncf) or NCF_REGEX_ECF.match(ncf))
    
    def _get_sequence_doc_ref(self, company_id: int, prefix: str):
        """
        Obtiene la referencia al documento de secuencia.
        
        El documento se identifica por company_id + prefix.
        """
        doc_id = f"{company_id}_{prefix}"
        return self.db.collection('ncf_sequence_configs').document(doc_id)
    
    def _find_last_invoice_ncf(self, company_id: int, prefix: str) -> Optional[str]:
        """
        Busca el último NCF usado en facturas para este prefix.
        
        Args:
            company_id: ID de la empresa
            prefix: Prefijo del NCF
        
        Returns:
            Último NCF encontrado o None
        """
        try:
            invoices_ref = self.db.collection('invoices')
            
            # Query por company_id y NCF que empiece con el prefix
            query = invoices_ref.where(
                'company_id', '==', company_id
            ).where(
                'invoice_number', '>=', prefix
            ).where(
                'invoice_number', '<', prefix + '\uf8ff'
            ).order_by(
                'invoice_number', direction='DESCENDING'
            ).limit(1)
            
            docs = list(query.stream())
            if docs:
                invoice_data = docs[0].to_dict()
                return invoice_data.get('invoice_number')
            
            return None
        except Exception as e:
            print(f"[NCF_FIRESTORE] Error buscando última factura: {e}")
            return None
    
    def _correct_sequence_if_needed(
        self, 
        company_id: int, 
        prefix: str,
        doc_data: Dict[str, Any]
    ) -> int:
        """
        Invoca el corrector de secuencias si hay inconsistencias.
        
        Valida que last_assigned + 1 == next_sequence.
        Si no, busca el máximo real en facturas y corrige.
        
        Args:
            company_id: ID de la empresa
            prefix: Prefijo del NCF
            doc_data: Datos del documento de secuencia
        
        Returns:
            Secuencia corregida a usar
        """
        last_assigned = doc_data.get('last_assigned', '')
        next_sequence = doc_data.get('next_sequence', 1)
        
        if not last_assigned:
            return next_sequence
        
        # Parsear last_assigned
        _, last_num = self._parse_ncf(last_assigned)
        expected_next = last_num + 1
        
        if next_sequence == expected_next:
            # Todo bien
            return next_sequence
        
        print(f"[NCF_FIRESTORE] Inconsistencia detectada para {prefix}: "
              f"last_assigned={last_num}, next_sequence={next_sequence}, expected={expected_next}")
        
        # Buscar máximo real en facturas
        real_last = self._find_last_invoice_ncf(company_id, prefix)
        if real_last:
            _, real_num = self._parse_ncf(real_last)
            corrected = max(real_num + 1, next_sequence, expected_next)
        else:
            corrected = max(next_sequence, expected_next)
        
        print(f"[NCF_FIRESTORE] Secuencia corregida a: {corrected}")
        return corrected
    
    def get_next_ncf(
        self, 
        company_id: int, 
        category: str, 
        prefix: Optional[str] = None
    ) -> str:
        """
        Obtiene el siguiente NCF disponible de forma transaccional.
        
        Esta función ejecuta una transacción Firestore para garantizar
        que el NCF sea único incluso bajo concurrencia.
        
        Args:
            company_id: ID de la empresa
            category: Categoría del comprobante (ej: "FACTURA PRIVADA")
            prefix: Prefijo explícito (opcional, se deriva de category si no se proporciona)
        
        Returns:
            NCF formateado (ej: "B0100000164")
        
        Raises:
            Exception: Si no se puede obtener un NCF después de los reintentos
        """
        if not self.db:
            raise RuntimeError("Firestore no está disponible")
        
        # Derivar prefix
        final_prefix = self._derive_prefix(category, prefix)
        
        # Importar firestore transaction
        from google.cloud import firestore as gc_firestore
        
        doc_ref = self._get_sequence_doc_ref(company_id, final_prefix)
        
        @gc_firestore.transactional
        def update_sequence(transaction):
            """Función transaccional que actualiza la secuencia."""
            snapshot = doc_ref.get(transaction=transaction)
            
            now = datetime.utcnow().isoformat()
            user = os.getenv('USER', 'system')
            
            if snapshot.exists:
                doc_data = snapshot.to_dict()
                
                # Verificar y corregir inconsistencias
                next_seq = self._correct_sequence_if_needed(
                    company_id, final_prefix, doc_data
                )
                
                # Formar NCF
                new_ncf = self._format_ncf(final_prefix, next_seq)
                
                # Actualizar documento
                transaction.update(doc_ref, {
                    'last_assigned': new_ncf,
                    'next_sequence': next_seq + 1,
                    'updated_at': now,
                    'updated_by': user
                })
                
                return new_ncf
            else:
                # Documento no existe, buscar en facturas existentes
                last_invoice_ncf = self._find_last_invoice_ncf(company_id, final_prefix)
                
                if last_invoice_ncf:
                    _, last_num = self._parse_ncf(last_invoice_ncf)
                    next_seq = last_num + 1
                    last_assigned = last_invoice_ncf
                else:
                    next_seq = 1
                    last_assigned = None
                
                # Formar NCF
                new_ncf = self._format_ncf(final_prefix, next_seq)
                
                # Crear documento inicial
                new_doc = {
                    'company_id': company_id,
                    'category': category,
                    'prefix': final_prefix,
                    'last_assigned': new_ncf,
                    'next_sequence': next_seq + 1,
                    'effective_from': now[:10],  # Solo fecha
                    'notes': '',
                    'created_at': now,
                    'created_by': user,
                    'updated_at': now,
                    'updated_by': user
                }
                
                transaction.set(doc_ref, new_doc)
                
                return new_ncf
        
        # Ejecutar transacción con reintentos
        last_error = None
        for attempt in range(self.max_retries):
            try:
                transaction = self.db.transaction()
                ncf = update_sequence(transaction)
                
                print(f"[NCF_FIRESTORE] NCF asignado: {ncf} (intento {attempt + 1})")
                return ncf
                
            except Exception as e:
                last_error = e
                print(f"[NCF_FIRESTORE] Intento {attempt + 1}/{self.max_retries} fallido: {e}")
                
                # Esperar antes de reintentar (backoff exponencial)
                if attempt < self.max_retries - 1:
                    wait_time = (2 ** attempt) * 0.1  # 0.1, 0.2, 0.4, 0.8, 1.6 segundos
                    time.sleep(wait_time)
        
        raise RuntimeError(
            f"No se pudo obtener NCF después de {self.max_retries} intentos. "
            f"Último error: {last_error}"
        )
    
    def get_sequence_info(self, company_id: int, prefix: str) -> Dict[str, Any]:
        """
        Obtiene información de la secuencia actual.
        
        Args:
            company_id: ID de la empresa
            prefix: Prefijo del NCF
        
        Returns:
            Dict con información de la secuencia
        """
        if not self.db:
            return {'error': 'Firestore no disponible'}
        
        try:
            doc_ref = self._get_sequence_doc_ref(company_id, prefix)
            snapshot = doc_ref.get()
            
            if snapshot.exists:
                data = snapshot.to_dict()
                return {
                    'exists': True,
                    'prefix': prefix,
                    'category': data.get('category', ''),
                    'last_assigned': data.get('last_assigned', ''),
                    'next_sequence': data.get('next_sequence', 1),
                    'next_ncf': self._format_ncf(prefix, data.get('next_sequence', 1)),
                    'effective_from': data.get('effective_from', ''),
                    'updated_at': data.get('updated_at', '')
                }
            else:
                # Buscar último en facturas
                last_ncf = self._find_last_invoice_ncf(company_id, prefix)
                if last_ncf:
                    _, last_num = self._parse_ncf(last_ncf)
                    next_seq = last_num + 1
                else:
                    next_seq = 1
                
                return {
                    'exists': False,
                    'prefix': prefix,
                    'category': '',
                    'last_assigned': last_ncf or '',
                    'next_sequence': next_seq,
                    'next_ncf': self._format_ncf(prefix, next_seq),
                    'effective_from': '',
                    'updated_at': ''
                }
                
        except Exception as e:
            return {'error': str(e)}
    
    def set_sequence(
        self, 
        company_id: int, 
        prefix: str, 
        last_sequence: int,
        category: Optional[str] = None
    ) -> bool:
        """
        Establece manualmente la secuencia (para correcciones).
        
        Args:
            company_id: ID de la empresa
            prefix: Prefijo del NCF
            last_sequence: Último número de secuencia usado
            category: Categoría (opcional)
        
        Returns:
            True si se actualizó correctamente
        """
        if not self.db:
            return False
        
        try:
            doc_ref = self._get_sequence_doc_ref(company_id, prefix)
            now = datetime.utcnow().isoformat()
            user = os.getenv('USER', 'system')
            
            last_ncf = self._format_ncf(prefix, last_sequence)
            
            doc_ref.set({
                'company_id': company_id,
                'category': category or '',
                'prefix': prefix,
                'last_assigned': last_ncf,
                'next_sequence': last_sequence + 1,
                'effective_from': now[:10],
                'notes': f'Secuencia establecida manualmente en {now}',
                'updated_at': now,
                'updated_by': user
            }, merge=True)
            
            print(f"[NCF_FIRESTORE] Secuencia establecida: {prefix} -> {last_sequence}")
            return True
            
        except Exception as e:
            print(f"[NCF_FIRESTORE] Error estableciendo secuencia: {e}")
            return False


# Instancia global
_ncf_firestore_service = None


def get_ncf_firestore_service() -> NCFFirestoreService:
    """Obtiene la instancia global del servicio NCF."""
    global _ncf_firestore_service
    if _ncf_firestore_service is None:
        _ncf_firestore_service = NCFFirestoreService()
    return _ncf_firestore_service


def get_next_ncf(company_id: int, category: str, prefix: Optional[str] = None) -> str:
    """
    Función de conveniencia para obtener el siguiente NCF.
    
    Args:
        company_id: ID de la empresa
        category: Categoría del comprobante
        prefix: Prefijo explícito (opcional)
    
    Returns:
        NCF formateado
    """
    service = get_ncf_firestore_service()
    return service.get_next_ncf(company_id, category, prefix)
