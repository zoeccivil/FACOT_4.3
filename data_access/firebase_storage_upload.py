import os
import mimetypes
import json
import time
from typing import Optional

import requests

class FirebaseStorageUploader:
    """
    Uploader usando la API REST de Firebase Storage con dominio firebasestorage.app.
    Configura:
      - storage_host: 'facot-app.firebasestorage.app'
      - bucket: 'facot-app' (nombre corto del proyecto)
      - auth_token: opcional (si requieres autenticación, por ejemplo ID token de usuario)
    Si el bucket permite acceso público (reglas adecuadas), la URL de descarga será accesible.
    """
    def __init__(self, storage_host: str = "facot-app.firebasestorage.app", bucket: str = "facot-app", auth_token: Optional[str] = None):
        self.storage_host = storage_host.strip()
        self.bucket = bucket.strip()
        self.auth_token = auth_token

    def upload_file_to_storage(self, local_path: str, storage_path: str) -> Optional[str]:
        """
        Sube un archivo y devuelve una URL de descarga pública.
        storage_path: ruta dentro del bucket, ej. 'logos/company_1.jpg'
        """
        try:
            if not os.path.exists(local_path):
                print(f"[REST-UPLOAD] Local file not found: {local_path}")
                return None

            # Detectar content-type
            ctype, _ = mimetypes.guess_type(local_path)
            if not ctype:
                ctype = "application/octet-stream"

            # Endpoint REST: https://firebasestorage.googleapis.com/v0/b/<bucket>/o?name=<path>
            # Nota: aunque el render de archivos sirva desde facot-app.firebasestorage.app,
            # la subida REST estable es en firebasestorage.googleapis.com
            base_url = f"https://firebasestorage.googleapis.com/v0/b/{self.bucket}/o"
            params = {"name": storage_path}
            headers = {"Content-Type": ctype}

            # Autenticación opcional con ?uploadType=media y header Authorization
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"

            with open(local_path, "rb") as f:
                data = f.read()

            resp = requests.post(base_url, params=params, headers=headers, data=data, timeout=60)
            if resp.status_code not in (200, 201):
                print(f"[REST-UPLOAD] ERROR {resp.status_code}: {resp.text}")
                return None

            j = resp.json()
            # Firebase REST devuelve un token de descarga. Construimos la URL pública:
            # https://firebasestorage.googleapis.com/v0/b/<bucket>/o/<path_encoded>?alt=media&token=<downloadTokens>
            download_tokens = j.get("downloadTokens")
            name_encoded = requests.utils.quote(storage_path, safe="")
            public_url = f"https://firebasestorage.googleapis.com/v0/b/{self.bucket}/o/{name_encoded}?alt=media"
            if download_tokens:
                public_url += f"&token={download_tokens}"

            print(f"[REST-UPLOAD] Uploaded: gs://{self.bucket}/{storage_path}")
            print(f"[REST-UPLOAD] Public URL: {public_url}")

            return public_url
        except Exception as e:
            print(f"[REST-UPLOAD] Exception: {e}")
            return None

    def make_public_url(self, storage_path: str, token: Optional[str] = None) -> str:
        """
        Construye la URL pública de descarga para un objeto ya subido.
        Si token es None, intentará acceder sin token (requiere reglas públicas).
        """
        name_encoded = requests.utils.quote(storage_path, safe="")
        url = f"https://firebasestorage.googleapis.com/v0/b/{self.bucket}/o/{name_encoded}?alt=media"
        if token:
            url += f"&token={token}"
        return url