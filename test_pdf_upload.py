#!/usr/bin/env python3
"""
Script de prueba: sube un PDF, registra metadata en Firestore y verifica.
Uso:
  python scripts/test_pdf_upload.py /ruta/a/sample.pdf invoice 123
  python scripts/test_pdf_upload.py /ruta/a/sample.pdf quotation 456
"""
import sys
import os
import tempfile

def eprint(*a, **k): print(*a, **k, file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) < 4:
        eprint("Uso: python scripts/test_pdf_upload.py <local_pdf_path> <invoice|quotation> <id>")
        sys.exit(2)

    local_pdf = sys.argv[1]
    typ = sys.argv[2].lower()
    target_id = sys.argv[3]

    if not os.path.exists(local_pdf):
        eprint("Archivo local no existe:", local_pdf)
        sys.exit(3)

    # Import helpers from tu proyecto
    try:
        from data_access import get_data_access, DataAccessMode
    except Exception as e:
        eprint("Error importando get_data_access:", e)
        sys.exit(4)

    try:
        da = get_data_access(user_id=None, mode=DataAccessMode.FIREBASE)
    except Exception as e:
        eprint("Error creando data_access:", e)
        sys.exit(5)

    # Construir storage_path simple: tipo/company_test/YYYY/MM/id.pdf
    # Aquí usamos company_id=1 para la prueba; ajusta si hace falta
    company_id = 1
    import datetime
    y = datetime.datetime.now().year
    m = f"{datetime.datetime.now().month:02d}"
    safe_company = "TEST_COMPANY"
    base_name = os.path.basename(local_pdf)
    # nombra por tipo/id para reproducibilidad
    storage_path = f"{('factura' if typ=='invoice' else 'cotizacion')}/{safe_company}/{y}/{m}/{target_id}_{base_name}"

    eprint("[TEST] storage_path ->", storage_path)

    # 1) subir el archivo
    try:
        upload_url = None
        if hasattr(da, "upload_file_to_storage"):
            upload_url = da.upload_file_to_storage(local_pdf, storage_path)
        elif hasattr(da, "data_access") and hasattr(da.data_access, "upload_file_to_storage"):
            upload_url = da.data_access.upload_file_to_storage(local_pdf, storage_path)
        eprint("[TEST] upload_url:", upload_url)
    except Exception as e:
        eprint("[TEST] Error en upload:", e)
        raise

    # 2) Registrar metadatos en Firestore
    try:
        if typ == "invoice":
            if hasattr(da, "set_invoice_pdf_info"):
                da.set_invoice_pdf_info(target_id, storage_path, upload_url)
            elif hasattr(da, "data_access") and hasattr(da.data_access, "set_invoice_pdf_info"):
                da.data_access.set_invoice_pdf_info(target_id, storage_path, upload_url)
            eprint("[TEST] Llamado set_invoice_pdf_info OK")
        else:
            if hasattr(da, "set_quotation_pdf_info"):
                da.set_quotation_pdf_info(target_id, storage_path, upload_url)
            elif hasattr(da, "data_access") and hasattr(da.data_access, "set_quotation_pdf_info"):
                da.data_access.set_quotation_pdf_info(target_id, storage_path, upload_url)
            eprint("[TEST] Llamado set_quotation_pdf_info OK")
    except Exception as e:
        eprint("[TEST] Error registrando metadata en Firestore:", e)
        raise

    # 3) Verificar Firestore document
    try:
        # acceder al cliente Firestore desde data_access si lo expone
        db = None
        if hasattr(da, "db"):
            db = da.db
        elif hasattr(da, "data_access") and hasattr(da.data_access, "db"):
            db = da.data_access.db

        if db is None:
            eprint("[TEST] No pude obtener referencia a Firestore desde data_access")
        else:
            if typ == "invoice":
                doc = db.collection("invoices").document(str(target_id)).get()
            else:
                doc = db.collection("quotations").document(str(target_id)).get()
            if doc.exists:
                d = doc.to_dict() or {}
                eprint("[TEST] Firestore doc fields:", {k: d.get(k) for k in ("pdf_storage_path","pdf_url")})
            else:
                eprint(f"[TEST] Documento {'invoices' if typ=='invoice' else 'quotations'}/{target_id} no existe (aún).")
    except Exception as e:
        eprint("[TEST] Error leyendo Firestore:", e)

    # 4) Verificar blob.exists() y opción de descarga
    try:
        storage = None
        if hasattr(da, "storage"):
            storage = da.storage
        elif hasattr(da, "data_access") and hasattr(da.data_access, "storage"):
            storage = da.data_access.storage

        if storage is None:
            eprint("[TEST] No pude obtener cliente de Storage desde data_access")
        else:
            blob = storage.blob(storage_path)
            exists = False
            try:
                exists = blob.exists()
            except Exception as e:
                eprint("[TEST] blob.exists() error:", e)
            eprint("[TEST] blob.exists() ->", exists)
            if exists:
                # descargar a temp y mostrar tamaño
                tmpf = os.path.join(tempfile.gettempdir(), "test_pdf_download.pdf")
                try:
                    blob.download_to_filename(tmpf)
                    eprint("[TEST] blob descargado a", tmpf, "size=", os.path.getsize(tmpf))
                except Exception as e:
                    eprint("[TEST] Error descargando blob:", e)
    except Exception as e:
        eprint("[TEST] Error verificando Storage:", e)

    eprint("[TEST] FIN")