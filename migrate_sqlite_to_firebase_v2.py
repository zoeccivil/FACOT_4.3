#!/usr/bin/env python3
"""
Script de Migración SQLite → Firebase (Versión 2)
Migra COMPLETA y limpiamente desde facturas_db.db a Firestore.

Uso:
    # Primero hacer dry-run para ver qué se va a migrar
    python migrate_sqlite_to_firebase_v2.py --dry-run
    
    # Luego migrar de verdad (borra Firebase y migra limpio)
    python migrate_sqlite_to_firebase_v2.py
"""

import sqlite3
import argparse
import sys
from datetime import datetime
from pathlib import Path

# Agregar directorio actual al path
sys.path.insert(0, str(Path(__file__).parent))

def print_header(text):
    """Imprime un encabezado visual"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)

def print_step(text):
    """Imprime un paso de proceso"""
    print(f"\n📋 {text}...")

def print_success(text):
    """Imprime mensaje de éxito"""
    print(f"  ✓ {text}")

def print_error(text):
    """Imprime mensaje de error"""
    print(f"  ✗ {text}")

def clear_firebase_collections(db, dry_run=False):
    """Borra todas las colecciones de Firebase para empezar limpio"""
    print_step("LIMPIANDO Firebase (borrar datos existentes)")
    
    collections = ['companies', 'items', 'third_parties', 'invoices', 'quotations', 'categories']
    
    if dry_run:
        print_success(f"[DRY-RUN] Se borrarían {len(collections)} colecciones")
        return
    
    total_deleted = 0
    for collection_name in collections:
        try:
            # Obtener todos los documentos
            docs = db.collection(collection_name).stream()
            batch = db.batch()
            count = 0
            
            for doc in docs:
                # Borrar subcollections si existen
                if collection_name in ['invoices', 'quotations']:
                    subcol_ref = db.collection(collection_name).document(doc.id).collection('items')
                    for subdoc in subcol_ref.stream():
                        batch.delete(subdoc.reference)
                        count += 1
                
                # Borrar documento principal
                batch.delete(doc.reference)
                count += 1
                
                # Commit cada 500 operaciones (límite de Firestore)
                if count >= 450:
                    batch.commit()
                    batch = db.batch()
                    total_deleted += count
                    count = 0
            
            # Commit final
            if count > 0:
                batch.commit()
                total_deleted += count
            
            print_success(f"Colección '{collection_name}' limpiada")
            
        except Exception as e:
            print_error(f"Error limpiando '{collection_name}': {e}")
    
    print_success(f"Total de documentos borrados: {total_deleted}")

def migrate_companies(sqlite_conn, db, dry_run=False):
    """Migra companies de SQLite a Firestore"""
    print_step("Migrando COMPANIES (Empresas)")
    
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM companies")
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    
    if dry_run:
        print_success(f"[DRY-RUN] Se migrarían {len(rows)} companies")
        return 0
    
    count = 0
    errors = 0
    
    for row in rows:
        try:
            data = dict(zip(columns, row))
            company_id = str(data.get('id', count + 1))
            
            # Limpiar datos
            doc_data = {
                'name': data.get('name', ''),
                'rnc': data.get('rnc', ''),
                'address': data.get('address', ''),
                'phone': data.get('phone', ''),
                'email': data.get('email', ''),
                'created_at': datetime.now(),
                'updated_at': datetime.now(),
            }
            
            # Campos opcionales
            for field in ['logo_path', 'address_line1', 'address_line2', 'signature_name', 'authorized_name']:
                if field in data and data[field]:
                    doc_data[field] = data[field]
            
            db.collection('companies').document(company_id).set(doc_data)
            count += 1
            
        except Exception as e:
            print_error(f"Error en company {company_id}: {e}")
            errors += 1
    
    print_success(f"{count} companies migradas ({errors} errores)")
    return count

def migrate_items(sqlite_conn, db, dry_run=False):
    """Migra items (catálogo de productos) de SQLite a Firestore"""
    print_step("Migrando ITEMS (Catálogo de Productos)")
    
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM items")
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    
    if dry_run:
        print_success(f"[DRY-RUN] Se migrarían {len(rows)} items")
        return 0
    
    count = 0
    errors = 0
    
    for row in rows:
        try:
            data = dict(zip(columns, row))
            item_id = str(data.get('id', count + 1))
            
            doc_data = {
                'code': data.get('code', ''),
                'name': data.get('name', ''),
                'unit': data.get('unit', 'UND'),
                'cost': float(data.get('cost', 0) or 0),
                'price': float(data.get('price', 0) or 0),
                'category_id': data.get('category_id', ''),
                'created_at': datetime.now(),
                'updated_at': datetime.now(),
            }
            
            db.collection('items').document(item_id).set(doc_data)
            count += 1
            
        except Exception as e:
            print_error(f"Error en item {item_id}: {e}")
            errors += 1
    
    print_success(f"{count} items migrados ({errors} errores)")
    return count

def migrate_third_parties(sqlite_conn, db, dry_run=False):
    """Migra third_parties (proveedores/clientes) de SQLite a Firestore"""
    print_step("Migrando THIRD_PARTIES (Proveedores/Clientes)")
    
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM third_parties")
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    
    if dry_run:
        print_success(f"[DRY-RUN] Se migrarían {len(rows)} third_parties")
        return 0
    
    count = 0
    errors = 0
    
    for row in rows:
        try:
            data = dict(zip(columns, row))
            third_party_id = str(data.get('id', count + 1))
            
            doc_data = {
                'rnc': data.get('rnc', ''),
                'name': data.get('name', ''),
                'created_at': datetime.now(),
                'updated_at': datetime.now(),
            }
            
            db.collection('third_parties').document(third_party_id).set(doc_data)
            count += 1
            
        except Exception as e:
            print_error(f"Error en third_party {third_party_id}: {e}")
            errors += 1
    
    print_success(f"{count} third_parties migrados ({errors} errores)")
    return count

def migrate_categories(sqlite_conn, db, dry_run=False):
    """Migra categories de SQLite a Firestore"""
    print_step("Migrando CATEGORIES (Categorías)")
    
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM categories")
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    
    if dry_run:
        print_success(f"[DRY-RUN] Se migrarían {len(rows)} categories")
        return 0
    
    count = 0
    errors = 0
    
    for row in rows:
        try:
            data = dict(zip(columns, row))
            category_id = str(data.get('id', count + 1))
            
            doc_data = {
                'name': data.get('name', ''),
                'code_prefix': data.get('code_prefix', ''),
                'next_seq': int(data.get('next_seq', 1) or 1),
                'created_at': datetime.now(),
                'updated_at': datetime.now(),
            }
            
            db.collection('categories').document(category_id).set(doc_data)
            count += 1
            
        except Exception as e:
            print_error(f"Error en category {category_id}: {e}")
            errors += 1
    
    print_success(f"{count} categories migradas ({errors} errores)")
    return count

def migrate_invoices(sqlite_conn, db, dry_run=False):
    """Migra invoices y sus items de SQLite a Firestore (compatible con FACTURAS-PyQT6)"""
    print_step("Migrando INVOICES (Facturas con Items)")
    
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM invoices")
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    
    if dry_run:
        print_success(f"[DRY-RUN] Se migrarían {len(rows)} invoices")
        return 0
    
    count = 0
    errors = 0
    total_items = 0
    
    for row in rows:
        try:
            data = dict(zip(columns, row))
            invoice_id = str(data.get('id', count + 1))
            company_id = str(data.get('company_id', '1'))
            
            # Documento principal de invoice (compatible con FACTURAS-PyQT6-GIT)
            doc_data = {
                'company_id': company_id,
                'invoice_type': data.get('invoice_type', 'emitida'),  # CRÍTICO: emitida/gasto
                'invoice_date': data.get('invoice_date', ''),
                'imputation_date': data.get('imputation_date') or data.get('invoice_date', ''),  # Fecha de imputación
                'invoice_number': data.get('invoice_number', ''),
                'invoice_category': data.get('invoice_category', ''),  # Categoría de factura
                'rnc': data.get('rnc', ''),
                'third_party_name': data.get('third_party_name') or data.get('client_name', ''),  # Compatibilidad
                'currency': data.get('currency', 'RD$'),
                'itbis': float(data.get('itbis', 0) or data.get('tax_amount', 0) or 0),
                'total_amount': float(data.get('total_amount', 0) or 0),
                'exchange_rate': float(data.get('exchange_rate', 1.0) or 1.0),
                'total_amount_rd': float(data.get('total_amount_rd') if data.get('total_amount_rd') is not None else (data.get('total_amount', 0) or 0)),
                'attachment_path': data.get('attachment_path'),
                'created_at': datetime.now(),
                'updated_at': datetime.now(),
            }
            
            # Campos opcionales adicionales
            for field in ['due_date', 'subtotal', 'discount', 'notes', 'ncf']:
                if field in data and data[field]:
                    doc_data[field] = data[field]
            
            db.collection('invoices').document(invoice_id).set(doc_data)
            
            # Migrar items de la factura (subcollection)
            cursor.execute("SELECT * FROM invoice_items WHERE invoice_id = ?", (data['id'],))
            item_rows = cursor.fetchall()
            item_columns = [desc[0] for desc in cursor.description]
            
            items_count = 0
            for item_row in item_rows:
                item_data = dict(zip(item_columns, item_row))
                item_doc_data = {
                    'description': item_data.get('description', ''),
                    'quantity': float(item_data.get('quantity', 0) or 0),
                    'unit_price': float(item_data.get('unit_price', 0) or 0),
                    'item_code': item_data.get('item_code', ''),
                    'unit': item_data.get('unit', 'UND'),
                }
                
                # Agregar a subcollection
                db.collection('invoices').document(invoice_id).collection('items').add(item_doc_data)
                items_count += 1
                total_items += 1
            
            if items_count > 0:
                print(f"    ... Factura {invoice_id}: {items_count} items")
            
            count += 1
            
        except Exception as e:
            print_error(f"Error en invoice {invoice_id}: {e}")
            errors += 1
    
    print_success(f"{count} invoices migradas con {total_items} items totales ({errors} errores)")
    return count

def migrate_quotations(sqlite_conn, db, dry_run=False):
    """Migra quotations y sus items de SQLite a Firestore"""
    print_step("Migrando QUOTATIONS (Cotizaciones con Items)")
    
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT * FROM quotations")
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    
    if dry_run:
        print_success(f"[DRY-RUN] Se migrarían {len(rows)} quotations")
        return 0
    
    count = 0
    errors = 0
    total_items = 0
    
    for row in rows:
        try:
            data = dict(zip(columns, row))
            quotation_id = str(data.get('id', count + 1))
            company_id = str(data.get('company_id', '1'))
            
            # Documento principal de quotation
            doc_data = {
                'company_id': company_id,
                'quotation_number': data.get('quotation_number', ''),
                'quotation_date': data.get('quotation_date', ''),
                'client_name': data.get('client_name', ''),
                'client_rnc': data.get('client_rnc', ''),
                'total_amount': float(data.get('total_amount', 0) or 0),
                'status': data.get('status', 'draft'),
                'created_at': datetime.now(),
                'updated_at': datetime.now(),
            }
            
            # Campos opcionales
            for field in ['due_date', 'subtotal', 'tax_amount', 'discount', 'notes', 'valid_until']:
                if field in data and data[field]:
                    doc_data[field] = data[field]
            
            db.collection('quotations').document(quotation_id).set(doc_data)
            
            # Migrar items de la cotización (subcollection)
            cursor.execute("SELECT * FROM quotation_items WHERE quotation_id = ?", (data['id'],))
            item_rows = cursor.fetchall()
            item_columns = [desc[0] for desc in cursor.description]
            
            items_count = 0
            for item_row in item_rows:
                item_data = dict(zip(item_columns, item_row))
                item_doc_data = {
                    'description': item_data.get('description', ''),
                    'quantity': float(item_data.get('quantity', 0) or 0),
                    'unit_price': float(item_data.get('unit_price', 0) or 0),
                    'item_code': item_data.get('item_code', ''),
                    'unit': item_data.get('unit', 'UND'),
                }
                
                # Agregar a subcollection
                db.collection('quotations').document(quotation_id).collection('items').add(item_doc_data)
                items_count += 1
                total_items += 1
            
            if items_count > 0:
                print(f"    ... Cotización {quotation_id}: {items_count} items")
            
            count += 1
            
        except Exception as e:
            print_error(f"Error en quotation {quotation_id}: {e}")
            errors += 1
    
    print_success(f"{count} quotations migradas con {total_items} items totales ({errors} errores)")
    return count

def main():
    parser = argparse.ArgumentParser(description='Migrar SQLite a Firebase (Versión 2)')
    parser.add_argument('--db', default='data/facturas_db.db', help='Ruta a la base de datos SQLite')
    parser.add_argument('--dry-run', action='store_true', help='Solo mostrar qué se haría sin hacer cambios')
    args = parser.parse_args()
    
    print_header("MIGRACIÓN SQLite → Firebase (Versión 2)")
    
    if args.dry_run:
        print("⚠️  MODO DRY-RUN: No se harán cambios reales")
    else:
        print("⚠️  MODO REAL: Se borrarán datos de Firebase y se migrarán desde SQLite")
        response = input("\n¿Continuar? (si/no): ")
        if response.lower() not in ['si', 's', 'yes', 'y']:
            print("Migración cancelada.")
            return
    
    # Conectar a SQLite
    db_path = Path(args.db)
    if not db_path.exists():
        print_error(f"Base de datos no encontrada: {db_path}")
        return
    
    print_step(f"Conectando a SQLite: {db_path}")
    sqlite_conn = sqlite3.connect(str(db_path))
    print_success("Conectado a SQLite")
    
    # Conectar a Firebase
    print_step("Conectando a Firebase")
    try:
        from firebase import get_firebase_client
        firebase_client = get_firebase_client()
        
        if not firebase_client.is_available():
            print_error("Firebase no está disponible. Verificar credenciales.")
            return
        
        db = firebase_client.get_firestore()
        print_success("Conectado a Firebase")
        
    except Exception as e:
        print_error(f"Error conectando a Firebase: {e}")
        return
    
    # Iniciar migración
    stats = {}
    
    # 1. Limpiar Firebase
    if not args.dry_run:
        clear_firebase_collections(db, dry_run=args.dry_run)
    
    # 2. Migrar companies
    stats['companies'] = migrate_companies(sqlite_conn, db, dry_run=args.dry_run)
    
    # 3. Migrar items (catálogo)
    stats['items'] = migrate_items(sqlite_conn, db, dry_run=args.dry_run)
    
    # 4. Migrar third_parties
    stats['third_parties'] = migrate_third_parties(sqlite_conn, db, dry_run=args.dry_run)
    
    # 5. Migrar categories
    stats['categories'] = migrate_categories(sqlite_conn, db, dry_run=args.dry_run)
    
    # 6. Migrar invoices con items
    stats['invoices'] = migrate_invoices(sqlite_conn, db, dry_run=args.dry_run)
    
    # 7. Migrar quotations con items
    stats['quotations'] = migrate_quotations(sqlite_conn, db, dry_run=args.dry_run)
    
    # Cerrar conexión SQLite
    sqlite_conn.close()
    
    # Mostrar resumen
    print_header("RESUMEN DE MIGRACIÓN")
    for key, value in stats.items():
        print(f"  {key.capitalize():15} {value:5} migrados")
    
    if args.dry_run:
        print("\n⚠️  Esto fue un DRY-RUN. No se hicieron cambios reales.")
        print("   Para migrar de verdad, ejecuta sin --dry-run")
    else:
        print("\n✅ MIGRACIÓN COMPLETADA")
        print("   Verificar en Firebase Console que los datos están correctos.")

if __name__ == '__main__':
    main()
