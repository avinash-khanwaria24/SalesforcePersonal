#!/usr/bin/env python3
"""Validate SF Switch trigger-bypass metadata and guide completeness."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NS = {"md": "http://soap.sforce.com/2006/04/metadata"}
FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)


def parse_xml(path: Path) -> ET.Element:
    try:
        return ET.parse(path).getroot()
    except ET.ParseError as exc:
        FAILURES.append(f"{path.relative_to(ROOT)}: invalid XML ({exc})")
        return ET.Element("invalid")


def text(root: ET.Element, tag: str) -> str | None:
    node = root.find(f"md:{tag}", NS)
    if node is None:
        node = root.find(tag)
    return None if node is None else (node.text or "").strip()


def main() -> int:
    xml_files = list((ROOT / "force-app").rglob("*.xml"))
    check(len(xml_files) >= 8, "expected force-app metadata XML files")
    for path in xml_files:
        parse_xml(path)

    service = ROOT / "force-app/main/default/classes/TriggerBypassService.cls"
    test_cls = ROOT / "force-app/main/default/classes/TriggerBypassServiceTest.cls"
    trigger = ROOT / "force-app/main/default/triggers/AccountTriggerBypassExample.trigger"
    trigger_meta = ROOT / "force-app/main/default/triggers/AccountTriggerBypassExample.trigger-meta.xml"
    cmdt = ROOT / "force-app/main/default/customMetadata/Trigger_Bypass.AccountTriggerBypassExample.md-meta.xml"
    guide = ROOT / "docs/sf-switch-deactivate-trigger-cross-reference.md"

    for path in (service, test_cls, trigger, trigger_meta, cmdt, guide):
        check(path.is_file(), f"missing {path.relative_to(ROOT)}")

    service_src = service.read_text()
    trigger_src = trigger.read_text()
    test_src = test_cls.read_text()
    guide_src = guide.read_text()

    check("isBypassed(" in service_src, "TriggerBypassService.isBypassed missing")
    check("Automation_Switch__c.getInstance()" in service_src, "hierarchy custom setting not consulted")
    check("Trigger_Bypass__mdt.getAll()" in service_src, "custom metadata not consulted")
    check("isBypassed('AccountTriggerBypassExample')" in trigger_src, "example trigger does not call bypass")
    check(test_src.count("@IsTest") >= 7, "expected service + trigger tests")
    check("hierarchySettingBypassesEveryTrigger" in test_src, "hierarchy setting test missing")
    check("customMetadataDisablesNamedTriggerOnly" in test_src, "CMDT test missing")
    check("exampleTriggerHonorsBypass" in test_src, "trigger bypass integration test missing")
    check("exampleTriggerRunsWhenNotBypassed" in test_src, "trigger active-path test missing")

    meta_root = parse_xml(trigger_meta)
    check(text(meta_root, "status") == "Active", "example trigger meta status must be Active")

    required_guide = [
        "INSUFFICIENT_ACCESS_ON_CROSS_REFERENCE_ENTITY",
        "NamespacePrefix",
        "Author Apex",
        "Modify Metadata Through Metadata API Functions",
        "RunLocalTests",
        "RunSpecifiedTests",
        "managed",
        "sf project deploy start",
        "TriggerBypassService",
        "Deployment Status",
    ]
    for needle in required_guide:
        check(needle in guide_src, f"guide missing required topic: {needle}")

    simulate_bypass_service()

    if FAILURES:
        print("VALIDATION FAILED")
        for item in FAILURES:
            print(f" - {item}")
        return 1

    print(f"OK: parsed {len(xml_files)} XML files; guide and bypass reference look complete.")
    return 0


def is_bypassed(trigger_name: str, bypass_all: bool, disabled_names: set[str]) -> bool:
    """Mirror of TriggerBypassService.isBypassed for contract checks."""
    if trigger_name is None or not str(trigger_name).strip():
        return False
    if bypass_all:
        return True
    return trigger_name in disabled_names


def simulate_bypass_service() -> None:
    cases = [
        ("null name", None, False, set(), False),
        ("blank name", "", False, set(), False),
        ("unknown trigger", "DoesNotExist", False, set(), False),
        ("hierarchy bypass named", "AccountTriggerBypassExample", True, set(), True),
        ("hierarchy bypass other", "AnyOtherTrigger", True, set(), True),
        ("cmdt named disabled", "AccountTriggerBypassExample", False, {"AccountTriggerBypassExample"}, True),
        ("cmdt other remains on", "SomeOtherTrigger", False, {"AccountTriggerBypassExample"}, False),
        ("no flags", "AccountTriggerBypassExample", False, set(), False),
    ]
    print("Bypass contract:")
    for label, name, bypass_all, disabled, expected in cases:
        actual = is_bypassed(name, bypass_all, disabled)
        print(f"  {label}: expected={expected} actual={actual}")
        check(actual is expected, f"{label}: expected {expected}, got {actual}")


if __name__ == "__main__":
    sys.exit(main())
