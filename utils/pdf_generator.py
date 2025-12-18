#!/usr/bin/env python3
"""
utils/pdf_generator.py

Generador de PDF (LETTER) usando ReportLab que replica el diseño React/Tailwind,
con los siguientes ajustes:

- Encabezado de UNA sola banda:
    [ LOGO (izquierda, tamaño fijo, sin nombre de empresa) | TÍTULO "COTIZACIÓN"/"FACTURA" alineado derecha ]
- Debajo del encabezado:
    - Columna izquierda: datos de la empresa (dirección, RNC, teléfono, correo) alineados a la izquierda.
    - Columna derecha: bloque de meta (NÚMERO, NCF opcional, FECHA, VENCE) alineado a la derecha.
- Cuerpo (cliente + tabla de items) se mantiene como antes.
- Bloque TOTAL A PAGAR con fuente más pequeña y suficiente ancho para números grandes.
- Tipografía base uniforme: Helvetica en todo el documento (solo negrita, sin Courier).
"""

from __future__ import annotations

import os
from typing import Dict, Any, List, Optional
from datetime import datetime

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate,
        Table,
        TableStyle,
        Paragraph,
        Spacer,
        Image,
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
except Exception as e:
    raise ImportError("reportlab is required. Install it with: pip install reportlab") from e


# --------------------------------------------------------------------- helpers
def _to_local_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    s = str(path)
    if s.startswith("file:///"):
        return s.replace("file:///", "")
    if s.startswith("file://"):
        return s.replace("file://", "")
    return s


def _fmt_date(date_str: Optional[str]) -> str:
    if not date_str:
        return ""
    s = str(date_str).strip()
    if not s:
        return ""
    try:
        d = datetime.strptime(s.split("T")[0], "%Y-%m-%d")
        return d.strftime("%d/%m/%Y")
    except Exception:
        return s


# ------------------------------------------------------------------ generator
class PDFGenerator:
    """
    Interfaz usada por los diálogos:

        gen = PDFGenerator(primary_color="#1f4e79")
        gen.generate_pdf(payload, dest_path)

    payload:
        COMPANY, TEMPLATE, INVOICE o QUOTATION
    """

    def __init__(self, primary_color: str = "#1f4e79", secondary_color: str = "#F5F5F5"):
        self.primary_color = colors.HexColor(primary_color)
        self.secondary_color = colors.HexColor(secondary_color)

        # Paleta aproximada Tailwind
        self.text_color = colors.HexColor("#334155")   # slate-700
        self.gray_50 = colors.HexColor("#f8fafc")
        self.gray_100 = colors.HexColor("#e5e7eb")
        self.gray_200 = colors.HexColor("#e2e8f0")
        self.gray_300 = colors.HexColor("#cbd5e1")
        self.gray_400 = colors.HexColor("#94a3b8")
        self.gray_600 = colors.HexColor("#4b5563")

        self.styles = getSampleStyleSheet()
        self._build_styles()
        self.company_website: str = ""

        # Tamaño máximo de logo en la banda de encabezado
        self.logo_max_width_mm = 40.0
        self.logo_max_height_mm = 18.0

    # ------------------------------------------------------------ styles
    def _build_styles(self):
        # Estilo base único (Helvetica) para todo el documento
        self.st_base = ParagraphStyle(
            "inv_base",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=self.text_color,
        )

        self.st_doc_type = ParagraphStyle(
            "inv_doc_type",
            parent=self.st_base,
            fontName="Helvetica-Bold",
            fontSize=20,
            textColor=self.primary_color,
            alignment=TA_RIGHT,
        )

        self.st_company_info = ParagraphStyle(
            "inv_company_info",
            parent=self.st_base,
            fontSize=8,
            textColor=self.text_color,
        )

        self.st_header_label = ParagraphStyle(
            "inv_header_label",
            parent=self.st_base,
            fontSize=8,
            textColor=self.gray_600,
        )

        self.st_meta_label = ParagraphStyle(
            "inv_meta_label",
            parent=self.st_base,
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=self.gray_600,
            alignment=TA_LEFT,
        )

        self.st_meta_value = ParagraphStyle(
            "inv_meta_value",
            parent=self.st_base,
            fontSize=9,
            textColor=colors.black,
            alignment=TA_RIGHT,
        )

        self.st_table_header = ParagraphStyle(
            "inv_table_header",
            parent=self.st_base,
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=colors.white,
            alignment=TA_CENTER,
        )

        self.st_table_desc = ParagraphStyle(
            "inv_table_desc",
            parent=self.st_base,
            fontSize=9,
        )

        self.st_table_code = ParagraphStyle(
            "inv_table_code",
            parent=self.st_base,
            fontSize=7,
            textColor=self.gray_400,
        )

        self.st_table_qty = ParagraphStyle(
            "inv_table_qty",
            parent=self.st_base,
            fontSize=9,
            alignment=TA_CENTER,
        )

        self.st_table_unit = ParagraphStyle(
            "inv_table_unit",
            parent=self.st_base,
            fontSize=8,
            textColor=self.gray_400,
            alignment=TA_CENTER,
        )

        self.st_table_price = ParagraphStyle(
            "inv_table_price",
            parent=self.st_base,
            fontSize=9,
            alignment=TA_RIGHT,
        )

        self.st_table_amount = ParagraphStyle(
            "inv_table_amount",
            parent=self.st_base,
            fontSize=9,
            fontName="Helvetica-Bold",
            alignment=TA_RIGHT,
        )

        self.st_notes_title = ParagraphStyle(
            "inv_notes_title",
            parent=self.st_base,
            fontSize=8,
            textColor=self.gray_600,
        )

        self.st_notes_text = ParagraphStyle(
            "inv_notes_text",
            parent=self.st_base,
            fontSize=8,
            textColor=self.gray_600,
        )

        self.st_sign = ParagraphStyle(
            "inv_sign",
            parent=self.st_base,
            fontSize=8,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
            textColor=self.gray_600,
        )

        self.st_tot_label = ParagraphStyle(
            "inv_tot_label",
            parent=self.st_base,
            fontSize=9,
            textColor=self.gray_600,
        )

        self.st_tot_value = ParagraphStyle(
            "inv_tot_value",
            parent=self.st_base,
            fontSize=9,
            alignment=TA_RIGHT,
        )

        # TOTAL A PAGAR → fuente algo más pequeña para aceptar montos grandes
        self.st_tot_main_label = ParagraphStyle(
            "inv_tot_main_label",
            parent=self.st_base,
            fontSize=9,
            textColor=colors.white,
            fontName="Helvetica-Bold",
        )

        self.st_tot_main_value = ParagraphStyle(
            "inv_tot_main_value",
            parent=self.st_base,
            fontSize=12,  # antes 14 → más espacio para números
            textColor=colors.white,
            fontName="Helvetica-Bold",
            alignment=TA_RIGHT,
        )

    # ------------------------------------------------------------ footer
    def _on_page_footer(self, canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(self.gray_400)
        text = "Documento generado electrónicamente."
        if self.company_website:
            text += f" Visítenos en {self.company_website}"
        canvas.drawCentredString(LETTER[0] / 2.0, 10 * mm, text)
        canvas.restoreState()

    # ------------------------------------------------------------ main
    def generate_pdf(self, payload: Dict[str, Any], dest_path: str) -> str:
        if not dest_path:
            raise ValueError("dest_path is required")

        # Normalizar payload
        company = payload.get("COMPANY") or payload.get("company") or {}
        template = payload.get("TEMPLATE") or payload.get("template") or {}
        doc_data = (
            payload.get("INVOICE")
            or payload.get("invoice")
            or payload.get("QUOTATION")
            or payload.get("quotation")
            or {}
        )
        items = doc_data.get("items") or doc_data.get("_items") or []
        currency = doc_data.get("currency", "RD$")

        # Color primario desde plantilla/empresa
        hex_color = template.get("primary_color") or company.get("primary_color") or "#1f4e79"
        try:
            self.primary_color = colors.HexColor(hex_color)
        except Exception:
            self.primary_color = colors.HexColor("#1f4e79")
        self._build_styles()  # refrescar estilos con el nuevo color

        self.company_website = company.get("website") or company.get("web") or ""

        doc = SimpleDocTemplate(
            dest_path,
            pagesize=LETTER,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=15 * mm,
            bottomMargin=20 * mm,
        )

        story: List[Any] = []

        # ==================== ENCABEZADO (banda única) ======================
        # Logo (SIEMPRE logo; no mostramos nombre de empresa aquí)
        logo_path = company.get("logo_path") or template.get("logo_path")
        local_logo = _to_local_path(logo_path) if logo_path else None
        logo_img = None
        if local_logo and os.path.exists(local_logo):
            try:
                logo_img = Image(local_logo)
                max_w = self.logo_max_width_mm * mm
                max_h = self.logo_max_height_mm * mm
                iw, ih = logo_img.drawWidth, logo_img.drawHeight
                if iw and ih:
                    scale = min(max_w / iw, max_h / ih, 1.0)
                    logo_img.drawWidth = iw * scale
                    logo_img.drawHeight = ih * scale
                else:
                    logo_img.drawWidth = max_w
                    logo_img.drawHeight = max_h
                logo_img.hAlign = "LEFT"
            except Exception:
                logo_img = None

        if not logo_img:
            # Bloque vacío para reservar espacio de encabezado
            logo_img = Table([[""]], colWidths=[self.logo_max_width_mm * mm], rowHeights=[self.logo_max_height_mm * mm])

        doc_type = doc_data.get("type") or (
            "COTIZACIÓN" if ("QUOTATION" in payload or payload.get("quotation")) else "FACTURA"
        )
        doc_type = str(doc_type).upper()

        header_band = Table(
            [[logo_img, Paragraph(doc_type, self.st_doc_type)]],
            colWidths=[50 * mm, 130 * mm],
        )
        header_band.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ]
            )
        )
        story.append(header_band)
        story.append(Spacer(1, 4 * mm))

        # ==================== BLOQUE EMPRESA + META =========================
        # Izquierda: datos empresa alineados a la izquierda
        company_flow: List[Any] = []

        addr = company.get("address") or company.get("address_line1")
        rnc = company.get("rnc") or company.get("rnc_number")
        phone = company.get("phone") or company.get("telefono")
        email = company.get("email") or company.get("correo")

        if rnc:
            company_flow.append(
                Paragraph(
                    f"<b>RNC:</b> {rnc}",
                    self.st_company_info,
                )
            )
        if addr:
            company_flow.append(Paragraph(addr, self.st_company_info))
        if phone:
            company_flow.append(Paragraph(f"Tel: {phone}", self.st_company_info))
        if email:
            company_flow.append(Paragraph(email, self.st_company_info))

        left_company_tbl = Table([[c] for c in company_flow] or [[""]], colWidths=[90 * mm])
        left_company_tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

        # Derecha: meta alineada a la derecha
        meta_rows: List[List[Any]] = []

        def add_meta(label: str, value: Optional[str], color=colors.black):
            if not value:
                return
            mv = ParagraphStyle("meta_val_tmp", parent=self.st_meta_value, textColor=color)
            meta_rows.append([Paragraph(label, self.st_meta_label), Paragraph(str(value), mv)])

        display_number = (
            doc_data.get("display_number")
            or doc_data.get("number")
            or doc_data.get("quotation_number")
            or doc_data.get("_id")
            or "---"
        )
        add_meta("NÚMERO:", display_number)
        add_meta("NCF:", doc_data.get("ncf"))
        add_meta("FECHA:", _fmt_date(doc_data.get("date") or doc_data.get("invoice_date") or doc_data.get("quotation_date")))
        add_meta("VENCE:", _fmt_date(doc_data.get("due_date")), colors.red)

        if not meta_rows:
            meta_rows = [[Paragraph("", self.st_meta_label), Paragraph("", self.st_meta_value)]]

        meta_tbl = Table(meta_rows, colWidths=[25 * mm, 35 * mm])
        meta_tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), self.gray_50),
                    ("LINEBEFORE", (0, 0), (0, -1), 4, self.primary_color),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )

        header_body = Table([[left_company_tbl, meta_tbl]], colWidths=[100 * mm, 80 * mm])
        header_body.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ]
            )
        )
        story.append(header_body)
        story.append(Spacer(1, 5 * mm))

        # Línea separadora
        sep = Table([[""]], colWidths=[180 * mm], rowHeights=[1.1 * mm])
        sep.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), self.primary_color)]))
        story.append(sep)
        story.append(Spacer(1, 6 * mm))

        # ==================== CLIENTE =======================================
        story.append(Paragraph("FACTURAR A", self.st_header_label))
        story.append(Spacer(1, 2))

        client_name = (
            doc_data.get("client_name")
            or doc_data.get("third_party_name")
            or "Cliente Mostrador"
        )
        client_rnc = doc_data.get("client_rnc") or doc_data.get("rnc")
        client_addr = doc_data.get("client_address")

        story.append(
            Paragraph(
                f"<b>{client_name}</b>",
                ParagraphStyle("inv_client_name", parent=self.st_base, fontSize=12),
            )
        )
        if client_rnc:
            story.append(Paragraph(f"RNC/Cédula: {client_rnc}", self.st_base))
        if client_addr:
            story.append(Paragraph(client_addr, self.st_base))

        story.append(Spacer(1, 8 * mm))

        # ==================== TABLA ITEMS ===================================
        table_data: List[List[Any]] = [
            [
                Paragraph("Descripción", ParagraphStyle("th_desc", parent=self.st_table_header, alignment=TA_LEFT)),
                Paragraph("Cant.", self.st_table_header),
                Paragraph("Unidad", self.st_table_header),
                Paragraph("Precio", ParagraphStyle("th_price", parent=self.st_table_header, alignment=TA_RIGHT)),
                Paragraph("Importe", ParagraphStyle("th_imp", parent=self.st_table_header, alignment=TA_RIGHT)),
            ]
        ]

        subtotal = 0.0

        for it in items:
            qty = float(it.get("quantity", 0) or 0)
            price = float(it.get("unit_price", it.get("price", 0)) or 0)
            line_total = qty * price
            subtotal += line_total

            desc_list: List[Any] = []
            code = it.get("code")
            if code:
                desc_list.append(Paragraph(str(code), self.st_table_code))
            desc = it.get("description") or it.get("name") or ""
            desc_list.append(Paragraph(desc, self.st_table_desc))

            desc_flow = Table([[d] for d in desc_list], colWidths=[85 * mm])
            desc_flow.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

            row = [
                desc_flow,
                Paragraph(f"{qty:g}", self.st_table_qty),
                Paragraph((it.get("unit") or "u").upper(), self.st_table_unit),
                Paragraph(f"{price:,.2f}", self.st_table_price),
                Paragraph(f"{line_total:,.2f}", self.st_table_amount),
            ]
            table_data.append(row)

        if not items:
            table_data.append(
                [Paragraph("No hay items registrados", self.st_base), "", "", "", ""]
            )

        col_widths = [85 * mm, 20 * mm, 20 * mm, 25 * mm, 30 * mm]
        t_items = Table(table_data, colWidths=col_widths, repeatRows=1)

        t_style: List[Any] = [
            ("BACKGROUND", (0, 0), (-1, 0), self.primary_color),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, self.gray_100),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]
        for i in range(1, len(table_data)):
            if i % 2 == 0:
                t_style.append(("BACKGROUND", (0, i), (-1, i), self.gray_50))

        t_items.setStyle(TableStyle(t_style))
        story.append(t_items)
        story.append(Spacer(1, 8 * mm))

        # ==================== TOTALES + NOTAS ===============================
        itbis_rate = float(template.get("itbis_rate", 0.18))
        apply_itbis = bool(doc_data.get("apply_itbis", True))
        itbis_amount = subtotal * itbis_rate if apply_itbis else 0.0
        total = subtotal + itbis_amount

        # Notas / Firma
        notes_flow: List[Any] = []
        notes_flow.append(Paragraph("Notas / Términos", self.st_notes_title))
        notes_flow.append(Spacer(1, 2))
        note_text = doc_data.get(
            "notes",
            "El pago debe realizarse dentro de los días estipulados.\nPrecios sujetos a cambio sin previo aviso si es una cotización.",
        ).replace("\n", "<br/>")
        note_box = Table(
            [[Paragraph(note_text, self.st_notes_text)]],
            colWidths=[90 * mm],
        )
        note_box.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, self.gray_200),
                    ("BACKGROUND", (0, 0), (-1, -1), self.gray_50),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        notes_flow.append(note_box)
        notes_flow.append(Spacer(1, 16 * mm))

        auth_name = (
            company.get("authorized_name")
            or company.get("signature_name")
            or "Firma Autorizada"
        )
        sign_tbl = Table([[Paragraph(auth_name, self.st_sign)]], colWidths=[60 * mm])
        sign_tbl.setStyle(
            TableStyle(
                [
                    ("LINEABOVE", (0, 0), (-1, -1), 1, self.gray_300),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        sign_wrap = Table([[sign_tbl]], colWidths=[90 * mm])
        sign_wrap.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        notes_flow.append(sign_wrap)

        # Totales
        totals_data: List[List[Any]] = []
        totals_data.append(
            [
                Paragraph("Subtotal", self.st_tot_label),
                Paragraph(f"{currency} {subtotal:,.2f}", self.st_tot_value),
            ]
        )
        if apply_itbis:
            totals_data.append(
                [
                    Paragraph(f"ITBIS ({itbis_rate*100:.0f}%)", self.st_tot_label),
                    Paragraph(f"{currency} {itbis_amount:,.2f}", self.st_tot_value),
                ]
            )
        totals_data.append(["", ""])
        totals_data.append(
            [
                Paragraph("TOTAL A PAGAR", self.st_tot_main_label),
                Paragraph(f"{currency} {total:,.2f}", self.st_tot_main_value),
            ]
        )

        t_totals = Table(totals_data, colWidths=[40 * mm, 45 * mm])
        t_totals.setStyle(
            TableStyle(
                [
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LINEBELOW", (0, -2), (-1, -2), 0.5, self.gray_300),
                    ("BACKGROUND", (0, -1), (-1, -1), self.primary_color),
                    ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
                    ("TOPPADDING", (0, -1), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
                    ("LEFTPADDING", (0, -1), (-1, -1), 8),
                    ("RIGHTPADDING", (0, -1), (-1, -1), 8),
                ]
            )
        )

        bottom = Table([[notes_flow, t_totals]], colWidths=[100 * mm, 80 * mm])
        bottom.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

        story.append(bottom)

        # Build
        doc.build(story, onFirstPage=self._on_page_footer, onLaterPages=self._on_page_footer)
        return dest_path