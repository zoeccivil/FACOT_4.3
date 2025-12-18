#!/usr/bin/env python3
"""
Selecciona credenciales de Firebase (Service Account JSON) con un file dialog
y muestra el último third_party guardado (colección 'third_parties').

Requisitos:
  pip install firebase-admin google-cloud-firestore
"""

import sys
import tkinter as tk
from tkinter import filedialog
import firebase_admin
from firebase_admin import credentials, firestore
import json

def pick_credentials_file():
    root = tk.Tk(); root.withdraw(); root.update()
    fpath = filedialog.askopenfilename(
        title="Selecciona el archivo de credenciales (service account JSON)",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
    )
    root.destroy()
    return fpath or None

def main():
    cred_path = pick_credentials_file()
    if not cred_path:
        print("No se seleccionó archivo de credenciales. Saliendo.")
        sys.exit(1)

    try:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"Error inicializando Firebase Admin: {e}")
        sys.exit(1)

    db = firestore.client()

    # Intentar ordenar por updated_at y, si falla, por created_at; si no, sin orden.
    third = None
    try:
        docs = list(db.collection("third_parties")
                       .order_by("updated_at", direction=firestore.Query.DESCENDING)
                       .limit(1).stream())
        if docs:
            third = docs[0]
    except Exception as e1:
        print(f"[WARN] order_by(updated_at) falló: {e1}")
    if third is None:
        try:
            docs = list(db.collection("third_parties")
                           .order_by("created_at", direction=firestore.Query.DESCENDING)
                           .limit(1).stream())
            if docs:
                third = docs[0]
        except Exception as e2:
            print(f"[WARN] order_by(created_at) falló: {e2}")
    if third is None:
        try:
            docs = list(db.collection("third_parties").limit(1).stream())
            if docs:
                third = docs[0]
        except Exception as e3:
            print(f"[ERROR] No se pudo obtener terceros: {e3}")

    if not third:
        print("No se encontró ningún third_party.")
        return

    data = third.to_dict() or {}
    data["id"] = third.id
    print("\n=== Último third_party ===")
    try:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        print(data)

if __name__ == "__main__":
    main()