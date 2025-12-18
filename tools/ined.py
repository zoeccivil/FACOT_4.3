from __future__ import annotations

"""
Inspector de diferencias de facturas 'emitida' en Firestore para un company_id dado.

Funcionalidad:
- Selecciona credenciales Firebase (JSON) mediante diálogo.
- Conecta a Firestore y verifica la colección 'invoices'.
- Obtiene y muestra todos los campos para los documentos con IDs especificados.
- Verifica también por company_id=6 todos los documentos 'emitida' para contextualizar.
- Compara diferencias campo por campo entre las facturas dadas.
- Señala causas típicas por las que "se ve" o "no se ve" en InvoiceHistory:
  - Filtro por company_id (tipo int vs string en el documento)
  - invoice_type / type, casing y normalización
  - Campos de fecha y rango aplicado
  - Campos de cliente y filtro de texto

IDs objetivo:
- Se ven: 1077
- No se ven: 1171, 1431, 1432
Company ID objetivo: 6

Cómo usar:
- python tools/inspect_emitidas_diff.py
- Selecciona el JSON de credenciales.
- Lee y muestra resultados en consola.
"""

import sys
from typing import Any, Dict, List, Tuple, Optional

from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

try:
    from google.cloud import firestore
    from google.oauth2 import service_account
    from google.cloud.firestore_v1 import FieldFilter
except Exception:
    firestore = None
    service_account = None
    FieldFilter = None  # type: ignore


TARGET_COMPANY_ID = 6
TARGET_IDS = [1077, 1171, 1431, 1432]


def pick_credentials() -> str:
    app = QApplication.instance() or QApplication(sys.argv)
    fn, _ = QFileDialog.getOpenFileName(
        None, "Seleccionar credenciales Firebase (JSON)", "", "JSON (*.json);;Todos (*.*)"
    )
    if not fn:
        print("[FB] No se seleccionó credencial JSON.")
        sys.exit(0)
    return fn


def normalize_invoice_type(data: Dict[str, Any]) -> str:
    """
    Devuelve el tipo de factura normalizado a minúsculas leyendo 'invoice_type' o 'type'.
    """
    val = data.get("invoice_type")
    if val is None:
        val = data.get("type")
    return str(val or "").strip().lower()


def get_doc_by_id(fs, col_name: str, doc_id: Any) -> Optional[Dict[str, Any]]:
    """
    Obtiene un documento por ID exacto y devuelve su dict incluyendo 'id', None si no existe.
    """
    try:
        doc_ref = fs.collection(col_name).document(str(doc_id))
        doc = doc_ref.get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        data["id"] = int(doc.id) if str(doc.id).isdigit() else doc.id
        return data
    except Exception as e:
        print(f"[FB] Error leyendo doc {col_name}/{doc_id}: {e}")
        return None


def list_emitidas_for_company(fs, company_id: Any) -> List[Dict[str, Any]]:
    """
    Lista documentos de 'invoices' para company_id indicado y filtra en cliente por emitida.
    Intenta con FieldFilter e intenta company_id como int y como string.
    """
    col = fs.collection("invoices")
    out: List[Dict[str, Any]] = []
    total_hits = 0

    # Base por company_id (int o str) + filtro en cliente
    for cid_variant in (company_id, str(company_id)):
        try:
            if FieldFilter:
                base = col.where(filter=FieldFilter("company_id", "==", cid_variant))
            else:
                base = col.where("company_id", "==", cid_variant)
            base_docs = list(base.stream())
            total_hits += len(base_docs)
            for d in base_docs:
                data = d.to_dict() or {}
                if normalize_invoice_type(data) == "emitida":
                    data["id"] = int(d.id) if d.id.isdigit() else d.id
                    out.append(data)
        except Exception as e:
            print(f"[FB] Error base company_id={cid_variant}: {e}")

    print(f"[FB] Company {company_id}: hits={total_hits}, emitida={len(out)}")
    return out


def compare_fields(a: Dict[str, Any], b: Dict[str, Any]) -> List[Tuple[str, Any, Any, str]]:
    """
    Compara campo por campo los dicts a y b.
    Retorna lista de tuples: (campo, valor_a, valor_b, hint)
    hint sugiere por qué puede afectar la visibilidad en InvoiceHistory.
    """
    keys = set(a.keys()) | set(b.keys())
    diffs: List[Tuple[str, Any, Any, str]] = []
    for k in sorted(keys):
        va = a.get(k, None)
        vb = b.get(k, None)
        if va != vb:
            hint = ""
            k_low = k.lower()
            if k_low in ("company_id", "invoice_type", "type", "invoice_date", "date", "created_at", "issued_at",
                         "third_party_name", "client_name"):
                # Sugerencias específicas
                if k_low == "company_id":
                    hint = "Tipo/valor de company_id puede causar que la consulta no empareje (int vs string)."
                elif k_low in ("invoice_type", "type"):
                    hint = "El filtro de history usa 'emitida' en minúscula; revisar casing/uso de 'type' vs 'invoice_type'."
                elif k_low in ("invoice_date", "date", "created_at", "issued_at"):
                    hint = "Fuera de rango de fechas en la UI puede ocultar el documento."
                elif k_low in ("third_party_name", "client_name"):
                    hint = "Filtro de texto por cliente puede ocultarlo si no coincide."
            diffs.append((k, va, vb, hint))
    return diffs


def classify_visibility_causes(data: Dict[str, Any], company_id: Any) -> List[str]:
    """
    Analiza un documento y retorna posibles causas por las que podría 'NO verse' en InvoiceHistory.
    """
    causes: List[str] = []
    cid = data.get("company_id")
    type_norm = normalize_invoice_type(data)
    if cid not in (company_id, str(company_id)):
        causes.append(f"company_id {cid} no coincide con {company_id} o '{company_id}' (tipo/valor).")
    if type_norm != "emitida":
        causes.append(f"invoice_type/type normalizado es '{type_norm}', no 'emitida'.")
    # Nota: rango de fechas y filtro de cliente dependen de la UI; aquí solo señalamos campos relevantes
    if not (data.get("invoice_date") or data.get("date") or data.get("created_at") or data.get("issued_at")):
        causes.append("No tiene campo de fecha reconocible (invoice_date/date/created_at/issued_at).")
    client_name = (data.get("third_party_name") or data.get("client_name") or "").strip()
    if not client_name:
        causes.append("Campo de cliente vacío; un filtro de texto podría excluirlo si se busca por nombre.")
    return causes


def pretty_print_doc(label: str, doc: Optional[Dict[str, Any]]):
    """
    Imprime un documento completo con sus tipos de valor para facilitar la comparación.
    """
    print(f"\n=== {label} ===")
    if doc is None:
        print("(no existe)")
        return
    for k in sorted(doc.keys()):
        v = doc.get(k)
        t = type(v).__name__
        print(f"{k}: {v!r} ({t})")
    print("Tipo normalizado:", normalize_invoice_type(doc))


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
    print(f"[FB] Objetivo company_id={TARGET_COMPANY_ID}, IDs={TARGET_IDS}")

    # 1) Leer documentos por ID exacto
    docs_by_id: Dict[int, Optional[Dict[str, Any]]] = {}
    for iid in TARGET_IDS:
        docs_by_id[iid] = get_doc_by_id(fs, "invoices", iid)

    # 2) Mostrar cada documento (con tipos)
    for iid in TARGET_IDS:
        pretty_print_doc(f"Documento ID {iid}", docs_by_id[iid])

    # 3) Revisar por qué podrían no verse (clasificación básica)
    for iid in TARGET_IDS:
        doc = docs_by_id[iid]
        print(f"\n--- Visibilidad potencial para ID {iid} ---")
        if doc is None:
            print("No existe el documento en Firestore.")
            continue
        causes = classify_visibility_causes(doc, TARGET_COMPANY_ID)
        if not causes:
            print("No se detectan causas obvias; verificar rango de fechas y filtro de cliente en la UI.")
        else:
            for c in causes:
                print(f"- {c}")

    # 4) Comparar diferencias campo por campo entre el que "se ve" (1077) y los que "no se ven"
    base_id = 1077
    base_doc = docs_by_id.get(base_id)
    if base_doc:
        for other_id in [i for i in TARGET_IDS if i != base_id]:
            other_doc = docs_by_id.get(other_id)
            print(f"\n### Comparando {base_id} vs {other_id} ###")
            if other_doc is None:
                print(f"ID {other_id} no existe en Firestore.")
                continue
            diffs = compare_fields(base_doc, other_doc)
            if not diffs:
                print("Sin diferencias relevantes en campos.")
            else:
                for k, va, vb, hint in diffs:
                    print(f"* {k}: {va!r} -> {vb!r}{' | ' + hint if hint else ''}")

    # 5) Contexto: listar emitidas para company_id=6 y ver si están presentes las IDs objetivo
    emitidas = list_emitidas_for_company(fs, TARGET_COMPANY_ID)
    ids_in_emitidas = set([d.get("id") for d in emitidas])
    print("\n[FB] Emitidas para company_id=6 IDs presentes:", sorted(ids_in_emitidas))
    for iid in TARGET_IDS:
        present = iid in ids_in_emitidas
        print(f"ID {iid} {'ESTÁ' if present else 'NO ESTÁ'} en la lista de emitidas filtrada en cliente.")

    # 6) Conclusiones básicas
    print("\nConclusiones posibles:")
    print("- Si una factura no 'se ve' en History, pero aparece aquí y es 'emitida':")
    print("  revisa el rango de fechas en la UI y el filtro de cliente.")
    print("- Si company_id en el documento es string pero la UI consulta con int (o viceversa),")
    print("  las consultas en Firestore no matchean; el History debe hacer fallback por company_id y filtrar en cliente.")
    print("- Si 'invoice_type' está en minúsculas ('emitida'), el History debe normalizar a minúsculas.")
    print("- Si alguna de las 'no visibles' tiene campos vacíos o diferentes en 'invoice_date' o 'third_party_name',")
    print("  puede quedar fuera por filtros de fecha/cliente activos.")

    print("\n[FIN] Revisa la salida anterior para las diferencias y causas potenciales.")
    print("Si quieres, puedo generar un reporte Markdown o CSV con estas diferencias.")
    

if __name__ == "__main__":
    main()