#!/usr/bin/env python3
"""Generate the Salesforce solution design Word document.

Produces: docs/Salesforce_Batch_Contact_Update_Solution.docx

The document consolidates the full solution discussed for updating child
Contacts on high-volume Account data loads, including the partial-failure
retry design.
"""

from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

CODE_FONT = "Consolas"
CODE_SHADE = "F2F2F2"
ACCENT = RGBColor(0x1F, 0x4E, 0x79)


def set_cell_background(cell, color_hex):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color_hex)
    tc_pr.append(shd)


def add_code_block(doc, code):
    """Add a shaded, monospaced, single-cell table as a code block."""
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    set_cell_background(cell, CODE_SHADE)
    # borders
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:color"), "D0D0D0")
        borders.append(el)
    tbl_pr.append(borders)

    para = cell.paragraphs[0]
    para.paragraph_format.space_after = Pt(0)
    para.paragraph_format.space_before = Pt(0)
    for i, line in enumerate(code.split("\n")):
        run = para.add_run(line)
        run.font.name = CODE_FONT
        run.font.size = Pt(9)
        r = run._element
        r.rPr.rFonts.set(qn("w:cs"), CODE_FONT)
        if i != len(code.split("\n")) - 1:
            run.add_break()
    doc.add_paragraph()


def add_bullets(doc, items):
    for it in items:
        p = doc.add_paragraph(style="List Bullet")
        _add_rich(p, it)


def add_numbered(doc, items):
    for it in items:
        p = doc.add_paragraph(style="List Number")
        _add_rich(p, it)


def _add_rich(p, text):
    """Support **bold** and `code` inline markup."""
    import re
    tokens = re.split(r"(\*\*.*?\*\*|`.*?`)", text)
    for tok in tokens:
        if not tok:
            continue
        if tok.startswith("**") and tok.endswith("**"):
            run = p.add_run(tok[2:-2])
            run.bold = True
        elif tok.startswith("`") and tok.endswith("`"):
            run = p.add_run(tok[1:-1])
            run.font.name = CODE_FONT
            run.font.size = Pt(10)
            run._element.rPr.rFonts.set(qn("w:cs"), CODE_FONT)
        else:
            p.add_run(tok)


def add_para(doc, text):
    p = doc.add_paragraph()
    _add_rich(p, text)
    return p


def add_table(doc, headers, rows):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Light Grid Accent 1"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        _add_rich(hdr[i].paragraphs[0], f"**{h}**")
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            _add_rich(cells[i].paragraphs[0], val)
    doc.add_paragraph()


def h(doc, text, level):
    heading = doc.add_heading(text, level=level)
    return heading


def build():
    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # ---- Title page ----
    title = doc.add_heading("", level=0)
    run = title.add_run("Updating Child Contacts on High-Volume Account Loads")
    run.font.color.rgb = ACCENT
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.LEFT
    srun = sub.add_run("Salesforce Solution Design — Batch Apex, Governor Limits, and Partial-Failure Retry")
    srun.italic = True
    srun.font.size = Pt(13)
    srun.font.color.rgb = RGBColor(0x40, 0x40, 0x40)
    doc.add_paragraph()

    # ---- 1. Requirement ----
    h(doc, "1. Requirement & Context", 1)
    add_para(doc,
        "A Data Loader process inserts/updates millions of records in the "
        "**Account** object. When an Account is updated, all **Contact** records "
        "related to that Account must be updated. Each Account has **more than "
        "1,000 Contacts**. The solution must respect Salesforce governor limits "
        "and be optimized for performance, throughput, and resilience under a "
        "sustained high-volume load.")

    # ---- 2. Key challenges ----
    h(doc, "2. Key Challenges & Governor Limits", 1)
    add_bullets(doc, [
        "**Volume fan-out:** 200 Accounts per Apex transaction x 1,000+ Contacts = 200,000+ child rows — far beyond the synchronous limits of 10,000 DML rows and 50,000 SOQL rows per transaction. The child update must be asynchronous and chunked.",
        "**Async concurrency:** Only **5** Batch jobs may be Active/Holding at once; the Apex flex queue caps at **100** Holding jobs.",
        "**24-hour async cap:** Async Apex executions per 24h = max(250,000, licenses x 200). Fanning out one job per load batch burns this quickly.",
        "**Row-lock contention:** Updating a Contact locks its parent Account. Touching child Contacts while Data Loader is still updating the same Accounts (especially Bulk API parallel mode) causes `UNABLE_TO_LOCK_ROW` errors.",
        "**Trigger re-fire:** Data Loader fires the Account trigger thousands of times across the load; work must not be duplicated.",
    ])

    # ---- 3. Anti-pattern ----
    h(doc, "3. Why \u201cBatch Apex from Trigger\u201d Is an Anti-Pattern", 1)
    add_para(doc,
        "Calling `Database.executeBatch()` (or enqueuing a Queueable) directly "
        "from the Account trigger on every load batch does not scale:")
    add_bullets(doc, [
        "Each of the thousands of trigger invocations would attempt to start a job, immediately hitting `Too many queued batch jobs: 5` and flex-queue-full `LimitException`, failing the load rows.",
        "Per-batch and per-account fan-out rapidly consumes the 24-hour async execution limit.",
        "Firing child updates concurrently with the ongoing Account load maximizes lock contention.",
    ])
    add_para(doc,
        "**Principle:** decouple *detecting* the change from *processing* the "
        "children, and process with a single controlled job rather than many "
        "trigger-spawned jobs.")

    # ---- 4. Recommended architecture ----
    h(doc, "4. Recommended Architecture: Detect \u2192 Queue \u2192 Process", 1)
    add_numbered(doc, [
        "Keep the Account trigger **thin** — detect only relevant field changes and record affected Account Ids into a lightweight staging queue.",
        "Process Contact updates in **one controlled Batch Apex job** whose `start()` queries all Contacts for the queued Accounts; let the batch framework chunk them.",
        "Before writing Apex, confirm DML is even required — a **cross-object formula field** may eliminate the problem entirely.",
    ])

    h(doc, "4.1 Thin Trigger — Capture Changed Account Ids Only", 2)
    add_para(doc,
        "Only enqueue when a field that actually matters to Contacts changed. "
        "This dramatically reduces downstream volume.")
    add_code_block(doc,
        "// AccountTrigger.trigger  (one trigger per object; delegate to a handler)\n"
        "trigger AccountTrigger on Account (after update) {\n"
        "    AccountTriggerHandler.handleAfterUpdate(Trigger.new, Trigger.oldMap);\n"
        "}")
    add_code_block(doc,
        "public with sharing class AccountTriggerHandler {\n"
        "    public static void handleAfterUpdate(List<Account> newList,\n"
        "                                         Map<Id, Account> oldMap) {\n"
        "        List<Contact_Update_Queue__c> queue = new List<Contact_Update_Queue__c>();\n"
        "        for (Account a : newList) {\n"
        "            Account old = oldMap.get(a.Id);\n"
        "            // Only relevant field changes -> cuts volume drastically\n"
        "            if (a.Industry != old.Industry || a.Rating != old.Rating) {\n"
        "                queue.add(new Contact_Update_Queue__c(\n"
        "                    Account__c   = a.Id,\n"
        "                    Processed__c = false\n"
        "                ));\n"
        "            }\n"
        "        }\n"
        "        if (!queue.isEmpty()) {\n"
        "            insert queue;   // fast, no async fan-out from the trigger\n"
        "        }\n"
        "    }\n"
        "}")

    h(doc, "4.2 Staging Queue Object (Contact_Update_Queue__c)", 2)
    add_para(doc,
        "A simple custom object that buffers the work. A Platform Event or "
        "Change Data Capture would also work, but a custom object is the most "
        "robust and debuggable choice for a millions-row backfill.")
    add_bullets(doc, [
        "`Account__c` (Lookup) — the changed Account.",
        "`Processed__c` (Checkbox) — marks the row as attempted.",
        "`Error__c` (Long Text, optional) — observability/retry.",
    ])

    h(doc, "4.3 One Controlled Batch Apex over Queued Accounts", 2)
    add_para(doc,
        "Query the **child** Contacts in `start()` so the framework streams and "
        "chunks up to 50 million records automatically.")
    add_code_block(doc,
        "public class ContactUpdateBatch\n"
        "        implements Database.Batchable<SObject>, Database.Stateful {\n"
        "\n"
        "    public Database.QueryLocator start(Database.BatchableContext bc) {\n"
        "        return Database.getQueryLocator([\n"
        "            SELECT Id, Some_Field__c, Account.Industry, Account.Rating\n"
        "            FROM Contact\n"
        "            WHERE Account__c IN (\n"
        "                SELECT Account__c FROM Contact_Update_Queue__c\n"
        "                WHERE Processed__c = false\n"
        "            )\n"
        "        ]);\n"
        "    }\n"
        "\n"
        "    public void execute(Database.BatchableContext bc, List<Contact> scope) {\n"
        "        for (Contact c : scope) {\n"
        "            c.Some_Field__c = c.Account.Industry;   // derive your value\n"
        "        }\n"
        "        // allOrNone = false: one bad row must not roll back the chunk\n"
        "        Database.SaveResult[] results = Database.update(scope, false);\n"
        "        // capture failures (see section 6)\n"
        "    }\n"
        "\n"
        "    public void finish(Database.BatchableContext bc) {\n"
        "        // mark queue rows processed / chain next run\n"
        "    }\n"
        "}")
    add_para(doc, "Run with a small scope so each chunk stays inside async limits:")
    add_code_block(doc,
        "Database.executeBatch(new ContactUpdateBatch(), 200); // tune 200-2000")
    add_para(doc,
        "Kick it off from **Scheduled Apex** (e.g. every 15-30 min) that checks "
        "the flex queue is clear, or run it after the load completes. Exactly "
        "**one** batch job drains the queue regardless of how many load batches fired.")

    # ---- 5. Data Loader side ----
    h(doc, "5. Handling the Data Loader Side", 1)
    add_bullets(doc, [
        "**Serial vs parallel:** Prefer Bulk API **serial** mode (or smaller batch sizes) for the Account load to reduce `UNABLE_TO_LOCK_ROW`. Group the load file by parent/owner if lock errors persist.",
        "**Timing:** Because processing is decoupled, the queue lets the load finish (or run slightly behind) before Contacts are touched — this removes most lock contention.",
        "**Idempotency / retry:** The `Processed__c` flag plus an error log lets a failed chunk be reprocessed without redoing everything.",
    ])

    # ---- 6. Optimization ----
    h(doc, "6. Optimization: Do You Need Apex at All?", 1)
    add_para(doc,
        "If the Contact field simply **reflects** Account data (for display or "
        "reporting), replace the entire solution with a **cross-object formula "
        "field** on Contact referencing `Account.Field__c`: zero DML, zero "
        "governor limits, zero batch jobs, always in sync. Use Apex only when the "
        "value must be **physically stored** (external integration, indexed "
        "filtering, history tracking) or the logic is too complex for a formula. "
        "This is the single biggest optimization for this requirement.")

    # ---- 7. Partial failure & retry ----
    h(doc, "7. Partial Failure & Retry: Reprocessing Only Failed Contacts", 1)
    add_para(doc,
        "With `allOrNone = false`, successful Contacts in a chunk are committed "
        "and failed ones are not. `Database.SaveResult[]` is returned **in the "
        "same order as the input list**, so failures are correlated by index, "
        "persisted to a dead-letter object, and retried by a separate job that "
        "distinguishes **transient** from **permanent** errors.")

    h(doc, "7.1 Capture Only the Failed Records", 2)
    add_code_block(doc,
        "public void execute(Database.BatchableContext bc, List<Contact> scope) {\n"
        "    for (Contact c : scope) {\n"
        "        c.Some_Field__c = c.Account.Industry;\n"
        "    }\n"
        "\n"
        "    Database.SaveResult[] results = Database.update(scope, false);\n"
        "\n"
        "    List<Contact_Update_Error__c> failures = new List<Contact_Update_Error__c>();\n"
        "    for (Integer i = 0; i < results.size(); i++) {\n"
        "        Database.SaveResult sr = results[i];\n"
        "        if (!sr.isSuccess()) {\n"
        "            Contact failed = scope[i];              // same index = same record\n"
        "            Database.Error err = sr.getErrors()[0];\n"
        "            failures.add(new Contact_Update_Error__c(\n"
        "                Contact__c     = failed.Id,\n"
        "                Account__c     = failed.Account__c,\n"
        "                Status_Code__c = String.valueOf(err.getStatusCode()),\n"
        "                Error__c       = err.getMessage(),\n"
        "                Fields__c      = String.join(err.getFields(), ','),\n"
        "                Retry_Count__c = 0,\n"
        "                Resolved__c    = false\n"
        "            ));\n"
        "        }\n"
        "    }\n"
        "    if (!failures.isEmpty()) {\n"
        "        insert failures;   // dead-letter queue, per-Contact\n"
        "    }\n"
        "}")
    add_para(doc,
        "The successful Contacts under the same Account are committed and simply "
        "not recorded, so retry naturally targets only the failed subset.")

    h(doc, "7.2 Dead-Letter Object (Contact_Update_Error__c)", 2)
    add_para(doc,
        "Track failures at the **Contact** level (not Account level), because "
        "\u201cfew succeeded, few failed under the same Account\u201d is exactly the case.")
    add_table(doc,
        ["Field", "Type", "Purpose"],
        [
            ["`Contact__c`", "Lookup", "The record to retry"],
            ["`Account__c`", "Lookup", "Reporting / grouping"],
            ["`Status_Code__c`", "Text", "e.g. UNABLE_TO_LOCK_ROW"],
            ["`Error__c`", "Long Text", "Error message"],
            ["`Fields__c`", "Text", "Offending fields"],
            ["`Retry_Count__c`", "Number", "Capping / backoff"],
            ["`Resolved__c`", "Checkbox", "True when a retry succeeds"],
            ["`Dead_Letter__c`", "Checkbox", "Give up -> human review"],
            ["`Last_Attempt__c`", "DateTime", "Backoff timing"],
        ])
    add_para(doc,
        "This decouples the Account queue from Contact outcomes: the "
        "`Contact_Update_Queue__c` row is marked `Processed__c = true` once its "
        "Contacts are **attempted**, while retries live independently here — no "
        "re-querying or re-updating the thousands of already-successful Contacts.")

    h(doc, "7.3 Classify: Transient vs Permanent (the crux)", 2)
    add_bullets(doc, [
        "**Transient / retry-worthy:** `UNABLE_TO_LOCK_ROW`, `UNABLE_TO_OBTAIN_LOCK`, `LOCK_TIMEOUT`, `QUERY_TIMEOUT` — succeed once contention clears.",
        "**Permanent / needs a fix:** `FIELD_CUSTOM_VALIDATION_EXCEPTION`, `REQUIRED_FIELD_MISSING`, `FIELD_INTEGRITY_EXCEPTION`, `INSUFFICIENT_ACCESS_ON_CROSS_REFERENCE_ENTITY` — retrying is pointless; flag as dead letter.",
    ])
    add_code_block(doc,
        "public class RetryClassifier {\n"
        "    private static final Set<String> TRANSIENT = new Set<String>{\n"
        "        'UNABLE_TO_LOCK_ROW', 'UNABLE_TO_OBTAIN_LOCK',\n"
        "        'LOCK_TIMEOUT', 'QUERY_TIMEOUT'\n"
        "    };\n"
        "    public static Boolean isRetryable(String statusCode) {\n"
        "        return TRANSIENT.contains(statusCode);\n"
        "    }\n"
        "}")

    h(doc, "7.4 Retry Batch (only the failed Contacts)", 2)
    add_code_block(doc,
        "public class ContactUpdateRetryBatch\n"
        "        implements Database.Batchable<SObject>, Database.Stateful {\n"
        "\n"
        "    private static final Integer MAX_RETRIES = 5;\n"
        "\n"
        "    public Database.QueryLocator start(Database.BatchableContext bc) {\n"
        "        return Database.getQueryLocator([\n"
        "            SELECT Id, Contact__c, Retry_Count__c,\n"
        "                   Contact__r.Account.Industry\n"
        "            FROM Contact_Update_Error__c\n"
        "            WHERE Resolved__c = false\n"
        "              AND Dead_Letter__c = false\n"
        "              AND Retry_Count__c < :MAX_RETRIES\n"
        "        ]);\n"
        "    }\n"
        "\n"
        "    public void execute(Database.BatchableContext bc,\n"
        "                        List<Contact_Update_Error__c> errs) {\n"
        "        Map<Id, Contact_Update_Error__c> byContact =\n"
        "            new Map<Id, Contact_Update_Error__c>();\n"
        "        List<Contact> retryContacts = new List<Contact>();\n"
        "        for (Contact_Update_Error__c e : errs) {\n"
        "            retryContacts.add(new Contact(\n"
        "                Id = e.Contact__c,\n"
        "                Some_Field__c = e.Contact__r.Account.Industry\n"
        "            ));\n"
        "            byContact.put(e.Contact__c, e);\n"
        "        }\n"
        "\n"
        "        Database.SaveResult[] results = Database.update(retryContacts, false);\n"
        "\n"
        "        List<Contact_Update_Error__c> toUpdate =\n"
        "            new List<Contact_Update_Error__c>();\n"
        "        for (Integer i = 0; i < results.size(); i++) {\n"
        "            Contact_Update_Error__c e = byContact.get(retryContacts[i].Id);\n"
        "            e.Retry_Count__c =\n"
        "                (e.Retry_Count__c == null ? 0 : e.Retry_Count__c) + 1;\n"
        "            e.Last_Attempt__c = System.now();\n"
        "            if (results[i].isSuccess()) {\n"
        "                e.Resolved__c = true;\n"
        "            } else {\n"
        "                Database.Error err = results[i].getErrors()[0];\n"
        "                e.Status_Code__c = String.valueOf(err.getStatusCode());\n"
        "                e.Error__c = err.getMessage();\n"
        "                if (!RetryClassifier.isRetryable(e.Status_Code__c)\n"
        "                    || e.Retry_Count__c >= MAX_RETRIES) {\n"
        "                    e.Dead_Letter__c = true;\n"
        "                }\n"
        "            }\n"
        "            toUpdate.add(e);\n"
        "        }\n"
        "        update toUpdate;\n"
        "    }\n"
        "\n"
        "    public void finish(Database.BatchableContext bc) {\n"
        "        // Optional: chain another run after a delay if retryable rows remain\n"
        "        // System.scheduleBatch(new ContactUpdateRetryBatch(), 'retry', 30);\n"
        "    }\n"
        "}")

    h(doc, "7.5 Backoff, Capping & Idempotency", 2)
    add_bullets(doc, [
        "**Retry cap** (`MAX_RETRIES`): anything still failing becomes a **dead letter**; report on it, never loop forever.",
        "**Delay between attempts:** schedule the retry batch on a timer (`System.scheduleBatch` in `finish()`, or Scheduled Apex). Retrying *after* Data Loader releases parent-Account locks is the whole point for `UNABLE_TO_LOCK_ROW`.",
        "**Serialize retries** (small scope, avoid parallel) so retried Contacts under the same Account don't re-collide.",
        "**Idempotency:** setting `Contact.Some_Field__c = Account.Industry` yields the same result whether run once or three times. Avoid non-idempotent logic (incrementing/appending) in anything retried, or guard it with a processed marker.",
    ])

    # ---- 8. End-to-end flow ----
    h(doc, "8. End-to-End Flow", 1)
    add_numbered(doc, [
        "`ContactUpdateBatch` updates Contacts with `allOrNone = false` -> commits good rows, writes only failures to `Contact_Update_Error__c`.",
        "The `Contact_Update_Queue__c` row is marked processed (attempted) — no re-work of successful Contacts.",
        "`ContactUpdateRetryBatch` (scheduled) drains the error object, retrying only failed Contacts, classifying transient vs permanent, incrementing `Retry_Count__c`, resolving successes, and dead-lettering the rest.",
        "A report / list view on `Dead_Letter__c = true` surfaces records needing a data or config fix.",
    ])

    # ---- 9. Decision cheat-sheet ----
    h(doc, "9. Decision Cheat-Sheet", 1)
    add_table(doc,
        ["Situation", "Best Approach"],
        [
            ["Contact field just mirrors Account data", "Cross-object **formula field** (no code)"],
            ["Must store value; event-driven from Account change", "Thin trigger -> **staging queue** -> **Scheduled Batch**"],
            ["One-time / periodic backfill of millions", "Run **Batch Apex** standalone (skip the trigger)"],
            ["Small, near-real-time, low volume", "**Queueable** from trigger (filter field changes) — not for millions"],
            ["Never", "`Database.executeBatch()` inside the trigger per load batch"],
        ])

    # ---- 10. Best-practice checklist ----
    h(doc, "10. Best-Practice Checklist", 1)
    add_bullets(doc, [
        "One trigger per object; logic in a handler class; recursion guards.",
        "Always filter on actual field changes via `Trigger.oldMap`.",
        "`Database.update(list, false)` plus failure logging for partial success.",
        "Bulkify everything; never SOQL/DML inside loops.",
        "Tune batch scope size **down** (not up) when each parent has 1,000+ children, to stay well under the 10k DML / CPU limits per chunk.",
        "Decouple detection from processing; run exactly one draining batch job.",
        "Prefer declarative (formula/roll-up) over Apex whenever the value only needs to be reflected.",
    ])

    out = "docs/Salesforce_Batch_Contact_Update_Solution.docx"
    doc.save(out)
    print(f"Wrote {out}")


if __name__ == "__main__":
    build()
