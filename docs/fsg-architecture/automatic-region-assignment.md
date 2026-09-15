# Automatic Account-to-region assignment

**Applies to:** FreshSource Global (FSG) on Salesforce Core + Experience Cloud LWR + B2B Commerce + Order Management  
**Companion to:** [FSG_ENTERPRISE_SOLUTION_ARCHITECTURE.md](./FSG_ENTERPRISE_SOLUTION_ARCHITECTURE.md) §7 (ETM) and §9 (region sharing)

This is the runbook for **automatically** placing every Account into the correct FSG region. It does not put buyers into territories. It does not use the role hierarchy as a map of the world.

---

## What “assigned to a region” means

Two layers must both be automatic. Mixing them is the usual failure mode.

| Layer | What is stored | Who consumes it | Automatic engine |
| --- | --- | --- | --- |
| **1. Region code** | Account.`Region_Code__c` = `NA-US-NE`, `EMEA-DACH`, … | Commerce (Buyer Group, WebStore, currency, default DC) | Before-save Flow + Custom Metadata (address → code) |
| **2. Territory** | `ObjectTerritory2Association` to Territory2 `NA / US-Northeast` | Internal Q&C, supplier managers, AEs (sharing) | Enterprise Territory Management assignment rules on `Region_Code__c` |

Buyers never sit in Territory2. A Boston chef sees the Boston **Branch Account** via Sharing Sets. Q&C officers see that same Account because ETM shared it into `US-Northeast`.

```text
Billing address
    → Region_Mapping__mdt
        → Account.Region_Code__c  (+ currency, timezone, default DC, WebStore key)
            → ETM rule  → Territory2 (internal sharing)
            → Buyer Group extension (catalog / storefront)
            → Store_Profile__c.Default_Location__c (fulfillment)
```

---

## Prerequisites (do these once)

1. Enable **State and Country/Territory Picklists** (Setup → Data → State and Country/Territory Picklists). ETM and Flow criteria must use the integration-value codes (`US`, `DE`), not free-text “United States.”
2. Enable **Enterprise Territory Management** (Setup → Territories → Territory Settings). This is one-way.
3. Enable **External Organization-Wide Defaults**. Account OWD = **Private** internal and external.
4. Enable **Filter-Based Opportunity Territory Assignment** only if you later align Opportunities. Not required for Account-to-region.
5. Enable **Parallel Sharing Recalculation**.
6. Confirm Account record types exist: `Enterprise_HQ`, `Enterprise_Cluster`, `Enterprise_Branch`, `Micro_Buyer`, `Supplier`.

---

## Step 1 — Define the region catalog (data, not roles)

Create a closed list of leaf regions. Keep it identical to the ETM leaf territories from the architecture (three or four levels, geography-primary).

| `Region_Code__c` | Macro | Leaf territory | WebStore | Default currency |
| --- | --- | --- | --- | --- |
| `NA-US-NE` | NA | US-Northeast | FSG Wholesale NA | USD |
| `NA-US-SE` | NA | US-Southeast | FSG Wholesale NA | USD |
| `NA-US-MW` | NA | US-Midwest | FSG Wholesale NA | USD |
| `NA-US-W` | NA | US-West | FSG Wholesale NA | USD |
| `NA-CA` | NA | Canada | FSG Wholesale NA | CAD |
| `NA-MX` | NA | Mexico | FSG Wholesale NA | MXN |
| `LATAM-BR` | LATAM | Brazil | FSG Wholesale LATAM | BRL |
| `LATAM-AN` | LATAM | Andean | FSG Wholesale LATAM | (per country) |
| `LATAM-SC` | LATAM | Southern Cone | FSG Wholesale LATAM | (per country) |
| `EMEA-UK-IE` | EMEA | UK-IE | FSG Wholesale EMEA | GBP |
| `EMEA-DACH` | EMEA | DACH | FSG Wholesale EMEA | EUR |
| `EMEA-FR-BE` | EMEA | France-Benelux | FSG Wholesale EMEA | EUR |
| `EMEA-IB` | EMEA | Iberia | FSG Wholesale EMEA | EUR |
| `EMEA-ND` | EMEA | Nordics | FSG Wholesale EMEA | EUR / SEK / NOK |
| `EMEA-MEA` | EMEA | MEA | FSG Wholesale EMEA | (per country) |

`Region_Code__c` is a **restricted picklist** (or text with a matching validation + Custom Metadata). It is **indexed**. It is **not** unique per Account — thousands of Boston restaurants share `NA-US-NE`. Do **not** mark it Unique/External ID.

Create supporting Account fields (all indexed where used in rules):

| API name | Type | Purpose |
| --- | --- | --- |
| `Region_Code__c` | Picklist | Assignment key |
| `Macro_Region__c` | Formula or picklist | `NA` / `LATAM` / `EMEA` — WebStore routing |
| `TimeZoneSidKey__c` | Text | Local delivery windows |
| `Default_Location__c` | Lookup(Location) | Default DC for ATP / same-day radius |
| `Region_Assignment_Status__c` | Picklist | `Auto` / `Manual_Override` / `Unmapped` |
| `Evaluate_Territory_Rules__c` | Formula or use standard evaluate-on-save | See Step 7 |

Add `Region_Code__c` and `Macro_Region__c` to every Account page layout and to the Buyer Account compact layout.

---

## Step 2 — Build the mapping table (Custom Metadata)

Do **not** hard-code country/state/ZIP logic in Flow decision trees. FSG will add postal ranges during harvest expansion. Custom Metadata is deployable, cacheable, and bulk-safe.

**Custom Metadata Type:** `Region_Mapping__mdt`

| Field | Example | Notes |
| --- | --- | --- |
| `Country_Code__c` | `US` | ISO from state/country picklists |
| `State_Code__c` | `MA` | Blank = whole country |
| `Postal_Prefix__c` | `021` | Optional; blank = ignore postal |
| `Postal_From__c` / `Postal_To__c` | `10000` / `14999` | Optional numeric ZIP band (US) |
| `Region_Code__c` | `NA-US-NE` | Must match the picklist |
| `Macro_Region__c` | `NA` | |
| `Currency_Iso__c` | `USD` | Stamps Account currency on create only if blank |
| `Time_Zone__c` | `America/New_York` | |
| `Default_Location_Code__c` | `DC-BOS-01` | Matches Location.ExternalId |
| `WebStore_Key__c` | `FSG_NA` | For Buyer Group extension |
| `Priority__c` | `10` | Lower wins: postal beats state beats country |
| `Is_Active__c` | `true` | |

**Match order (most specific wins):**

1. Country + postal prefix or ZIP band  
2. Country + state/province  
3. Country only  

Examples:

| Country | State / postal | Region |
| --- | --- | --- |
| US | MA, CT, NY, NJ, PA, RI, VT, NH, ME | `NA-US-NE` |
| US | CA, OR, WA, NV, AZ | `NA-US-W` |
| US | ZIP `10000`–`14999` (NY metro overlay if needed) | `NA-US-NE` |
| CA | (all) | `NA-CA` |
| MX | (all) | `NA-MX` |
| BR | (all) | `LATAM-BR` |
| DE, AT, CH | (all) | `EMEA-DACH` |
| GB, IE | (all) | `EMEA-UK-IE` |

Seed this table before any Account load. Treat it as master data owned by Digital + Q&C, not by individual AEs.

---

## Step 3 — Stamp `Region_Code__c` with a before-save Flow

**Flow:** `Account_Before_Save_Assign_Region`  
**Type:** Record-Triggered, **Fast Field Updates** (before save)  
**Object:** Account  
**Trigger:** Create and Update  
**Entry conditions:** `Region_Assignment_Status__c` ≠ `Manual_Override` AND (`BillingCountryCode` is changed OR `BillingStateCode` is changed OR `BillingPostalCode` is changed OR `Region_Code__c` is null)

### Flow logic

1. **Get records:** `Region_Mapping__mdt` where `Is_Active__c = true` (Custom Metadata in before-save is allowed; keep the table small — hundreds of rows, not tens of thousands).
2. **Transform / loop in memory** (no DML, no SOQL per Account):
   - Normalize `BillingCountryCode`, `BillingStateCode`, first 3–5 chars of `BillingPostalCode`.
   - Find the lowest `Priority__c` row that matches.
3. **If match found:**
   - Assign `Region_Code__c`, `Macro_Region__c`, `TimeZoneSidKey__c`.
   - If `CurrencyIsoCode` is blank (new Account), set it from the mapping. Do **not** overwrite currency on update — finance owns that after create.
   - Set `Region_Assignment_Status__c = Auto`.
4. **If no match:**
   - Set `Region_Assignment_Status__c = Unmapped`.
   - Leave `Region_Code__c` unchanged (or clear it on create).
   - Do not fail the save for guest micro-buyer registration — send those to a Case/queue in the after-save Flow (Step 8).

### Why before-save

- No extra DML on 150k nightly updates.
- `Region_Code__c` is populated **in the same save** that ETM evaluates, so territory rules see the new code.
- Bulk-safe for Data Loader and self-registration.

### Invocable Apex (only if ZIP bands need it)

If US ZIP ranges cannot be expressed cleanly in Flow, add `RegionMapper.stamp(List<Account>)` called from the before-save Flow. The class:

- Queries `Region_Mapping__mdt` once per transaction (static cache).
- Uses no SOQL inside the Account loop.
- Is `without sharing` for mapping data only; it does not grant Account access.

Do **not** put this logic in an Account trigger in addition to the Flow.

---

## Step 4 — Build the ETM model (Planning first)

1. Setup → **Territory Models** → New.
2. Name: `FSG Geographic Coverage FY26`.
3. State: **Planning** (does not affect sharing until Activate).
4. Create **Territory Types:** `Sales_Coverage`, `Quality_Compliance`, `Supply_Management`.
5. Build the hierarchy (same as the architecture):

```text
FSG Global
 ├─ NA
 │   ├─ US-Northeast
 │   ├─ US-Southeast
 │   ├─ US-Midwest
 │   ├─ US-West
 │   ├─ Canada
 │   └─ Mexico
 ├─ LATAM
 │   ├─ Brazil
 │   ├─ Andean
 │   └─ Southern Cone
 └─ EMEA
     ├─ UK-IE
     ├─ DACH
     ├─ France-Benelux
     ├─ Iberia
     ├─ Nordics
     └─ MEA
```

Duplicate the leaf set under `Quality_Compliance` and `Supply_Management` types **or** assign Q&C users into the same geographic leaves with a different access level. Prefer **one geographic hierarchy** and multiple user assignments with different access, rather than three cloned trees.

6. Assign FSG users to leaves (Q&C officer → `US-Northeast`, Q&C manager → parent `NA` as Territory Manager). Community users: **none**.

---

## Step 5 — Create account assignment rules (the automatic territory step)

Rules run against **Account fields**, not against who owns the record. Use **indexed, restrictive** criteria. One primary rule per leaf. Inherit parent rules so the engine can skip whole branches.

### 5.1 Parent (inherited) rules

On territory **NA**, new assignment rule:

| Setting | Value |
| --- | --- |
| Rule name | `NA macro` |
| Active | Yes |
| Apply to child territories | **Yes** |
| Criteria | `Macro_Region__c` equals `NA` |

On **LATAM**: `Macro_Region__c` equals `LATAM` (inherit).  
On **EMEA**: `Macro_Region__c` equals `EMEA` (inherit).

This is Salesforce LDV guidance: inherited rules on parents stop the engine from evaluating EMEA leaves for a Brazilian farm.

### 5.2 Leaf (direct) rules

On **US-Northeast**:

| Setting | Value |
| --- | --- |
| Rule name | `NA-US-NE leaf` |
| Active | Yes |
| Apply to child territories | No (leaf) |
| Criteria | `Region_Code__c` equals `NA-US-NE`  
AND `RecordType.DeveloperName` is in `Enterprise_Branch, Enterprise_Cluster, Enterprise_HQ, Micro_Buyer, Supplier` |

Repeat one rule per leaf (`NA-US-W` → US-West, `EMEA-DACH` → DACH, …).

**Do not** put ZIP or city in ETM rules. ZIP matching is alphanumeric and slow. The Flow already collapsed address → `Region_Code__c`. ETM only equals that code.

**Do not** reference OwnerId in rules (circular).  
**Do not** use “Description contains …”.

### 5.3 Named-account exception (largest enterprise client)

Marriott HQ may sit in `NA-US-NE` by address but must also be visible to the global AE overlay:

- Create territory `Named — Marriott` (type Sales_Coverage) under Global.
- **Manually** associate the HQ Account (and only HQ / maybe clusters — not 15,000 branches).
- Manual assignment **persists** even if a rule would not match. Document this. Run the Manual Assignment report monthly.

Branches still follow postal → `Region_Code__c` → leaf territory so local Q&C covers the Boston hotel, not the global AE.

### 5.4 Preview in Planning

From the model, **Run Rules** (Planning does not change live sharing). Check:

- Sample of 50 Accounts per leaf.
- Zero Accounts with two leaf territories in the **same** type (a branch should not be US-Northeast and US-West).
- HQ + clusters assigned; 15k Marriott branches assigned to **their city leaf**, not to Named-Marriott.

---

## Step 6 — Activate the model (sharing goes live)

1. Freeze large data loads.
2. Activate `FSG Geographic Coverage FY26` in a maintenance window. Salesforce recommends planning this carefully above ~50,000 Accounts — FSG is at 150k+ branches plus suppliers. **Run off-peak.** Parallel sharing recalc must be on.
3. After activate, new and updated Accounts in the **active** model are assigned when territory rules run on save (Step 7).
4. Keep a **Planning clone** for the next realignment. Never edit the live model in place for a large re-carve; clone → change rules → preview → activate (replaces the previous active model).

---

## Step 7 — Make every save evaluate territory rules

ETM assigns on create/update only when:

- A model is **Active**, and
- The Account is evaluated against territory rules.

### Interactive users

Add the standard checkbox **Evaluate this account against territory rules on save** to Account layouts (label may appear as “Evaluate this account against territory rules on save”).  
Default it to **true** via record type / before-save Flow for all FSG record types except when `Region_Assignment_Status__c = Manual_Override`.

### API / Data Loader / MuleSoft

SOAP/REST `AssignmentRuleHeader.useDefaultRule = true` on Account create/update. Without this header, bulk loads **skip** ETM and you will think automation is broken.

### Apex

`Database.DMLOptions` **does not** run territory assignment rules. For Apex-created Accounts (self-registration handler, application conversion):

- Stamp `Region_Code__c` in the same transaction (call the mapper / let before-save Flow run).
- Update the Account via the **SOAP/REST API AssignmentRuleHeader**, or
- After insert, use a fire-and-forget that updates the Account as an API user with the header, or
- Schedule the standard **Run Rules** at territory/model level for the unmapped set (nightly catch-up, Step 9).

Practical FSG pattern: before-save Flow stamps the code; a **platform event / queueable using the REST Assignment Rule header** (integration user) updates `Id` only so ETM attaches. Nightly “Run Rules” is the safety net for anything missed.

---

## Step 8 — Wire each intake process (so region is set at birth)

### 8.1 Micro-buyer self-registration (LWR)

1. Buyer enters billing/shipping address on the regional store (prefer the store they landed on, but **trust the address**, not the URL, as source of truth).
2. Self-reg handler creates Account (`Micro_Buyer`) + Contact + User.
3. Before-save Flow stamps `Region_Code__c` from the address.
4. If `Macro_Region__c` does not match the store they registered on (registered on NA site with a Paris address), after-save Flow:
   - Does **not** leave them on the wrong WebStore Buyer Group.
   - Either blocks activation with a message “Use the EMEA store” or auto-assigns EMEA groups and emails the buyer.
5. Buyer Group Extension reads `Region_Code__c` / `Macro_Region__c` at session start.

### 8.2 Corporate chef / branch create

1. FSG ops or MuleSoft upserts the Branch Account with `Store_Code__c` and billing address of the restaurant (not the HQ address).
2. Before-save Flow stamps region from **branch** address.
3. Cluster parent is chosen from `Region_Code__c` (e.g. all `NA-US-NE` Marriott branches under `Marriott US Northeast`). A separate before-save / invocable sets `ParentId` if blank, using `Master_Agreement_Number__c` + `Region_Code__c` — **never** parent 15k children to HQ.
4. Chef registration only attaches a Contact to that already-regionalized Branch.

### 8.3 Supplier application conversion

1. Guest submits `Supplier_Application__c` with farm address.
2. On approve, Flow creates Account (`Supplier`) copying address from the application.
3. Before-save Flow stamps `Region_Code__c`.
4. ETM assigns Q&C territory. The vetting Case is owned by the territory queue / assigned via Case assignment that keys off Account region.

### 8.4 Integration upserts (ERP / MDM)

1. External ID: `Store_Code__c` or `Supplier_Code__c`.
2. Always send country, state, postal.
3. Set Assignment Rule header.
4. Do not send `Region_Code__c` from ERP unless MDM is the winner — pick **one** source of truth. Recommended: **Salesforce Flow owns the code**; ERP owns the address.

---

## Step 9 — Nightly catch-up (LDV safety net)

**Scheduled Flow or Batch Apex** (off-peak, 14-time-zone aware — run after last EMEA close):

1. Query Accounts where `Region_Assignment_Status__c = Unmapped` OR (`LastModifiedDate` = today AND no `ObjectTerritory2Association` in the active model). Keep the query **selective** (status picklist + last modified).
2. Re-run the mapper (update address-derived fields). That update, with assignment-rule header or a subsequent model **Run Rules**, attaches territories.
3. Open a Case to Digital Ops for remaining Unmapped (bad country picklist, PO box, ship-to-only).
4. Do **not** run full-org “Run Rules” every night. That recalculates sharing across 150k Accounts. Run rules **scoped** or only on the delta set.

---

## Step 10 — Downstream automation that depends on the region

Once `Region_Code__c` is set, these stay automatic. They are not additional “region assignment” engines.

| Consumer | How it reads region |
| --- | --- |
| Buyer Group Extension | Maps `Macro_Region__c` → `BG_NA_LIST` / `BG_LATAM_LIST` / `BG_EMEA_LIST`; contract groups still static |
| WebStore | User is a member of the matching regional LWR site; redirect if mismatch |
| Default DC | Mapping `Default_Location_Code__c` → `Location`; stamped onto `Default_Location__c` / `Store_Profile__c` |
| Currency | Mapping on **create**; ACM dated rates for reporting |
| Same-day Ultra-Fresh | Shipping extension uses `Default_Location__c` + postal |
| Inspection Case | Queue / ETM users for that territory |

---

## Step 11 — Manual override (break-glass)

A farm on a border, or a DC that serves two leaves:

1. User with permission set `PS_Region_Override` sets `Region_Assignment_Status__c = Manual_Override` and picks `Region_Code__c`.
2. Before-save Flow **skips** mapping.
3. Optionally add a **manual** territory association (persists).
4. Audit field history on `Region_Code__c` and `Region_Assignment_Status__c` (Shield Field Audit Trail if food-safety requires it).

Without the status flag, the next address edit would overwrite a carefully chosen border region.

---

## Step 12 — Verify (definition of done)

| Check | Expected |
| --- | --- |
| New cafe in Boston | `Region_Code__c = NA-US-NE`, currency USD, territory US-Northeast, Buyer Group NA, store FSG Wholesale NA |
| New cafe in Munich | `EMEA-DACH`, EUR, territory DACH, EMEA store |
| Marriott Boston branch | Leaf `NA-US-NE`; parent = Marriott US Northeast cluster; **not** parent = Marriott HQ |
| Marriott HQ | Named-account overlay + address-based leaf; AEs via Account Team / Named territory |
| Farm in Paraná, Brazil | Supplier, `LATAM-BR`, Q&C Brazil territory, inspections inherit Account share |
| Address change MA → CA | Region becomes `NA-US-W`; ETM moves association on save; Buyer Groups follow at next session |
| Bulk 10k branch load | Region stamped in same batch; AssignmentRuleHeader set; no CPU timeouts |
| Unmapped postal | Status Unmapped; Digital Ops Case; Account still saves |
| Community user | Not in any Territory2 |

Reports to build:

- Accounts by `Region_Code__c` (count) vs territory associations (count) — they should match at leaf level.
- `Unmapped` aging.
- Accounts in two leaves of the same territory type.

---

## What not to do

| Anti-pattern | Why it fails at FSG scale |
| --- | --- |
| Role per country | 150k CC+ / internal role explosion; Salesforce says do not clone territory in roles |
| ETM rule on BillingPostalCode ranges | Alphanumeric ZIP compares (`9` > `80000`); unselective; slow |
| Apex sharing to “NA public group” | Share-row explosion |
| Putting chefs in territories | Wrong engine; leaks all regional restaurants to a manager |
| Parent 15k Marriott children to HQ | Lookup skew; region of HQ is not region of the branch |
| Overwriting currency on every address edit | Breaks open orders and rebates |
| Full-org Run Rules nightly | Sharing recalc incident |
| Hard-coded Flow decisions for 50 states | Unmaintainable; use `Region_Mapping__mdt` |

---

## Worked path (Boston restaurant)

1. MuleSoft upserts Account record type `Enterprise_Branch`, billing `Boston, MA, US, 02108`, `Store_Code__c = MAR-BOS-001`, `Master_Agreement_Number__c = MARRIOTT-2026`.
2. Before-save Flow matches `Region_Mapping__mdt` (US + MA) → `Region_Code__c = NA-US-NE`, `Macro_Region__c = NA`, timezone `America/New_York`, default DC `DC-BOS-01`.
3. Flow sets `ParentId` to Cluster “Marriott US Northeast” (agreement number + `NA-US-NE`), not Marriott HQ.
4. Assignment rules on the active model: inherited `Macro_Region__c = NA` plus leaf `Region_Code__c = NA-US-NE` → Territory **US-Northeast**.
5. Q&C officer in that territory can see the Account; Inspection__c inherits.
6. Buyer Group Extension at chef login assigns `BG_NA_LIST` + `BG_MARRIOTT_US`. Catalog is NA produce in USD. Sharing Sets still limit the chef to **this** branch only.

That is automatic Account-to-region assignment in this design: **address → mapping → region code → ETM leaf**, with commerce and sharing as downstream consumers, not competing assignment engines.
