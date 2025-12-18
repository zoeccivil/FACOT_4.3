"""
FirebaseClient - Cliente unificado para Firebase (Firestore, Storage, Auth).

Cambios clave:
- Usa EXCLUSIVAMENTE los valores de facot_config.get_firebase_config() para credenciales y bucket.
- Normaliza automáticamente el bucket del config a formato canónico *.appspot.com.
- Deja de derivar el bucket desde el project_id del JSON de credenciales (evita "progain-25fdf" inesperado).
- Deshabilita temporalmente el SDK de Storage (get_storage -> None) para forzar REST hasta que todo esté alineado.
"""

from __future__ import annotations
import os
import json
from typing import Optional

# Firebase Admin SDK
try:
    import firebase_admin
    from firebase_admin import credentials, firestore, storage, auth
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    print("[FIREBASE] Firebase Admin SDK no disponible. Instalar con: pip install firebase-admin")


def _normalize_bucket_to_canonical(bucket: str) -> str:
    """
    Convierte cualquier forma de bucket a canónico *.appspot.com:
    - project-id           -> project-id.appspot.com
    - project-id.appspot.com -> project-id.appspot.com
    - project-id.firebasestorage.app -> project-id.appspot.com
    """
    b = (bucket or "").strip()
    if not b:
        return ""
    if b.endswith(".appspot.com"):
        return b
    if b.endswith(".firebasestorage.app"):
        proj = b.replace(".firebasestorage.app", "")
        return f"{proj}.appspot.com"
    # caso: solo project-id
    return f"{b}.appspot.com"


class FirebaseClient:
    _instance: Optional["FirebaseClient"] = None
    _initialized: bool = False
    _credentials_path: Optional[str] = None
    _storage_bucket_canonical: Optional[str] = None
    _storage_bucket_web: Optional[str] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized and FIREBASE_AVAILABLE:
            self._initialize_firebase()
            FirebaseClient._initialized = True

    def _initialize_firebase(self, cred_path: Optional[str] = None, storage_bucket: Optional[str] = None) -> bool:
        """
        Inicializa Firebase usando EXCLUSIVAMENTE credenciales y bucket provenientes del config
        (facot_config.get_firebase_config) o parámetros explícitos.
        """
        # Si ya hay app, no re-inicializar
        try:
            firebase_admin.get_app()
            print("[FIREBASE] Ya inicializado")
            return True
        except ValueError:
            pass

        # 1) Leer del config (si no se pasan parámetros)
        cfg_cred, cfg_bucket = None, None
        try:
            import facot_config
            cfg_cred, cfg_bucket = facot_config.get_firebase_config()
        except Exception:
            pass

        # 2) Resolver credenciales y bucket:
        final_cred_path = (cred_path or cfg_cred or "").strip()
        if not final_cred_path or not os.path.exists(final_cred_path):
            # fallback: variables de entorno
            env_cred = os.getenv("FIREBASE_CREDENTIALS") \
                       or os.getenv("FIREBASE_CREDENTIALS_PATH") \
                       or os.getenv("GOOGLE_APPLICATION_CREDENTIALS") \
                       or ""
            if env_cred and os.path.exists(env_cred):
                final_cred_path = env_cred

        if not final_cred_path or not os.path.exists(final_cred_path):
            print("[FIREBASE] ⚠️ No se encontró archivo de credenciales Firebase (config/env).")
            return False

        raw_bucket = (storage_bucket or cfg_bucket or "").strip()
        # Si no hay bucket en config, como ÚLTIMO recurso usa project_id del JSON
        if not raw_bucket:
            try:
                with open(final_cred_path, "r", encoding="utf-8") as f:
                    proj = (json.load(f) or {}).get("project_id", "")
                raw_bucket = proj or ""
            except Exception:
                raw_bucket = ""

        final_bucket_canonical = _normalize_bucket_to_canonical(raw_bucket)
        final_bucket_web = final_bucket_canonical.replace(".appspot.com", ".firebasestorage.app")

        # 3) Inicializar Admin SDK con bucket canónico del CONFIG
        try:
            cred = credentials.Certificate(final_cred_path)
            firebase_admin.initialize_app(cred, {
                "storageBucket": final_bucket_canonical
            })
            FirebaseClient._credentials_path = final_cred_path
            FirebaseClient._storage_bucket_canonical = final_bucket_canonical
            FirebaseClient._storage_bucket_web = final_bucket_web

            print("[FIREBASE] ✓ Inicializado correctamente")
            print(f"[FIREBASE]   Credenciales (config/env): {final_cred_path}")
            print(f"[FIREBASE]   Storage Bucket (SDK): {final_bucket_canonical}")
            print(f"[FIREBASE]   Storage Bucket (web): {final_bucket_web}")
            return True
        except Exception as e:
            print(f"[FIREBASE] ✗ Error al inicializar: {e}")
            return False

    def is_available(self) -> bool:
        if not FIREBASE_AVAILABLE:
            return False
        try:
            firebase_admin.get_app()
            return True
        except ValueError:
            return False

    def get_firestore(self):
        if not self.is_available():
            print("[FIREBASE] Firestore no disponible")
            return None
        try:
            return firestore.client()
        except Exception as e:
            print(f"[FIREBASE] Error al obtener Firestore: {e}")
            return None

    def get_storage(self):
        """
        Deshabilitado temporalmente para evitar usar el SDK de Storage mientras se alinea
        el proyecto y el bucket. Usa REST en DataAccess.
        """
        if not self.is_available():
            print("[FIREBASE] Storage no disponible")
            return None
        print("[FIREBASE] Storage SDK deshabilitado (usaremos REST en DataAccess).")
        return None

    def get_auth(self):
        if not self.is_available():
            print("[FIREBASE] Auth no disponible")
            return None
        return auth


_firebase_client: Optional[FirebaseClient] = None

def get_firebase_client() -> FirebaseClient:
    global _firebase_client
    if _firebase_client is None:
        _firebase_client = FirebaseClient()
    return _firebase_client

def reinitialize_firebase(credentials_path: str, storage_bucket: str) -> bool:
    global _firebase_client
    if not FIREBASE_AVAILABLE:
        print("[FIREBASE] SDK no disponible")
        return False
    # Borrar app previa
    try:
        app = firebase_admin.get_app()
        firebase_admin.delete_app(app)
        FirebaseClient._initialized = False
    except ValueError:
        pass
    _firebase_client = FirebaseClient()
    return _firebase_client._initialize_firebase(credentials_path, storage_bucket)