from __future__ import annotations
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from collections import defaultdict

try:
    import openpyxl
except Exception:
    openpyxl = None  # requerido para export_excel

class ReportingService:
    def __init__(self, data_access):
        self.data_access = data_access

    # ------------ utilidades internas ------------

    def _parse_date(self, value) -> Optional[date]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        s = str(value).strip()
        for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"]:
            try:
                return datetime.strptime(s[:10], fmt).date()
            except ValueError:
                continue
        return None

    def _amount(self, inv: dict) -> float:
        # Prioridad: total_amount -> total_amount_rd -> total
        try:
            return float(
                inv.get("total_amount",
                    inv.get("total_amount_rd",
                        inv.get("total", 0.0)
                    )
                ) or 0.0
            )
        except Exception:
            return 0.0

    def _amount_rd(self, inv: dict) -> float:
        try:
            if inv.get("total_amount_rd") not in (None, ""):
                return float(inv.get("total_amount_rd") or 0.0)
            amt = float(inv.get("total_amount") or 0.0)
            exr = float(inv.get("exchange_rate") or 1.0)
            return round(amt * exr, 2)
        except Exception:
            return 0.0

    def _get_invoices_in_period(
        self,
        start_date: date,
        end_date: date,
        company_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtiene todas las facturas para el rango y empresa (si se pasa).
        """
        invoices = []
        try:
            if hasattr(self.data_access, "get_invoices"):
                invoices = self.data_access.get_invoices(company_id=company_id, limit=50000)  # sin paginar, alto límite
            elif hasattr(self.data_access, "get_facturas"):
                invoices = self.data_access.get_facturas(company_id)
        except Exception:
            invoices = []

        out = []
        for inv in invoices or []:
            inv_date = self._parse_date(inv.get("invoice_date") or inv.get("date") or None)
            if not inv_date:
                continue
            if start_date <= inv_date <= end_date:
                out.append(inv)
        return out

    # ------------ reportes públicos ------------

    def sales_by_period(
        self,
        start_date: date,
        end_date: date,
        company_id: Optional[int] = None,
        group_by: str = "month",  # usamos mes por defecto
    ) -> List[Dict[str, Any]]:
        """
        Agrupa ventas por mes (YYYY-MM). Devuelve por fila:
        - key: 'YYYY-MM'
        - count_invoices
        - totals_by_currency: dict{currency: suma}
        - total_rd: suma en RD$
        - first_date / last_date
        """
        invoices = self._get_invoices_in_period(start_date, end_date, company_id)
        if not invoices:
            return []

        groups = defaultdict(lambda: {
            "count_invoices": 0,
            "totals_by_currency": defaultdict(float),
            "total_rd": 0.0,
            "dates": []
        })

        for inv in invoices:
            inv_date = self._parse_date(inv.get("invoice_date") or inv.get("date") or None)
            key = inv_date.strftime("%Y-%m") if inv_date else "unknown"

            currency = (inv.get("currency") or "RD$").strip()
            amt = self._amount(inv)
            amt_rd = self._amount_rd(inv)

            g = groups[key]
            g["count_invoices"] += 1
            g["totals_by_currency"][currency] += amt
            g["total_rd"] += amt_rd
            if inv_date:
                g["dates"].append(inv_date)

        results = []
        for key, data in groups.items():
            dates = data["dates"]
            count = data["count_invoices"]
            total_rd = data["total_rd"]
            # Promedio en RD$ (referencia)
            avg_rd = round(total_rd / count, 2) if count else 0.0
            results.append({
                "key": key,
                "count_invoices": count,
                "totals_by_currency": {k: round(v, 2) for k, v in data["totals_by_currency"].items()},
                "total_rd": round(total_rd, 2),
                "avg_rd": avg_rd,
                "first_date": min(dates).isoformat() if dates else None,
                "last_date": max(dates).isoformat() if dates else None,
            })

        results.sort(key=lambda x: x["key"])
        return results

    def clients_by_period(
        self,
        start_date: date,
        end_date: date,
        company_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Agrupa por cliente. Devuelve por fila:
        - client_id (RNC/ID)
        - client_name
        - invoices_count
        - totals_by_currency
        - total_rd
        - last_invoice_date
        """
        invoices = self._get_invoices_in_period(start_date, end_date, company_id)
        if not invoices:
            return []

        clients = defaultdict(lambda: {
            "client_name": "",
            "invoices_count": 0,
            "totals_by_currency": defaultdict(float),
            "total_rd": 0.0,
            "dates": []
        })

        for inv in invoices:
            client_id = (
                inv.get("client_rnc")
                or inv.get("rnc")
                or inv.get("third_party_rnc")
                or inv.get("client_name")
                or inv.get("third_party_name")
                or "Sin Cliente"
            )
            client_name = (
                inv.get("client_name")
                or inv.get("third_party_name")
                or client_id
            )
            inv_date = self._parse_date(inv.get("invoice_date") or inv.get("date") or None)
            currency = (inv.get("currency") or "RD$").strip()
            amt = self._amount(inv)
            amt_rd = self._amount_rd(inv)

            c = clients[client_id]
            c["client_name"] = client_name
            c["invoices_count"] += 1
            c["totals_by_currency"][currency] += amt
            c["total_rd"] += amt_rd
            if inv_date:
                c["dates"].append(inv_date)

        results = []
        for cid, data in clients.items():
            dates = data["dates"]
            results.append({
                "client_id": cid,
                "client_name": data["client_name"],
                "invoices_count": data["invoices_count"],
                "totals_by_currency": {k: round(v, 2) for k, v in data["totals_by_currency"].items()},
                "total_rd": round(data["total_rd"], 2),
                "last_invoice_date": max(dates).isoformat() if dates else None,
            })

        # orden por total_rd desc
        results.sort(key=lambda x: x["total_rd"], reverse=True)
        return results

    # ------------ exportar Excel (simple, por dict) ------------

    def export_excel(self, rows: List[Dict[str, Any]], headers: List[str], file_path: str) -> bool:
        if not openpyxl:
            print("[EXPORT-EXCEL] openpyxl no está instalado.")
            return False
        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(headers)
            for r in rows:
                ws.append([r.get(h, "") for h in headers])
            wb.save(file_path)
            return True
        except Exception as e:
            print(f"[EXPORT-EXCEL] Error: {e}")
            return False

    # ------------ hook para PDF (implementa tu generador aquí) ------------

    def export_pdf(self, rows: List[Dict[str, Any]], title: str, file_path: str) -> bool:
        """
        Hook: implementa tu generador de PDF aquí.
        """
        print("[EXPORT-PDF] Implementa el generador de PDF según tu layout.")
        return False