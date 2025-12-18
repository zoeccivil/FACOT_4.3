from __future__ import annotations
import os
import sys

# Asegurar import del paquete tools al ejecutar desde examples/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.compare_invoices_tool import run_compare_tool_with_dialog

def main():
    # Abre el diálogo para elegir DB y credenciales, y lanza el comparador
    run_compare_tool_with_dialog()

if __name__ == "__main__":
    main()