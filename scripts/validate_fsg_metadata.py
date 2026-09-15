#!/usr/bin/env python3
"""Validate Salesforce metadata XML is well-formed and required FSG files exist."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORCE_APP = ROOT / "force-app" / "main" / "default"

REQUIRED = [
    FORCE_APP / "objects" / "Region__c" / "Region__c.object-meta.xml",
    FORCE_APP / "objects" / "Product_Availability__c" / "Product_Availability__c.object-meta.xml",
    FORCE_APP / "objects" / "Supplier_Product__c" / "Supplier_Product__c.object-meta.xml",
    FORCE_APP / "permissionsets" / "FSG_Catalog_Admin.permissionset-meta.xml",
    FORCE_APP / "permissionsets" / "FSG_Regional_Merchandiser.permissionset-meta.xml",
    FORCE_APP / "permissionsets" / "FSG_Supplier_Portal.permissionset-meta.xml",
    FORCE_APP / "permissionsets" / "FSG_Buyer_Portal.permissionset-meta.xml",
    FORCE_APP / "sharingRules" / "Product_Availability__c.sharingRules-meta.xml",
    FORCE_APP / "sharingRules" / "Supplier_Product__c.sharingRules-meta.xml",
    FORCE_APP / "customPermissions" / "FSG_Bypass_Region_Validation.customPermission-meta.xml",
]


def main() -> int:
    xml_files = sorted(FORCE_APP.rglob("*.xml"))
    if not xml_files:
        print("No XML files found under force-app", file=sys.stderr)
        return 1

    errors: list[str] = []
    for path in xml_files:
        try:
            ET.parse(path)
        except ET.ParseError as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")

    for path in REQUIRED:
        if not path.exists():
            errors.append(f"missing required file: {path.relative_to(ROOT)}")

    admin = (FORCE_APP / "permissionsets" / "FSG_Catalog_Admin.permissionset-meta.xml").read_text()
    if admin.count("<label>FSG Catalog Admin</label>") != 1:
        errors.append("FSG_Catalog_Admin permission set must contain exactly one label element")
    if "FSG_Bypass_Region_Validation" not in admin:
        errors.append("FSG_Catalog_Admin must include FSG_Bypass_Region_Validation")

    sharing = (FORCE_APP / "sharingRules" / "Product_Availability__c.sharingRules-meta.xml").read_text()
    for region in ("NA", "EMEA", "APAC", "LATAM"):
        if f"<value>{region}</value>" not in sharing:
            errors.append(f"Product Availability sharing rules missing region {region}")

    supplier_ps = (FORCE_APP / "permissionsets" / "FSG_Supplier_Portal.permissionset-meta.xml").read_text()
    if "<object>Product2</object>" in supplier_ps:
        errors.append("FSG_Supplier_Portal must not grant Product2 object permissions")

    arch = ROOT / "docs" / "architecture" / "FSG_Product_Catalog_Architecture.md"
    if not arch.exists():
        errors.append("missing architecture document")
    else:
        text = arch.read_text()
        for needle, label in (
            ("Commerce Markets", "architecture: Commerce Markets"),
            ("Product_Availability__c", "architecture: Product Availability"),
            ("2,000", "architecture: entitlement search limit"),
            ("external OWD Private", "architecture: Product external OWD"),
            ("sharing set", "architecture: sharing sets"),
        ):
            if needle.lower() not in text.lower():
                errors.append(f"missing {label}")

    if errors:
        print("Metadata validation failed:")
        for item in errors:
            print(f"  - {item}")
        return 1

    print(f"OK: parsed {len(xml_files)} XML files; required catalog metadata present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
