from __future__ import annotations
import os, sys
from typing import Any, Dict

from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

try:
    from google.cloud import firestore
    from google.oauth2 import service_account
except Exception:
    firestore = None
    service_account = None

def pick_credentials() -> str:
    app = QApplication.instance() or QApplication(sys.argv)
    fn, _ = QFileDialog.getOpenFileName(None, "Seleccionar credenciales (JSON)", "", "JSON (*.json)")
    if not fn:
        print("No seleccionaste credenciales.")
        sys.exit(0)
    return fn

def main():
    creds_path = pick_credentials()
    if firestore is None or service_account is None:
        QMessageBox.critical(None, "Firebase", "Instala google-cloud-firestore")
        sys.exit(1)
    creds = service_account.Credentials.from_service_account_file(creds_path)
    fs = firestore.Client(credentials=creds, project=creds.project_id)

    col = fs.collection("invoices")
    # Muestra 10 docs para ver estructura:
    print("[MUESTRA] Primeros 10 documentos de invoices:")
    for i, d in enumerate(col.limit(10).stream()):
        data = d.to_dict()
        print(f"- {d.id}: keys={list(data.keys())}")
        print(f"    company_id={data.get('company_id')} invoice_type={data.get('invoice_type')} type={data.get('type')}")
        if i >= 9:
            break

    # Agrupa por company_id y cuenta con varias heurísticas de campo de tipo
    counts: Dict[str, int] = {}
    for d in col.stream():
        data = d.to_dict()
        cid = str(data.get("company_id") or "")
        # variantes de tipo
        raw_type = data.get("invoice_type", None)
        if raw_type is None:
            raw_type = data.get("type", None)
        s = str(raw_type or "").strip().upper()
        if cid and s == "EMITIDA":
            counts[cid] = counts.get(cid, 0) + 1

    print("\n[CUENTAS] EMITIDA por company_id (heurística invoice_type/type):")
    if not counts:
        print("  (sin resultados)")
    else:
        total = 0
        for cid, cnt in counts.items():
            print(f"  {cid}: {cnt}")
            total += cnt
        print(f"Total: {total}")

if __name__ == "__main__":
    main()