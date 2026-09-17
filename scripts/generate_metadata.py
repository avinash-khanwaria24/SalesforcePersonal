#!/usr/bin/env python3
"""Generate Salesforce source metadata for the supply-operations data model."""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
OBJ_ROOT = ROOT / "force-app" / "main" / "default" / "objects"
TAB_ROOT = ROOT / "force-app" / "main" / "default" / "tabs"
APP_ROOT = ROOT / "force-app" / "main" / "default" / "applications"
PERM_ROOT = ROOT / "force-app" / "main" / "default" / "permissionsets"
NS = "http://soap.sforce.com/2006/04/metadata"
API = "62.0"

STANDARD_OBJECTS = {
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


def xml(tag_body: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{tag_body}\n'


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def field_xml(field: dict) -> str:
    """Emit Salesforce CustomField metadata with a stable element order."""
    ftype = field["type"]
    required_types = {
        "Text",
        "Number",
        "Currency",
        "Percent",
        "Date",
        "DateTime",
        "Time",
        "Email",
        "Phone",
        "Url",
        "TextArea",
        "Picklist",
        "Lookup",
    }
    lines = [
        f'<CustomField xmlns="{NS}">',
        f'    <fullName>{field["api"]}</fullName>',
    ]
    if ftype == "Checkbox":
        lines.append(f'    <defaultValue>{str(field.get("defaultValue", False)).lower()}</defaultValue>')
    if ftype == "Lookup":
        lines.append(f'    <deleteConstraint>{field.get("deleteConstraint", "SetNull")}</deleteConstraint>')
    if field.get("description"):
        lines.append(f'    <description>{escape(field["description"])}</description>')
    if field.get("inlineHelp"):
        lines.append(f'    <inlineHelpText>{escape(field["inlineHelp"])}</inlineHelpText>')
    lines.append(f'    <label>{escape(field["label"])}</label>')
    if ftype == "Text":
        lines.append(f'    <length>{field.get("length", 255)}</length>')
    elif ftype in {"LongTextArea", "Html"}:
        lines.append(f'    <length>{field.get("length", 32768)}</length>')
    if ftype in {"Currency", "Number", "Percent"}:
        default_scale = 0 if ftype == "Number" else 2
        lines.append(f'    <precision>{field.get("precision", 18)}</precision>')
        lines.append(f'    <scale>{field.get("scale", default_scale)}</scale>')
    if ftype in {"Lookup", "MasterDetail"}:
        lines.append(f'    <referenceTo>{field["referenceTo"]}</referenceTo>')
        lines.append(f'    <relationshipLabel>{escape(field["relationshipLabel"])}</relationshipLabel>')
        lines.append(f'    <relationshipName>{field["relationshipName"]}</relationshipName>')
    if ftype == "MasterDetail":
        lines.append(f'    <relationshipOrder>{field.get("relationshipOrder", 0)}</relationshipOrder>')
        lines.append(
            f'    <reparentableMasterDetail>{str(field.get("reparentable", False)).lower()}</reparentableMasterDetail>'
        )
    if ftype in required_types:
        lines.append(f'    <required>{str(bool(field.get("required", False))).lower()}</required>')
    if field.get("trackHistory") and ftype not in {"LongTextArea", "Html", "MasterDetail"}:
        lines.append("    <trackHistory>true</trackHistory>")
    if ftype == "Text":
        lines.append("    <unique>false</unique>")
    if ftype in {"LongTextArea", "Html"}:
        lines.append(f'    <visibleLines>{field.get("visibleLines", 3)}</visibleLines>')
    lines.append(f"    <type>{ftype}</type>")
    if ftype == "MasterDetail":
        lines.append(
            f'    <writeRequiresMasterRead>{str(field.get("writeRequiresMasterRead", False)).lower()}</writeRequiresMasterRead>'
        )
    if ftype == "Picklist":
        default = field.get("default")
        lines.append("    <valueSet>")
        lines.append(f'        <restricted>{str(field.get("restricted", True)).lower()}</restricted>')
        lines.append("        <valueSetDefinition>")
        lines.append("            <sorted>false</sorted>")
        for i, value in enumerate(field["values"]):
            if isinstance(value, str):
                full_name, label = value, value
            else:
                full_name, label = value
            is_default = (full_name == default) if default is not None else i == 0
            lines.append("            <value>")
            lines.append(f"                <fullName>{escape(full_name)}</fullName>")
            lines.append(f"                <default>{str(is_default).lower()}</default>")
            lines.append(f"                <label>{escape(label)}</label>")
            lines.append("            </value>")
        lines.append("        </valueSetDefinition>")
        lines.append("    </valueSet>")
    lines.append("</CustomField>")
    return xml("\n".join(lines))


def object_xml(obj: dict) -> str:
    md_child = any(f["type"] == "MasterDetail" for f in obj["fields"])
    sharing = "ControlledByParent" if md_child else obj.get("sharing", "ReadWrite")
    name = obj["nameField"]
    lines = [
        f'<CustomObject xmlns="{NS}">',
        "    <deploymentStatus>Deployed</deploymentStatus>",
        f'    <description>{escape(obj["description"])}</description>',
        "    <enableActivities>true</enableActivities>",
        "    <enableBulkApi>true</enableBulkApi>",
        "    <enableFeeds>true</enableFeeds>",
        "    <enableHistory>true</enableHistory>",
        "    <enableLicensing>false</enableLicensing>",
        "    <enableReports>true</enableReports>",
        "    <enableSearch>true</enableSearch>",
        "    <enableSharing>true</enableSharing>",
        "    <enableStreamingApi>true</enableStreamingApi>",
        f"    <externalSharingModel>{sharing}</externalSharingModel>",
        f'    <label>{escape(obj["label"])}</label>',
        "    <nameField>",
    ]
    if name["type"] == "AutoNumber":
        lines.append(f'        <displayFormat>{escape(name["displayFormat"])}</displayFormat>')
        lines.append(f'        <label>{escape(name["label"])}</label>')
        lines.append("        <type>AutoNumber</type>")
    else:
        lines.append(f'        <label>{escape(name["label"])}</label>')
        lines.append("        <trackHistory>true</trackHistory>")
        lines.append("        <type>Text</type>")
    lines += [
        "    </nameField>",
        f'    <pluralLabel>{escape(obj["plural"])}</pluralLabel>',
        f"    <sharingModel>{sharing}</sharingModel>",
        "    <visibility>Public</visibility>",
        "</CustomObject>",
    ]
    return xml("\n".join(lines))


def compact_xml(api: str, label: str, fields: list[str]) -> str:
    body = "\n".join(
        [
            f'<CompactLayout xmlns="{NS}">',
            f"    <fullName>{api}</fullName>",
            *[f"    <fields>{f}</fields>" for f in fields],
            f"    <label>{escape(label)}</label>",
            "</CompactLayout>",
        ]
    )
    return xml(body)


def listview_xml(columns: list[str], label: str = "All") -> str:
    body = "\n".join(
        [
            f'<ListView xmlns="{NS}">',
            "    <fullName>All</fullName>",
            *[f"    <columns>{col}</columns>" for col in columns],
            "    <filterScope>Everything</filterScope>",
            f"    <label>{escape(label)}</label>",
            "</ListView>",
        ]
    )
    return xml(body)


def validation_xml(rule: dict) -> str:
    body = "\n".join(
        [
            f'<ValidationRule xmlns="{NS}">',
            f'    <fullName>{rule["api"]}</fullName>',
            "    <active>true</active>",
            f'    <errorConditionFormula>{escape(rule["formula"])}</errorConditionFormula>',
            f'    <errorDisplayField>{rule["field"]}</errorDisplayField>' if rule.get("field") else "",
            f'    <errorMessage>{escape(rule["message"])}</errorMessage>',
            "</ValidationRule>",
        ]
    )
    body = "\n".join(ln for ln in body.split("\n") if ln != "")
    return xml(body)


def tab_xml(obj_api: str, motif: str) -> str:
    return xml(
        "\n".join(
            [
                f'<CustomTab xmlns="{NS}">',
                "    <customObject>true</customObject>",
                f"    <motif>{motif}</motif>",
                "</CustomTab>",
            ]
        )
    )


# ---------------------------------------------------------------------------
# Model definition
# ---------------------------------------------------------------------------

CUSTOM_OBJECTS = [
    {
        "api": "Supplier_Application__c",
        "label": "Supplier Application",
        "plural": "Supplier Applications",
        "description": "Onboarding application submitted by or on behalf of a supplier Account.",
        "nameField": {"type": "AutoNumber", "label": "Application Number", "displayFormat": "SA-{00000}"},
        "tabMotif": "Custom57: Hands",
        "compact": ["Name", "Account__c", "Status__c", "Submitted_Date__c"],
        "list": ["NAME", "Account__c", "Status__c", "Submitted_Date__c"],
        "fields": [
            {
                "api": "Account__c",
                "label": "Account",
                "type": "Lookup",
                "referenceTo": "Account",
                "relationshipName": "Supplier_Applications",
                "relationshipLabel": "Supplier Applications",
                "deleteConstraint": "Restrict",
                "required": True,
                "description": "Supplier Account this application belongs to.",
                "trackHistory": True,
            },
            {
                "api": "Status__c",
                "label": "Status",
                "type": "Picklist",
                "values": ["Draft", "Submitted", "Under Review", "Approved", "Rejected", "Withdrawn"],
                "default": "Draft",
                "required": True,
                "trackHistory": True,
            },
            {
                "api": "Application_Type__c",
                "label": "Application Type",
                "type": "Picklist",
                "values": ["New Supplier", "Reactivation", "Category Expansion"],
                "default": "New Supplier",
                "required": True,
            },
            {"api": "Submitted_Date__c", "label": "Submitted Date", "type": "Date"},
            {"api": "Approved_Date__c", "label": "Approved Date", "type": "Date"},
            {
                "api": "Reviewed_By__c",
                "label": "Reviewed By",
                "type": "Lookup",
                "referenceTo": "User",
                "relationshipName": "Supplier_Applications_Reviewed",
                "relationshipLabel": "Supplier Applications Reviewed",
                "deleteConstraint": "SetNull",
            },
            {"api": "Notes__c", "label": "Notes", "type": "LongTextArea", "length": 32768, "visibleLines": 4},
        ],
        "validations": [
            {
                "api": "Approved_Requires_Date",
                "formula": 'ISPICKVAL(Status__c, "Approved") && ISBLANK(Approved_Date__c)',
                "field": "Approved_Date__c",
                "message": "Approved Date is required when Status is Approved.",
            }
        ],
    },
    {
        "api": "FD_Certificate__c",
        "label": "F&D Certificate",
        "plural": "F&D Certificates",
        "description": "Food and drink compliance certificate held by a supplier Account.",
        "nameField": {"type": "AutoNumber", "label": "Certificate Number", "displayFormat": "CERT-{00000}"},
        "tabMotif": "Custom14: Handshake",
        "compact": ["Name", "Account__c", "Certificate_Type__c", "Status__c", "Expiry_Date__c"],
        "list": ["NAME", "Account__c", "Certificate_Type__c", "Status__c", "Expiry_Date__c"],
        "fields": [
            {
                "api": "Account__c",
                "label": "Account",
                "type": "MasterDetail",
                "referenceTo": "Account",
                "relationshipName": "FD_Certificates",
                "relationshipLabel": "F&D Certificates",
                "description": "Supplier Account that holds this certificate.",
                "trackHistory": True,
            },
            {
                "api": "Certificate_Type__c",
                "label": "Certificate Type",
                "type": "Picklist",
                "values": [
                    "Food Hygiene",
                    "HACCP",
                    "Organic",
                    "Allergen",
                    "Halal",
                    "Kosher",
                    "BRC",
                    "Other",
                ],
                "required": True,
                "trackHistory": True,
            },
            {
                "api": "External_Certificate_No__c",
                "label": "External Certificate No",
                "type": "Text",
                "length": 80,
            },
            {"api": "Issuing_Body__c", "label": "Issuing Body", "type": "Text", "length": 120},
            {"api": "Issue_Date__c", "label": "Issue Date", "type": "Date", "required": True},
            {"api": "Expiry_Date__c", "label": "Expiry Date", "type": "Date", "required": True, "trackHistory": True},
            {
                "api": "Status__c",
                "label": "Status",
                "type": "Picklist",
                "values": ["Valid", "Expiring Soon", "Expired", "Revoked"],
                "default": "Valid",
                "required": True,
                "trackHistory": True,
            },
            {"api": "Document_URL__c", "label": "Document URL", "type": "Url"},
        ],
        "validations": [
            {
                "api": "Expiry_After_Issue",
                "formula": "Expiry_Date__c < Issue_Date__c",
                "field": "Expiry_Date__c",
                "message": "Expiry Date must be on or after Issue Date.",
            }
        ],
    },
    {
        "api": "Supplier_Catalogue__c",
        "label": "Supplier Catalogue",
        "plural": "Supplier Catalogues",
        "description": "Sellable catalogue published by a supplier Account.",
        "nameField": {"type": "Text", "label": "Catalogue Name"},
        "tabMotif": "Custom43: Books",
        "compact": ["Name", "Account__c", "Status__c", "Effective_From__c"],
        "list": ["NAME", "Account__c", "Status__c", "Effective_From__c", "Effective_To__c"],
        "fields": [
            {
                "api": "Account__c",
                "label": "Account",
                "type": "Lookup",
                "referenceTo": "Account",
                "relationshipName": "Supplier_Catalogues",
                "relationshipLabel": "Supplier Catalogues",
                "deleteConstraint": "Restrict",
                "required": True,
                "description": "Supplier Account that owns this catalogue.",
                "trackHistory": True,
            },
            {
                "api": "Status__c",
                "label": "Status",
                "type": "Picklist",
                "values": ["Draft", "Active", "Seasonal", "Retired"],
                "default": "Draft",
                "required": True,
                "trackHistory": True,
            },
            {"api": "Effective_From__c", "label": "Effective From", "type": "Date"},
            {"api": "Effective_To__c", "label": "Effective To", "type": "Date"},
            {"api": "Currency_Code__c", "label": "Currency Code", "type": "Text", "length": 3},
            {"api": "Description__c", "label": "Description", "type": "LongTextArea", "length": 32768, "visibleLines": 3},
        ],
        "validations": [
            {
                "api": "Effective_To_After_From",
                "formula": "NOT(ISBLANK(Effective_To__c)) && NOT(ISBLANK(Effective_From__c)) && Effective_To__c < Effective_From__c",
                "field": "Effective_To__c",
                "message": "Effective To must be on or after Effective From.",
            }
        ],
    },
    {
        "api": "Supplier_Catalogue_Item__c",
        "label": "Supplier Catalogue Item",
        "plural": "Supplier Catalogue Items",
        "description": "Line item offered in a supplier catalogue. Nested under Supplier Catalogue on the whiteboard.",
        "nameField": {"type": "Text", "label": "Item Name"},
        "tabMotif": "Custom20: Basket",
        "compact": ["Name", "Supplier_Catalogue__c", "SKU__c", "Unit_Price__c", "Is_Active__c"],
        "list": ["NAME", "Supplier_Catalogue__c", "SKU__c", "Unit_Price__c", "Is_Active__c"],
        "fields": [
            {
                "api": "Supplier_Catalogue__c",
                "label": "Supplier Catalogue",
                "type": "MasterDetail",
                "referenceTo": "Supplier_Catalogue__c",
                "relationshipName": "Catalogue_Items",
                "relationshipLabel": "Catalogue Items",
                "description": "Parent catalogue for this item.",
            },
            {
                "api": "Product__c",
                "label": "Product",
                "type": "Lookup",
                "referenceTo": "Product2",
                "relationshipName": "Catalogue_Items",
                "relationshipLabel": "Supplier Catalogue Items",
                "deleteConstraint": "SetNull",
                "description": "Optional link to the standard Product catalog.",
            },
            {"api": "SKU__c", "label": "SKU", "type": "Text", "length": 80, "required": True},
            {"api": "Unit_Price__c", "label": "Unit Price", "type": "Currency", "precision": 18, "scale": 2, "required": True},
            {
                "api": "Unit_of_Measure__c",
                "label": "Unit of Measure",
                "type": "Picklist",
                "values": ["Each", "Case", "Kg", "Litre", "Pallet", "Pack"],
                "default": "Each",
                "required": True,
            },
            {"api": "Minimum_Order_Qty__c", "label": "Minimum Order Qty", "type": "Number", "precision": 12, "scale": 2},
            {"api": "Is_Active__c", "label": "Active", "type": "Checkbox", "defaultValue": True},
            {"api": "Description__c", "label": "Description", "type": "LongTextArea", "length": 32768, "visibleLines": 3},
        ],
        "validations": [
            {
                "api": "Price_Non_Negative",
                "formula": "Unit_Price__c < 0",
                "field": "Unit_Price__c",
                "message": "Unit Price cannot be negative.",
            }
        ],
    },
    {
        "api": "Pickup_Delivery_Schedule__c",
        "label": "Pickup Delivery Schedule",
        "plural": "Pickup Delivery Schedules",
        "description": "Standing pickup or delivery window for a supplier or customer Account.",
        "nameField": {"type": "Text", "label": "Schedule Name"},
        "tabMotif": "Custom25: Clock",
        "compact": ["Name", "Account__c", "Schedule_Type__c", "Day_of_Week__c", "Is_Active__c"],
        "list": ["NAME", "Account__c", "Schedule_Type__c", "Day_of_Week__c", "Window_Start__c", "Window_End__c"],
        "fields": [
            {
                "api": "Account__c",
                "label": "Account",
                "type": "Lookup",
                "referenceTo": "Account",
                "relationshipName": "Pickup_Delivery_Schedules",
                "relationshipLabel": "Pickup Delivery Schedules",
                "deleteConstraint": "Restrict",
                "required": True,
                "description": "Account this standing schedule applies to.",
            },
            {
                "api": "Schedule_Type__c",
                "label": "Schedule Type",
                "type": "Picklist",
                "values": ["Pickup", "Delivery"],
                "required": True,
            },
            {
                "api": "Day_of_Week__c",
                "label": "Day of Week",
                "type": "Picklist",
                "values": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                "required": True,
            },
            {"api": "Window_Start__c", "label": "Window Start", "type": "Time", "required": True},
            {"api": "Window_End__c", "label": "Window End", "type": "Time", "required": True},
            {"api": "Location__c", "label": "Location", "type": "Text", "length": 255},
            {"api": "Is_Active__c", "label": "Active", "type": "Checkbox", "defaultValue": True},
        ],
        "validations": [
            {
                "api": "Window_End_After_Start",
                "formula": "Window_End__c <= Window_Start__c",
                "field": "Window_End__c",
                "message": "Window End must be after Window Start.",
            }
        ],
    },
    {
        "api": "Delivery_Schedule__c",
        "label": "Delivery Schedule",
        "plural": "Delivery Schedules",
        "description": "Contracted delivery cadence for a customer Contract.",
        "nameField": {"type": "Text", "label": "Schedule Name"},
        "tabMotif": "Custom9: Car",
        "compact": ["Name", "Contract__c", "Frequency__c", "Status__c"],
        "list": ["NAME", "Contract__c", "Frequency__c", "Start_Date__c", "End_Date__c", "Status__c"],
        "fields": [
            {
                "api": "Contract__c",
                "label": "Contract",
                "type": "MasterDetail",
                "referenceTo": "Contract",
                "relationshipName": "Delivery_Schedules",
                "relationshipLabel": "Delivery Schedules",
                "description": "Customer contract this schedule is attached to.",
            },
            {
                "api": "Frequency__c",
                "label": "Frequency",
                "type": "Picklist",
                "values": ["Daily", "Weekly", "Fortnightly", "Monthly"],
                "required": True,
            },
            {
                "api": "Delivery_Day__c",
                "label": "Delivery Day",
                "type": "Picklist",
                "values": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            },
            {"api": "Start_Date__c", "label": "Start Date", "type": "Date", "required": True},
            {"api": "End_Date__c", "label": "End Date", "type": "Date"},
            {
                "api": "Status__c",
                "label": "Status",
                "type": "Picklist",
                "values": ["Draft", "Active", "Suspended", "Completed"],
                "default": "Draft",
                "required": True,
                "trackHistory": True,
            },
            {"api": "Notes__c", "label": "Notes", "type": "LongTextArea", "length": 32768, "visibleLines": 3},
        ],
        "validations": [
            {
                "api": "End_After_Start",
                "formula": "NOT(ISBLANK(End_Date__c)) && End_Date__c < Start_Date__c",
                "field": "End_Date__c",
                "message": "End Date must be on or after Start Date.",
            }
        ],
    },
    {
        "api": "Volume_Discount_Tier__c",
        "label": "Volume Discount Tier",
        "plural": "Volume Discount Tiers",
        "description": "Quantity break and discount percent on a Contract.",
        "nameField": {"type": "Text", "label": "Tier Name"},
        "tabMotif": "Custom41: Credit Card",
        "compact": ["Name", "Contract__c", "Min_Quantity__c", "Max_Quantity__c", "Discount_Percent__c"],
        "list": ["NAME", "Contract__c", "Min_Quantity__c", "Max_Quantity__c", "Discount_Percent__c"],
        "fields": [
            {
                "api": "Contract__c",
                "label": "Contract",
                "type": "MasterDetail",
                "referenceTo": "Contract",
                "relationshipName": "Volume_Discount_Tiers",
                "relationshipLabel": "Volume Discount Tiers",
            },
            {"api": "Min_Quantity__c", "label": "Min Quantity", "type": "Number", "precision": 12, "scale": 2, "required": True},
            {"api": "Max_Quantity__c", "label": "Max Quantity", "type": "Number", "precision": 12, "scale": 2},
            {
                "api": "Discount_Percent__c",
                "label": "Discount Percent",
                "type": "Percent",
                "precision": 5,
                "scale": 2,
                "required": True,
            },
            {"api": "Sequence__c", "label": "Sequence", "type": "Number", "precision": 3, "scale": 0, "required": True},
            {"api": "Is_Active__c", "label": "Active", "type": "Checkbox", "defaultValue": True},
        ],
        "validations": [
            {
                "api": "Max_Gte_Min",
                "formula": "NOT(ISBLANK(Max_Quantity__c)) && Max_Quantity__c < Min_Quantity__c",
                "field": "Max_Quantity__c",
                "message": "Max Quantity must be greater than or equal to Min Quantity.",
            },
            {
                "api": "Discount_Range",
                "formula": "Discount_Percent__c < 0 || Discount_Percent__c > 100",
                "field": "Discount_Percent__c",
                "message": "Discount Percent must be between 0 and 100.",
            },
        ],
    },
    {
        "api": "Commitment_Process__c",
        "label": "Commitment Process",
        "plural": "Commitment Processes",
        "description": "Service commitment process tied to an Entitlement. Analogous to an Entitlement Process, stored as data.",
        "nameField": {"type": "AutoNumber", "label": "Process Number", "displayFormat": "CP-{00000}"},
        "tabMotif": "Custom15: Gantt Chart",
        "compact": ["Name", "Entitlement__c", "Account__c", "Status__c"],
        "list": ["NAME", "Entitlement__c", "Account__c", "Status__c", "Start_Date__c", "End_Date__c"],
        "fields": [
            {
                "api": "Entitlement__c",
                "label": "Entitlement",
                "type": "Lookup",
                "referenceTo": "Entitlement",
                "relationshipName": "Commitment_Processes",
                "relationshipLabel": "Commitment Processes",
                "deleteConstraint": "Restrict",
                "required": True,
                "description": "Entitlement this commitment process implements.",
                "trackHistory": True,
            },
            {
                "api": "Account__c",
                "label": "Account",
                "type": "Lookup",
                "referenceTo": "Account",
                "relationshipName": "Commitment_Processes",
                "relationshipLabel": "Commitment Processes",
                "deleteConstraint": "SetNull",
                "description": "Account copied from the Entitlement for reporting.",
            },
            {
                "api": "Status__c",
                "label": "Status",
                "type": "Picklist",
                "values": ["Draft", "Active", "Paused", "Completed", "Cancelled"],
                "default": "Draft",
                "required": True,
                "trackHistory": True,
            },
            {
                "api": "Commitment_Type__c",
                "label": "Commitment Type",
                "type": "Picklist",
                "values": ["SLA", "Volume", "Service Level", "On-Time Delivery"],
                "required": True,
            },
            {"api": "Start_Date__c", "label": "Start Date", "type": "Date", "required": True},
            {"api": "End_Date__c", "label": "End Date", "type": "Date"},
            {"api": "Description__c", "label": "Description", "type": "LongTextArea", "length": 32768, "visibleLines": 3},
        ],
        "validations": [
            {
                "api": "End_After_Start",
                "formula": "NOT(ISBLANK(End_Date__c)) && End_Date__c < Start_Date__c",
                "field": "End_Date__c",
                "message": "End Date must be on or after Start Date.",
            }
        ],
    },
    {
        "api": "Commitment_Milestone__c",
        "label": "Commitment Milestone",
        "plural": "Commitment Milestones",
        "description": "Timed milestone within a Commitment Process. Whiteboard: Milestones.",
        "nameField": {"type": "Text", "label": "Milestone Name"},
        "tabMotif": "Custom16: Gantt Chart",
        "compact": ["Name", "Commitment_Process__c", "Due_Date__c", "Status__c"],
        "list": ["NAME", "Commitment_Process__c", "Sequence__c", "Due_Date__c", "Status__c"],
        "fields": [
            {
                "api": "Commitment_Process__c",
                "label": "Commitment Process",
                "type": "MasterDetail",
                "referenceTo": "Commitment_Process__c",
                "relationshipName": "Commitment_Milestones",
                "relationshipLabel": "Commitment Milestones",
            },
            {"api": "Sequence__c", "label": "Sequence", "type": "Number", "precision": 3, "scale": 0, "required": True},
            {"api": "Due_Date__c", "label": "Due Date", "type": "Date", "required": True, "trackHistory": True},
            {"api": "Completed_Date__c", "label": "Completed Date", "type": "Date", "trackHistory": True},
            {
                "api": "Status__c",
                "label": "Status",
                "type": "Picklist",
                "values": ["Not Started", "In Progress", "Completed", "Missed", "Waived"],
                "default": "Not Started",
                "required": True,
                "trackHistory": True,
            },
            {"api": "Target_Hours__c", "label": "Target Hours", "type": "Number", "precision": 8, "scale": 2},
            {"api": "Notes__c", "label": "Notes", "type": "LongTextArea", "length": 32768, "visibleLines": 3},
        ],
        "validations": [
            {
                "api": "Completed_Requires_Date",
                "formula": 'ISPICKVAL(Status__c, "Completed") && ISBLANK(Completed_Date__c)',
                "field": "Completed_Date__c",
                "message": "Completed Date is required when Status is Completed.",
            }
        ],
    },
    {
        "api": "Invoice__c",
        "label": "Invoice",
        "plural": "Invoices",
        "description": "Customer invoice for an Order. Use standard Invoice if Revenue Cloud / Billing is licensed.",
        "nameField": {"type": "AutoNumber", "label": "Invoice Number", "displayFormat": "INV-{00000}"},
        "tabMotif": "Custom41: Credit Card",
        "compact": ["Name", "Account__c", "Order__c", "Status__c", "Amount__c"],
        "list": ["NAME", "Account__c", "Order__c", "Invoice_Date__c", "Amount__c", "Status__c"],
        "fields": [
            {
                "api": "Order__c",
                "label": "Order",
                "type": "MasterDetail",
                "referenceTo": "Order",
                "relationshipName": "Invoices",
                "relationshipLabel": "Invoices",
                "description": "Order this invoice bills.",
                "trackHistory": True,
            },
            {
                "api": "Account__c",
                "label": "Account",
                "type": "Lookup",
                "referenceTo": "Account",
                "relationshipName": "Invoices",
                "relationshipLabel": "Invoices",
                "deleteConstraint": "Restrict",
                "required": True,
                "description": "Bill-to Account. Should match the Order Account.",
            },
            {"api": "Invoice_Date__c", "label": "Invoice Date", "type": "Date", "required": True},
            {"api": "Due_Date__c", "label": "Due Date", "type": "Date", "required": True},
            {"api": "Amount__c", "label": "Amount", "type": "Currency", "precision": 18, "scale": 2, "required": True},
            {"api": "Tax_Amount__c", "label": "Tax Amount", "type": "Currency", "precision": 18, "scale": 2},
            {
                "api": "Status__c",
                "label": "Status",
                "type": "Picklist",
                "values": ["Draft", "Issued", "Partially Paid", "Paid", "Overdue", "Void"],
                "default": "Draft",
                "required": True,
                "trackHistory": True,
            },
            {"api": "Paid_Date__c", "label": "Paid Date", "type": "Date"},
            {"api": "External_Invoice_No__c", "label": "External Invoice No", "type": "Text", "length": 80},
        ],
        "validations": [
            {
                "api": "Due_After_Invoice",
                "formula": "Due_Date__c < Invoice_Date__c",
                "field": "Due_Date__c",
                "message": "Due Date must be on or after Invoice Date.",
            },
            {
                "api": "Paid_Requires_Date",
                "formula": 'ISPICKVAL(Status__c, "Paid") && ISBLANK(Paid_Date__c)',
                "field": "Paid_Date__c",
                "message": "Paid Date is required when Status is Paid.",
            },
        ],
    },
    {
        "api": "Fulfillment_Order__c",
        "label": "Fulfillment Order",
        "plural": "Fulfillment Orders",
        "description": "Warehouse fulfillment request split from an Order. Maps to FulfillmentOrder when Order Management is licensed.",
        "nameField": {"type": "AutoNumber", "label": "Fulfillment Number", "displayFormat": "FO-{00000}"},
        "tabMotif": "Custom55: Truck",
        "compact": ["Name", "Order__c", "Account__c", "Status__c"],
        "list": ["NAME", "Order__c", "Account__c", "Status__c", "Requested_Date__c"],
        "fields": [
            {
                "api": "Order__c",
                "label": "Order",
                "type": "MasterDetail",
                "referenceTo": "Order",
                "relationshipName": "Fulfillment_Orders",
                "relationshipLabel": "Fulfillment Orders",
                "description": "Sales order being fulfilled.",
            },
            {
                "api": "Account__c",
                "label": "Account",
                "type": "Lookup",
                "referenceTo": "Account",
                "relationshipName": "Fulfillment_Orders",
                "relationshipLabel": "Fulfillment Orders",
                "deleteConstraint": "SetNull",
                "description": "Ship-to / sold-to Account from the Order.",
            },
            {
                "api": "Status__c",
                "label": "Status",
                "type": "Picklist",
                "values": ["Draft", "Allocated", "Picked", "Packed", "Shipped", "Complete", "Cancelled"],
                "default": "Draft",
                "required": True,
                "trackHistory": True,
            },
            {"api": "Requested_Date__c", "label": "Requested Date", "type": "Date"},
            {"api": "Fulfilled_Date__c", "label": "Fulfilled Date", "type": "Date"},
            {"api": "Warehouse__c", "label": "Warehouse", "type": "Text", "length": 120},
            {"api": "Notes__c", "label": "Notes", "type": "LongTextArea", "length": 32768, "visibleLines": 3},
        ],
        "validations": [],
    },
    {
        "api": "Shipment_Lot__c",
        "label": "Shipment Lot",
        "plural": "Shipment Lots",
        "description": "Physical lot / consignment shipped for an Order, optionally from a Fulfillment Order.",
        "nameField": {"type": "AutoNumber", "label": "Lot Number", "displayFormat": "LOT-{00000}"},
        "tabMotif": "Custom56: Truck",
        "compact": ["Name", "Order__c", "Status__c", "Ship_Date__c"],
        "list": ["NAME", "Order__c", "Fulfillment_Order__c", "Status__c", "Ship_Date__c", "Tracking_Number__c"],
        "fields": [
            {
                "api": "Order__c",
                "label": "Order",
                "type": "MasterDetail",
                "referenceTo": "Order",
                "relationshipName": "Shipment_Lots",
                "relationshipLabel": "Shipment Lots",
            },
            {
                "api": "Fulfillment_Order__c",
                "label": "Fulfillment Order",
                "type": "Lookup",
                "referenceTo": "Fulfillment_Order__c",
                "relationshipName": "Shipment_Lots",
                "relationshipLabel": "Shipment Lots",
                "deleteConstraint": "SetNull",
                "description": "Optional fulfillment order this lot was packed from.",
            },
            {"api": "External_Lot_No__c", "label": "External Lot No", "type": "Text", "length": 80},
            {
                "api": "Status__c",
                "label": "Status",
                "type": "Picklist",
                "values": ["Open", "Packed", "Shipped", "In Transit", "Delivered", "Exception"],
                "default": "Open",
                "required": True,
                "trackHistory": True,
            },
            {"api": "Ship_Date__c", "label": "Ship Date", "type": "Date"},
            {"api": "Carrier__c", "label": "Carrier", "type": "Text", "length": 80},
            {"api": "Tracking_Number__c", "label": "Tracking Number", "type": "Text", "length": 80},
            {"api": "Package_Count__c", "label": "Package Count", "type": "Number", "precision": 6, "scale": 0},
        ],
        "validations": [],
    },
    {
        "api": "Delivery_Note__c",
        "label": "Delivery Note",
        "plural": "Delivery Notes",
        "description": "Proof-of-delivery document for a Shipment Lot. Marked custom on the whiteboard.",
        "nameField": {"type": "AutoNumber", "label": "Delivery Note Number", "displayFormat": "DN-{00000}"},
        "tabMotif": "Custom48: Document",
        "compact": ["Name", "Shipment_Lot__c", "Delivery_Date__c", "Status__c"],
        "list": ["NAME", "Shipment_Lot__c", "Delivery_Date__c", "Recipient_Name__c", "Status__c"],
        "fields": [
            {
                "api": "Shipment_Lot__c",
                "label": "Shipment Lot",
                "type": "MasterDetail",
                "referenceTo": "Shipment_Lot__c",
                "relationshipName": "Delivery_Notes",
                "relationshipLabel": "Delivery Notes",
                "description": "Shipment lot this delivery note confirms.",
            },
            {"api": "Delivery_Date__c", "label": "Delivery Date", "type": "Date", "required": True, "trackHistory": True},
            {"api": "Recipient_Name__c", "label": "Recipient Name", "type": "Text", "length": 120},
            {
                "api": "Status__c",
                "label": "Status",
                "type": "Picklist",
                "values": ["Draft", "Issued", "Signed", "Disputed"],
                "default": "Draft",
                "required": True,
                "trackHistory": True,
            },
            {"api": "Proof_of_Delivery__c", "label": "Proof of Delivery", "type": "Checkbox", "defaultValue": False},
            {"api": "Exception_Notes__c", "label": "Exception Notes", "type": "LongTextArea", "length": 32768, "visibleLines": 3},
        ],
        "validations": [
            {
                "api": "Signed_Requires_POD",
                "formula": 'ISPICKVAL(Status__c, "Signed") && Proof_of_Delivery__c = FALSE',
                "field": "Proof_of_Delivery__c",
                "message": "Proof of Delivery must be checked when Status is Signed.",
            }
        ],
    },
]


STANDARD_FIELDS = {
    "Account": [
        {
            "api": "Account_Type__c",
            "label": "Account Type",
            "type": "Picklist",
            "values": ["Customer", "Supplier", "Both"],
            "description": "Whether this Account is a buying customer, a supplying vendor, or both.",
            "trackHistory": True,
        },
        {
            "api": "Supplier_Status__c",
            "label": "Supplier Status",
            "type": "Picklist",
            "values": ["Not Applicable", "Applicant", "Active", "Suspended", "Offboarded"],
            "default": "Not Applicable",
            "description": "Lifecycle status when the Account is a supplier.",
            "trackHistory": True,
        },
        {
            "api": "Customer_Status__c",
            "label": "Customer Status",
            "type": "Picklist",
            "values": ["Not Applicable", "Prospect", "Active", "Inactive"],
            "default": "Not Applicable",
            "trackHistory": True,
        },
    ],
    "Contract": [
        {
            "api": "Volume_Commitment__c",
            "label": "Volume Commitment",
            "type": "Number",
            "precision": 18,
            "scale": 2,
            "description": "Committed volume for discount and entitlement calculations.",
        },
        {
            "api": "Delivery_Terms__c",
            "label": "Delivery Terms",
            "type": "Text",
            "length": 255,
        },
    ],
    "Order": [
        {
            "api": "Requested_Delivery_Date__c",
            "label": "Requested Delivery Date",
            "type": "Date",
        },
        {
            "api": "Delivery_Instructions__c",
            "label": "Delivery Instructions",
            "type": "LongTextArea",
            "length": 32768,
            "visibleLines": 3,
        },
    ],
    "Entitlement": [
        {
            "api": "Contract__c",
            "label": "Sales Contract",
            "type": "Lookup",
            "referenceTo": "Contract",
            "relationshipName": "Entitlements",
            "relationshipLabel": "Entitlements",
            "deleteConstraint": "SetNull",
            "description": "Optional link from the service Entitlement to the commercial Contract.",
        }
    ],
}

ACCOUNT_RECORD_TYPES = [
    ("Customer", "Buying customer Account."),
    ("Supplier", "Supplying vendor Account."),
]


def record_type_xml(full_name: str, description: str) -> str:
    defaults = {
        "Customer": {
            "Account_Type__c": "Customer",
            "Supplier_Status__c": "Not Applicable",
            "Customer_Status__c": "Prospect",
        },
        "Supplier": {
            "Account_Type__c": "Supplier",
            "Supplier_Status__c": "Applicant",
            "Customer_Status__c": "Not Applicable",
        },
    }
    picklists = []
    for field in STANDARD_FIELDS["Account"]:
        if field["type"] != "Picklist":
            continue
        values_xml = []
        default_value = defaults[full_name][field["api"]]
        for value in field["values"]:
            values_xml.append(
                "\n".join(
                    [
                        "        <values>",
                        f"            <fullName>{escape(value)}</fullName>",
                        f'            <default>{str(value == default_value).lower()}</default>',
                        "        </values>",
                    ]
                )
            )
        picklists.append(
            "    <picklistValues>\n        <picklist>"
            + field["api"]
            + "</picklist>\n"
            + "\n".join(values_xml)
            + "\n    </picklistValues>"
        )
    body = "\n".join(
        [
            f'<RecordType xmlns="{NS}">',
            f"    <fullName>{full_name}</fullName>",
            "    <active>true</active>",
            f"    <description>{escape(description)}</description>",
            f"    <label>{full_name}</label>",
            *picklists,
            "</RecordType>",
        ]
    )
    return xml(body)


def permission_set_xml() -> str:
    lines = [
        f'<PermissionSet xmlns="{NS}">',
        "    <description>Create and maintain the supply-operations data model objects.</description>",
        "    <hasActivationRequired>false</hasActivationRequired>",
        "    <label>Supply Operations User</label>",
    ]
    # Custom fields on standard objects
    for obj_api, fields in STANDARD_FIELDS.items():
        for field in fields:
            if field.get("required") and field["type"] != "MasterDetail":
                continue
            if field["type"] == "MasterDetail":
                continue
            lines += [
                "    <fieldPermissions>",
                "        <editable>true</editable>",
                f'        <field>{obj_api}.{field["api"]}</field>',
                "        <readable>true</readable>",
                "    </fieldPermissions>",
            ]
    for obj in CUSTOM_OBJECTS:
        for field in obj["fields"]:
            if field["type"] in {"MasterDetail"}:
                continue
            if field.get("required") and field["type"] not in {"Checkbox", "Formula", "Summary"}:
                continue
            lines += [
                "    <fieldPermissions>",
                "        <editable>true</editable>",
                f'        <field>{obj["api"]}.{field["api"]}</field>',
                "        <readable>true</readable>",
                "    </fieldPermissions>",
            ]
        lines += [
            "    <objectPermissions>",
            "        <allowCreate>true</allowCreate>",
            "        <allowDelete>true</allowDelete>",
            "        <allowEdit>true</allowEdit>",
            "        <allowRead>true</allowRead>",
            "        <modifyAllRecords>true</modifyAllRecords>",
            f'        <object>{obj["api"]}</object>',
            "        <viewAllRecords>true</viewAllRecords>",
            "    </objectPermissions>",
            "    <tabSettings>",
            f'        <tab>{obj["api"]}</tab>',
            "        <visibility>Visible</visibility>",
            "    </tabSettings>",
        ]
    # Record type visibility
    for rt, _ in ACCOUNT_RECORD_TYPES:
        lines += [
            "    <recordTypeVisibilities>",
            f"        <recordType>Account.{rt}</recordType>",
            "        <visible>true</visible>",
            "    </recordTypeVisibilities>",
        ]
    lines += [
        "    <tabSettings>",
        "        <tab>standard-Account</tab>",
        "        <visibility>Visible</visibility>",
        "    </tabSettings>",
        "    <tabSettings>",
        "        <tab>standard-Contact</tab>",
        "        <visibility>Visible</visibility>",
        "    </tabSettings>",
        "    <tabSettings>",
        "        <tab>standard-Contract</tab>",
        "        <visibility>Visible</visibility>",
        "    </tabSettings>",
        "    <tabSettings>",
        "        <tab>standard-Order</tab>",
        "        <visibility>Visible</visibility>",
        "    </tabSettings>",
        "    <tabSettings>",
        "        <tab>standard-Case</tab>",
        "        <visibility>Visible</visibility>",
        "    </tabSettings>",
        "</PermissionSet>",
    ]
    return xml("\n".join(lines))


def application_xml() -> str:
    tabs = [
        "standard-home",
        "standard-Account",
        "standard-Contact",
        "standard-Contract",
        "standard-Order",
        "standard-Case",
        "standard-Entitlement",
    ] + [obj["api"] for obj in CUSTOM_OBJECTS]
    lines = [
        f'<CustomApplication xmlns="{NS}">',
        "    <defaultLandingTab>standard-home</defaultLandingTab>",
        "    <description>Customer, supplier, contract, order, and fulfillment data model from the whiteboard ERD.</description>",
        "    <formFactors>Small</formFactors>",
        "    <formFactors>Large</formFactors>",
        "    <isNavAutoTempTabsDisabled>false</isNavAutoTempTabsDisabled>",
        "    <isNavPersonalizationDisabled>false</isNavPersonalizationDisabled>",
        "    <label>Supply Operations</label>",
        "    <navType>Standard</navType>",
    ]
    for tab in tabs:
        lines.append(f"    <tabs>{tab}</tabs>")
    lines += [
        "    <uiType>Lightning</uiType>",
        "</CustomApplication>",
    ]
    return xml("\n".join(lines))


def generate() -> None:
    # Custom objects
    for obj in CUSTOM_OBJECTS:
        base = OBJ_ROOT / obj["api"]
        write(base / f'{obj["api"]}.object-meta.xml', object_xml(obj))
        for field in obj["fields"]:
            write(base / "fields" / f'{field["api"]}.field-meta.xml', field_xml(field))
        compact_name = obj["api"].replace("__c", "_Compact")
        write(
            base / "compactLayouts" / f"{compact_name}.compactLayout-meta.xml",
            compact_xml(compact_name, f'{obj["label"]} Compact', obj["compact"]),
        )
        # assign compact layout by rewriting object xml
        obj_meta = (base / f'{obj["api"]}.object-meta.xml').read_text(encoding="utf-8")
        obj_meta = obj_meta.replace(
            "<deploymentStatus>Deployed</deploymentStatus>",
            f"<compactLayoutAssignment>{compact_name}</compactLayoutAssignment>\n    <deploymentStatus>Deployed</deploymentStatus>",
        )
        (base / f'{obj["api"]}.object-meta.xml').write_text(obj_meta, encoding="utf-8")
        write(base / "listViews" / "All.listView-meta.xml", listview_xml(obj["list"]))
        for rule in obj.get("validations", []):
            write(
                base / "validationRules" / f'{rule["api"]}.validationRule-meta.xml',
                validation_xml(rule),
            )
        write(TAB_ROOT / f'{obj["api"]}.tab-meta.xml', tab_xml(obj["api"], obj["tabMotif"]))

    # Standard object custom fields / record types
    for obj_api, fields in STANDARD_FIELDS.items():
        base = OBJ_ROOT / obj_api
        for field in fields:
            write(base / "fields" / f'{field["api"]}.field-meta.xml', field_xml(field))
    for rt, desc in ACCOUNT_RECORD_TYPES:
        write(
            OBJ_ROOT / "Account" / "recordTypes" / f"{rt}.recordType-meta.xml",
            record_type_xml(rt, desc),
        )

    write(PERM_ROOT / "Supply_Operations_User.permissionset-meta.xml", permission_set_xml())
    write(APP_ROOT / "Supply_Operations.app-meta.xml", application_xml())

    print(f"Generated {len(CUSTOM_OBJECTS)} custom objects under {OBJ_ROOT}")


if __name__ == "__main__":
    generate()
