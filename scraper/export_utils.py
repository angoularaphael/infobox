"""Export CSV et PDF côté serveur."""
from __future__ import annotations

import csv
import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


COLUMNS = ("name", "email", "phone", "role", "search_country", "location", "profile_url")


def people_to_csv_rows(people: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=[
            "nom",
            "email",
            "telephone",
            "adresse",
            "role",
            "pays_recherche",
            "localisation",
        ],
        delimiter=";",
        extrasaction="ignore",
    )
    writer.writeheader()
    for p in people:
        writer.writerow(
            {
                "nom": p.get("name", ""),
                "email": p.get("email", ""),
                "telephone": p.get("phone", ""),
                "adresse": p.get("address", ""),
                "role": p.get("role", ""),
                "pays_recherche": p.get("search_country", ""),
                "localisation": p.get("location", ""),
            }
        )
    text = "sep=;\n" + buf.getvalue()
    return b"\xff\xfe" + text.encode("utf-16-le")


def people_to_pdf_bytes(people: list[dict[str, Any]], title: str = "BoxRec — Contacts") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=title)
    styles = getSampleStyleSheet()
    elements = [Paragraph(title, styles["Title"]), Spacer(1, 12)]

    data = [
        ["Nom", "Email", "Téléphone", "Adresse", "Rôle", "Pays (recherche)", "Localisation"]
    ]
    for p in people:
        data.append(
            [
                p.get("name", "")[:60],
                p.get("email", "")[:50],
                p.get("phone", "")[:30],
                p.get("address", "")[:50],
                p.get("role", "")[:20],
                p.get("search_country", "")[:40],
                p.get("location", "")[:40],
            ]
        )

    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#9f1239")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#57534e")),
                ("LINEBELOW", (0, 0), (-1, 0), 1.2, colors.HexColor("#7f0d2d")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fffdf8")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(table)
    doc.build(elements)
    return buf.getvalue()
