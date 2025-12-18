from __future__ import annotations
import os
import sys

# Asegura import de tools al ejecutar desde examples/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.sql_to_firestore_migrator import run_sql_to_firestore_migrator

if __name__ == "__main__":
    run_sql_to_firestore_migrator()