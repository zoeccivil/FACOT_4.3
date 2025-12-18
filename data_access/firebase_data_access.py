"""
Implementación de DataAccess para Firebase (Firestore).
Proporciona acceso a datos usando Firestore como backend.
"""

from __future__ import annotations
import os
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import time
from datetime import datetime, timedelta
import facot_config  # se usará PDF_SIGNED_URL_DAYS si está definido
import mimetypes
import requests
from google.cloud import storage as gcs_storage
from google.oauth2 import service_account
from google.cloud import storage as gcs_storage
from google.oauth2 import service_account
import mimetypes, os
from typing import Optional
from firebase_admin import firestore  # <‑‑ añade este import arriba

# Asegúrate de que estos imports funcionen en tu proyecto
try:
    from .base import DataAccess
except ImportError:
    # Si base.py no existe o falla, definimos una clase base dummy
    class DataAccess: pass

from firebase import get_firebase_client
from utils.logger import get_audit_logger


# Añade estos imports al inicio del archivo si no existen
import os
import mimetypes
from typing import Optional
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleAuthRequest

NCF_CATEGORY_MAP = {
    'B01': 'Factura Privada',
    'B02': 'Consumidor Final',
    'B04': 'Nota de Crédito',
    'B14': 'Factura Gubernamental',
    'B15': 'Factura Exenta',
    'B16': 'Gubernamental Exenta',
    'E31': 'Factura Privada (e-CF)',
    'E32': 'Consumidor Final (e-CF)',
    'E33': 'Nota de Débito (e-CF)',
    'E34': 'Nota de Crédito (e-CF)',
}

def _derive_invoice_category(self, invoice_number: str) -> Optional[str]:
    if not invoice_number:
        return None
    prefix = (invoice_number or "").strip().upper()[:3]
    return NCF_CATEGORY_MAP.get(prefix)


class FirebaseDataAccess:
    # ===== Método __init__ corregido =====
    def __init__(self, user_id: Optional[str] = None):
        # Cliente Firebase (Firestore y opcionalmente Storage SDK)
        self.client = get_firebase_client()

        # Firestore
        self.db = getattr(self.client, "get_firestore", lambda: None)()
        if not self.db:
            raise RuntimeError("Firestore no está disponible. Verificar configuración de Firebase.")

        # Storage SDK (puede venir deshabilitado desde firebase_client.get_storage)
        self.storage = getattr(self.client, "get_storage", lambda: None)()

        # Usuario y auditoría
        self.user_id = user_id or "system"
        self.audit_logger = get_audit_logger()

        # Resolver bucket desde facot_config y normalizar a dominio moderno *.firebasestorage.app
        try:
            import facot_config
            cred_path, raw_bucket = facot_config.get_firebase_config()
        except Exception:
            cred_path, raw_bucket = "", ""

        def _to_new_bucket(b: str) -> str:
            """
            Normaliza bucket a dominio moderno *.firebasestorage.app:
            - 'facot-app' -> 'facot-app.firebasestorage.app'
            - '*.appspot.com' -> '*.firebasestorage.app'
            - '*.firebasestorage.app' -> tal cual
            """
            b = (b or "").strip()
            if not b:
                return "facot-app.firebasestorage.app"
            if b.endswith(".firebasestorage.app"):
                return b
            if b.endswith(".appspot.com"):
                proj = b.replace(".appspot.com", "")
                return f"{proj}.firebasestorage.app"
            return f"{b}.firebasestorage.app"

        self.storage_bucket = _to_new_bucket(raw_bucket)
        # Host web y bucket son el mismo dominio en proyectos nuevos
        self.storage_host = self.storage_bucket

        # Generar token OAuth2 de la cuenta de servicio para subir vía REST con Authorization: Bearer
        self.storage_auth_token = self._get_service_account_token(cred_path)

        print(f"[STORAGE] Config -> host={self.storage_host} bucket={self.storage_bucket} sdk={'YES' if self.storage else 'NO'}")
        print(f"[STORAGE] Auth token {'OK' if self.storage_auth_token else 'ABSENTE'}")




    # ===== Método helper nuevo para obtener token =====
    def _get_service_account_token(self, json_path: str) -> Optional[str]:
        """
        Obtiene un access token OAuth2 usando el archivo de credenciales del service account.
        Scopes: devstorage.full_control para permitir escribir en Firebase Storage (GCS).
        """
        try:
            if not json_path or not os.path.exists(json_path):
                return None
            scopes = ["https://www.googleapis.com/auth/devstorage.full_control"]
            creds = service_account.Credentials.from_service_account_file(json_path, scopes=scopes)
            creds.refresh(GoogleAuthRequest())
            return getattr(creds, "token", None)
        except Exception as e:
            print(f"[AUTH] No se pudo obtener token de servicio: {e}")
            return None

    # ===== Método upload_file_to_storage corregido (REST con Bearer) =====
    def upload_file_to_storage(self, local_path: str, storage_path: str) -> Optional[str]:
        """
        Sube un archivo a Storage del proyecto facot-app.

        Estrategia:
        1) Intentar Google Cloud Storage (GCS) con Service Account (recomendado, no depende de reglas de Firebase Storage).
        - Requiere roles: storage.objectAdmin (o storage.admin) sobre el proyecto.
        - Devuelve URL firmada (v4) de descarga por 7 días si es posible.
        2) Fallback REST (API v0) con Authorization: Bearer (Service Account).
        - Puede devolver 403 si las reglas Firebase requieren Firebase Auth en vez de SA OAuth2.
        - Devuelve alt=media con token si las reglas generan downloadTokens.

        Retorna:
            URL de descarga (firmada o alt=media con token) si la subida fue exitosa; None si falla.
        """
        # Determinar content-type
        try:
            import mimetypes
            ctype, _ = mimetypes.guess_type(local_path)
            if not ctype:
                _, ext = os.path.splitext(local_path)
                ctype = "application/pdf" if ext.lower() == ".pdf" else "application/octet-stream"
        except Exception:
            ctype = "application/octet-stream"

        # 1) Intentar subir con Google Cloud Storage SDK (no depende de reglas de Firebase Storage)
        try:
            from google.cloud import storage as gcs_storage
            from google.oauth2 import service_account

            # Obtener credenciales desde config
            try:
                import facot_config
                cred_path, _ = facot_config.get_firebase_config()
            except Exception:
                cred_path = ""

            if cred_path and os.path.exists(cred_path):
                creds = service_account.Credentials.from_service_account_file(cred_path)
                client = gcs_storage.Client(credentials=creds, project=creds.project_id)

                # Nota: tu bucket confirmado es '*.firebasestorage.app'
                bucket = client.bucket(self.storage_bucket)
                blob = bucket.blob(storage_path)

                blob.upload_from_filename(local_path, content_type=ctype)
                print(f"[GCS-UPLOAD] OK -> gs://{self.storage_bucket}/{storage_path}")

                # Intentar URL firmada v4 por 7 días
                try:
                    from datetime import timedelta
                    signed_url = blob.generate_signed_url(version="v4", expiration=timedelta(days=7), method="GET")
                    print(f"[GCS-UPLOAD] Signed URL (7d): {signed_url}")
                    return signed_url
                except Exception as e:
                    print(f"[GCS-UPLOAD] No se pudo generar URL firmada: {e}")
                    # Si no se puede firmar, continuamos con REST para intentar obtener alt=media con token
            else:
                print("[GCS-UPLOAD] Credenciales no encontradas para GCS upload. Intentando REST...")
        except Exception as e:
            print(f"[GCS-UPLOAD] Error subiendo archivo: {e}")
            # Continuar al fallback REST

        # 2) Fallback: API REST v0 con Bearer
        try:
            # Leer archivo binario
            with open(local_path, "rb") as f:
                data = f.read()

            import requests
            base_url = f"https://firebasestorage.googleapis.com/v0/b/{self.storage_bucket}/o"
            params = {
                "name": storage_path
            }
            headers = {"Content-Type": ctype}
            if getattr(self, "storage_auth_token", None):
                headers["Authorization"] = f"Bearer {self.storage_auth_token}"

            resp = requests.post(base_url, params=params, headers=headers, data=data, timeout=60)

            if resp.status_code in (200, 201):
                info = resp.json()
                token = (info.get("downloadTokens") or "").split(",")[0] if info.get("downloadTokens") else ""
                from urllib.parse import quote
                encoded = quote(storage_path, safe="")
                public_url = f"https://firebasestorage.googleapis.com/v0/b/{self.storage_bucket}/o/{encoded}?alt=media"
                if token:
                    public_url += f"&token={token}"
                print(f"[REST-UPLOAD] OK -> {public_url}")
                return public_url
            else:
                try:
                    print(f"[REST-UPLOAD] ERROR {resp.status_code}: {resp.text}")
                except Exception:
                    print(f"[REST-UPLOAD] ERROR {resp.status_code}")
                # Si obtienes 403, lo más probable es que las reglas de Firebase requieran Firebase Auth (usuario)
                # En ese caso, usa GCS (arriba) o ajusta reglas temporalmente para pruebas.
                return None

        except Exception as e:
            print(f"[REST-UPLOAD] Excepción subiendo archivo: {e}")
            return None

    def _add_metadata(self, data: Dict[str, Any], is_update: bool = False) -> Dict[str, Any]:
        """Agrega metadatos de auditoría a un documento."""
        now = datetime.utcnow().isoformat()
        if not is_update:
            data['created_at'] = now
            data['created_by'] = self.user_id
        data['updated_at'] = now
        data['updated_by'] = self.user_id
        return data

    # ==========================================
    #               EMPRESAS
    # ==========================================

    def get_all_companies(self) -> List[Dict[str, Any]]:
        try:
            companies_ref = self.db.collection('companies')
            docs = list(companies_ref.stream())
            companies = []
            for doc in docs:
                d = doc.to_dict() or {}
                # Asegurar ID (int si es dígito)
                cid = doc.id
                if isinstance(cid, str) and cid.isdigit():
                    cid = int(cid)
                d['id'] = cid
                # Si no hay invoice_due_date en el doc, intentar sequences/<id>_meta
                if not d.get('invoice_due_date'):
                    try:
                        meta_ref = self.db.collection('sequences').document(f"{cid}_meta")
                        meta_doc = meta_ref.get()
                        if meta_doc.exists:
                            meta = meta_doc.to_dict() or {}
                            inv_due = meta.get('invoice_due_date')
                            if inv_due:
                                d['invoice_due_date'] = inv_due
                    except Exception:
                        pass
                companies.append(d)
            return companies
        except Exception as e:
            print(f"[FIREBASE] ERROR obteniendo empresas: {e}")
            return []

    def get_company_details(self, company_id: int) -> Optional[Dict[str, Any]]:
        try:
            company_id_str = str(company_id)
            doc_ref = self.db.collection('companies').document(company_id_str)
            doc = doc_ref.get()
            if doc.exists:
                d = doc.to_dict() or {}
                d['id'] = company_id if isinstance(company_id, int) else company_id_str
                # Merge invoice_due_date desde sequences/<id>_meta si falta
                if not d.get('invoice_due_date'):
                    try:
                        meta_ref = self.db.collection('sequences').document(f"{company_id_str}_meta")
                        meta_doc = meta_ref.get()
                        if meta_doc.exists:
                            meta = meta_doc.to_dict() or {}
                            inv_due = meta.get('invoice_due_date')
                            if inv_due:
                                d['invoice_due_date'] = inv_due
                    except Exception:
                        pass
                return d
            return None
        except Exception as e:
            print(f"[FIREBASE] Error getting company {company_id}: {e}")
            return None

    def add_company(self, name: str, rnc: str, address: str = "") -> int:
        try:
            import time
            company_id = int(time.time() * 1000) % 1000000
            company_data = {
                'name': name, 'rnc': rnc, 'address': address,
                'address_line1': address, 'company_id': company_id
            }
            company_data = self._add_metadata(company_data)
            self.db.collection('companies').document(str(company_id)).set(company_data)
            return company_id
        except Exception as e:
            print(f"[FIREBASE] Error adding company: {e}")
            raise

    def update_company_fields(self, company_id: int, fields: Dict[str, Any]) -> None:
        """
        Actualiza campos en el doc companies/{id} y, si 'invoice_due_date' está presente,
        también lo guarda en sequences/{id}_meta (merge, no sobrescribe otros campos).
        """
        try:
            # split meta fields: currently only 'invoice_due_date'
            fields = dict(fields or {})
            meta_updates = {}
            if 'invoice_due_date' in fields:
                inv_due = (fields.get('invoice_due_date') or '').strip()
                meta_updates['invoice_due_date'] = inv_due
                # no guardamos en company doc si prefieres solo sequences, pero mantenemos ambos por compatibilidad
            # update company document
            company_updates = dict(fields)
            company_updates = self._add_metadata(company_updates, is_update=True)
            self.db.collection('companies').document(str(company_id)).set(company_updates, merge=True)

            # update sequences meta
            if meta_updates:
                meta_updates = self._add_metadata(meta_updates, is_update=True)
                self.db.collection('sequences').document(f"{company_id}_meta").set(meta_updates, merge=True)

        except Exception as e:
            print(f"[FIREBASE] Error updating company {company_id}: {e}")
            raise

    def delete_company(self, company_id: int) -> Tuple[bool, str]:
        try:
            # borrar doc de company
            self.db.collection('companies').document(str(company_id)).delete()
            # borrar meta opcional (no crítico si falla)
            try:
                self.db.collection('sequences').document(f"{company_id}_meta").delete()
            except Exception:
                pass
            return True, "Eliminada correctamente"
        except Exception as e:
            print(f"[FIREBASE] Error deleting company {company_id}: {e}")
            return False, str(e)

    # ==========================================
    #               CATEGORÍAS
    # ==========================================

    def get_all_categories(self) -> List[Dict[str, Any]]:
        try:
            cats_ref = self.db.collection('categories')
            docs = list(cats_ref.stream())
            categories = []
            for doc in docs:
                d = doc.to_dict() or {}
                d['id'] = doc.id
                categories.append(d)
            return categories
        except Exception as e:
            print(f"[FIREBASE] ERROR categorías: {e}")
            return []

    def add_category(self, data: Dict[str, Any]) -> str:
        try:
            import time
            cat_id = str(int(time.time() * 1000))
            data = self._add_metadata(data)
            self.db.collection('categories').document(cat_id).set(data)
            return cat_id
        except Exception as e:
            print(f"[FIREBASE] Error adding category: {e}")
            raise

    def update_category(self, cat_id: str, data: Dict[str, Any]):
        try:
            data = self._add_metadata(data, is_update=True)
            self.db.collection('categories').document(str(cat_id)).update(data)
        except Exception as e:
            print(f"[FIREBASE] Error updating category: {e}")
            raise

    def delete_category(self, cat_id: str):
        try:
            self.db.collection('categories').document(str(cat_id)).delete()
        except Exception as e:
            print(f"[FIREBASE] Error deleting category: {e}")
            raise

    # ==========================================
    #               ÍTEMS
    # ==========================================

    def get_all_items(self) -> List[Dict[str, Any]]:
        try:
            items_ref = self.db.collection('items')
            docs = list(items_ref.stream())
            items = []
            for doc in docs:
                item_data = doc.to_dict() or {}
                item_data['id'] = doc.id
                items.append(item_data)
            return items
        except Exception as e:
            print(f"[FIREBASE] ERROR ítems: {e}")
            return []

    def add_item(self, data: Dict[str, Any]) -> str:
        try:
            item_id = data.get('code')
            if not item_id:
                import time
                item_id = f"ITEM_{int(time.time()*1000)}"
            data = self._add_metadata(data)
            self.db.collection('items').document(item_id).set(data)
            return item_id
        except Exception as e:
            print(f"[FIREBASE] Error adding item: {e}")
            raise

    def update_item(self, item_id: str, data: Dict[str, Any]):
        try:
            data = self._add_metadata(data, is_update=True)
            self.db.collection('items').document(str(item_id)).update(data)
        except Exception as e:
            print(f"[FIREBASE] Error updating item: {e}")
            raise

    def delete_item(self, item_id: str):
        try:
            self.db.collection('items').document(str(item_id)).delete()
        except Exception as e:
            print(f"[FIREBASE] Error deleting item: {e}")
            raise

    def get_next_code(self, category_id: str) -> str:
        return "GEN0000"  # TODO: implementar con sequences si se usa en Firestore

    def get_item_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        try:
            items_ref = self.db.collection('items')
            doc = items_ref.document(code).get()
            if doc.exists:
                d = doc.to_dict() or {}
                d['id'] = doc.id
                return d

            query = items_ref.where('code', '==', code).limit(1)
            docs = list(query.stream())
            if docs:
                d = docs[0].to_dict() or {}
                d['id'] = docs[0].id
                return d
            return None
        except Exception as e:
            print(f"[FIREBASE] Error getting item by code {code}: {e}")
            return None

    def get_items_like(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        all_items = self.get_all_items()
        q = (query or "").lower()
        filtered = [
            i for i in all_items
            if q in str(i.get('code', '')).lower() or q in str(i.get('name', '')).lower()
        ]
        return filtered[:limit]

    # ==========================================
    #      RESTO (Facturas, Cotizaciones, Terceros)
    # ==========================================


    def get_third_party_by_rnc(self, rnc: str) -> Optional[Dict[str, Any]]:
        rnc = (rnc or "").strip()
        if not rnc:
            return None
        try:
            parties_ref = self.db.collection("third_parties")
            docs = list(parties_ref.where("rnc", "==", rnc).limit(1).stream())
            if not docs:
                return None
            party_data = docs[0].to_dict() or {}
            party_data["id"] = docs[0].id
            return party_data
        except Exception as e:
            print(f"[FIREBASE] Error getting third party by RNC {rnc}: {e}")
            return None


    def search_third_parties(self, query: str, search_by: str = "name") -> List[Dict[str, Any]]:
        """
        Búsqueda robusta sin depender de índices especiales:
        - search_by='rnc': primero exacto; si no, filtra en los más recientes (updated_at desc).
        - search_by='name': filtra subcadena (case-insensitive) en los más recientes (updated_at desc).
        Limita a 20 resultados.
        """
        query = (query or "").strip()
        if not query:
            return []

        parties_ref = self.db.collection("third_parties")
        results: List[Dict[str, Any]] = []
        q_lower = query.lower()

        try:
            if search_by == "rnc":
                # 1) Exacto
                exact = list(parties_ref.where("rnc", "==", query).limit(1).stream())
                if exact:
                    d = exact[0]
                    data = d.to_dict() or {}
                    data["id"] = d.id
                    return [data]

                # 2) Recientes: updated_at desc, hasta 500, filtro contiene (prefijo o subcadena)
                try:
                    docs = list(
                        parties_ref.order_by("updated_at", direction=firestore.Query.DESCENDING)
                        .limit(500)
                        .stream()
                    )
                except Exception:
                    docs = list(parties_ref.limit(500).stream())

                for d in docs:
                    data = d.to_dict() or {}
                    data["id"] = d.id
                    if q_lower in str(data.get("rnc", "")).lower():
                        results.append(data)
                    if len(results) >= 20:
                        break
                return results

            # ---- search_by == "name" ----
            try:
                docs = list(
                    parties_ref.order_by("updated_at", direction=firestore.Query.DESCENDING)
                    .limit(500)
                    .stream()
                )
            except Exception:
                docs = list(parties_ref.limit(500).stream())

            for d in docs:
                data = d.to_dict() or {}
                data["id"] = d.id
                if q_lower in str(data.get("name", "")).lower():
                    results.append(data)
                if len(results) >= 20:
                    break
            return results

        except Exception as e:
            print(f"[SEARCH-TP] Error: {e}")
            return results

    def add_or_update_third_party(self, rnc: str, name: str, updated_by: str = None):
        """
        Upsert con normalización. Actualiza nombre si cambia y es (opcional) más largo.
        """
        rnc = (rnc or "").strip()
        name = (name or "").strip()
        if not rnc or not name:
            return None

        rnc_norm = rnc.upper()
        name_norm = " ".join(name.upper().split())
        now = datetime.utcnow().isoformat()

        coll = self.db.collection("third_parties")
        existing = list(coll.where("rnc", "==", rnc).limit(1).stream())
        if existing:
            ref = existing[0].reference
            data_old = existing[0].to_dict() or {}
            old_name = (data_old.get("name") or "").strip()
            old_name_norm = (data_old.get("name_norm") or "").strip()
            payload = {
                "rnc": rnc,
                "rnc_norm": rnc_norm,
                "name": old_name,
                "name_norm": old_name_norm,
                "updated_at": now,
                "updated_by": updated_by,
            }
            if name != old_name and len(name) >= len(old_name):
                payload["name"] = name
                payload["name_norm"] = name_norm
            ref.set(payload, merge=True)
            return ref.id
        else:
            doc = coll.document()
            doc.set(
                {
                    "rnc": rnc,
                    "rnc_norm": rnc_norm,
                    "name": name,
                    "name_norm": name_norm,
                    "created_at": now,
                    "updated_at": now,
                    "updated_by": updated_by,
                }
            )
            return doc.id
    # ===== FACTURAS (INVOICES) =====

    def get_facturas(self, company_id: int, only_issued: bool = True) -> List[Dict[str, Any]]:
        return self.get_invoices(company_id, limit=5000)

    def add_invoice(self, invoice_data: Dict[str, Any], items: List[Dict[str, Any]]) -> int:
        """
        Crea factura y sus ítems. Alineado con FACTURAS-PyQT6-GIT.
        """
        try:
            import time
            invoice_id = str(int(time.time() * 1000))
            data = dict(invoice_data or {})

            # Normalizar company_id
            if 'company_id' in data and isinstance(data['company_id'], str) and data['company_id'].isdigit():
                data['company_id'] = int(data['company_id'])

            # Generar invoice_number si se solicita (requiere ncf_type)
            ncf_type = (data.get('ncf_type') or '').strip().upper()
            if not data.get('invoice_number') and ncf_type:
                data['invoice_number'] = self.get_next_ncf(int(data.get('company_id')), ncf_type)

            # ---- Campos de compatibilidad requeridos ----
            data['invoice_type'] = data.get('invoice_type') or 'emitida'
            data['imputation_date'] = data.get('imputation_date') or data.get('invoice_date') or datetime.utcnow().date().isoformat()
            inv_num = data.get('invoice_number') or ''
            data['invoice_category'] = data.get('invoice_category') or self._derive_invoice_category(inv_num) or ''
            data['third_party_name'] = data.get('third_party_name') or data.get('client_name') or ''
            # Mantener client_name como espejo para compatibilidad retro (opcional)
            if 'client_name' not in data and data.get('third_party_name'):
                data['client_name'] = data['third_party_name']

            # total_amount_rd: total × exchange_rate (si ambos existen y son numéricos)
            try:
                tot = float(data.get('total_amount') or 0)
                exr = float(data.get('exchange_rate') or 1)
                data['total_amount_rd'] = data.get('total_amount_rd')
                if data['total_amount_rd'] in (None, '', 0):
                    data['total_amount_rd'] = round(tot * exr, 2)
            except Exception:
                pass

            # attachment_path opcional
            if 'attachment_path' not in data:
                data['attachment_path'] = data.get('attachment_path', None)

            # Añadir pdf fields si vienen desde preview
            pdf_storage_path = data.pop('pdf_storage_path', None)
            pdf_url = data.pop('pdf_url', None)

            data = self._add_metadata(data)
            if pdf_storage_path:
                data['pdf_storage_path'] = pdf_storage_path
            if pdf_url:
                data['pdf_url'] = pdf_url

            doc_ref = self.db.collection('invoices').document(invoice_id)
            doc_ref.set(data)

            for i, item in enumerate(items or []):
                item_data = self._add_metadata(dict(item or {}))
                doc_ref.collection('items').document(str(i)).set(item_data)

            if pdf_storage_path or pdf_url:
                try:
                    self.set_file_index(pdf_storage_path or f"invoices/{invoice_id}", {
                        "type": "invoice",
                        "invoice_id": invoice_id,
                        "storage_path": pdf_storage_path,
                        "url": pdf_url,
                        "company_id": data.get("company_id")
                    })
                except Exception:
                    pass

            return int(invoice_id) if invoice_id.isdigit() else invoice_id
        except Exception as e:
            print(f"[FIREBASE] Error adding invoice: {e}")
            raise

    def get_invoices(self, company_id: Optional[int] = None, limit: int = 50000, offset: int = 0) -> List[Dict[str, Any]]:
        try:
            ref = self.db.collection('invoices')
            docs = []
            if company_id is None:
                # Sin filtro de empresa: trae hasta 'limit'
                docs = list(ref.limit(limit).stream())
            else:
                try:
                    from google.cloud.firestore_v1 import FieldFilter
                    q1 = ref.where(filter=FieldFilter('company_id', '==', company_id)).limit(limit)
                    docs = list(q1.stream())
                    if not docs:
                        q2 = ref.where(filter=FieldFilter('company_id', '==', str(company_id))).limit(limit)
                        docs = list(q2.stream())
                except Exception:
                    q1 = ref.where('company_id', '==', company_id).limit(limit)
                    docs = list(q1.stream())
                    if not docs:
                        q2 = ref.where('company_id', '==', str(company_id)).limit(limit)
                        docs = list(q2.stream())
            out = []
            for d in docs:
                dd = d.to_dict() or {}
                try:
                    dd['id'] = int(d.id)
                except Exception:
                    dd['id'] = d.id
                out.append(dd)
            return out
        except Exception as e:
            print(f"[FIREBASE] Error getting invoices: {e}")
            return []

    def get_companies_list(self) -> List[Dict[str, Any]]:
        # Alias cómodo para los diálogos
        return self.get_all_companies()

    def get_invoice_by_id(self, invoice_id: int) -> Optional[Dict[str, Any]]:
        try:
            invoice_ref = self.db.collection('invoices').document(str(invoice_id))
            doc = invoice_ref.get()
            if not doc.exists:
                return None
            invoice_data = doc.to_dict() or {}
            invoice_data['id'] = invoice_id if isinstance(invoice_id, int) else str(invoice_id)
            items_ref = invoice_ref.collection('items')
            items = []
            for item_doc in items_ref.stream():
                item_data = item_doc.to_dict() or {}
                items.append(item_data)
            invoice_data['items'] = items
            return invoice_data
        except Exception as e:
            print(f"[FIREBASE] Error getting invoice {invoice_id}: {e}")
            return None

    def get_invoice_items(self, invoice_id: Any) -> List[Dict[str, Any]]:
        try:
            ref = self.db.collection('invoices').document(str(invoice_id)).collection('items')
            docs = list(ref.stream())
            out = []
            for d in docs:
                dd = d.to_dict() or {}
                dd['id'] = d.id
                out.append(dd)
            return out
        except Exception as e:
            print(f"[FIREBASE] Error getting invoice items: {e}")
            return []

    def delete_factura(self, invoice_id: int) -> bool:
            """
            Elimina una factura y sus subcolecciones (items).
            Retorna True si tuvo éxito.
            """
            try:
                print(f"[FIREBASE] Intentando borrar factura ID: {invoice_id}")
                doc_ref = self.db.collection('invoices').document(str(invoice_id))
                
                # 1. Verificar existencia
                if not doc_ref.get().exists:
                    print(f"[FIREBASE] Factura {invoice_id} no existe, se asume borrada.")
                    return True

                # 2. Borrar subcolección 'items' (Firestore no borra subcolecciones automáticamente)
                items_ref = doc_ref.collection('items')
                batch_size = 50
                while True:
                    # Borrar en lotes
                    items = list(items_ref.limit(batch_size).stream())
                    if not items:
                        break
                    for item in items:
                        item.reference.delete()

                # 3. Borrar el documento principal
                doc_ref.delete()
                print(f"[FIREBASE] Factura {invoice_id} eliminada correctamente.")
                return True
                
            except Exception as e:
                print(f"[FIREBASE] Error deleting invoice {invoice_id}: {e}")
                # Importante: devolver False y loguear para ver el error real
                import traceback; traceback.print_exc() 
                return False

    # ===== COTIZACIONES (QUOTATIONS) =====

    def add_quotation(self, quotation_data: Dict[str, Any], items: List[Dict[str, Any]]) -> int:
        try:
            import time
            quotation_id = int(time.time() * 1000) % 1000000
            quotation_doc = dict(quotation_data or {})

            # Preserve pdf keys if present
            pdf_storage_path = quotation_doc.pop('pdf_storage_path', None)
            pdf_url = quotation_doc.pop('pdf_url', None)

            quotation_doc = self._add_metadata(quotation_doc)
            if pdf_storage_path:
                quotation_doc['pdf_storage_path'] = pdf_storage_path
            if pdf_url:
                quotation_doc['pdf_url'] = pdf_url

            quotation_ref = self.db.collection('quotations').document(str(quotation_id))
            quotation_ref.set(quotation_doc)
            items_ref = quotation_ref.collection('items')
            for idx, item in enumerate(items or []):
                item_doc = self._add_metadata(dict(item or {}))
                items_ref.document(str(idx)).set(item_doc)

            # Index file if needed
            if pdf_storage_path or pdf_url:
                try:
                    self.set_file_index(pdf_storage_path or f"quotations/{quotation_id}", {
                        "type": "quotation",
                        "quotation_id": quotation_id,
                        "storage_path": pdf_storage_path,
                        "url": pdf_url,
                        "company_id": quotation_doc.get("company_id")
                    })
                except Exception:
                    pass

            return quotation_id
        except Exception as e:
            print(f"[FIREBASE] Error adding quotation: {e}")
            raise

    def get_quotations(self, company_id: Optional[int] = None, limit: int = 5000, offset: int = 0) -> List[Dict[str, Any]]:
        try:
            quotations_ref = self.db.collection('quotations')
            if company_id:
                query = quotations_ref.where('company_id', '==', company_id)
            else:
                query = quotations_ref
            query = query.limit(limit).offset(offset)
            quotations = []
            for doc in query.stream():
                quotation_data = doc.to_dict() or {}
                quotation_data['id'] = int(doc.id) if doc.id.isdigit() else doc.id
                quotations.append(quotation_data)
            return quotations
        except Exception as e:
            print(f"[FIREBASE] Error getting quotations: {e}")
            return []

    def get_quotation_by_id(self, quotation_id: int) -> Optional[Dict[str, Any]]:
        try:
            quotation_ref = self.db.collection('quotations').document(str(quotation_id))
            doc = quotation_ref.get()
            if not doc.exists:
                return None
            quotation_data = doc.to_dict() or {}
            quotation_data['id'] = quotation_id
            items_ref = quotation_ref.collection('items')
            items = []
            for item_doc in items_ref.stream():
                item_data = item_doc.to_dict() or {}
                items.append(item_data)
            quotation_data['items'] = items
            return quotation_data
        except Exception as e:
            print(f"[FIREBASE] Error getting quotation {quotation_id}: {e}")
            return None

    def get_quotation_items(self, quotation_id: Any) -> List[Dict[str, Any]]:
        """Obtiene solo los ítems de una cotización específica."""
        try:
            ref = self.db.collection('quotations').document(str(quotation_id)).collection('items')
            docs = list(ref.stream())
            out = []
            for d in docs:
                dd = d.to_dict() or {}
                dd['id'] = d.id
                out.append(dd)
            return out
        except Exception as e:
            print(f"[FIREBASE] Error getting quotation items: {e}")
            return []

    def delete_quotation(self, quotation_id: int) -> None:
        try:
            quotation_ref = self.db.collection('quotations').document(str(quotation_id))
            items_ref = quotation_ref.collection('items')
            for item_doc in items_ref.stream():
                item_doc.reference.delete()
            quotation_ref.delete()
        except Exception as e:
            print(f"[FIREBASE] Error deleting quotation {quotation_id}: {e}")
            raise

    def update_quotation(self, quotation_id: int, quotation_data: Dict[str, Any], items: List[Dict[str, Any]]) -> None:
        try:
            quotation_ref = self.db.collection('quotations').document(str(quotation_id))
            quotation_doc = dict(quotation_data or {})
            # preserve pdf keys if present
            pdf_storage_path = quotation_doc.pop('pdf_storage_path', None)
            pdf_url = quotation_doc.pop('pdf_url', None)

            quotation_doc = self._add_metadata(quotation_doc, is_update=True)
            if pdf_storage_path:
                quotation_doc['pdf_storage_path'] = pdf_storage_path
            if pdf_url:
                quotation_doc['pdf_url'] = pdf_url

            quotation_ref.update(quotation_doc)
            items_ref = quotation_ref.collection('items')
            for item_doc in items_ref.stream():
                item_doc.reference.delete()
            for idx, item in enumerate(items or []):
                item_doc = self._add_metadata(dict(item or {}))
                items_ref.document(str(idx)).set(item_doc)

            # update file index if pdf present
            if pdf_storage_path or pdf_url:
                try:
                    self.set_file_index(pdf_storage_path or f"quotations/{quotation_id}", {
                        "type": "quotation",
                        "quotation_id": quotation_id,
                        "storage_path": pdf_storage_path,
                        "url": pdf_url,
                        "company_id": quotation_doc.get("company_id")
                    })
                except Exception:
                    pass

        except Exception as e:
            print(f"[FIREBASE] Error updating quotation {quotation_id}: {e}")
            raise

    # ===== NCF / SECUENCIAS =====
    # ... (El resto de la sección NCF permanece igual - OMITIDO por brevedad en este bloque)
    # Copia la implementación existente de _normalize_ncf_prefix, _format_ncf, get_ncf_last_seq, set_ncf_last_seq, get_ncf_preview, allocate_next_ncf, get_company_due_date, set_company_due_date, get_next_ncf
    # (No ha habido cambios en la lógica NCF aquí; mantener la definición existente en tu archivo original)
    # ============================================================================================================
    # [Nota: en la versión real del archivo, conserva las funciones NCF completas previas tal y como estaban.]

    # ===== LOGOS EN STORAGE =====

    def upload_logo_to_storage(self, local_path: str, template_id: str) -> Optional[str]:
        """
        Sube un logo de compañía/plantilla a Storage y devuelve URL pública.
        - Usa SDK si está disponible (make_public; fallback signed URL v4 365 días para logos).
        - Si no hay SDK, usa REST (googleapis) y devuelve URL con token.
        storage_path: templates/<template_id>/logo.<ext>
        """
        if not os.path.exists(local_path):
            print(f"[UPLOAD-LOGO] Local file not found: {local_path}")
            return None

        # Resolver extensión y content-type de imagen
        _, ext = os.path.splitext(local_path)
        if not ext:
            ext = ".png"
        ext = ext.lower()
        content_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml"}
        content_type = content_types.get(ext, "application/octet-stream")
        storage_path = f"templates/{template_id}/logo{ext}"

        # SDK primero
        if self.storage:
            try:
                blob = self.storage.blob(storage_path)
                try:
                    blob.upload_from_filename(local_path, content_type=content_type)
                except TypeError:
                    blob.upload_from_filename(local_path)

                # Intentar publicar
                try:
                    blob.make_public()
                    public_url = getattr(blob, "public_url", None)
                    print(f"[UPLOAD-LOGO] SDK make_public OK: {public_url}")
                    return public_url
                except Exception as e_make:
                    print(f"[UPLOAD-LOGO] SDK make_public failed: {e_make}")

                # Fallback: signed URL con expiración larga para logos (1 año máx práctico)
                try:
                    expiration_seconds = 3600 * 24 * 365  # ~1 año
                    public_url = blob.generate_signed_url(version="v4", expiration=expiration_seconds, method="GET")
                    print(f"[UPLOAD-LOGO] SDK signed URL v4 (≈365d): {public_url}")
                    return public_url
                except Exception as e_signed:
                    print(f"[UPLOAD-LOGO] SDK signed URL error: {e_signed}")

            except Exception as e_sdk:
                print(f"[UPLOAD-LOGO] SDK upload failed, will try REST: {e_sdk}")

        # REST fallback
        try:
            base_url = f"https://firebasestorage.googleapis.com/v0/b/{self.storage_bucket}/o"
            params = {"name": storage_path}
            headers = {"Content-Type": content_type}
            if self.storage_auth_token:
                headers["Authorization"] = f"Bearer {self.storage_auth_token}"

            print(f"[REST-UPLOAD-LOGO] POST {base_url} name={storage_path} ctype={content_type}")
            with open(local_path, "rb") as f:
                data = f.read()

            resp = requests.post(base_url, params=params, headers=headers, data=data, timeout=120)
            if resp.status_code not in (200, 201):
                print(f"[REST-UPLOAD-LOGO] ERROR {resp.status_code}: {resp.text}")
                return None

            j = resp.json() if resp.content else {}
            download_tokens = j.get("downloadTokens")

            from requests.utils import quote
            name_encoded = quote(storage_path, safe="")
            public_url = f"https://firebasestorage.googleapis.com/v0/b/{self.storage_bucket}/o/{name_encoded}?alt=media"
            if download_tokens:
                public_url += f"&token={download_tokens}"

            print(f"[REST-UPLOAD-LOGO] Uploaded: gs://{self.storage_bucket}/{storage_path}")
            print(f"[REST-UPLOAD-LOGO] Public URL: {public_url}")
            return public_url

        except Exception as e:
            print(f"[REST-UPLOAD-LOGO] Exception uploading logo {local_path} -> {storage_path}: {e}")
            return None



    # ---------- NUEVAS FUNCIONES: UPLOAD FILES Y INDEXACIÓN ----------




    def generate_signed_url_for_path(self, storage_path: str, days: int | None = None) -> Optional[str]:
        """
        Genera y devuelve un signed URL para un archivo ya existente en Storage.
        No re-subirá el archivo. Retorna None si falla.
        - days: duración en días (por defecto facot_config.PDF_SIGNED_URL_DAYS o 7).
        """
        if not self.storage:
            print("[PDF-SIGN] storage cliente no disponible")
            return None
        try:
            days_cfg = int(getattr(facot_config, "PDF_SIGNED_URL_DAYS", 7) or 7)
            days = int(days or days_cfg)
            if days > 7:
                days = 7
            expiration_seconds = 3600 * 24 * days
            blob = self.storage.blob(storage_path)
            # verificar existencia
            try:
                if not blob.exists():
                    print(f"[PDF-SIGN] blob no existe: {storage_path}")
                    return None
            except Exception:
                # continuar e intentar generar igualmente
                pass
            try:
                url = blob.generate_signed_url(version="v4", expiration=expiration_seconds, method="GET")
                expires_at = (datetime.utcnow() + timedelta(seconds=expiration_seconds)).isoformat()
                # actualizar index si se desea
                try:
                    self.set_file_index(storage_path, {
                        "storage_path": storage_path,
                        "url": url,
                        "signed_at": datetime.utcnow().isoformat(),
                        "expires_at": expires_at
                    })
                except Exception:
                    pass
                print(f"[PDF-SIGN] Signed URL generado (expira en {days}d): {url}")
                return url
            except Exception as e:
                print(f"[PDF-SIGN] ERROR generating signed url for {storage_path}: {e}")
                return None
        except Exception as e:
            print(f"[PDF-SIGN] ERROR: {e}")
            return None
        
    def set_file_index(self, storage_path: str, data: dict) -> None:
        """
        Indexa archivo en 'files_index' (opcional).
        """
        try:
            doc_id = storage_path.replace("/", "_")
            self.db.collection("files_index").document(doc_id).set(data, merge=True)
        except Exception as e:
            print(f"[FILES-INDEX] Error indexando {storage_path}: {e}")




    def set_invoice_pdf_info(self, invoice_id: Any, storage_path: str, public_url: Optional[str], expires_at: Optional[str] = None) -> None:
        """
        Guarda metadata de PDF en invoices/{invoice_id} y actualiza el índice.
        Añade pdf_storage_path, pdf_url y pdf_url_expires_at.
        """
        try:
            if not invoice_id:
                return
            data = {
                "pdf_storage_path": storage_path or "",
                "pdf_url": public_url or "",
                "pdf_url_expires_at": expires_at or "",
                "updated_at": datetime.utcnow().isoformat(),
                "updated_by": self.user_id
            }
            self.db.collection('invoices').document(str(invoice_id)).set(data, merge=True)
            # Intentar indexar con info adicional (company_id si está disponible)
            try:
                inv_doc = self.db.collection('invoices').document(str(invoice_id)).get()
                inv = inv_doc.to_dict() or {}
                company_id = inv.get('company_id')
            except Exception:
                company_id = None
            self.set_file_index(storage_path or f"invoices/{invoice_id}", {
                "type": "invoice",
                "invoice_id": invoice_id,
                "storage_path": storage_path,
                "url": public_url,
                "company_id": company_id,
                "expires_at": expires_at or ""
            })
            print(f"[PDF-UPLOAD] invoice_id={invoice_id} pdf info saved")
        except Exception as e:
            print(f"[PDF-UPLOAD] ERROR set_invoice_pdf_info id={invoice_id}: {e}")


    def set_quotation_pdf_info(self, quotation_id: Any, storage_path: str, public_url: Optional[str], expires_at: Optional[str] = None) -> None:
        """
        Guarda metadata de PDF en quotations/{quotation_id} y actualiza el índice.
        Añade pdf_storage_path, pdf_url y pdf_url_expires_at.
        """
        try:
            if not quotation_id:
                return
            data = {
                "pdf_storage_path": storage_path or "",
                "pdf_url": public_url or "",
                "pdf_url_expires_at": expires_at or "",
                "updated_at": datetime.utcnow().isoformat(),
                "updated_by": self.user_id
            }
            self.db.collection('quotations').document(str(quotation_id)).set(data, merge=True)
            try:
                q_doc = self.db.collection('quotations').document(str(quotation_id)).get()
                q = q_doc.to_dict() or {}
                company_id = q.get('company_id')
            except Exception:
                company_id = None
            self.set_file_index(storage_path or f"quotations/{quotation_id}", {
                "type": "quotation",
                "quotation_id": quotation_id,
                "storage_path": storage_path,
                "url": public_url,
                "company_id": company_id,
                "expires_at": expires_at or ""
            })
            print(f"[PDF-UPLOAD] quotation_id={quotation_id} pdf info saved")
        except Exception as e:
            print(f"[PDF-UPLOAD] ERROR set_quotation_pdf_info id={quotation_id}: {e}")

    # ===== GET/SET PLANTILLA LOGIC PREEXISTENTE =====
    def download_logo(self, storage_path: str, template_id: str) -> Optional[str]:
        if not self.storage:
            return None
        CACHE_EXPIRATION_SECONDS = 24 * 60 * 60
        try:
            cache_dir = os.path.join(".", "data", "cache", "logos")
            os.makedirs(cache_dir, exist_ok=True)
            _, ext = os.path.splitext(storage_path)
            if not ext:
                ext = ".png"
            local_path = os.path.join(cache_dir, f"{template_id}{ext}")
            if os.path.exists(local_path):
                import time
                if time.time() - os.path.getmtime(local_path) < CACHE_EXPIRATION_SECONDS:
                    return local_path
            blob = self.storage.blob(storage_path)
            if not blob.exists():
                return None
            blob.download_to_filename(local_path)
            return local_path
        except Exception as e:
            print(f"[FIREBASE] Error descargando logo: {e}")
            return None

    def update_template_logo(self, template_id: str, local_logo_path: str) -> Dict[str, Any]:
        result = {}
        public_url = self.upload_logo_to_storage(local_logo_path, template_id)
        if public_url:
            _, ext = os.path.splitext(local_logo_path)
            storage_path = f"templates/{template_id}/logo{ext}"
            result = {"logo_storage_path": storage_path, "logo_url": public_url}
            try:
                template_ref = self.db.collection('templates').document(str(template_id))
                template_ref.update({
                    "logo_storage_path": storage_path, "logo_url": public_url,
                    "updated_at": datetime.utcnow().isoformat(), "updated_by": self.user_id
                })
            except Exception as e:
                print(f"[FIREBASE] Error actualizando plantilla: {e}")
        return result

    def get_template_logo(self, template_id: str, fallback_local_path: Optional[str] = None) -> Optional[str]:
        try:
            template_ref = self.db.collection('templates').document(str(template_id))
            doc = template_ref.get()
            if doc.exists:
                template_data = doc.to_dict() or {}
                storage_path = template_data.get('logo_storage_path')
                if storage_path:
                    local_path = self.download_logo(storage_path, template_id)
                    if local_path:
                        return local_path
            if fallback_local_path and os.path.exists(fallback_local_path):
                return fallback_local_path
            return None
        except Exception:
            if fallback_local_path and os.path.exists(fallback_local_path):
                return fallback_local_path
            return None

    def set_ncf_last_seq(self, company_id: int, prefix3: str, last_seq: int) -> bool:
        """
        Establece la última secuencia para un prefijo NCF.
        Retorna True si se guardó correctamente, False en caso de error.
        """
        try:
            prefix3 = self._normalize_ncf_prefix(prefix3)
            doc_id = f"{company_id}ncf{prefix3}"
            doc_ref = self.db.collection('sequences').document(doc_id)

            # Leer valor anterior (opcional, para logging)
            try:
                doc = doc_ref.get()
                before = int(doc.get('current') or 0) if doc.exists else 0
            except Exception:
                before = None

            data = {
                'current': int(last_seq),
                'updated_at': datetime.utcnow().isoformat(),
                'updated_by': self.user_id
            }
            doc_ref.set(data, merge=True)
            print(f"[SEQ set_ncf_last_seq] company={company_id} prefix={prefix3} before={before} after={last_seq} by={self.user_id}")
            return True
        except Exception as e:
            print(f"[SEQ set_ncf_last_seq] ERROR saving sequence for company={company_id} prefix={prefix3}: {e}")
            # opcional: loguear stacktrace
            import traceback; traceback.print_exc()
            return False

    def set_company_due_date(self, company_id: int, due: str) -> bool:
        """
        Establece la fecha de vencimiento fija para facturas.
        Retorna True si se guardó correctamente, False en caso de error.
        """
        try:
            due = (due or '').strip()
            meta_ref = self.db.collection('sequences').document(f"{company_id}_meta")
            meta_data = {
                'invoice_due_date': due,
                'updated_at': datetime.utcnow().isoformat(),
                'updated_by': self.user_id
            }
            meta_ref.set(meta_data, merge=True)
            # espejo en companies/{id}
            company_ref = self.db.collection('companies').document(str(company_id))
            company_ref.set({'invoice_due_date': due, 'updated_at': datetime.utcnow().isoformat(), 'updated_by': self.user_id}, merge=True)
            print(f"[DUE set_company_due_date] Guardado invoice_due_date={due} para company={company_id} por user={self.user_id}")
            return True
        except Exception as e:
            print(f"[DUE set_company_due_date] ERROR saving due date for company={company_id}: {e}")
            import traceback; traceback.print_exc()
            return False



    def allocate_next_ncf(self, company_id: int, prefix3: str) -> str:
        """
        Asigna y consume el siguiente NCF de forma atómica usando FieldValue.Increment
        cuando esté disponible. Si no es posible, usa fallback set/get.
        Retorna el NCF asignado (formateado).
        """
        prefix3 = (prefix3 or "").upper().strip()
        prefix3 = self._normalize_ncf_prefix(prefix3) if hasattr(self, "_normalize_ncf_prefix") else (prefix3 or "B01")
        doc_id = f"{company_id}ncf{prefix3}"
        doc_path = f"sequences/{doc_id}"
        print(f"[SEQ allocate_next_ncf] START company_id={company_id}, prefix3={prefix3}, doc_path={doc_path}")

        # Intentar usar google-cloud-firestore Increment (operación atómica en servidor)
        try:
            from google.cloud import firestore as gcf
            sequence_ref = self.db.collection('sequences').document(doc_id)

            # Aseguramos existencia del documento mínimo (no sobrescribe current si ya existe)
            try:
                sequence_ref.set({}, merge=True)
            except Exception:
                # ignore, seguimos (document may already exist or permission issue)
                pass

            try:
                # Intentar update con Increment
                sequence_ref.update({
                    "current": gcf.Increment(1),
                    "updated_at": datetime.utcnow().isoformat(),
                    "updated_by": self.user_id
                })
            except Exception as e_update:
                # Si update falla (p. ej. por no existir o permisos), intentar set con merge de forma segura
                try:
                    # Leer, calcular y set (menos ideal, pero fallback)
                    doc = sequence_ref.get()
                    before = int(doc.get("current") or 0) if doc.exists else 0
                    after = before + 1
                    sequence_ref.set({
                        "current": after,
                        "updated_at": datetime.utcnow().isoformat(),
                        "updated_by": self.user_id
                    }, merge=True)
                    allocated_ncf = self._format_ncf(prefix3, after) if hasattr(self, "_format_ncf") else f"{prefix3}00000001"
                    print(f"[SEQ allocate_next_ncf] fallback_write after failed update: before={before}, after={after}, allocated_ncf={allocated_ncf}")
                    return allocated_ncf
                except Exception as e2:
                    print(f"[SEQ allocate_next_ncf] ERROR during fallback write after update fail: {e_update} / {e2}")
                    # continuará al bloque de lectura final para intentar leer whatever exists

            # Leer valor actualizado
            try:
                doc_after = sequence_ref.get()
                after_val = int(doc_after.get("current") or 0) if doc_after.exists else 0
                allocated_ncf = self._format_ncf(prefix3, after_val) if hasattr(self, "_format_ncf") else f"{prefix3}{after_val:08d}"
                print(f"[SEQ allocate_next_ncf] allocated via Increment: after={after_val}, allocated_ncf={allocated_ncf}")
                return allocated_ncf
            except Exception as e_read:
                print(f"[SEQ allocate_next_ncf] ERROR reading after increment: {e_read}")
                # dejar caer a fallback NO-TXN
        except Exception as e:
            print(f"[SEQ allocate_next_ncf] Increment path unavailable or failed: {e}")

        # FALLBACK NO-TXN: read -> increment -> write (no es atómico, pero ya tenías este fallback)
        try:
            seq_ref = self.db.collection('sequences').document(doc_id)
            doc = seq_ref.get()
            before = int(doc.get('current') or 0) if doc.exists else 0
            after = before + 1
            seq_ref.set({
                'current': after,
                'updated_at': datetime.utcnow().isoformat(),
                'updated_by': self.user_id
            }, merge=True)
            allocated_ncf = self._format_ncf(prefix3, after) if hasattr(self, "_format_ncf") else f"{prefix3}{after:08d}"
            print(f"[SEQ allocate_next_ncf FALLBACK-NO-TXN] before={before}, after={after}, allocated_ncf={allocated_ncf}")
            return allocated_ncf
        except Exception as e_final:
            print(f"[SEQ allocate_next_ncf] ERROR final al escribir secuencia: {e_final}")
            # retorno seguro
            try:
                return self._format_ncf(prefix3, 1) if hasattr(self, "_format_ncf") else f"{prefix3}00000001"
            except Exception:
                return f"{prefix3}00000001"
        
        # Función transaccional
        def _txn_allocate(transaction, ref):
            snapshot = ref.get(transaction=transaction)
            before = int(snapshot.get('current') or 0) if snapshot.exists else 0
            after = before + 1
            transaction.set(
                ref,
                {
                    'current': after,
                    'updated_at': datetime.utcnow().isoformat(),
                    'updated_by': self.user_id
                },
                merge=True
            )
            return before, after

        # Reintentos en caso de abortos por conflicto
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                transaction = self.db.transaction()
                before, after = _txn_allocate(transaction, sequence_ref) if False else None
                # Usar el decorador transactional correcto:
                @gcf.transactional
                def _wrapped(tx, ref):
                    return _txn_allocate(tx, ref)

                before, after = _wrapped(transaction, sequence_ref)
                allocated_ncf = self._format_ncf(prefix3, after)
                print(f"[SEQ allocate_next_ncf] attempt={attempt} before={before}, after={after}, allocated_ncf={allocated_ncf}")
                return allocated_ncf
            except Exception as tx_err:
                # Transacción fallida: intentar de nuevo con backoff
                print(f"[SEQ allocate_next_ncf] attempt={attempt} TRANSACCIÓN fallida: {tx_err}")
                if attempt >= max_retries:
                    print(f"[SEQ allocate_next_ncf] ERROR: alcanzado max_retries ({max_retries}). Aborting.")
                    break
                import time
                time.sleep(0.1 * attempt)  # backoff simple

        # Si arribamos aquí, transacción falló repetidamente: fallback NO-TXN
        try:
            doc = sequence_ref.get()
            before = int(doc.get('current') or 0) if doc.exists else 0
        except Exception:
            before = 0
        after = before + 1
        try:
            sequence_ref.set({
                'current': after,
                'updated_at': datetime.utcnow().isoformat(),
                'updated_by': self.user_id
            }, merge=True)
            allocated_ncf = self._format_ncf(prefix3, after)
            print(f"[SEQ allocate_next_ncf FALLBACK-NO-TXN] before={before}, after={after}, allocated_ncf={allocated_ncf}")
            return allocated_ncf
        except Exception as e_final:
            print(f"[SEQ allocate_next_ncf] ERROR final al escribir secuencia: {e_final}")
            return self._format_ncf(prefix3, 1)

    def _normalize_ncf_prefix(self, prefix3: str) -> str:
        """
        Normaliza el prefijo a formato estándar (B01, E31, etc.).
        Acepta: "B01", "01", "31", "E31", "B1", "b01", "01" etc.
        """
        try:
            p = (prefix3 or "").upper().strip()
            if not p:
                return "B01"
            # Ya en formato correcto (3 chars, letra + 2 dígitos)
            if len(p) == 3 and p[0].isalpha() and p[1:].isdigit():
                return p
            # Solo dígitos -> puede venir como "01" o "31"
            if p.isdigit():
                if p == "31":
                    return "E31"
                # asegurar 2 dígitos
                p2 = p.zfill(2)
                return f"B{p2}"
            # Empieza con letra pero no tiene 3 caracteres
            if p and p[0].isalpha():
                if len(p) >= 3:
                    return p[:3]
                if len(p) == 2:
                    return f"{p[0]}{p[1]}"[:3].ljust(3, "0")[:3]
                # len == 1
                return f"{p}01"
            # Fallback
            return "B01"
        except Exception:
            return "B01"

    def _format_ncf(self, prefix3: str, seq_num: int) -> str:
        """
        Formatea un NCF según el prefijo normalizado.
        - E-prefijos: E + 2 dígitos tipo + 11 dígitos secuencia (total E + 13)
        - B-prefijos: Prefix (3 chars) + 8 dígitos secuencia
        """
        try:
            pref = (prefix3 or "").upper().strip()
            pref = self._normalize_ncf_prefix(pref)
            if pref.startswith("E"):
                tipo = pref[1:3]
                return f"E{tipo}{int(seq_num):011d}"
            # NCF estándar (Bxx)
            return f"{pref}{int(seq_num):08d}"
        except Exception:
            # Fallback seguro
            try:
                pref = (prefix3 or "B01").upper()[:3]
                return f"{pref}{int(seq_num):08d}"
            except Exception:
                return f"B0100000001"

    def get_next_ncf(self, company_id: int, ncf_type: str) -> str:
        """
        Compatibilidad: retorna y (preferiblemente) asigna/consume el siguiente NCF.
        Delegamos a allocate_next_ncf (transaccional) cuando esté disponible.
        Si falla, devolvemos un NCF formateado con secuencia 1 como fallback.
        """
        try:
            # Intentar delegar a la implementación transaccional si existe
            if hasattr(self, "allocate_next_ncf"):
                return self.allocate_next_ncf(company_id, ncf_type)
        except Exception as e:
            print(f"[FIREBASE] get_next_ncf delegate error: {e}")

        # Fallback: formatear un NCF base sin incrementar en backend
        try:
            pref = self._normalize_ncf_prefix(ncf_type)
            return self._format_ncf(pref, 1)
        except Exception as e:
            print(f"[FIREBASE] get_next_ncf fallback error: {e}")
            return "B0100000001"
        
    def commit(self) -> None:
        pass

    def close(self) -> None:
        pass

# ==========================================
    #           NCF / SECUENCIAS (CORREGIDO)
    # ==========================================

    def get_ncf_last_seq(self, company_id: int, prefix3: str) -> int:
        """
        Obtiene la última secuencia usada (campo 'current') para un prefijo.
        Es vital que el doc_id coincida con set_ncf_last_seq: "{id}ncf{prefix}"
        """
        try:
            prefix3 = self._normalize_ncf_prefix(prefix3)
            # ID idéntico al usado en set_ncf_last_seq
            doc_id = f"{company_id}ncf{prefix3}"
            doc = self.db.collection('sequences').document(doc_id).get()
            
            if doc.exists:
                data = doc.to_dict() or {}
                # Devuelve 'current' (último usado). 
                return int(data.get('current', 0))
            return 0
        except Exception as e:
            print(f"[SEQ get_ncf_last_seq] Error reading {company_id}/{prefix3}: {e}")
            return 0

    def get_ncf_preview(self, company_id: int, prefix3: str) -> str:
        """
        Retorna el PRÓXIMO NCF (current + 1) formateado sin consumirlo.
        """
        try:
            last_seq = self.get_ncf_last_seq(company_id, prefix3)
            next_seq = last_seq + 1
            return self._format_ncf(prefix3, next_seq)
        except Exception as e:
            print(f"[SEQ preview] Error: {e}")
            return "ERROR"

    # ==========================================
    #           VENCIMIENTOS (CORREGIDO)
    # ==========================================

    def get_company_due_date(self, company_id: int) -> str:
        """
        Recupera invoice_due_date buscando en sequences/{id}_meta y luego en companies/{id}.
        """
        try:
            # 1. Intentar metadata específica (sequences)
            meta_ref = self.db.collection('sequences').document(f"{company_id}_meta")
            doc = meta_ref.get()
            if doc.exists:
                val = doc.to_dict().get('invoice_due_date')
                if val: return str(val).strip()

            # 2. Fallback al documento de la empresa
            comp_ref = self.db.collection('companies').document(str(company_id))
            cdoc = comp_ref.get()
            if cdoc.exists:
                val = cdoc.to_dict().get('invoice_due_date')
                if val: return str(val).strip()
            
            return ""
        except Exception as e:
            print(f"[FIREBASE] Error get_company_due_date: {e}")
            return ""
        


    def _sdk_upload(self, local_path: str, storage_path: str) -> Optional[str]:
        try:
            import facot_config
            cred_path, _ = facot_config.get_firebase_config()
        except Exception:
            cred_path = ""

        if not cred_path or not os.path.exists(cred_path):
            return None

        creds = service_account.Credentials.from_service_account_file(cred_path)
        client = gcs_storage.Client(credentials=creds, project=creds.project_id)
        bucket = client.bucket(self.storage_bucket)  # ej: facot-app.firebasestorage.app
        blob = bucket.blob(storage_path)

        ctype, _ = mimetypes.guess_type(local_path)
        if not ctype:
            _, ext = os.path.splitext(local_path)
            ctype = "application/pdf" if ext.lower() == ".pdf" else "application/octet-stream"

        blob.upload_from_filename(local_path, content_type=ctype)

        # Intentar URL firmada v4 (descarga)
        try:
            from datetime import timedelta
            url = blob.generate_signed_url(version="v4", expiration=timedelta(days=7), method="GET")
            return url
        except Exception:
            return None
        


    def _gcs_upload(self, local_path: str, storage_path: str) -> Optional[str]:
        """
        Sube un archivo usando Google Cloud Storage client (omite reglas de Firebase Storage).
        Requiere que el Service Account tenga permisos de Storage en el proyecto facot-app.
        """
        try:
            import facot_config
            cred_path, _ = facot_config.get_firebase_config()
        except Exception:
            cred_path = ""

        if not cred_path or not os.path.exists(cred_path):
            print("[GCS] Credenciales no encontradas para GCS upload.")
            return None

        try:
            # Construir cliente GCS con service account
            creds = service_account.Credentials.from_service_account_file(cred_path)
            client = gcs_storage.Client(credentials=creds, project=creds.project_id)

            # Tu bucket es 'facot-app.firebasestorage.app' (confirmado)
            bucket = client.bucket(self.storage_bucket)
            blob = bucket.blob(storage_path)

            # Content-Type
            ctype, _ = mimetypes.guess_type(local_path)
            if not ctype:
                _, ext = os.path.splitext(local_path)
                ctype = "application/pdf" if ext.lower() == ".pdf" else "application/octet-stream"

            # Subida
            blob.upload_from_filename(local_path, content_type=ctype)
            print(f"[GCS-UPLOAD] OK -> gs://{self.storage_bucket}/{storage_path}")

            # URL firmada opcional por 7 días para descarga
            try:
                from datetime import timedelta
                url = blob.generate_signed_url(version="v4", expiration=timedelta(days=7), method="GET")
                print(f"[GCS-UPLOAD] Signed URL (7d): {url}")
                return url
            except Exception as e:
                print(f"[GCS-UPLOAD] No se pudo generar URL firmada: {e}")
                return None

        except Exception as e:
            print(f"[GCS-UPLOAD] Error subiendo archivo: {e}")
            return None