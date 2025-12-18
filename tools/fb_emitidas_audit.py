from __future__ import annotations
import os
import sys
from typing import Dict

from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

try:
    from google.cloud import firestore
    from google.oauth2 import service_account
except Exception:
    firestore = None
    service_account = None

def pick_credentials() -> str:
    app = QApplication.instance() or QApplication(sys.argv)
    fn, _ = QFileDialog.getOpenFileName(
        None, "Seleccionar credenciales (JSON)", "", "JSON (*.json);;Todos (*.*)"
    )
    if not fn:
        print("[FB] No se seleccionó credencial JSON.")
        sys.exit(0)
    return fn

def normalize_type_val(val) -> str:
    # Normaliza el tipo a minúsculas
    return str(val or "").strip().lower()

def main():
    creds_path = pick_credentials()
    if firestore is None or service_account is None:
        QMessageBox.critical(None, "Firebase", "Instala google-cloud-firestore")
        sys.exit(1)
    try:
        creds = service_account.Credentials.from_service_account_file(creds_path)
        fs = firestore.Client(credentials=creds, project=creds.project_id)
    except Exception as e:
        QMessageBox.critical(None, "Firebase", f"No se pudo inicializar Firestore:\n{e}")
        sys.exit(1)

    print(f"[FB] Proyecto: {fs.project}")
    col = fs.collection("invoices")

    # Barrido único de toda la colección y conteo en cliente (sin filtros compuestos)
    # Evita problemas de índice y de tipos (string vs int) en company_id.
    consolidated: Dict[str, int] = {}
    total = 0
    try:
        docs = col.stream()
        for d in docs:
            data = d.to_dict() or {}
            # Normaliza company_id a string para agrupar consistentemente
            cid_raw = data.get("company_id")
            cid = str(cid_raw) if cid_raw is not None else ""
            if not cid:
                continue
            inv_type = normalize_type_val(data.get("invoice_type") or data.get("type"))
            if inv_type == "emitida":
                consolidated[cid] = consolidated.get(cid, 0) + 1
                total += 1
    except Exception as e:
        QMessageBox.critical(None, "Firebase", f"Error auditando invoices:\n{e}")
        sys.exit(1)

    print("\n[FB] EMITIDA por company_id (conteo en cliente):")
    if not consolidated:
        print("  (sin registros)")
    else:
        for cid, cnt in consolidated.items():
            print(f"  {cid}: {cnt}")
        print(f"\n[FB] Total EMITIDA: {total}")

if __name__ == "__main__":
    main()