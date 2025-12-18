from __future__ import annotations

"""
Auditor de SQLite (DB Browser compatible):
- Lista todas las tablas de la base de datos.
- Detecta cuáles tienen columnas 'company_id' e 'invoice_type'.
- Para cada tabla compatible, cuenta registros por company_id con invoice_type='EMITIDA'.
- Muestra un resumen por tabla y un consolidado total por company_id.

Uso:
- Ejecuta este script con Python.
- Selecciona la base de datos SQLite mediante el diálogo.
"""

import os
import sys
import sqlite3
from typing import Dict, List, Tuple

from PyQt6.QtWidgets import QApplication, QFileDialog

def pick_sqlite_db() -> str:
    app = QApplication.instance() or QApplication(sys.argv)
    fn, _ = QFileDialog.getOpenFileName(
        None,
        "Seleccionar base de datos SQLite",
        "",
        "SQLite (*.db *.sqlite *.sqlite3);;Todos (*.*)"
    )
    if not fn:
        print("[SQL] No se seleccionó base de datos.")
        sys.exit(0)
    return fn

def list_tables(conn: sqlite3.Connection) -> List[str]:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    return [r[0] for r in cur.fetchall()]

def get_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info('{table}')")
    cols = [row[1] for row in cur.fetchall()]
    return cols

def count_emitidas_grouped(conn: sqlite3.Connection, table: str) -> Dict[str, int]:
    """
    Cuenta por company_id las filas con invoice_type='EMITIDA' (case-insensitive).
    Requiere columnas company_id e invoice_type.
    """
    out: Dict[str, int] = {}
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT company_id, COUNT(*) FROM '{table}' WHERE UPPER(invoice_type)='EMITIDA' GROUP BY company_id;"
        )
        rows = cur.fetchall()
        for cid, cnt in rows:
            out[str(cid)] = int(cnt or 0)
    except Exception as e:
        print(f"[SQL] Error contando en tabla '{table}': {e}")
    return out

def main():
    db_path = pick_sqlite_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    print(f"[SQL] DB: {db_path}")
    tables = list_tables(conn)
    print(f"[SQL] Tablas encontradas ({len(tables)}): {tables}")

    summary_by_table: Dict[str, Dict[str, int]] = {}
    consolidated: Dict[str, int] = {}

    for t in tables:
        cols = get_columns(conn, t)
        has_company = "company_id" in [c.lower() for c in cols]
        has_type = "invoice_type" in [c.lower() for c in cols]
        if not (has_company and has_type):
            print(f"[SQL] Saltando '{t}': no tiene company_id y/o invoice_type")
            continue

        counts = count_emitidas_grouped(conn, t)
        summary_by_table[t] = counts

        # Consolidado
        for cid, cnt in counts.items():
            consolidated[cid] = consolidated.get(cid, 0) + cnt

    print("\n[SQL] Resumen por tabla (company_id -> count EMITIDA):")
    for t, counts in summary_by_table.items():
        if not counts:
            print(f"  - {t}: (sin registros EMITIDA)")
            continue
        print(f"  - {t}:")
        for cid, cnt in counts.items():
            print(f"      {cid}: {cnt}")

    print("\n[SQL] Consolidado por company_id (sumando todas las tablas compatibles):")
    if not consolidated:
        print("  (sin registros EMITIDA en tablas compatibles)")
    else:
        for cid, total in consolidated.items():
            print(f"  {cid}: {total}")

    conn.close()

if __name__ == "__main__":
    main()