#!/usr/bin/env python3
"""Redraw the Salesforce schema-builder capture as a readable data-model PDF."""

from __future__ import annotations

import os
import sys
from math import hypot

from reportlab.lib.colors import Color, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# Tabloid landscape. Large enough for the full graph, still a real paper size.
PAGE_W, PAGE_H = 1224.0, 792.0

pdfmetrics.registerFont(TTFont("Inter", "/usr/share/fonts/truetype/macos/Inter-Regular.ttf"))
pdfmetrics.registerFont(TTFont("Inter-Med", "/usr/share/fonts/truetype/macos/Inter-Medium.ttf"))
pdfmetrics.registerFont(TTFont("Inter-Sem", "/usr/share/fonts/truetype/macos/Inter-SemiBold.ttf"))
pdfmetrics.registerFont(TTFont("Inter-Bold", "/usr/share/fonts/truetype/macos/Inter-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Inter-It", "/usr/share/fonts/truetype/macos/Inter-Italic.ttf"))
pdfmetrics.registerFont(TTFont("Mono", "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Medium.ttf"))


def hex_color(value: str, alpha: float = 1.0) -> Color:
    value = value.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return Color(r, g, b, alpha)


BG = hex_color("#F5F2EB")
CARD = hex_color("#FFFDFB")
INK = hex_color("#1C1917")
MUTED = hex_color("#746C64")
FAINT = hex_color("#A39B92")
LINE = hex_color("#6F675F")
RULE = hex_color("#E6E0D6")
CHIP = hex_color("#F5F2EB")
SHADOW = hex_color("#E4DDD2")

# Domain accents. Custom objects use violet so they stand apart from standard ones.
ACCENT = {
    "prospect": hex_color("#0F766E"),
    "customer": hex_color("#1D4ED8"),
    "service": hex_color("#C2410C"),
    "files": hex_color("#57534E"),
    "people": hex_color("#334155"),
    "custom": hex_color("#6D28D9"),
}
WASH = {
    "prospect": hex_color("#0F766E", 0.06),
    "customer": hex_color("#1D4ED8", 0.055),
    "service": hex_color("#C2410C", 0.06),
    "files": hex_color("#57534E", 0.06),
    "people": hex_color("#334155", 0.05),
    "custom": hex_color("#6D28D9", 0.07),
}

# field tuple: (api or label, parent object, qualifier or None)
OBJECTS = [
    {
        "name": "Lead",
        "group": "prospect",
        "role": "Unqualified prospect",
        "fields": [
            ("ConvertedAccountId", "Account", None),
            ("ConvertedContactId", "Contact", None),
            ("ConvertedOpportunityId", "Opportunity", None),
        ],
    },
    {
        "name": "Campaign",
        "group": "prospect",
        "role": "Marketing program",
        "fields": [],
    },
    {
        "name": "CampaignMember",
        "group": "prospect",
        "role": "Person on a campaign",
        "fields": [
            ("CampaignId", "Campaign", None),
            ("LeadId", "Lead", None),
        ],
    },
    {
        "name": "SurveyInvitation",
        "group": "prospect",
        "role": "Survey sent to a lead",
        "fields": [
            ("ParticipantId", "Lead", None),
        ],
    },
    {
        "name": "Account",
        "group": "customer",
        "role": "Company or household",
        "fields": [
            ("Potential HQ to launch", "Account", "self"),
        ],
    },
    {
        "name": "Contact",
        "group": "customer",
        "role": "Person at an account",
        "fields": [
            ("AccountId", "Account", None),
        ],
    },
    {
        "name": "Opportunity",
        "group": "customer",
        "role": "Deal in progress",
        "fields": [
            ("AccountId", "Account", None),
        ],
    },
    {
        "name": "Case",
        "group": "service",
        "role": "Customer issue",
        "fields": [
            ("ContactId", "Contact", None),
            ("AccountId", "Account", None),
        ],
    },
    {
        "name": "Task",
        "group": "service",
        "role": "Follow-up activity",
        "fields": [
            ("WhatId", "Case", "escalation"),
        ],
    },
    {
        "name": "User",
        "group": "people",
        "role": "Internal user",
        "fields": [],
    },
    {
        "name": "ContentDocumentLink",
        "group": "files",
        "role": "File attached to a record",
        "fields": [
            ("LinkedEntityId", "Opportunity", None),
        ],
    },
    {
        "name": "ProcessInstance",
        "group": "files",
        "role": "Approval in progress",
        "fields": [
            ("TargetObjectId", "Opportunity", None),
        ],
    },
    {
        "name": "Cross_Sell_Deal__c",
        "group": "custom",
        "role": "Related customer deal",
        "fields": [
            ("Opportunity__c", "Opportunity", None),
            ("Account__c", "Account", "other customer"),
        ],
    },
    {
        "name": "Award_Nomination__c",
        "group": "custom",
        "role": "Recognition nomination",
        "fields": [
            ("Nominee__c", "User", None),
            ("Nominator__c", "User", "employee"),
            ("Nominator__c", "Contact", "customer"),
        ],
    },
]

# Grid. Row 0 is the top. Empty cells keep routing channels open.
GRID = [
    [None, None, None, "ContentDocumentLink", "ProcessInstance"],
    [None, "Account", "Opportunity", "Cross_Sell_Deal__c", None],
    ["Lead", "SurveyInvitation", "Contact", "Case", "Task"],
    ["Campaign", "CampaignMember", "User", "Award_Nomination__c", None],
]

# Relationship index, in reading order. `child` stores the lookup.
RELATIONS = [
    ("ConvertedAccountId", None, "Lead", "Account", "Set when a lead is converted."),
    ("ConvertedContactId", None, "Lead", "Contact", "Set when a lead is converted."),
    ("ConvertedOpportunityId", None, "Lead", "Opportunity", "Set when a lead is converted."),
    ("ParticipantId", None, "SurveyInvitation", "Lead", "Polymorphic in Salesforce. This view shows Lead."),
    ("Potential HQ to launch", "self", "Account", "Account", "Self-lookup on Account, labeled as in the source view."),
    ("CampaignId", None, "CampaignMember", "Campaign", "Master-detail in the standard Salesforce schema."),
    ("LeadId", None, "CampaignMember", "Lead", "Lead represented by this campaign membership."),
    ("AccountId", None, "Opportunity", "Account", "Account that owns the deal."),
    ("AccountId", None, "Contact", "Account", "Account this person belongs to."),
    ("AccountId", None, "Case", "Account", "Account on the case."),
    ("Opportunity__c", None, "Cross_Sell_Deal__c", "Opportunity", "Opportunity this cross-sell deal is for."),
    ("Account__c", "other customer", "Cross_Sell_Deal__c", "Account", "Second account, labeled “other customer” on the schema."),
    ("ContactId", None, "Case", "Contact", "Contact on the case."),
    ("WhatId", "escalation", "Task", "Case", "Polymorphic in Salesforce. This view shows Case, labeled “escalation”."),
    ("LinkedEntityId", None, "ContentDocumentLink", "Opportunity", "Polymorphic in Salesforce. This view shows Opportunity."),
    ("TargetObjectId", None, "ProcessInstance", "Opportunity", "Polymorphic in Salesforce. This view shows Opportunity."),
    ("Nominee__c", None, "Award_Nomination__c", "User", "User who is nominated."),
    ("Nominator__c", "employee", "Award_Nomination__c", "User", "Labeled “employee” on the schema."),
    ("Nominator__c", "customer", "Award_Nomination__c", "Contact", "Labeled “customer” on the schema."),
]

TITLE_H = 15
ROLE_H = 12
RULE_GAP_TOP = 7
RULE_GAP_BOT = 6
FIELD_H = 15
PAD_TOP = 11
PAD_BOT = 10
# Room for the stacked masthead (eyebrow, title, subtitle, rule).
DIAGRAM_TOP = PAGE_H - 108


def content_height(n_fields: int) -> float:
    if n_fields == 0:
        return PAD_TOP + TITLE_H + 2 + ROLE_H + PAD_BOT
    return (
        PAD_TOP
        + TITLE_H
        + 2
        + ROLE_H
        + RULE_GAP_TOP
        + 1
        + RULE_GAP_BOT
        + n_fields * FIELD_H
        + PAD_BOT
    )


class Card:
    def __init__(self, spec, col, row, x, y, w, h):
        self.spec = spec
        self.name = spec["name"]
        self.group = spec["group"]
        self.col = col
        self.row = row
        self.x = x
        self.y = y  # bottom
        self.w = w
        self.h = h
        self.fields = spec["fields"]

    @property
    def top(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def side_point(self, side: str, t: float) -> tuple[float, float]:
        t = min(1.0, max(0.0, t))
        if side == "left":
            return (self.x, self.y + self.h * t)
        if side == "right":
            return (self.x + self.w, self.y + self.h * t)
        if side == "top":
            return (self.x + self.w * t, self.top)
        if side == "bottom":
            return (self.x + self.w * t, self.y)
        raise ValueError(side)

    def point_at(self, side: str, x: float | None = None, y: float | None = None):
        if side in ("left", "right"):
            y = self.cy if y is None else y
            y = min(self.top - 8, max(self.y + 8, y))
            return (self.x if side == "left" else self.x + self.w, y)
        x = self.cx if x is None else x
        x = min(self.x + self.w - 14, max(self.x + 14, x))
        return (x, self.top if side == "top" else self.y)

    def contains(self, px, py, pad=0.0) -> bool:
        return (self.x - pad) < px < (self.x + self.w + pad) and (self.y - pad) < py < (self.top + pad)


def layout():
    margin_x = 40
    gap_x = 34
    footer_h = 48
    top = DIAGRAM_TOP
    bottom = 16 + footer_h
    avail_h = top - bottom
    cols = len(GRID[0])
    card_w = (PAGE_W - margin_x * 2 - gap_x * (cols - 1)) / cols

    by_name = {spec["name"]: spec for spec in OBJECTS}
    natural = {}
    for row in GRID:
        for name in row:
            if name:
                natural[name] = content_height(len(by_name[name]["fields"]))
    row_h = []
    for row in GRID:
        row_h.append(max(natural[n] for n in row if n))

    gap_y = (avail_h - sum(row_h)) / (len(GRID) - 1)
    cards = {}
    slots = []  # (bottom, top) per row, top > bottom
    y_cursor = top
    for r, row in enumerate(GRID):
        h = row_h[r]
        slot_top = y_cursor
        slot_bottom = y_cursor - h
        slots.append((slot_bottom, slot_top))
        for c, name in enumerate(row):
            if not name:
                continue
            x = margin_x + c * (card_w + gap_x)
            # Center shorter cards in the row so they don't stretch into empty boxes.
            # Same-row links still meet, because the neighbor's side covers that y.
            nh = natural[name]
            y = slot_bottom + (h - nh) / 2
            cards[name] = Card(by_name[name], c, r, x, y, card_w, nh)
        y_cursor = slot_bottom - gap_y

    def gutters():
        xs = []
        for c in range(cols - 1):
            left = margin_x + (c + 1) * card_w + c * gap_x
            xs.append(left + gap_x / 2)
        return xs

    def lanes(upper_row, lower_row, n, pad=16):
        upper_bottom = slots[upper_row][0]
        lower_top = slots[lower_row][1]
        lo = lower_top + pad
        hi = upper_bottom - pad
        if n == 1:
            return [(lo + hi) / 2]
        step = (hi - lo) / (n - 1)
        return [hi - i * step for i in range(n)]

    ctx = {
        "cards": cards,
        "slots": slots,
        "gap_x": gap_x,
        "gap_y": gap_y,
        "card_w": card_w,
        "margin_x": margin_x,
        "gutter": gutters(),
        "lanes": {
            "AB": lanes(0, 1, 3),
            "BC": lanes(1, 2, 3),
            "CD": lanes(2, 3, 3),
        },
        "row_mid": [ (b + t) / 2 for b, t in slots ],
    }
    return ctx


def ortho(points):
    """Insert elbows so every step is horizontal or vertical."""
    cleaned = [points[0]]
    for pt in points[1:]:
        prev = cleaned[-1]
        if abs(prev[0] - pt[0]) < 0.4 and abs(prev[1] - pt[1]) < 0.4:
            continue
        if abs(prev[0] - pt[0]) > 0.4 and abs(prev[1] - pt[1]) > 0.4:
            cleaned.append((pt[0], prev[1]))
        if abs(cleaned[-1][0] - pt[0]) > 0.4 or abs(cleaned[-1][1] - pt[1]) > 0.4:
            cleaned.append(pt)
    return cleaned


def build_routes(ctx):
    C = ctx["cards"]
    AB = ctx["lanes"]["AB"]
    BC = ctx["lanes"]["BC"]
    CD = ctx["lanes"]["CD"]
    lead, account, contact = C["Lead"], C["Account"], C["Contact"]
    opp, cs = C["Opportunity"], C["Cross_Sell_Deal__c"]
    case, task = C["Case"], C["Task"]
    survey, camp, member = C["SurveyInvitation"], C["Campaign"], C["CampaignMember"]
    user, award = C["User"], C["Award_Nomination__c"]
    cdl, proc = C["ContentDocumentLink"], C["ProcessInstance"]
    run_y = ctx["row_mid"][0]

    def shared_y(child, index, parent, side):
        """Field-row y on the child, clamped onto the parent's side."""
        y = field_y(child, index)
        return parent.point_at(side, y=y)[1]

    routes = []

    y = shared_y(survey, 0, lead, "right")
    routes.append({
        "pts": [(lead.x + lead.w, y), survey.point_at("left", y=field_y(survey, 0))],
        "child_side": "left",
        "parent_side": "right",
        "label": None,
    })
    y = field_y(member, 0)
    routes.append({
        "pts": [camp.point_at("right", y=y), member.point_at("left", y=y)],
        "child_side": "left",
        "parent_side": "right",
        "label": None,
    })
    y = field_y(opp, 0)
    routes.append({
        "pts": [account.point_at("right", y=y), opp.point_at("left", y=y)],
        "child_side": "left",
        "parent_side": "right",
        "label": None,
    })
    y = field_y(cs, 0)
    routes.append({
        "pts": [opp.point_at("right", y=y), cs.point_at("left", y=y)],
        "child_side": "left",
        "parent_side": "right",
        "label": None,
    })
    y = field_y(case, 0)
    routes.append({
        "pts": [contact.point_at("right", y=y), case.point_at("left", y=y)],
        "child_side": "left",
        "parent_side": "right",
        "label": None,
    })
    y = field_y(task, 0)
    routes.append({
        "pts": [case.point_at("right", y=y), task.point_at("left", y=y)],
        "child_side": "left",
        "parent_side": "right",
        "label": None,
    })
    y = field_y(award, 0)
    routes.append({
        "pts": [user.point_at("right", y=y), award.point_at("left", y=y)],
        "child_side": "left",
        "parent_side": "right",
        "label": None,
    })
    y = field_y(award, 1)
    routes.append({
        "pts": [user.point_at("right", y=y), award.point_at("left", y=y)],
        "child_side": "left",
        "parent_side": "right",
        "label": None,
    })

    # ConvertedOpportunityId — across the empty top row, into Lead.
    x_lead = lead.x + 28
    x_opp = opp.x + opp.w * 0.30
    routes.append({
        "pts": ortho([
            (x_opp, opp.top),
            (x_opp, run_y),
            (x_lead, run_y),
            (x_lead, lead.top),
        ]),
        "child_side": "top",
        "parent_side": "top",
        "label": "ConvertedOpportunityId",
        "label_at": 1,
    })

    # ConvertedAccountId — long horizontal through the empty cell above Lead,
    # so the field name fits on the line.
    x_up = lead.x + 78
    y_acc = account.cy
    routes.append({
        "pts": ortho([
            (account.x, y_acc),
            (x_up, y_acc),
            (x_up, lead.top),
        ]),
        "child_side": "top",
        "parent_side": "left",
        "label": "ConvertedAccountId",
        "label_at": 0,
    })

    # ConvertedContactId — under the survey card, in the lower channel.
    routes.append({
        "pts": ortho([
            (contact.x + 28, contact.y),
            (contact.x + 28, CD[0]),
            (lead.cx, CD[0]),
            (lead.cx, lead.y),
        ]),
        "child_side": "bottom",
        "parent_side": "bottom",
        "label": "ConvertedContactId",
        "label_at": 1,
    })

    # LeadId — stays left of ConvertedContactId so the two lines do not cross.
    routes.append({
        "pts": ortho([
            (lead.x + 36, lead.y),
            (lead.x + 36, CD[2]),
            (member.x + 32, CD[2]),
            (member.x + 32, member.top),
        ]),
        "child_side": "top",
        "parent_side": "bottom",
        "label": "LeadId",
        "label_at": 1,
    })

    # Account trunk for the three lookups that are not the adjacent opportunity link.
    stem = account.cx
    routes.append({
        "pts": ortho([
            (stem, account.y),
            (stem, BC[0]),
            (cs.x + 36, BC[0]),
            (cs.x + 36, cs.y),
        ]),
        "child_side": "bottom",
        "parent_side": "bottom",
        "label": "Account__c  ·  other customer",
        "label_at": 1,
    })
    routes.append({
        "pts": ortho([
            (stem, account.y),
            (stem, BC[1]),
            (case.x + case.w - 32, BC[1]),
            (case.x + case.w - 32, case.top),
        ]),
        "child_side": "top",
        "parent_side": "bottom",
        "label": "AccountId",
        "label_at": 1,
    })
    routes.append({
        "pts": ortho([
            (stem, account.y),
            (stem, BC[2]),
            (contact.x + 36, BC[2]),
            (contact.x + 36, contact.top),
        ]),
        "child_side": "top",
        "parent_side": "bottom",
        "label": "AccountId",
        "label_at": 1,
    })

    # Files and approvals leave the top of Opportunity and stay right of the conversion drop.
    routes.append({
        "pts": ortho([
            (opp.x + opp.w * 0.78, opp.top),
            (opp.x + opp.w * 0.78, AB[0]),
            (cdl.cx, AB[0]),
            (cdl.cx, cdl.y),
        ]),
        "child_side": "bottom",
        "parent_side": "top",
        "label": "LinkedEntityId",
        "label_at": 1,
    })
    routes.append({
        "pts": ortho([
            (opp.x + opp.w * 0.56, opp.top),
            (opp.x + opp.w * 0.56, AB[1]),
            (proc.cx, AB[1]),
            (proc.cx, proc.y),
        ]),
        "child_side": "bottom",
        "parent_side": "top",
        "label": "TargetObjectId",
        "label_at": 1,
    })

    # Customer nominator — contact down to the award.
    routes.append({
        "pts": ortho([
            (contact.x + contact.w - 34, contact.y),
            (contact.x + contact.w - 34, CD[1]),
            (award.x + 46, CD[1]),
            (award.x + 46, award.top),
        ]),
        "child_side": "top",
        "parent_side": "bottom",
        "label": "Nominator__c  ·  customer",
        "label_at": 1,
    })

    for route in routes:
        route["pts"] = ortho(route["pts"])
    return routes


def field_y(card: Card, index: int) -> float:
    """Vertical center of a field row, measured from the top of the card."""
    from_top = (
        PAD_TOP
        + TITLE_H
        + 2
        + ROLE_H
        + RULE_GAP_TOP
        + 1
        + RULE_GAP_BOT
        + index * FIELD_H
        + FIELD_H / 2
    )
    return card.top - from_top


def draw_foot(c, x, y, side, color=LINE):
    s, spread = 7.0, 3.6
    c.saveState()
    c.setStrokeColor(color)
    c.setLineWidth(1.15)
    c.setLineCap(1)
    c.setLineJoin(1)
    if side == "top":
        apex = (x, y + s)
        c.line(*apex, x - spread, y)
        c.line(*apex, x, y)
        c.line(*apex, x + spread, y)
    elif side == "bottom":
        apex = (x, y - s)
        c.line(*apex, x - spread, y)
        c.line(*apex, x, y)
        c.line(*apex, x + spread, y)
    elif side == "left":
        apex = (x - s, y)
        c.line(*apex, x, y - spread)
        c.line(*apex, x, y)
        c.line(*apex, x, y + spread)
    else:
        apex = (x + s, y)
        c.line(*apex, x, y - spread)
        c.line(*apex, x, y)
        c.line(*apex, x, y + spread)
    c.restoreState()
    return apex


def draw_one(c, x, y, side):
    s = 5.2
    c.saveState()
    c.setStrokeColor(LINE)
    c.setLineWidth(1.25)
    c.setLineCap(1)
    if side in ("left", "right"):
        c.line(x, y - s, x, y + s)
    else:
        c.line(x - s, y, x + s, y)
    c.restoreState()


def shorten_end(pts, end, dist):
    pts = [tuple(p) for p in pts]
    if len(pts) < 2 or dist <= 0:
        return pts
    if end == "last":
        x1, y1 = pts[-2]
        x2, y2 = pts[-1]
        dx, dy = x2 - x1, y2 - y1
        length = hypot(dx, dy)
        if length <= dist + 0.2:
            return pts
        scale = (length - dist) / length
        pts[-1] = (x1 + dx * scale, y1 + dy * scale)
    else:
        x1, y1 = pts[0]
        x2, y2 = pts[1]
        dx, dy = x2 - x1, y2 - y1
        length = hypot(dx, dy)
        if length <= dist + 0.2:
            return pts
        scale = dist / length
        pts[0] = (x1 + dx * scale, y1 + dy * scale)
    return pts


def draw_route(c, route):
    pts = route["pts"]
    child_side = route["child_side"]
    parent_side = route["parent_side"]
    # Crow's foot sits outside the child edge; the bar sits on the parent edge.
    end = pts[-1]
    start = pts[0]
    foot = draw_foot(c, end[0], end[1], child_side)
    draw_one(c, start[0], start[1], parent_side)
    drawn = shorten_end(pts, "last", 7.0)
    # Pull the start off the bar by a hair so the cap doesn't blob.
    drawn = shorten_end(drawn, "first", 1.2)
    c.saveState()
    c.setStrokeColor(LINE)
    c.setFillColor(LINE)
    c.setLineWidth(1.15)
    c.setLineCap(1)
    c.setLineJoin(1)
    path = c.beginPath()
    path.moveTo(*drawn[0])
    for pt in drawn[1:]:
        path.lineTo(*pt)
    c.drawPath(path, stroke=1, fill=0)
    c.restoreState()
    label = route.get("label")
    if not label:
        return
    seg = route.get("label_at", 0)
    seg = min(seg, len(pts) - 2)
    (x1, y1), (x2, y2) = pts[seg], pts[seg + 1]
    if abs(y1 - y2) > 0.5:
        return  # only label horizontal runs; vertical labels collide
    c.setFont("Inter-Med", 7.5)
    text_w = c.stringWidth(label, "Inter-Med", 7.5)
    seg_w = abs(x2 - x1)
    if seg_w < text_w + 18:
        return
    cx = (x1 + x2) / 2
    cy = y1
    pad_x, pad_y = 5, 3
    w, h = text_w + pad_x * 2, 7.5 + pad_y * 2
    c.setFillColor(CARD)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.6)
    c.roundRect(cx - w / 2, cy - h / 2, w, h, 3, fill=1, stroke=1)
    c.setFillColor(INK)
    c.drawCentredString(cx, cy - 2.6, label)


def rounded_clip(c, x, y, w, h, r):
    p = c.beginPath()
    p.roundRect(x, y, w, h, r)
    c.clipPath(p, stroke=0, fill=0)


def draw_card(c, card: Card):
    x, y, w, h = card.x, card.y, card.w, card.h
    accent = ACCENT[card.group]
    c.saveState()
    c.setFillColor(SHADOW)
    c.roundRect(x, y - 1.6, w, h, 8, fill=1, stroke=0)
    c.restoreState()

    c.saveState()
    c.setFillColor(CARD)
    c.roundRect(x, y, w, h, 8, fill=1, stroke=0)
    c.saveState()
    rounded_clip(c, x, y, w, h, 8)
    c.setFillColor(accent)
    c.rect(x, y, 4.0, h, fill=1, stroke=0)
    c.restoreState()
    c.setStrokeColor(RULE)
    c.setLineWidth(0.8)
    c.roundRect(x, y, w, h, 8, fill=0, stroke=1)
    c.restoreState()

    inner_l = x + 14
    inner_r = x + w - 10
    cursor = card.top - PAD_TOP - 11

    custom = card.name.endswith("__c")
    c.setFont("Inter-Sem", 11)
    if custom:
        pill = "Custom"
        c.setFont("Inter-Med", 6.5)
        pill_w = c.stringWidth(pill, "Inter-Med", 6.5) + 10
        c.setFillColor(hex_color("#EDE9FE"))
        c.roundRect(inner_r - pill_w, cursor - 3, pill_w, 12, 3, fill=1, stroke=0)
        c.setFillColor(ACCENT["custom"])
        c.drawString(inner_r - pill_w + 5, cursor, pill)
    c.setFillColor(INK)
    c.setFont("Inter-Sem", 11)
    c.drawString(inner_l, cursor, card.name)

    cursor -= ROLE_H
    c.setFillColor(MUTED)
    c.setFont("Inter-It", 8)
    c.drawString(inner_l, cursor, card.spec["role"])

    if not card.fields:
        return

    rule_y = cursor - RULE_GAP_TOP
    c.setStrokeColor(RULE)
    c.setLineWidth(0.6)
    c.line(inner_l, rule_y, inner_r, rule_y)

    fy = rule_y - RULE_GAP_BOT - 9
    inner_w = inner_r - inner_l
    for field, parent, qualifier in card.fields:
        c.setFillColor(INK)
        c.setFont("Mono", 7.2)
        shown = field
        c.drawString(inner_l, fy, shown)
        name_w = c.stringWidth(shown, "Mono", 7.2)
        rest = "   →   " + parent
        if qualifier and qualifier != "self":
            rest = f"   ·   {qualifier}   →   {parent}"
        c.setFillColor(MUTED)
        c.setFont("Inter", 7.2)
        rest_w = c.stringWidth(rest, "Inter", 7.2)
        if name_w + rest_w > inner_w:
            print(f"OVERFLOW {card.name}: {shown}{rest} ({name_w + rest_w:.0f} > {inner_w:.0f})", file=sys.stderr)
        c.drawString(inner_l + name_w, fy, rest)
        fy -= FIELD_H


def draw_self_loop(c, account: Card):
    x1 = account.x + account.w * 0.22
    x2 = account.x + account.w * 0.78
    y0 = account.top
    rise = 30
    c.saveState()
    c.setStrokeColor(LINE)
    c.setLineWidth(1.15)
    c.setLineCap(1)
    path = c.beginPath()
    path.moveTo(x1, y0 + 5.2)
    path.curveTo(x1, y0 + rise, x2, y0 + rise, x2, y0 + 7)
    c.drawPath(path, stroke=1, fill=0)
    c.restoreState()
    draw_one(c, x1, y0, "top")
    draw_foot(c, x2, y0, "top")
    label = "Potential HQ to launch"
    c.setFont("Inter-Med", 7.5)
    tw = c.stringWidth(label, "Inter-Med", 7.5)
    cx = (x1 + x2) / 2
    cy = y0 + rise + 5
    c.setFillColor(CARD)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.6)
    c.roundRect(cx - tw / 2 - 5, cy - 3, tw + 10, 13, 3, fill=1, stroke=1)
    c.setFillColor(INK)
    c.drawCentredString(cx, cy, label)


def draw_washes(c, ctx):
    cards = ctx["cards"]

    def wash(names, key, pad=10):
        selected = [cards[n] for n in names]
        x = min(card.x for card in selected) - pad
        y = min(card.y for card in selected) - pad
        r = max(card.x + card.w for card in selected) + pad
        t = max(card.top for card in selected) + pad
        c.setFillColor(WASH[key])
        c.roundRect(x, y, r - x, t - y, 14, fill=1, stroke=0)

    wash(["ContentDocumentLink", "ProcessInstance"], "files")
    wash(["Account", "Opportunity", "Cross_Sell_Deal__c"], "customer")
    wash(["Lead", "SurveyInvitation", "Campaign", "CampaignMember"], "prospect")
    wash(["Case", "Task"], "service")
    wash(["User", "Award_Nomination__c"], "people")


def draw_masthead(c, title, subtitle):
    c.setFillColor(ACCENT["prospect"])
    c.setFont("Inter-Sem", 8)
    c.drawString(40, PAGE_H - 28, "SALESFORCE")
    c.setFillColor(INK)
    c.setFont("Inter-Sem", 22)
    c.drawString(40, PAGE_H - 54, title)
    c.setFillColor(MUTED)
    c.setFont("Inter", 9.5)
    c.drawString(40, PAGE_H - 72, subtitle)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.8)
    c.line(40, PAGE_H - 86, PAGE_W - 40, PAGE_H - 86)


def draw_footer(c, page, pages):
    y = 28
    c.setStrokeColor(RULE)
    c.setLineWidth(0.8)
    c.line(40, 46, PAGE_W - 40, 46)

    # Mini crow's foot
    draw_foot(c, 52, y + 2, "left")
    c.setFillColor(MUTED)
    c.setFont("Inter", 7.5)
    c.drawString(64, y, "Crow’s foot — object that holds the lookup")

    draw_one(c, 268, y + 4, "left")
    c.setFillColor(MUTED)
    c.drawString(278, y, "Bar — record the lookup points to")

    c.setFillColor(ACCENT["custom"])
    c.roundRect(430, y - 1, 8, 8, 1.5, fill=1, stroke=0)
    c.setFillColor(MUTED)
    c.drawString(444, y, "Custom object")

    c.drawString(530, y, "Names match the labels in the source diagram.")
    c.setFillColor(FAINT)
    c.setFont("Inter", 7.5)
    c.drawRightString(PAGE_W - 40, y, f"{page}  /  {pages}")


def check_routes(routes, cards):
    """Print segments that cut through a card. Endpoints on a card edge are allowed."""
    problems = []
    for i, route in enumerate(routes):
        pts = route["pts"]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            for card in cards.values():
                if _segment_crosses_card(x1, y1, x2, y2, card):
                    problems.append((i, route.get("label"), card.name, (x1, y1), (x2, y2)))
    return problems


def _segment_crosses_card(x1, y1, x2, y2, card, pad=2.0):
    # Shrink the card so a segment that merely touches the edge is not a hit.
    left, right = card.x + pad, card.x + card.w - pad
    bottom, top = card.y + pad, card.top - pad
    if abs(y1 - y2) < 0.4:  # horizontal
        y = y1
        if not (bottom < y < top):
            return False
        lo, hi = sorted((x1, x2))
        return hi > left and lo < right
    if abs(x1 - x2) < 0.4:  # vertical
        x = x1
        if not (left < x < right):
            return False
        lo, hi = sorted((y1, y2))
        return hi > bottom and lo < top
    return False


def draw_diagram(c, ctx, routes):
    c.setFillColor(BG)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    draw_masthead(
        c,
        "Data model",
        "Objects and lookups from the schema builder view. The field is listed on the object that stores it.",
    )
    draw_washes(c, ctx)
    for card in ctx["cards"].values():
        draw_card(c, card)
    for route in routes:
        draw_route(c, route)
    draw_self_loop(c, ctx["cards"]["Account"])
    draw_footer(c, 1, 2)


def draw_index(c):
    c.setFillColor(BG)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    draw_masthead(
        c,
        "Relationship index",
        "Nineteen lookups. The field lives on the first object and points to the second.",
    )

    groups = [
        ("Prospects and conversion", "prospect", RELATIONS[0:5]),
        ("Campaigns", "prospect", RELATIONS[5:7]),
        ("Customers and pipeline", "customer", RELATIONS[7:12]),
        ("Service", "service", RELATIONS[12:14]),
        ("Files and approvals", "files", RELATIONS[14:16]),
        ("Recognition", "custom", RELATIONS[16:19]),
    ]

    left = 40
    right = PAGE_W - 40
    col_field = left + 16
    col_on = 310
    col_to = 520
    col_note = 700
    y = PAGE_H - 114

    c.setFillColor(FAINT)
    c.setFont("Inter-Sem", 7)
    c.drawString(col_field, y, "LOOKUP FIELD")
    c.drawString(col_on, y, "ON OBJECT")
    c.drawString(col_to, y, "POINTS TO")
    c.drawString(col_note, y, "NOTE")
    y -= 8
    c.setStrokeColor(RULE)
    c.setLineWidth(0.6)
    c.line(left, y, right, y)
    y -= 18

    for title, key, rows in groups:
        c.setFillColor(WASH[key])
        c.roundRect(left, y - 6, right - left, 20, 3, fill=1, stroke=0)
        c.setFillColor(ACCENT[key])
        c.rect(left, y - 6, 3, 20, fill=1, stroke=0)
        c.setFont("Inter-Sem", 8.5)
        c.drawString(left + 12, y, title.upper())
        y -= 24
        for field, qualifier, child, parent, note in rows:
            label = field if not qualifier or qualifier == "self" else f"{field}   ·   {qualifier}"
            c.setFillColor(INK)
            c.setFont("Mono", 8)
            c.drawString(col_field, y, label)
            c.setFont("Inter", 8.5)
            c.drawString(col_on, y, child)
            c.setFillColor(MUTED)
            c.drawString(col_to, y, parent)
            c.setFillColor(MUTED)
            c.setFont("Inter", 8)
            c.drawString(col_note, y, note)
            y -= 16
        y -= 8

    y -= 4
    c.setStrokeColor(RULE)
    c.line(left, y + 12, right, y + 12)
    c.setFillColor(MUTED)
    c.setFont("Inter", 8)
    notes = [
        "Reading the source. Labels are the ones visible on the schema builder capture. Objects were collapsed there, so this sheet lists relationships rather than every column.",
        "Standard behavior, beyond what the capture can show: CampaignMember.CampaignId is master-detail. ParticipantId, WhatId, LinkedEntityId, and TargetObjectId are polymorphic;",
        "only the target drawn in the capture is included. “Potential HQ to launch” is the self-lookup label on Account. Qualifiers such as “other customer”, “employee”, “customer”, and “escalation”",
        "are the words printed beside those fields in the capture.",
    ]
    for line in notes:
        c.drawString(left, y, line)
        y -= 12

    draw_footer(c, 2, 2)


def build(path: str) -> None:
    ctx = layout()
    routes = build_routes(ctx)
    problems = check_routes(routes, ctx["cards"])
    if problems:
        print(f"{len(problems)} line(s) pass through a card:", file=sys.stderr)
        for item in problems:
            print(" ", item, file=sys.stderr)
    else:
        print("Routing is clear of every card.")

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    pdf = canvas.Canvas(path, pagesize=(PAGE_W, PAGE_H))
    pdf.setTitle("Salesforce data model")
    pdf.setAuthor("Salesforce schema, redrawn")
    pdf.setSubject("Objects and lookups from the schema builder view")
    draw_diagram(pdf, ctx, routes)
    pdf.showPage()
    draw_index(pdf)
    pdf.save()
    print(f"Wrote {path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "salesforce-data-model.pdf"
    )
    build(out)
