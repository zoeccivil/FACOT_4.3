"""
Lista los buckets de Cloud Storage seleccionando el archivo de credenciales con un diálogo.

Requisitos:
- pip install google-cloud-storage
- pip install tk (en Windows normalmente viene con Python)

Uso:
  python scripts/list_gcs_buckets.py
  - Se abrirá un diálogo para elegir el JSON de credenciales (service account).
  - Intentará detectar el project_id del JSON; si no puede, te pedirá el project_id por input.

Salida:
  - Lista de buckets del proyecto y verificación de existencia de 'facot-app.appspot.com'.
"""

import os
import sys
import json
import tkinter as tk
from tkinter import filedialog

from google.cloud import storage
from google.oauth2 import service_account


def ask_for_credentials_file() -> str:
    root = tk.Tk()
    root.withdraw()
    root.update()
    filetypes = [("JSON files", "*.json"), ("All files", "*.*")]
    cred_path = filedialog.askopenfilename(
        title="Selecciona el archivo de credenciales (Service Account JSON)",
        filetypes=filetypes
    )
    root.destroy()
    return cred_path or ""


def detect_project_id_from_json(cred_path: str) -> str:
    try:
        with open(cred_path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        # Campos típicos en service account
        # "project_id" suele estar presente
        pid = (data.get("project_id") or "").strip()
        return pid
    except Exception:
        return ""


def main():
    # 1) Elegir archivo de credenciales
    cred_path = ask_for_credentials_file()
    if not cred_path or not os.path.exists(cred_path):
        print("[ERROR] No se seleccionó un archivo válido de credenciales.")
        sys.exit(1)

    print(f"[INFO] cred_path: {cred_path}")

    # 2) Detectar project_id del JSON o pedirlo por input
    project_id = detect_project_id_from_json(cred_path)
    if not project_id:
        project_id = input("Ingrese el project_id (ej: facot-app): ").strip()

    if not project_id:
        print("[ERROR] No se proporcionó project_id.")
        sys.exit(1)

    print(f"[INFO] project_id: {project_id}")

    # 3) Construir cliente de Storage con credenciales explícitas
    try:
        creds = service_account.Credentials.from_service_account_file(cred_path)
        client = storage.Client(project=project_id, credentials=creds)

        print("[INFO] Listando buckets del proyecto...")
        buckets = list(client.list_buckets(project=project_id))
        if not buckets:
            print("[RESULT] No se encontraron buckets en el proyecto.")
            return

        print("[RESULT] Buckets encontrados:")
        for b in buckets:
            print(f" - {b.name}")

        target = "facot-app.appspot.com"
        exists = any(b.name == target for b in buckets)
        print(f"[CHECK] ¿Existe '{target}'? -> {'SI' if exists else 'NO'}")

    except Exception as e:
        print(f"[ERROR] Falló la lista de buckets: {e}")


if __name__ == "__main__":
    main()