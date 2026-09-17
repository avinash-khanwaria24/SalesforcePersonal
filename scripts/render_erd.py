#!/usr/bin/env python3
"""Render a Salesforce-style ERD of the whiteboard data model to SVG."""

from __future__ import annotations

from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "erd.svg"
ARTIFACT = Path("/opt/cursor/artifacts/salesforce_data_model_erd.svg")

# Box definitions: id, label, kind, x, y, w, h, lines (fields)
# kind: standard | custom | setup
BOXES = [
    ("SA", "Supplier Application", "custom", 40, 80, 230, 118, ["Lookup → Account", "Status, Type, Dates"]),
    ("CERT", "F&D Certificate", "custom", 40, 230, 230, 118, ["MD → Account", "Type, Issue, Expiry"]),
    ("CAT", "Supplier Catalogue", "custom", 40, 380, 230, 118, ["Lookup → Account", "Status, Effective dates"]),
    ("ITEM", "Supplier Catalogue Item", "custom", 40, 530, 230, 132, ["MD → Catalogue", "Lookup → Product2", "SKU, Price, UOM"]),
    ("PDS", "Pickup Delivery Schedule", "custom", 40, 700, 230, 118, ["Lookup → Account", "Type, Day, Window"]),
    ("DS", "Delivery Schedule", "custom", 340, 72, 220, 118, ["MD → Contract", "Frequency, Dates"]),
    ("VDT", "Volume Discount Tier", "custom", 590, 72, 230, 118, ["MD → Contract", "Min/Max qty, %"]),
    ("CONTRACT", "Contract", "standard", 470, 210, 220, 118, ["Lookup → Account", "Standard Salesforce"]),
    ("MS", "Commitment Milestone", "custom", 1170, 72, 240, 118, ["MD → Commitment Process", "Due date, Status"]),
    ("CP", "Commitment Process", "custom", 1170, 220, 240, 118, ["Lookup → Entitlement", "Lookup → Account"]),
    ("ENT", "Entitlement", "standard", 1170, 360, 240, 118, ["Lookup → Account", "Lookup → Contract"]),
    ("ACCOUNT", "Account", "standard", 470, 400, 240, 150, ["Hub object", "Record types: Customer, Supplier", "Account Type, Status"]),
    ("ORDER", "Order", "standard", 860, 400, 210, 118, ["Lookup → Account", "Lookup → Contract"]),
    ("INV", "Invoice", "custom", 860, 250, 210, 118, ["MD → Order", "Lookup → Account"]),
    ("FO", "Fulfillment Order", "custom", 860, 560, 210, 118, ["MD → Order", "Lookup → Account"]),
    ("LOT", "Shipment Lot", "custom", 1140, 560, 220, 118, ["MD → Order", "Lookup → Fulfillment Order"]),
    ("DN", "Delivery Note", "custom", 1140, 720, 220, 118, ["MD → Shipment Lot", "Marked custom on board"]),
    ("CONTACT", "Contact", "standard", 340, 620, 200, 100, ["Lookup → Account"]),
    ("CASE", "Case", "standard", 570, 620, 200, 100, ["Lookup → Account", "Lookup → Entitlement"]),
    ("BH", "Business Hours", "setup", 570, 760, 200, 100, ["Case.BusinessHoursId", "Setup object"]),
]

# Edges: from, to, label, kind md|lookup|standard
EDGES = [
    ("SA", "ACCOUNT", "Lookup", "lookup"),
    ("CERT", "ACCOUNT", "Master-Detail", "md"),
    ("CAT", "ACCOUNT", "Lookup", "lookup"),
    ("ITEM", "CAT", "Master-Detail", "md"),
    ("PDS", "ACCOUNT", "Lookup", "lookup"),
    ("DS", "CONTRACT", "Master-Detail", "md"),
    ("VDT", "CONTRACT", "Master-Detail", "md"),
    ("CONTRACT", "ACCOUNT", "Standard", "standard"),
    ("MS", "CP", "Master-Detail", "md"),
    ("CP", "ENT", "Lookup", "lookup"),
    ("ENT", "ACCOUNT", "Standard", "standard"),
    ("CONTACT", "ACCOUNT", "Standard", "standard"),
    ("CASE", "ACCOUNT", "Standard", "standard"),
    ("CASE", "BH", "Standard", "standard"),
    ("ORDER", "ACCOUNT", "Standard", "standard"),
    ("INV", "ORDER", "Master-Detail", "md"),
    ("INV", "ACCOUNT", "Lookup", "lookup"),
    ("FO", "ORDER", "Master-Detail", "md"),
    ("FO", "ACCOUNT", "Lookup", "lookup"),
    ("LOT", "ORDER", "Master-Detail", "md"),
    ("LOT", "FO", "Lookup", "lookup"),
    ("DN", "LOT", "Master-Detail", "md"),
]

# Orthogonal routes that would otherwise pass through another box.
WAYPOINTS = {
    ("PDS", "ACCOUNT"): [(270, 759), (305, 759), (305, 548), (470, 548)],
    ("ENT", "ACCOUNT"): [(1170, 419), (1088, 419), (1088, 475), (710, 475)],
}

COLORS = {
    "standard": ("#E8F4FF", "#0B5CAB", "#032D60"),
    "custom": ("#E3F3E1", "#2E844A", "#1B5E20"),
    "setup": ("#F3E8FD", "#9050E9", "#401A75"),
}

EDGE_COLORS = {
    "md": "#2E844A",
    "lookup": "#0B5CAB",
    "standard": "#5C5C5C",
}


def box_map():
    return {b[0]: b for b in BOXES}


def center(box):
    _, _, _, x, y, w, h, _ = box
    return x + w / 2, y + h / 2


def edge_points(src, dst):
    _, _, _, sx, sy, sw, sh, _ = src
    _, _, _, dx, dy, dw, dh, _ = dst
    scx, scy = sx + sw / 2, sy + sh / 2
    dcx, dcy = dx + dw / 2, dy + dh / 2
    # start at border of src toward dst
    def border(x, y, w, h, cx, cy, ox, oy):
        vx, vy = ox - cx, oy - cy
        if vx == 0 and vy == 0:
            return cx, cy
        # intersect with rectangle
        scale_candidates = []
        if vx != 0:
            tx = ((x + w) - cx) / vx if vx > 0 else (x - cx) / vx
            scale_candidates.append(tx)
        if vy != 0:
            ty = ((y + h) - cy) / vy if vy > 0 else (y - cy) / vy
            scale_candidates.append(ty)
        t = min(t for t in scale_candidates if t > 0)
        return cx + vx * t, cy + vy * t

    x1, y1 = border(sx, sy, sw, sh, scx, scy, dcx, dcy)
    x2, y2 = border(dx, dy, dw, dh, dcx, dcy, scx, scy)
    return x1, y1, x2, y2


def render() -> str:
    boxes = box_map()
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1460" height="920" viewBox="0 0 1460 920" font-family="Inter, Segoe UI, Arial, sans-serif">',
        '<rect width="1460" height="920" fill="#F4F6F9"/>',
        '<text x="40" y="32" font-size="22" font-weight="700" fill="#032D60">Supply Operations — Salesforce Data Model</text>',
        '<text x="40" y="54" font-size="13" fill="#5C5C5C">Whiteboard ERD converted to Salesforce objects. Solid green = master-detail, dashed blue = lookup, gray = standard.</text>',
        # legend
        '<rect x="1040" y="12" width="14" height="14" rx="2" fill="#E8F4FF" stroke="#0B5CAB"/>',
        '<text x="1060" y="24" font-size="12" fill="#032D60">Standard</text>',
        '<rect x="1140" y="12" width="14" height="14" rx="2" fill="#E3F3E1" stroke="#2E844A"/>',
        '<text x="1160" y="24" font-size="12" fill="#032D60">Custom</text>',
        '<rect x="1230" y="12" width="14" height="14" rx="2" fill="#F3E8FD" stroke="#9050E9"/>',
        '<text x="1250" y="24" font-size="12" fill="#032D60">Setup</text>',
        '<rect x="24" y="72" width="262" height="762" rx="12" fill="none" stroke="#DD7A01" stroke-dasharray="6 4" stroke-width="2"/>',
        '<text x="36" y="68" font-size="11" font-weight="700" fill="#A15C00">SUPPLIER DOMAIN</text>',
        """<defs>
  <marker id="arrow-md" markerWidth="10" markerHeight="8" refX="8" refY="4" orient="auto"><polygon points="0 0, 10 4, 0 8" fill="#2E844A"/></marker>
  <marker id="arrow-lookup" markerWidth="10" markerHeight="8" refX="8" refY="4" orient="auto"><polygon points="0 0, 10 4, 0 8" fill="#0B5CAB"/></marker>
  <marker id="arrow-standard" markerWidth="10" markerHeight="8" refX="8" refY="4" orient="auto"><polygon points="0 0, 10 4, 0 8" fill="#5C5C5C"/></marker>
</defs>""",
    ]
    # edges first
    for src_id, dst_id, label, kind in EDGES:
        color = EDGE_COLORS[kind]
        dash = ' stroke-dasharray="6 4"' if kind == "lookup" else ""
        width = "2.4" if kind == "md" else "1.6"
        points = WAYPOINTS.get((src_id, dst_id))
        if points:
            pts = " ".join(f"{x},{y}" for x, y in points)
            parts.append(
                f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}"{dash} marker-end="url(#arrow-{kind})"/>'
            )
            mx = sum(p[0] for p in points) / len(points)
            my = sum(p[1] for p in points) / len(points)
        else:
            x1, y1, x2, y2 = edge_points(boxes[src_id], boxes[dst_id])
            parts.append(
                f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{width}"{dash} marker-end="url(#arrow-{kind})"/>'
            )
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        parts.append(
            f'<text x="{mx:.1f}" y="{my - 6:.1f}" font-size="10" text-anchor="middle" fill="{color}">{escape(label)}</text>'
        )

    for bid, label, kind, x, y, w, h, lines in BOXES:
        fill, stroke, ink = COLORS[kind]
        badge = {"standard": "STD", "custom": "CSTM", "setup": "SETUP"}[kind]
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="28" rx="10" fill="{stroke}"/>')
        parts.append(f'<rect x="{x}" y="{y + 18}" width="{w}" height="10" fill="{stroke}"/>')
        parts.append(f'<text x="{x + 10}" y="{y + 19}" font-size="13" font-weight="700" fill="#FFFFFF">{escape(label)}</text>')
        parts.append(
            f'<text x="{x + w - 10}" y="{y + 18}" font-size="9" text-anchor="end" fill="#FFFFFF">{badge}</text>'
        )
        for i, line in enumerate(lines):
            parts.append(
                f'<text x="{x + 12}" y="{y + 48 + i * 18}" font-size="12" fill="{ink}">{escape(line)}</text>'
            )

    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    svg = render()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg, encoding="utf-8")
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(svg, encoding="utf-8")
    print(f"Wrote {OUT} and {ARTIFACT}")


if __name__ == "__main__":
    main()
