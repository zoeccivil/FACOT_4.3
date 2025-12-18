from __future__ import annotations
import os
import sys

# Asegurar import del paquete tools al ejecutar desde examples/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.emitidas_counter_tool import run_emitidas_counter_tool

if __name__ == "__main__":
    run_emitidas_counter_tool()