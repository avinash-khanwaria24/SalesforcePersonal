#!/usr/bin/env python3
"""Validate the Salesforce supply-operations data model metadata."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORCE = ROOT / "force-app" / "main" / "default"
NS = {"m": "http://soap.sforce.com/2006/04/metadata"}

STANDARD_PARENTS = {
    "Account",
    "Contact",
    "Contract",
    "Order",
    "Case",
    "Entitlement",
    "BusinessHours",
    "Product2",
    "User",
}

WHITEBOARD_OBJECTS = {
    "Account",
    "Contact",
    "Contract",
    "Order",
    "Case",
    "Entitlement",
    "BusinessHours",
    "Supplier_Application__c",
    "FD_Certificate__c",
    "Supplier_Catalogue__c",
    "Supplier_Catalogue_Item__c",
    "Pickup_Delivery_Schedule__c",
    "Delivery_Schedule__c",
    "Volume_Discount_Tier__c",
    "Commitment_Process__c",
    "Commitment_Milestone__c",
    "Invoice__c",
    "Fulfillment_Order__c",
    "Shipment_Lot__c",
    "Delivery_Note__c",
}

REQUIRED_EDGES = {
    ("Contact", "Account", "standard"),
    ("Contract", "Account", "standard"),
    ("Order", "Account", "standard"),
    ("Case", "Account", "standard"),
    ("Case", "BusinessHours", "standard"),
    ("Entitlement", "Account", "standard"),
    ("Supplier_Application__c", "Account", "Lookup"),
    ("FD_Certificate__c", "Account", "MasterDetail"),
    ("Supplier_Catalogue__c", "Account", "Lookup"),
    ("Supplier_Catalogue_Item__c", "Supplier_Catalogue__c", "MasterDetail"),
    ("Pickup_Delivery_Schedule__c", "Account", "Lookup"),
    ("Delivery_Schedule__c", "Contract", "MasterDetail"),
    ("Volume_Discount_Tier__c", "Contract", "MasterDetail"),
    ("Commitment_Process__c", "Entitlement", "Lookup"),
    ("Commitment_Milestone__c", "Commitment_Process__c", "MasterDetail"),
    ("Invoice__c", "Order", "MasterDetail"),
    ("Invoice__c", "Account", "Lookup"),
    ("Fulfillment_Order__c", "Order", "MasterDetail"),
    ("Fulfillment_Order__c", "Account", "Lookup"),
    ("Shipment_Lot__c", "Order", "MasterDetail"),
    ("Shipment_Lot__c", "Fulfillment_Order__c", "Lookup"),
    ("Delivery_Note__c", "Shipment_Lot__c", "MasterDetail"),
}


def text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def parse(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


def custom_objects() -> list[Path]:
    return sorted(
        p for p in (FORCE / "objects").iterdir() if p.is_dir() and p.name.endswith("__c")
    )


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    xml_files = list(FORCE.rglob("*.xml"))
    if not xml_files:
        errors.append("No XML metadata found under force-app")

    for path in xml_files:
        try:
            parse(path)
        except ET.ParseError as exc:
            errors.append(f"Invalid XML {path.relative_to(ROOT)}: {exc}")

    objects: dict[str, dict] = {}
    fields_by_object: dict[str, dict[str, dict]] = defaultdict(dict)
    rels_by_parent: dict[str, list[tuple[str, str, str]]] = defaultdict(list)

    for obj_dir in custom_objects():
        api = obj_dir.name
        meta = parse(obj_dir / f"{api}.object-meta.xml")
        sharing = text(meta.find("m:sharingModel", NS))
        objects[api] = {
            "label": text(meta.find("m:label", NS)),
            "sharing": sharing,
            "history": text(meta.find("m:enableHistory", NS)),
            "compact": text(meta.find("m:compactLayoutAssignment", NS)),
        }
        if len(api) > 40:
            errors.append(f"{api} exceeds 40-character API name limit")
        if objects[api]["history"] != "true":
            errors.append(f"{api} should enable field history")
        if not (obj_dir / "listViews" / "All.listView-meta.xml").exists():
            errors.append(f"{api} missing All list view")
        tab = FORCE / "tabs" / f"{api}.tab-meta.xml"
        if not tab.exists():
            errors.append(f"{api} missing custom tab")

        md_count = 0
        for field_path in (obj_dir / "fields").glob("*.field-meta.xml"):
            froot = parse(field_path)
            fname = text(froot.find("m:fullName", NS))
            ftype = text(froot.find("m:type", NS))
            fields_by_object[api][fname] = {
                "type": ftype,
                "referenceTo": text(froot.find("m:referenceTo", NS)),
                "relationshipName": text(froot.find("m:relationshipName", NS)),
                "required": text(froot.find("m:required", NS)),
            }
            if len(fname) > 40:
                errors.append(f"{api}.{fname} exceeds 40-character API name limit")
            if ftype in {"Lookup", "MasterDetail"}:
                target = fields_by_object[api][fname]["referenceTo"]
                rel_name = fields_by_object[api][fname]["relationshipName"]
                if not target:
                    errors.append(f"{api}.{fname} missing referenceTo")
                elif target not in STANDARD_PARENTS and not target.endswith("__c"):
                    errors.append(f"{api}.{fname} references unknown object {target}")
                elif target.endswith("__c") and not (FORCE / "objects" / target).exists():
                    errors.append(f"{api}.{fname} references missing custom object {target}")
                if not rel_name:
                    errors.append(f"{api}.{fname} missing relationshipName")
                else:
                    rels_by_parent[target].append((rel_name, api, fname))
            if ftype == "MasterDetail":
                md_count += 1
        if md_count > 2:
            errors.append(f"{api} has {md_count} master-detail fields (max 2)")
        if md_count >= 1 and sharing != "ControlledByParent":
            errors.append(f"{api} is a master-detail child but sharingModel={sharing}")
        if md_count == 0 and sharing == "ControlledByParent":
            errors.append(f"{api} is ControlledByParent without a master-detail field")

        compact_name = objects[api]["compact"]
        compact_path = obj_dir / "compactLayouts" / f"{compact_name}.compactLayout-meta.xml"
        if compact_name and compact_path.exists():
            croot = parse(compact_path)
            for col in croot.findall("m:fields", NS):
                col_name = (col.text or "").strip()
                if col_name not in {"Name", "Id", "CreatedDate"} and col_name not in fields_by_object[api]:
                    errors.append(f"{api} compact layout references missing field {col_name}")

    # Standard custom fields
    for std in ["Account", "Contract", "Order", "Entitlement"]:
        field_dir = FORCE / "objects" / std / "fields"
        if not field_dir.exists():
            errors.append(f"Missing custom fields on standard object {std}")
            continue
        for field_path in field_dir.glob("*.field-meta.xml"):
            froot = parse(field_path)
            fname = text(froot.find("m:fullName", NS))
            ftype = text(froot.find("m:type", NS))
            fields_by_object[std][fname] = {
                "type": ftype,
                "referenceTo": text(froot.find("m:referenceTo", NS)),
                "relationshipName": text(froot.find("m:relationshipName", NS)),
            }
            if ftype in {"Lookup", "MasterDetail"}:
                target = fields_by_object[std][fname]["referenceTo"]
                rels_by_parent[target].append(
                    (fields_by_object[std][fname]["relationshipName"], std, fname)
                )

    for parent, rels in rels_by_parent.items():
        seen = {}
        for rel_name, child, field in rels:
            key = (parent, rel_name)
            if key in seen:
                errors.append(
                    f"Duplicate relationshipName {rel_name} on {parent}: {seen[key]} and {child}.{field}"
                )
            seen[key] = f"{child}.{field}"

    found_edges = set()
    for child, fields in fields_by_object.items():
        for fname, meta in fields.items():
            if meta.get("type") in {"Lookup", "MasterDetail"}:
                found_edges.add((child, meta["referenceTo"], meta["type"]))

    for edge in REQUIRED_EDGES:
        child, parent, rtype = edge
        if rtype == "standard":
            continue
        if edge not in found_edges:
            errors.append(f"Missing whiteboard relationship {child} --{rtype}--> {parent}")

    for api in WHITEBOARD_OBJECTS:
        if api.endswith("__c") and api not in objects:
            errors.append(f"Whiteboard custom object {api} was not generated")

    perm_path = FORCE / "permissionsets" / "Supply_Operations_User.permissionset-meta.xml"
    if not perm_path.exists():
        errors.append("Missing Supply_Operations_User permission set")
    else:
        perm = parse(perm_path)
        perm_objects = {text(el.find("m:object", NS)) for el in perm.findall("m:objectPermissions", NS)}
        for api in objects:
            if api not in perm_objects:
                errors.append(f"Permission set missing object CRUD for {api}")
        perm_tabs = {text(el.find("m:tab", NS)) for el in perm.findall("m:tabSettings", NS)}
        for api in objects:
            if api not in perm_tabs:
                errors.append(f"Permission set missing tab visibility for {api}")

    app_path = FORCE / "applications" / "Supply_Operations.app-meta.xml"
    if not app_path.exists():
        errors.append("Missing Supply_Operations Lightning app")
    else:
        app = parse(app_path)
        app_tabs = {text(el) for el in app.findall("m:tabs", NS)}
        for api in objects:
            if api not in app_tabs:
                errors.append(f"Lightning app missing tab {api}")

    rt_dir = FORCE / "objects" / "Account" / "recordTypes"
    for rt_name in ("Customer", "Supplier"):
        rt_path = rt_dir / f"{rt_name}.recordType-meta.xml"
        if not rt_path.exists():
            errors.append(f"Missing Account record type {rt_name}")
            continue
        rt = parse(rt_path)
        for pv in rt.findall("m:picklistValues", NS):
            picklist = text(pv.find("m:picklist", NS))
            defaults = [
                text(v.find("m:fullName", NS))
                for v in pv.findall("m:values", NS)
                if text(v.find("m:default", NS)) == "true"
            ]
            if len(defaults) != 1:
                errors.append(
                    f"Account.{rt_name} picklist {picklist} has {len(defaults)} defaults {defaults}"
                )

    print(f"XML files: {len(xml_files)}")
    print(f"Custom objects: {len(objects)}")
    print(f"Custom fields: {sum(len(v) for k, v in fields_by_object.items() if k.endswith('__c'))}")
    print(f"Relationships: {sum(len(v) for v in rels_by_parent.values())}")
    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  - {w}")
    if errors:
        print("FAILURES:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("OK: Salesforce data model metadata is internally consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
