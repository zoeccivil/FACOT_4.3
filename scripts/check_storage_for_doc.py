#!/usr/bin/env python3
"""
Comprobador robusto de Storage/Firestore para un invoice/quotation.
Uso:
  python scripts/check_storage_for_doc.py invoice 123
  python scripts/check_storage_for_doc.py quotation 456

Este script intenta cargar el data access del proyecto de varias formas para
evitar errores de import en entornos donde Pylance/VSCode no detecta paths.
"""
import sys
import os
import tempfile

def eprint(*a, **k):
    print(*a, **k, file=sys.stderr)

def locate_project_root():
    # Asumimos que el script vive en <project>/scripts/
    p = os.path.dirname(os.path.abspath(__file__))
    pr = os.path.abspath(os.path.join(p, ".."))
    return pr

# Añadir project root al sys.path para facilitar imports locales
project_root = locate_project_root()
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Intentos de obtener data_access de forma flexible
da = None
db = None
storage = None

# 1) Intentar obtener get_data_access desde el paquete data_access (preferido)
try:
    try:
        from data_access import get_data_access, DataAccessMode  # type: ignore
        da = get_data_access(user_id=None, mode=DataAccessMode.FIREBASE)
    except Exception:
        # 2) Intentar importar la clase FirebaseDataAccess desde el paquete data_access
        try:
            from data_access.firebase_data_access import FirebaseDataAccess  # type: ignore
            da = FirebaseDataAccess(user_id="system")
        except Exception:
            # 3) Último recurso: intentar importar un módulo legacy llamado firebase_data_access
            try:
                import importlib
                fda = importlib.import_module("firebase_data_access")  # noqa: E402
                if hasattr(fda, "FirebaseDataAccess"):
                    da = fda.FirebaseDataAccess(user_id="system")
            except Exception as ex:
                eprint("Fallo importando firebase_data_access (legacy):", ex)
except Exception as ex:
    eprint("Advertencia: no pude obtener data_access via get_data_access o data_access.firebase_data_access:", ex)

if da is None:
    eprint("No se pudo instanciar data_access. Asegúrate de ejecutar este script desde la raíz del proyecto")
    sys.exit(1)

db = getattr(da, "db", None)
storage = getattr(da, "storage", None)

def usage_and_exit():
    eprint("Uso: python scripts/check_storage_for_doc.py <invoice|quotation> <id>")
    sys.exit(2)

if len(sys.argv) < 3:
    usage_and_exit()

typ = sys.argv[1].lower()
doc_id = str(sys.argv[2])

if db is None:
    eprint("El data_access no expone cliente Firestore (da.db es None). Verifica la inicialización de Firebase.")
    # Seguimos para intentar verificar cosas de storage si aplica.

def fetch_doc():
    if db is None:
        return None
    try:
        if typ == "invoice":
            doc = db.collection("invoices").document(doc_id).get()
        elif typ == "quotation":
            doc = db.collection("quotations").document(doc_id).get()
        else:
            eprint("Tipo inválido:", typ)
            usage_and_exit()
        if not doc.exists:
            return {}
        return doc.to_dict() or {}
    except Exception as e:
        eprint("Error leyendo Firestore:", e)
        return None

doc = fetch_doc()
if doc is None:
    eprint("No se pudo leer el documento desde Firestore (cliente no disponible o error).")
else:
    if not doc:
        eprint(f"{typ} {doc_id} no existe en Firestore.")
    else:
        eprint(f"Firestore fields for {typ}/{doc_id}:")
        for k in ("pdf_storage_path", "pdf_url", "pdf_url_expires_at"):
            eprint(f"  {k}: {doc.get(k)}")

storage_path = (doc or {}).get("pdf_storage_path")
if not storage_path:
    eprint("No hay pdf_storage_path registrado en Firestore para este documento.")
    # aún intentamos ver si hay entradas en files_index (opcional)
    if db is not None:
        try:
            idx_q = db.collection("files_index").where("invoice_id", "==", doc_id).limit(1)
            res = list(idx_q.stream())
            if res:
                eprint("Encontrado registro en files_index (by invoice_id):", res[0].id, res[0].to_dict())
        except Exception:
            pass
    sys.exit(0)

if storage is None:
    eprint("No pude obtener cliente Storage desde data_access (da.storage es None).")
    sys.exit(0)

blob = storage.blob(storage_path)
try:
    exists = blob.exists()
except Exception as e:
    eprint("Error llamando blob.exists():", e)
    exists = None

eprint("Blob.exists() ->", exists)
if exists:
    try:
        tmpf = os.path.join(tempfile.gettempdir(), f"check_{os.path.basename(storage_path)}")
        blob.download_to_filename(tmpf)
        eprint("Blob descargado a:", tmpf, "size=", os.path.getsize(tmpf))
    except Exception as e:
        eprint("Error descargando blob:", e)
else:
    eprint("El blob no existe en Storage. Posibles causas: la subida falló o se guardó otro storage_path.")

eprint("FIN")