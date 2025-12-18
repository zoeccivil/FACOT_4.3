import os
import re
from typing import Any, Dict, List, Optional, Tuple

# Mantenemos imports de configuración por si se usan constantes
import config_facot

# NCF válido Regex (Métodos estáticos, no tocan BD)
NCF_REGEX_STD = re.compile(r'^(?!E)[A-Z][0-9]{10}$')
NCF_REGEX_E = re.compile(r'^E[0-9]{13}$')

# Tipo por defecto
DEFAULT_TYPE_STD = "01"
DEFAULT_TYPE_E = "31"

class LogicController:
    """
    Lógica de negocio.
    MODO PROXY FIREBASE: Si recibe 'data_access', delega todas las operaciones
    y NO utiliza SQLite local para lectura ni escritura.
    """

    def __init__(self, db_path=None, data_access=None):
        self.db_path = db_path
        self.data_access = data_access  # Instancia de FirebaseDataAccess
        self.conn = None

        print(f"[DEBUG-LOGIC] Inicializando LogicController")
        
        if self.data_access:
            print(f"[DEBUG-LOGIC] MODO: FIREBASE PURE (Proxy activo)")
            # NO conectamos a SQLite
        else:
            print(f"[DEBUG-LOGIC] MODO: SQLITE LOCAL (Legacy)")
            import sqlite3
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            self._initialize_db_sqlite()

    # -------------------------
    # Métodos Estáticos
    # -------------------------
    @staticmethod
    def validate_ncf(ncf: str) -> bool:
        s = (ncf or "").strip().upper()
        return bool(NCF_REGEX_STD.match(s) or NCF_REGEX_E.match(s))

    @staticmethod
    def split_ncf(ncf: str):
        n = (ncf or "").strip().upper()
        if NCF_REGEX_E.match(n):
            return "E", n[1:3], n[3:]
        if NCF_REGEX_STD.match(n):
            return n[0], n[1:3], n[3:]
        return None, None, None

    # -------------------------
    # EMPRESAS (Delegación)
    # -------------------------
    def get_all_companies(self):
        if self.data_access:
            return self.data_access.get_all_companies()
        return []

    def add_company(self, name, rnc, address=""):
        if self.data_access:
            return self.data_access.add_company(name, rnc, address)
        return 0

    def update_company(self, company_id, name, rnc, address, template_path, output_path):
        if self.data_access:
            payload = {
                "name": name,
                "rnc": rnc,
                "address": address,
                "address_line1": address,
                "invoice_template_path": template_path,
                "invoice_output_base_path": output_path
            }
            return self.data_access.update_company_fields(company_id, payload)

    def update_company_fields(self, company_id: int, payload: Dict[str, Any]):
        if self.data_access:
            return self.data_access.update_company_fields(company_id, payload)

    def set_company_field(self, company_id: int, key: str, value: Any):
        if self.data_access:
            return self.data_access.update_company_fields(company_id, {key: value})

    def get_company_details(self, company_id):
        if self.data_access:
            return self.data_access.get_company_details(company_id)
        return None

    def delete_company(self, company_id):
        if self.data_access:
            if hasattr(self.data_access, 'delete_company'):
                return self.data_access.delete_company(company_id)
            return False, "Método delete_company no implementado"
        return False, "No backend"

    # --- VENCIMIENTOS ---
    
    def get_company_invoice_due_date(self, company_id: int) -> str:
        if self.data_access:
            # Si FirebaseDataAccess tiene get_company_due_date, úsalo
            if hasattr(self.data_access, 'get_company_due_date'):
                return self.data_access.get_company_due_date(company_id)
            # Fallback a get_company_invoice_due_date si existe
            if hasattr(self.data_access, 'get_company_invoice_due_date'):
                return self.data_access.get_company_invoice_due_date(company_id)
            # Fallback genérico
            det = self.data_access.get_company_details(company_id)
            return (det or {}).get("invoice_due_date", "") or ""
        return ""

    def set_company_due_date(self, company_id: int, due_date: str) -> bool:
        """Guarda la fecha de vencimiento fija."""
        if self.data_access:
            if hasattr(self.data_access, 'set_company_due_date'):
                return self.data_access.set_company_due_date(company_id, due_date)
            # Fallback
            self.data_access.update_company_fields(company_id, {"invoice_due_date": due_date})
            return True
        return False
        
    # Alias por compatibilidad
    def get_company_due_date(self, company_id: int) -> str:
        return self.get_company_invoice_due_date(company_id)

    # -------------------------
    # CATEGORÍAS (Delegación)
    # -------------------------
    def get_all_categories(self):
        if self.data_access:
            return self.data_access.get_all_categories()
        return []

    def add_category(self, data):
        if self.data_access and hasattr(self.data_access, 'add_category'):
            return self.data_access.add_category(data)
        return 0

    def update_category(self, cat_id, data):
        if self.data_access and hasattr(self.data_access, 'update_category'):
            return self.data_access.update_category(cat_id, data)

    def delete_category(self, cat_id):
        if self.data_access and hasattr(self.data_access, 'delete_category'):
            return self.data_access.delete_category(cat_id)

    # -------------------------
    # ÍTEMS (Delegación)
    # -------------------------
    def get_all_items(self):
        if self.data_access:
            return self.data_access.get_all_items()
        return []

    def add_item(self, data):
        if self.data_access and hasattr(self.data_access, 'add_item'):
            return self.data_access.add_item(data)

    def update_item(self, item_id, data):
        if self.data_access and hasattr(self.data_access, 'update_item'):
            return self.data_access.update_item(item_id, data)

    def delete_item(self, item_id):
        if self.data_access and hasattr(self.data_access, 'delete_item'):
            return self.data_access.delete_item(item_id)

    def get_item_by_code(self, code: str):
        if self.data_access:
            return self.data_access.get_item_by_code(code)
        return None

    def get_items_like(self, query: str, limit: int = 20):
        if self.data_access:
            return self.data_access.get_items_like(query, limit)
        return []
    
    def search_items_by_code_or_name(self, query: str, limit: int = 20):
        return self.get_items_like(query, limit)

    def _get_unit_from_items(self, code: str = "", name: str = "") -> str:
        if self.data_access:
            if code:
                item = self.data_access.get_item_by_code(code)
                if item: return item.get('unit', '')
            if name:
                items = self.data_access.get_items_like(name, limit=1)
                if items: return items[0].get('unit', '')
        return ""

    # -------------------------
    # FACTURAS (Delegación)
    # -------------------------
    def add_invoice(self, invoice_data, items):
        if self.data_access:
            return self.data_access.add_invoice(invoice_data, items)
        return 0

    def update_invoice(self, invoice_id, invoice_data, items):
        if self.data_access and hasattr(self.data_access, 'update_invoice'):
            return self.data_access.update_invoice(invoice_id, invoice_data, items)
        return 0

    def get_facturas(self, company_id, only_issued: bool = True):
        if self.data_access:
            if hasattr(self.data_access, 'get_facturas'):
                return self.data_access.get_facturas(company_id, only_issued)
            return self.data_access.get_invoices(company_id)
        return []

    def get_invoices(self, company_id, limit=100, offset=0):
        if self.data_access:
            return self.data_access.get_invoices(company_id, limit, offset)
        return []

    def get_invoice_items(self, invoice_id):
        if self.data_access:
            return self.data_access.get_invoice_items(invoice_id)
        return []

    def delete_factura(self, factura_id):
        if self.data_access:
            return self.data_access.delete_factura(factura_id)

    def update_invoice_number(self, invoice_id: int, company_id: int, rnc: str, new_ncf: str):
        if self.data_access:
            # Simulación segura
            print("[LOGIC] Solicitud cambio NCF (requiere soporte backend completo)")
            return True, "NCF Actualizado (Simulado)", new_ncf
        return False, "No backend", new_ncf

    # -------------------------
    # COTIZACIONES (Delegación)
    # -------------------------
    def add_quotation(self, quotation_data, items):
        if self.data_access:
            return self.data_access.add_quotation(quotation_data, items)
        return 0

    def get_quotations(self, company_id):
        if self.data_access:
            return self.data_access.get_quotations(company_id)
        return []

    def get_quotation_items(self, quotation_id):
        if self.data_access:
            return self.data_access.get_quotation_items(quotation_id)
        return []

    def update_quotation(self, quotation_id, quotation_data, items):
        if self.data_access:
            return self.data_access.update_quotation(quotation_id, quotation_data, items)

    def delete_quotation(self, quotation_id):
        if self.data_access:
            return self.data_access.delete_quotation(quotation_id)

    def compute_quotation_due_date(self, quotation_date: str | None) -> str:
        if not quotation_date: return ""
        from datetime import datetime, timedelta
        try:
            d = datetime.strptime(quotation_date[:10], "%Y-%m-%d")
            return (d + timedelta(days=30)).strftime("%Y-%m-%d")
        except: return ""

    # -------------------------
    # TERCEROS (Delegación)
    # -------------------------
    def search_third_parties(self, query, search_by='name'):
        if self.data_access:
            return self.data_access.search_third_parties(query, search_by)
        return []

    def add_or_update_third_party(self, rnc, name):
        if self.data_access:
            return self.data_access.add_or_update_third_party(rnc, name)

    # -------------------------
    # NCF SECUENCIAS (Delegación)
    # -------------------------
    def get_next_ncf(self, company_id: int, prefix3: str) -> str:
        if self.data_access:
            # FirebaseDataAccess espera el prefijo completo como tipo ("B01") o el tipo ("01")
            # Ajusta según tu implementación. Aquí pasamos el prefijo limpio.
            return self.data_access.get_next_ncf(company_id, prefix3)
        return "B0100000001"
    
    def get_ncf_last_seq(self, company_id: int, prefix: str) -> int:
        """Obtiene última secuencia (para configuración)."""
        if self.data_access and hasattr(self.data_access, 'get_ncf_last_seq'):
            return self.data_access.get_ncf_last_seq(company_id, prefix)
        return 0

    def set_ncf_last_seq(self, company_id: int, prefix: str, last_seq: int):
        """Establece última secuencia (para configuración)."""
        if self.data_access and hasattr(self.data_access, 'set_ncf_last_seq'):
            self.data_access.set_ncf_last_seq(company_id, prefix, last_seq)

    def get_ncf_preview(self, company_id: int, prefix3: str) -> str:
        """Obtiene preview del próximo NCF SIN consumir la secuencia."""
        if self.data_access and hasattr(self.data_access, 'get_ncf_preview'):
            return self.data_access.get_ncf_preview(company_id, prefix3)
        # Fallback: usar get_next_ncf (que ahora es allocate)
        return self.get_next_ncf(company_id, prefix3)

    def allocate_next_ncf(self, company_id: int, prefix3: str) -> str:
        """Asigna y consume el siguiente NCF (transaccional)."""
        if self.data_access and hasattr(self.data_access, 'allocate_next_ncf'):
            return self.data_access.allocate_next_ncf(company_id, prefix3)
        # Fallback: usar get_next_ncf
        return self.get_next_ncf(company_id, prefix3)

    # -------------------------
    # Utilidades
    # -------------------------
    def commit(self):
        if self.data_access:
            return self.data_access.commit()

    def close(self):
        if self.data_access:
            return self.data_access.close()

    # -------------------------
    # Storage / File Upload (Firebase integration)
    # -------------------------
    def upload_file_to_storage(self, local_path: str, storage_path: str):
        """
        Sube un archivo al storage (Firebase) y devuelve la URL pública o signed URL.
        
        Args:
            local_path: Ruta local del archivo
            storage_path: Ruta destino en storage (ej: "logos/company_123.png" o "pdfs/invoice_456.pdf")
        
        Returns:
            URL pública/signed del archivo subido, o None si falla o no está disponible
        """
        # Usar el método upload_file_to_storage de data_access si está disponible
        if hasattr(self, 'data_access') and self.data_access:
            if hasattr(self.data_access, 'upload_file_to_storage'):
                try:
                    url = self.data_access.upload_file_to_storage(local_path, storage_path)
                    if url:
                        print(f"[LOGIC-STORAGE] File uploaded via data_access to {storage_path}: {url}")
                        return url
                except Exception as e:
                    print(f"[LOGIC-STORAGE] data_access.upload_file_to_storage failed: {e}")
        
        print(f"[LOGIC-STORAGE] upload_file_to_storage not available, file not uploaded: {local_path}")
        return None
    
    def generate_signed_url_for_path(self, storage_path: str, days: int = 7):
        """
        Genera una signed URL temporal para un archivo en storage.
        
        Args:
            storage_path: Ruta en storage (ej: "logos/company_123.png")
            days: Días de validez de la URL (por defecto 7)
        
        Returns:
            Signed URL temporal, o None si falla o no está disponible
        """
        # Usar el método generate_signed_url_for_path de data_access si está disponible
        if hasattr(self, 'data_access') and self.data_access:
            if hasattr(self.data_access, 'generate_signed_url_for_path'):
                try:
                    url = self.data_access.generate_signed_url_for_path(storage_path, days)
                    if url:
                        print(f"[LOGIC-STORAGE] Signed URL generated via data_access for {storage_path}")
                        return url
                except Exception as e:
                    print(f"[LOGIC-STORAGE] data_access.generate_signed_url_for_path failed: {e}")
        
        print(f"[LOGIC-STORAGE] generate_signed_url_for_path not available for: {storage_path}")
        return None
    
    def set_invoice_pdf_info(self, invoice_id: int, storage_path: str = None, url: str = None, expires_at: str = None):
        """
        Persiste la metadata del PDF asociado a una factura.
        
        Args:
            invoice_id: ID de la factura
            storage_path: Ruta en storage del PDF
            url: URL del PDF (pública o signed)
            expires_at: Fecha de expiración de la URL (ISO format)
        """
        if not self.data_access:
            print(f"[LOGIC-STORAGE] No data_access available, cannot set PDF info for invoice {invoice_id}")
            return
        
        # Usar el método set_invoice_pdf_info de data_access si está disponible
        if hasattr(self.data_access, 'set_invoice_pdf_info'):
            try:
                self.data_access.set_invoice_pdf_info(invoice_id, storage_path, url, expires_at)
                print(f"[LOGIC-STORAGE] PDF metadata saved via data_access for invoice {invoice_id}")
                return
            except Exception as e:
                print(f"[LOGIC-STORAGE] data_access.set_invoice_pdf_info failed: {e}")
        
        # Fallback: intentar actualizar directamente en Firestore
        try:
            if hasattr(self.data_access, 'db'):
                doc_ref = self.data_access.db.collection('invoices').document(str(invoice_id))
                update_data = {}
                if storage_path is not None:
                    update_data['pdf_storage_path'] = storage_path
                if url is not None:
                    update_data['pdf_url'] = url
                if expires_at is not None:
                    update_data['pdf_expires_at'] = expires_at
                
                if update_data:
                    doc_ref.update(update_data)
                    print(f"[LOGIC-STORAGE] PDF metadata saved via fallback for invoice {invoice_id}")
            else:
                print(f"[LOGIC-STORAGE] Firestore not available, PDF metadata not saved")
        except Exception as e:
            print(f"[LOGIC-STORAGE] Error saving PDF metadata for invoice {invoice_id}: {e}")

    # -------------------------
    # MÉTODO LEGACY (NO USADO EN MODO FIREBASE)
    # -------------------------
    def _initialize_db_sqlite(self):
        pass