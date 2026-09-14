# FreshSource Global — Corporate Ordering Solution Architecture

**Document type:** Salesforce Solution Architecture (OOTB + Custom)  
**Audience:** Enterprise Architects, Salesforce Architects, Product Owners, Implementation Leads  
**Scope:** Corporate Ordering under multi-year Master Agreements, including self-registration of store managers / head chefs onto a pre-negotiated catalog, tiered volume discounts, contracted delivery schedules, and branch-scoped user administration.  
**Scale drivers:** 50,000+ orders/day, 14 time zones, 1,200+ enterprise accounts, up to 15,000 branch locations under a single Master Agreement, ~150,000 branch buyers/chefs.  
**Salesforce documentation baseline:** Lightning B2B Commerce, Experience Cloud, Sales Cloud Contract, Revenue Cloud contract-based pricing, Manufacturing Cloud Rebate Management, Designing Record Access for Enterprise Scale.

---

## 1. Executive recommendation

Implement Corporate Ordering as a **Lightning B2B Commerce (LWR) storefront on Experience Cloud**, with **Sales Cloud Accounts / Contracts** as the system of record for the Master Agreement, and **Commerce Buyer Groups + Entitlement Policies + Contracted Price Books** as the runtime catalog and price engine.

Do **not** park 15,000 branch contacts or orders on a single parent Account. Model each branch as its own **Buyer Account**, hang those accounts under a **shallow, fan-out-controlled hierarchy**, and grant storefront access with **high-volume Customer Community users** plus **Sharing Sets**. Reserve **Customer Community Plus** only for the one designated Branch User Administrator per location, using OOTB **Delegated External User Administration**.

| Capability | Primary approach | Why |
|---|---|---|
| Master Agreement | OOTB `Contract` on the Corporate Account, with a contracted Commerce Price Book | Standard Account–Contract relationship; price book is what B2B Commerce actually prices from |
| Corporate catalog | OOTB `ProductCatalog` + `CommerceEntitlementPolicy` + `BuyerGroup` | B2B stores support multiple entitlement policies; catalog visibility is buyer-group based |
| Self-registration with corporate email | OOTB Experience Cloud self-registration **plus** custom Apex handler | Standard self-reg always attaches users to one default Account; FSG must resolve Branch Account by email domain + location code |
| Branch-only user management | OOTB Delegated External User Administrator on the Branch Account | Permission is account-scoped; a branch admin cannot manage another branch |
| Tiered volume discounts (order/SKU) | OOTB `PriceAdjustmentSchedule` / `PriceAdjustmentTier` | Native B2B Commerce volume pricing (Range or Slab) |
| Enterprise volume rebates (across 15,000 branches) | OOTB Manufacturing Cloud Rebate Management **or** custom aggregation | Cart-level price adjustment cannot roll up volume across branches |
| Delivery schedules | OOTB `CartDeliveryGroup.DesiredDeliveryDate` + `OrderDeliveryMethod` **plus** custom schedule validation | Commerce captures requested date; contracted windows are not a native MSA object |
| 15,000-branch scale | High-volume community licenses, Sharing Sets, Buyer Group Extension, hierarchy sharding | Avoids role explosion, parent-child data skew, and lookup skew |

---

## 2. Requirement interpretation

### 2.1 What “Corporate Ordering” must do

1. FSG Sales / Legal onboards an enterprise on a **multi-year Master Agreement (MSA)**.
2. The MSA defines a **pre-negotiated catalog**, **tiered volume discounts**, **rebate terms**, and **delivery schedules**.
3. After the Corporate Account is active, a **store manager or head chef** registers with a **corporate email address**.
4. The user is placed on the **correct branch location** (not the legal-entity parent, and not a sibling branch).
5. The storefront shows **only that enterprise’s entitled products and contracted prices**.
6. Checkout honors **contracted delivery windows** for that branch.
7. **One user per branch** can create, deactivate, and reset passwords for **other users in that branch only**.
8. One MSA may cover **15,000+ branch locations** without sharing leakage, catalog leakage, or sharing-recalculation collapse.

### 2.2 Adjacent constraints from the company profile

These are not the primary story, but they constrain the design:

- Two buyer populations share one org: **Enterprise Corporate** and **Direct B2B Micro-Buyers**. Keep registration, catalogs, and licenses separate.
- Orders are perishable / cold-chain. Delivery method and DC assignment are first-class, not afterthoughts.
- 50k orders/day and 14 time zones require an asynchronous order-to-fulfillment path (Salesforce Order Management + integration), not synchronous ERP calls on Place Order.
- Quality & Compliance Officers are internal users; they must see DC / inspection data without becoming commerce buyers.

### 2.3 Explicit non-goals for this workstream

- Supplier (farm) onboarding and inbound procurement.
- Micro-buyer one-off checkout (separate buyer group / guest-or-self-reg path).
- Full Field Service / inspection mobile app for Quality Officers (interface only: Order and Shipment visibility).

---

## 3. Target Salesforce product stack

### 3.1 Products (OOTB)

| Product | Role in Corporate Ordering |
|---|---|
| **Sales Cloud** | Corporate Account, Branch Account, Contact, Opportunity (MSA sell cycle), standard `Contract` |
| **Lightning B2B Commerce (LWR)** | Store, catalog, cart, checkout, buyer groups, entitlement policies, price books, volume price adjustment |
| **Experience Cloud (LWR B2B template)** | Authenticated storefront, login, self-registration, Account Management |
| **Salesforce Identity** | Email OTP verification, later SAML/OIDC SSO for largest enterprises |
| **Salesforce Order Management** | Order Summary, fulfillment, change order, split shipments after Place Order |
| **Revenue Cloud / Salesforce Contracts (recommended)** | Contract Item Prices and contract-based volume tiers when MSA pricing is more than a static price book |
| **Manufacturing Cloud Rebate Management (recommended)** | Aggregate volume rebates across all branches of one MSA |
| **MuleSoft / Platform Events / Change Data Capture** | Order export to WMS/TMS/ERP; catalog and inventory inbound |

Use the **B2B Commerce (LWR)** store template. Salesforce documents LWR as the recommended template for new B2B stores (Aura remains only for older orgs).

### 3.2 License model (critical)

| Persona | License | Why this license |
|---|---|---|
| Store chef / buyer (~150k users) | **Customer Community** (high-volume) | No roles; Sharing Sets; designed for thousands-to-millions of external users |
| Branch User Administrator (1 per branch) | **Customer Community Plus** | Required for Delegated External User Administration and Buyer Manager / Account Switcher patterns |
| Corporate HQ merchandiser (rare, optional) | Customer Community Plus + **External Managed Accounts** | Can switch into selected branches; **hard limit 200 external managed accounts per user** — cannot be used to administer 15,000 branches |
| FSG Account Executive / Contract Admin | Internal Sales Cloud | Owns Corporate Account and Contract |
| FSG Commerce Merchandiser | Internal + Commerce permission sets | Catalog, price books, entitlements |
| FSG Quality & Compliance Officer | Internal | Cases, shipments, custom inspection objects |
| FSG Integration user | Integration / API | Middleware identity |

This hybrid model is intentional. Granting Customer Community Plus **and roles** to 150,000 chefs under 15,000 accounts would create tens of thousands of Experience Cloud account roles (default org maximum 50,000 account roles; 100,000 with support review). High-volume licenses avoid that.

Salesforce documents Delegated External User Administration for Partner Community, Customer Community Plus, Gold Partner, and related licenses — **not** for high-volume Customer Community. Hence CCP is reserved for the branch admin only.

---

## 4. Logical architecture

```text
                    ┌──────────────────────────────────────────────┐
                    │  FSG Internal (Lightning / Commerce App)     │
                    │  MSA sell → Contract → Price Book + Catalog  │
                    │  Branch master data, delivery windows, DCs   │
                    └──────────────────────┬───────────────────────┘
                                           │
     ┌─────────────────────────────────────┼──────────────────────────────────┐
     │                                     │                                  │
     ▼                                     ▼                                  ▼
┌──────────────┐                 ┌─────────────────────┐            ┌─────────────────┐
│ Experience   │  Buyer Groups / │ B2B Commerce Store  │  Orders    │ Order           │
│ Cloud LWR    │  Entitlements   │ Cart / Checkout     │───────────▶│ Management      │
│ Corporate    │────────────────▶│ PriceAdjustment     │            │ Fulfillment     │
│ Storefront   │                 │ Delivery Groups     │            └────────┬────────┘
└──────┬───────┘                 └─────────────────────┘                     │
       │ Self-reg + login                                                    │ Platform Events
       ▼                                                                     ▼
┌──────────────┐                                                    ┌─────────────────┐
│ Identity     │                                                    │ ERP / WMS / TMS │
│ Email OTP or │                                                    │ Inventory,      │
│ Enterprise   │                                                    │ routing, invoice│
│ SSO (JIT)    │                                                    └─────────────────┘
└──────────────┘
```

One **WebStore** is sufficient for Corporate and Micro-Buyer if buyer groups fully isolate catalogs and prices. Prefer **two stores** (or two Experience sites on one store) only if UX, brand, or guest-browse rules diverge enough to justify the operational cost. Recommendation: **one LWR B2B store**, two registration entry points, distinct buyer groups.

---

## 5. Data model

### 5.1 Account topology (OOTB Account Hierarchy, with scale controls)

```text
Corporate Account (Legal entity / MSA holder)
  Record Type: Corporate_Customer
  IsBuyer: false (HQ does not place store-level orders)
  Allowed_Email_Domains__c = "acmecorporate.com,acme-dining.com"
  MSA_Contract__c → Contract
       │
       ├── Region Account (optional shard; Record Type: Corporate_Region)
       │     Used when a single parent would otherwise exceed ~10,000 children
       │     Example: Acme – AMER East, Acme – AMER West, Acme – EMEA
       │         │
       │         └── Branch Account (Record Type: Corporate_Branch)  ← BUYER ACCOUNT
       │               Location_Code__c (External ID, unique)
       │               ParentId → Region or Corporate
       │               Ultimate_Parent__c → Corporate Account (denormalized)
       │               Active_Contract__c → MSA Contract
       │               Default_DC__c → Distribution Center Account/Custom
       │               Delivery_Schedule__c → contracted windows
       │               IsBuyer = true (BuyerAccount)
       │               Contacts: chefs, managers
       │               Users: Community users
```

**Why Branch is the Buyer Account**

B2B Commerce entitlements, carts, orders, and credit limits hang off the **Buyer Account**. If the chef’s Contact lived on the 15,000-child Corporate Account, every order and contact would create **parent-child data skew** on that Account. Salesforce’s *Designing Record Access for Enterprise Scale* treats **10,000+ children on one parent** as the skew threshold that degrades implicit-share maintenance and row locking.

**Why an intermediate Region Account exists**

Account Hierarchy itself can hold 15,000 children. The problem is not the UI; it is:

- Parent-child skew on the Corporate Account if branches, contacts, and orders all point at it.
- Lightning Account Hierarchy view is documented to display up to **2,000** accounts.
- Formula “ultimate parent” walks (`Parent.Parent.Name`) consume compile size and the Account object’s cross-object relationship budget.

Mitigation: shard the largest client into regional parents so **no Account has ≥ 10,000 direct children**, and store `Ultimate_Parent__c` with a **before-save Flow or Apex** (not a deep formula).

### 5.2 Master Agreement (OOTB Contract + thin custom)

Use the standard **Contract** object on the Corporate Account.

| Field / related | OOTB or custom | Purpose |
|---|---|---|
| `AccountId` | OOTB | Corporate legal entity |
| `StartDate` / `EndDate` / `Status` | OOTB | Multi-year term; Activated vs Expired |
| `Pricebook2Id` | OOTB | Contracted Commerce price book |
| `ContractNumber` | OOTB | MSA number |
| `IsPricingContract` / Contract Item Prices | OOTB Revenue Cloud | Dynamic contracted unit prices and volume tiers |
| `Catalog_Entitlement_Policy__c` | Custom lookup | Which Commerce entitlement policy this MSA uses |
| `Buyer_Group__c` | Custom lookup | Runtime buyer group for all branches of this MSA |
| `Rebate_Program__c` | Custom lookup | Manufacturing Cloud rebate program, if used |
| `Pricing_Strategy__c` | Custom picklist | `PriceBook`, `RevenueCloudContract`, `Hybrid` |

**Contract Line Items / Sales Contract Lines** capture SKU or category scope of the catalog (included produce families, excluded SKUs, private-label items). Commerce still needs those SKUs copied into an **Entitlement Policy**; the Contract is the legal source, the entitlement policy is the storefront source.

Do **not** create 15,000 Contracts (one per branch). One MSA, many branches. Branch Accounts lookup to the single Contract (`Active_Contract__c`).

### 5.3 Identity objects

| Object | Usage |
|---|---|
| `Contact` | Person at a Branch. Primary `AccountId` = Branch Account. |
| `User` | Experience Cloud user. `ContactId` required. Username = corporate email. |
| `BuyerAccount` | Enable on each Branch Account (`CommerceEnable` / Buyer Account). Credit limit, order limit optional. |
| `BuyerAccountAccess` / Buyer & Buyer Manager roles | Explicit contact-level commerce role. **Account membership alone does not grant storefront buying.** Salesforce Commerce setup guidance: missing Buyer / Buyer Manager role produces an empty store or authorization error. |
| `AccountContactRelation` | Only if a district chef must buy for multiple branches. Enable Contacts to Multiple Accounts. Sharing Sets can use `Contact.RelatedAccount`. Prefer this over External Managed Accounts when the user needs to shop, not just administer. |

### 5.4 Custom objects (only where OOTB is insufficient)

| Object | Purpose | Why not OOTB |
|---|---|---|
| `Email_Domain__c` | Allow-listed corporate domains → Corporate Account | Account.Website is not a reliable unique domain index; one MSA can have several domains |
| `Location_Code__c` on Account (field) | Store number used at registration | Standard Account has no store-number external ID |
| `Delivery_Schedule__c` | Contracted order-cut-off, delivery days, time windows, blackout dates, per branch or per region | Commerce `CartDeliveryGroup.DesiredDeliveryDate` stores a requested date, not a recurring MSA calendar |
| `Registration_Request__c` | Pending self-reg when domain matches but branch code is wrong / first-user admin designation | Standard self-reg is create-or-fail; FSG needs an approval queue |
| `Standing_Order__c` + `Standing_Order_Line__c` | Recurring produce replenishment (Mon/Wed/Fri par levels) | Native Commerce subscriptions are for subscription *products* and installment payments, not wholesale standing orders |
| `Distribution_Center__c` | Regional DC master, timezone, cold-chain capability | Not a Commerce native; maps to fulfillment location |

Keep SKU, price, cart, order, shipment on **standard Commerce / Order Management objects**.

### 5.5 Commerce objects (OOTB — do not replace)

| Object | API | FSG usage |
|---|---|---|
| Store | `WebStore` | One corporate wholesale store |
| Catalog / Category / Product | `ProductCatalog`, `ProductCategory`, `Product2` | Global FSG assortment; entitlement hides what the MSA does not include |
| Entitlement Policy | `CommerceEntitlementPolicy` | `CanViewProduct`, `CanViewPrice` for an MSA catalog |
| Buyer Group / Member | `BuyerGroup`, `BuyerGroupMember` | MSA-level group; optional region group |
| Buyer Group Price Book | `BuyerGroupPricebook` | Maps MSA price book; `Priority` if using Priority pricing strategy |
| Price Book / Entry | `Pricebook2`, `PricebookEntry` | Contracted unit prices |
| Price Adjustment Schedule / Tier | `PriceAdjustmentSchedule`, `PriceAdjustmentTier` | SKU quantity breaks |
| Cart / Cart Item | `WebCart`, `CartItem` | Branch-context cart |
| Cart Delivery Group | `CartDeliveryGroup` | Ship-to branch address, `DesiredDeliveryDate`, delivery method |
| Order / Order Item | `Order`, `OrderItem` | Placed order |
| Order Summary | Order Management | Downstream fulfillment |

---

## 6. End-to-end process design

### 6.1 Process 1 — Corporate onboarding (internal, mostly OOTB)

```text
Opportunity (MSA) → Legal review → Contract Activated
        → Generate / assign Contracted Price Book
        → Create / clone Entitlement Policy (MSA catalog)
        → Create Buyer Group “BG-{ContractNumber}”
        → Link BuyerGroupPricebook + CommerceEntitlementBuyerGroup
        → Load Branch Accounts (bulk API) with Location_Code__c
        → Enable BuyerAccount on each Branch (batch)
        → Load Delivery_Schedule__c per branch or region
        → Enroll Corporate Account in Rebate Program (optional)
        → Enable Email_Domain__c allow-list
        → Invite first Branch Admins OR open self-registration
```

**OOTB tools**

- Opportunity + Contract + Approval Process for legal activation.
- Commerce App: catalogs, entitlement policies, buyer groups, price books.
- Data Loader / Bulk API 2.0 / Commerce Data Import for 15,000 branches.
- Flow: when Contract status = Activated, create Buyer Group and stamp `Buyer_Group__c` / `Catalog_Entitlement_Policy__c`.

**Custom**

- Flow/Apex to clone a template entitlement policy and associate the MSA’s allowed products from Contract Lines (OOTB has no “create entitlement from Contract” button).
- Batch to enable `BuyerAccount` and default ship-to addresses from Branch Account billing/shipping.
- Do **not** insert 15,000 `BuyerGroupMember` rows in a tight loop if using **Buyer Group Extension** (see §8). If stored membership is used, load via Bulk API off-hours.

### 6.2 Process 2 — Store manager / chef self-registration (OOTB + custom)

Standard Experience Cloud self-registration **always associates the new user to the single Account configured on Login & Registration** (`NetworkSelfRegistration.AccountId`). That cannot place a chef onto the correct one of 15,000 branches. Salesforce documents two extension points:

1. `Auth.ConfigurableSelfRegHandler` — modify generated handler; verification via email OTP is OOTB.
2. Custom LWC + Apex (`CommerceSelfRegistrationController` pattern in the B2B Commerce Developer Guide) — required when the form must collect **Branch Location Code** and must create `BuyerAccount` / permission-set assignment.

**Recommended UX**

1. Corporate registration page (not the Micro-Buyer page).
2. Fields: First Name, Last Name, Corporate Email, Location Code, Role (Chef / Manager / Admin request).
3. OOTB **email verification method** (OTP). Salesforce generates the user only after the code succeeds, which reduces dummy users.
4. Reject public domains (`gmail.com`, `yahoo.com`, etc.) via Custom Metadata.
5. Match `emailDomain` → `Email_Domain__c` → Corporate Account.
6. Match `Location_Code__c` → Branch Account where `Ultimate_Parent__c` = that Corporate Account **and** `Active_Contract__c.Status` = Activated **and** Contract dates contain today.
7. Create Contact on the **Branch Account** (never on Corporate).
8. Create User:
   - Default: Customer Community + OOTB **Buyer** permission set.
   - If this is the first active user on the branch **or** Role = Branch Admin and no admin exists: Customer Community Plus + **Buyer Manager** permission set + profile with **Delegated External User Administrator**.
9. Enable Buyer role on the Contact (`BuyerAccountAccess`).
10. Do not create a new Account.

**Failure paths**

| Condition | Behavior |
|---|---|
| Domain not allow-listed | Block. Direct user to Micro-Buyer registration. |
| Domain valid, location code invalid | Create `Registration_Request__c` (Pending). Email FSG onboarding / Corporate HQ. Do not create a User. |
| Contract expired or not Activated | Block with “account not enabled for ordering”. |
| Email already a User | Login / password reset, do not duplicate. |
| Email domain match is necessary but not sufficient | OTP + valid issued location code. Optionally require Branch Admin approval for 2nd+ users. |

**Security notes (Salesforce Identity + guest-user hardening)**

- Guest profile: only the self-reg Apex class; `with sharing`; no unrelated CRUD.
- Location codes must be **non-sequential issued IDs**, not “Store-1”.
- Rate-limit: Salesforce allows a small number of verification codes per email per hour; still log guest Apex invocations (Event Monitoring).
- Email domain matching is **not** proof of employment. Largest enterprises should move to **SSO (SAML / OpenID Connect) with JIT** (`Auth.RegistrationHandler`) mapping IdP attributes `email`, `storeNumber` → Branch Account.

### 6.3 Process 3 — Branch-scoped user management (OOTB)

Requirement: *one of the users in the branch must be able to manage other users only in their branch.*

**OOTB feature:** **Delegated External User Administration** (Experience Cloud).

A user with this permission on a Customer Community Plus (or Partner) profile can, for **their Account**:

- Create and edit external users
- Reset passwords
- Deactivate users
- Assign allowed permission sets

They cannot manage users on a sibling branch because those Contacts belong to a different Account.

**Storefront configuration**

- Experience Builder: Account Management / Members list bound to `{!CurrentUser.effectiveAccountId}` (Salesforce B2B Help: Grant Buyers Access to External Accounts).
- Branch Admin profile: Delegated External User Administrator.
- Delegated External User Profiles: only the Chef/Buyer community profiles.
- Delegated permission sets: only Buyer (not Buyer Manager, not internal permission sets).

**First admin bootstrap**

- Self-reg promotes the first verified user on a branch to Branch Admin, **or**
- FSG internally converts one Contact → CCP user (Commerce Customer Workspace).

**What not to use**

- **External Managed Accounts / Account Switcher** for this requirement. That feature lets a user manage **other** accounts (up to 200). FSG’s rule is the opposite: stay inside one branch.
- **Experience Cloud Super User** / External Account Hierarchy roll-up. Super User would let a parent-account user see child-account data — HQ seeing 15,000 branches — which violates branch isolation and does not scale.
- Internal Delegated Administration groups. Those are for internal Salesforce users, not storefront chefs.

**Optional: Buyer Manager vs Delegated Admin**

Salesforce preconfigured **Buyer Manager** permission set lets the user manage carts/orders/contacts for the account and is the commerce counterpart of “account admin.” Combine:

- Buyer Manager → shop and see account carts/orders.
- Delegated External User Administrator → create/deactivate users.

Both are OOTB; both must be assigned only to the designated branch admin.

### 6.4 Process 4 — Shop the pre-negotiated catalog (OOTB)

Runtime resolution:

1. User authenticates. Effective Account = Branch Account (`User.AccountId` or `User.Commerce.EffectiveAccountId`).
2. Branch is a Buyer Account in the store.
3. Buyer groups for that account are loaded (stored members **or** Buyer Group Extension).
4. Entitlement policies on those groups determine **which products** appear (`CanViewProduct`) and **whether prices are visible** (`CanViewPrice`).
5. `BuyerGroupPricebook` determines **which unit prices** apply.
6. Search, PLP, PDP, and cart all run in that account context.

B2B stores support **multiple entitlement policies**; D2C stores support only one. This is why B2B (not D2C) is mandatory.

**Catalog strategy**

- One **ProductCatalog** on the store (a store has a single catalog).
- Global assortment lives in that catalog.
- Each MSA gets an entitlement policy that includes only contracted products/categories.
- Optional second policy for **regional / cold-chain SKUs** (for example, “EMEA chilled protein”) assigned via a region buyer group so a LATAM branch cannot see EMEA-only SKUs.

Do not clone the entire catalog per customer. Entitlements are the documented isolation mechanism.

### 6.5 Process 5 — Tiered volume discounts (OOTB) vs volume rebates (OOTB product, different engine)

These are different commercial instruments and must not be implemented as one discount class.

**A. Cart / order-line volume discount (OOTB Commerce)**

Use **Price Adjustment Schedules** on Price Book Entries:

- `ScheduleType = Volume`
- `AdjustmentMethod = Range` (all units take the highest tier) or `Slab` (each band priced separately)
- Tiers: `LowerBound`, `UpperBound` (not inclusive; last tier upper bound optional), `TierType` = Percentage / Amount / Override
- Tiers cannot overlap or have gaps

This matches “buy 10 cases of avocados, unit price drops.” It is evaluated **in the current cart / quantity**, not across 15,000 branches.

If using **Revenue Cloud** contract-based pricing, use **Contract Item Price** + **Contract Item Price Adjustment Tier**, and enable “Use contract-based pricing” on the pricing procedure. Child-account contracted prices override parent contracted prices (CPQ/Revenue Cloud documented behavior) — useful for a handful of branch exceptions, not for 15,000 unique price lists.

**B. Enterprise volume rebate (across the MSA)**

“If Acme’s 15,000 branches together move 2M lbs of berries this quarter, Acme earns 3%.” This is **not** a Price Adjustment Schedule.

OOTB: **Manufacturing Cloud Rebate Management**

- Rebate Program on the Corporate Account (member = Corporate, not each branch).
- Rebate Type: Aggregate Based, measure Total Quantity or Total Transaction Amount.
- Benefit tiers for volume bands.
- Data Processing Engine definition aggregates transactions.
- Rebate Orchestration Flow calculates accrual/payout.
- Frequency: monthly / quarterly / annually aligned to the MSA.

Integration: Order Summaries (or ERP invoices) must be visible as rebate transactions. Prefer replicating Order/OrderItem to the rebate transaction object via DPE rather than custom Apex roll-ups on Account (which would hit skew and 50k-order/day volumes).

If Manufacturing Cloud is not in the commercial stack, build `Rebate_Program__c` + nightly Big Object / BigQuery / Heroku aggregation. Do not use Aggregate Query on `Order` in Apex for 15,000 branches.

**Pricing strategy on the store**

Configure the WebStore pricing strategy (Lowest Price vs Priority). For contracted catalogs, **Priority** with a single MSA price book is simpler and avoids accidental list-price leakage. If a list price book is also assigned, ensure entitlement `CanViewPrice` and buyer-group price books cannot surface the wrong book.

### 6.6 Process 6 — Delivery schedules (OOTB capture + custom rules)

**OOTB**

- Branch Account Shipping Address = default cart delivery address.
- `CartDeliveryGroup.DesiredDeliveryDate` = buyer-requested delivery date.
- `OrderDeliveryMethod` / `CartDeliveryGroupMethod` = Cold Chain, Ambient, Next-Day Cutoff, etc.
- Split shipments via Cart Delivery Group APIs (`arrange-items`, `itemDistributions`) when lines ship from different DCs.
- Checkout update API accepts `desiredDeliveryDate`, `deliveryAddress`, `deliveryMethodId` and re-runs shipping/tax calculators.

**Custom (required for “contracted delivery schedules”)**

OOTB Commerce does not store “this branch may only receive Tue/Thu 04:00–07:00 from DC Dallas, order cutoff 14:00 CT previous day.”

Model `Delivery_Schedule__c`:

- `Branch_Account__c` (or Region, with branch override)
- `Delivery_Days__c` (multi-select)
- `Cutoff_Time__c` + `Cutoff_Timezone__c` (org is multi-timezone; **never** assume org-default GMT)
- `Window_Start__c` / `Window_End__c`
- `Allowed_Delivery_Method__c`
- `Default_DC__c`
- `Blackout_Date__c` child (holidays, farm closures)

Enforce with a **custom Commerce checkout calculator** or `Commerce_Domain_Shipping` / checkout extension:

1. Convert now() to branch timezone.
2. Reject dates not in `Delivery_Days__c`.
3. Reject dates after cutoff.
4. Default `DesiredDeliveryDate` to next eligible slot.
5. Filter available delivery methods to those on the schedule.
6. Stamp `Default_DC__c` onto the Cart Delivery Group (custom field) for OMS routing.

**Standing / recurring orders**

Native Commerce “Create Subscription Records” checkout action is for subscription products and installment billing. FSG produce replenishment should be a **custom Standing Order**:

- Chef saves a cart as a standing order (custom LWC on cart).
- Scheduled Flow / Queueable (timezone-aware) clones a cart / places an order for the next eligible delivery date.
- Chef can pause, skip, or edit quantities.

This is the main custom commerce extension besides registration and schedule validation.

### 6.7 Process 7 — Place order to fulfillment

1. Checkout Flow (OOTB B2B checkout) → `Order` + `OrderItem`.
2. Generate Order Summary (Order Management action).
3. Platform Event `Order_Placed__e` or CDC on Order Summary → MuleSoft.
4. WMS allocates from `Default_DC__c`; TMS books cold-chain.
5. Fulfillment Order / Shipment updates return via API.
6. Invoice in ERP; optional Salesforce AR snapshot.
7. Rebate DPE picks up qualified transactions.

Place Order must **not** wait on ERP. 50k orders/day requires async integration, idempotent keys (`Order.Id` / `OrderReferenceNumber`), and bulk APIs outbound.

---

## 7. Security, sharing, and branch isolation

### 7.1 Organization-Wide Defaults

| Object | OWD | Reason |
|---|---|---|
| Account | Private | Branch A must not see Branch B |
| Contact | Controlled by Parent | Follows Account |
| Contract | Private | MSA visible internally; external via sharing set to Corporate? Usually **internal only**. Storefront does not need to read Contract if prices come from price books |
| Order / Order Summary | Private | Branch sees only its orders |
| Opportunity | Private | Internal sales |
| Custom Delivery_Schedule__c | Private / Controlled by Parent | Branch or internal ops |
| Product2 | Public Read | Visibility is entitlement-controlled in the store, not CRUD |

### 7.2 High-volume buyers (Customer Community)

Use **Sharing Sets** (Experience Cloud), not roles:

- User.Account = Account.Id → Read on Account  
- User.Account = Order.AccountId → Read/Write on Order (as required)  
- User.Contact = Contact.Id → Read own contact  

Result: a chef automatically sees **only their Branch Account and its orders**. No Apex sharing, no roles, no implicit-share explosion.

If a district chef must operate two branches, use **Contacts to Multiple Accounts** + Sharing Set on `Contact.RelatedAccount` (documented for Experience Cloud when CTMA is enabled). Cap the number of extra branches; this is not an HQ tool.

### 7.3 Branch admins (Customer Community Plus)

- One role per account is the Salesforce-recommended default (up to three is possible; more roles hurt performance).
- Do **not** enable External Account Hierarchy for the 15,000-child client. EAH supports max **five levels**, does not roll up Sharing Sets, and would fight branch isolation.
- Super User Access: **off** for branch users.

### 7.4 Internal users

- Role hierarchy by FSG region (NA / LATAM / EMEA) and function (Sales, Commerce, Quality, Ops).
- Criteria-based sharing: Quality Officers see Orders where `Default_DC__c` is in their region.
- Account Teams on Corporate Account for the FSG Account Executive.

### 7.5 Entitlement vs sharing

Do not use sharing to hide products. Product records can be org-wide readable; **Commerce Entitlement Policy** is the storefront control. Sharing protects CRM data (accounts, orders, contracts). Mixing the two is a common anti-pattern.

---

## 8. Scale design for 15,000 branches under one MSA

This is the architectural risk that will fail a design review if ignored.

### 8.1 Parent-child data skew

Salesforce documents serious implicit-share cost when **≥ 10,000 children** sit under one parent (example: 300,000 contacts under one dummy account). Rules:

- Contacts live on **Branch**, not Corporate.
- Orders look up to **Branch**, not Corporate.
- Corporate parent has **Region children**, not 15,000 branch children.
- Never use a dummy “Unassigned Corporate Users” account for self-reg fall-through.

### 8.2 Ownership skew

Do not assign 15,000 Branch Accounts to one FSG integration user as owner if those accounts participate in role-based sharing. Use a small pool of regional owner users, or make branches owned by a user **without** a role in a deep hierarchy, and rely on sharing sets for externals.

### 8.3 Lookup skew

Avoid 15,000 branches looking up to a **single** hot record that is updated concurrently (for example a “Current Price Book” custom object row, or a single Buyer Group record that is updated when members change).

**Buyer Group membership pattern**

Stored `BuyerGroupMember` for 15,000 accounts on one `BuyerGroup` is a lookup skew on that group. It often works if the group record is rarely updated. Safer OOTB-extension pattern:

**Buyer Group Extension** (`CommerceBuyGrp.BuyerGroupEvaluationService`, extension point `Commerce_Domain_BuyerGroup_EvaluationService`)

At storefront runtime, Apex returns buyer group Ids from `Account.Active_Contract__r.Buyer_Group__c` (+ region group). No 15,000 member rows, no member-insert lock storm during onboarding.

Cache the Contract → Buyer Group map in Platform Cache (org partition) with a short TTL; do not SOQL Contract on every PDP if avoidable.

### 8.4 Role limits

| Item | Documented guidance |
|---|---|
| Experience Cloud account roles default max | 50,000 (100,000 with support + design review; absolute max 500,000 with special approval) |
| Roles created per CCP/Partner account | 1–3 |
| High-volume Customer Community | **Zero roles** |

If every branch admin is CCP with 1 role × 15,000 branches = 15,000 roles — acceptable. If every chef is CCP with 1 role, 150,000 roles — **fails default limit**. This is why chefs are high-volume.

### 8.5 External Managed Accounts limit

200 target accounts per managing user. Irrelevant for branch-local admin; fatal if someone proposes “corporate admin switches into every store.”

### 8.6 Order volume (50k/day)

- Index `AccountId`, `EffectiveDate`, `Status`, `Location_Code__c` (via Account), custom DC fields.
- Thin triggers: before-save Flow for denormalized `Ultimate_Parent__c` / `Contract_Number__c` on Order; no SOQL in loops.
- Move ERP to **async** (PE + Queueable / middleware).
- Order Management for fulfillment state, not custom status fields on `Order` with heavy workflow.
- Big Objects or data archive for orders older than the rebate/audit window.
- Search: Commerce Connect API / Connect in Apex; do not run SOSL across all products without entitlement filters (platform already entitlement-filters store APIs).

### 8.7 Time zones

- Org default timezone is irrelevant to chefs.
- User timezone on the Experience user.
- `Delivery_Schedule__c.Cutoff_Timezone__c` is the **branch/DC** zone, not the user zone.
- All cutoff calculations in Apex `TimeZone.getTimeZone(id).getOffset()`.
- Contract dates stored as dates (not datetimes) to avoid “expired at midnight GMT” bugs.

---

## 9. Identity options by enterprise maturity

| Tier | Mechanism | When |
|---|---|---|
| 1 | Email OTP + domain allow-list + location code | Default for most of 1,200 enterprises |
| 2 | Same, plus Branch Admin approval of 2nd+ users (`Registration_Request__c`) | Higher fraud sensitivity |
| 3 | SAML / OIDC SSO with JIT `Auth.RegistrationHandler` | The 15,000-location client and any enterprise with a corporate IdP |

JIT mapping (documented Salesforce Identity pattern): IdP assertion includes `email`, `firstName`, `lastName`, `storeNumber`. Handler finds Branch by Location Code + domain, creates Contact/User if absent, updates attributes, never creates a new Account.

My Domain + named Experience URL. Optional Login Discovery if the same email could exist on Micro-Buyer and Corporate (prefer unique username = email and a single person, one Contact).

---

## 10. Coexistence with Micro-Buyers

| Topic | Corporate | Micro-Buyer |
|---|---|---|
| Account | Branch Buyer Account under Corporate | Standalone Business Account (or Person Account if truly one person) |
| Registration | Domain + location code; never auto-create Account | OOTB B2B self-reg may create a Business Account + default buyer groups (up to 20) |
| Catalog | MSA entitlement policy | Open wholesale catalog entitlement |
| Price book | Contracted | Standard wholesale |
| License | HVPU + one CCP admin | HVPU |
| Guest browse | Off for contracted prices | Optional |

Mis-registration (chef uses Micro-Buyer form) is blocked by detecting an allow-listed domain and redirecting to Corporate registration.

---

## 11. OOTB vs custom decision matrix

| Requirement | OOTB | Custom | Decision |
|---|---|---|---|
| Store, cart, checkout, PLP/PDP | B2B LWR Commerce | — | OOTB |
| Product catalog & categories | `ProductCatalog` | — | OOTB |
| Hide non-contracted SKUs | `CommerceEntitlementPolicy` | Flow to sync policy from Contract Lines | OOTB + light automation |
| Contracted unit prices | `Pricebook2` + `BuyerGroupPricebook` | Generate price book from Contract on activation | OOTB + automation |
| SKU quantity breaks | `PriceAdjustmentSchedule` | — | OOTB |
| Contract-based pricing engine | Revenue Cloud Contract Item Price | — | OOTB if licensed |
| MSA legal record | `Contract` | Extra MSA fields | OOTB + fields |
| Multi-year term / expiry gating | Contract dates + Flow to disable BuyerAccount | — | OOTB automation |
| Self-reg email OTP | Configurable Self-Reg / Identity | — | OOTB |
| Bind user to correct branch | — | Apex handler + Location Code | **Custom (required)** |
| Domain allow-list | — | `Email_Domain__c` | **Custom (required)** |
| Branch-only user admin | Delegated External User Administrator | First-admin bootstrap Flow | **OOTB** + bootstrap |
| Shop as another branch | External Managed Accounts (≤200) / CTMA | — | OOTB, limited use |
| Requested delivery date | `CartDeliveryGroup.DesiredDeliveryDate` | — | OOTB |
| Contracted delivery calendar | — | `Delivery_Schedule__c` + checkout calculator | **Custom (required)** |
| Split shipments / multi-DC | Cart Delivery Groups | Stamp default DC | OOTB + field |
| Standing produce orders | Not a native wholesale feature | `Standing_Order__c` + scheduled job | **Custom** |
| Enterprise volume rebate | Rebate Management | DIY aggregation | OOTB product preferred |
| 15k buyer group assignment | BuyerGroupMember **or** Buyer Group Extension | Extension Apex | **Extension recommended** |
| SSO JIT | SAML/OIDC + RegistrationHandler | Attribute mapping Apex | OOTB + handler |
| Order fulfillment | Order Management | ERP adapter | OOTB + integration |
| Branch isolation | Sharing Sets | — | OOTB |
| HQ analytics across 15k branches | CRM Analytics / Big Object, internal users | — | OOTB analytics, not storefront |

---

## 12. Representative custom implementation notes (for the required gaps)

These are design-level, not production code. They map to documented extension points.

### 12.1 Self-registration handler responsibilities

Implements `Auth.ConfigurableSelfRegHandler` **or** a guest-exposed Apex controller used by a custom LWR registration LWC (B2B Developer Guide: *Implement Custom Self-Registration for a B2B Store*).

Must:

- Run in a dedicated without-sharing service only for the domain/location lookup, then create Contact/User in a `with sharing` context where possible.
- Query `Email_Domain__c` by domain (indexed).
- Query Branch Account by `Location_Code__c` (External ID) and `Ultimate_Parent__c`.
- Call `createBuyerAccount` only if `BuyerAccount` is missing (idempotent).
- Assign Buyer permission set group configured on the store (`CommerceConfigRelatedRecord` / store self-reg config for defaults).
- Prefer `Site.createExternalUser` / the handler’s `createUser(accountId, profileId, …)` passing the **Branch** accountId, not the L&R default account.
- Never attach corporate users to the default self-reg Account (that Account would become a skew magnet).

### 12.2 Buyer Group Evaluation Service

Extension: `Commerce_Domain_BuyerGroup_EvaluationService`.

Return:

1. MSA buyer group from `Account.Active_Contract__r.Buyer_Group__c`
2. Optional region group from `Account.Parent.Region_Buyer_Group__c`
3. Optional global promotions group

Respect documented considerations (governor limits; this runs on storefront requests). Memoize per Account in request cache.

### 12.3 Delivery calculator

Custom shipping calculator in the B2B checkout sequence (documented checkout calculators). Input: cart account, requested date, methods. Output: filtered methods, possibly overwritten date, error code for LWR checkout component.

### 12.4 Standing order job

`Schedulable` + `Database.Batchable` over `Standing_Order__c WHERE Next_Run__c <= TODAY AND Status = Active`, chunked by timezone windows so EMEA cutoffs do not wait for NA. Create cart via Connect API or create `Order` directly with an integration user, then Generate Order Summary. Idempotency key: `StandingOrderId + DeliveryDate`.

---

## 13. Integration architecture

```text
Salesforce B2B  --CDC/PE-->  MuleSoft  -->  ERP (pricing truth optional)
                                 |          WMS (allocation, lot, expiry)
                                 |          TMS (cold-chain routing)
                                 |          Payment / Trade credit
Farm / PIM assortment  -->  MuleSoft  -->  Product2, inventory cache
IdP (enterprise SSO)   -->  SAML/OIDC -->  Experience Cloud
```

**Inventory:** Commerce Inventory Service or custom availability adapter; do not query ERP on every PDP.

**Pricing truth:** For FSG, Salesforce contracted price book is execution truth for the storefront; ERP remains invoice truth. Nightly reconcilers flag mismatches.

**Idempotency:** ExternalId on Order = `FSG-{OrderNumber}`.

---

## 14. Internal FSG personas (how they use this)

| Persona | App | Actions |
|---|---|---|
| Enterprise AE | Sales Cloud | Wins MSA Opportunity, submits Contract for approval |
| Contract / Pricing Admin | Commerce + Contract | Loads entitlement products, price book, adjustment tiers, rebate program |
| Branch Onboarding | Data / Flow | Bulk loads locations, issues location codes, monitors `Registration_Request__c` |
| Quality & Compliance | Lightning | Sees shipments/orders for their DCs; logs inspections (custom or Cases) |
| Customer Support | Console | Account-hierarchy aware, but opens Branch Account, not parent, to avoid UI of 15k children |

---

## 15. Governance, limits, and risks

| Risk | Mitigation |
|---|---|
| Self-reg attaches 150k users to one default Account | Custom handler must pass Branch `accountId`; monitor Account contact counts |
| CCP for all chefs blows role limit | HVPU for chefs; CCP only for branch admin |
| Price book with 50k SKUs × 1,200 MSAs | Do not clone full assortment per MSA; entitle a subset; generate price book entries only for contracted SKUs |
| Entitlement policy with huge product lists | Prefer category-level entitlement where Commerce allows; otherwise batch maintain `CommerceEntitlementProduct` |
| Contract expiry while carts are open | Nightly job: if Contract expired, deactivate BuyerAccount / remove extension groups; checkout validator refuses place-order |
| Guest Apex attack surface | Minimal guest class access, domain allow-list, OTP, Event Monitoring |
| Account Hierarchy UI useless at 15k | Custom LWC “Find Branch” search by Location Code for internal users |
| Rebate calc on live Order object | DPE / off-platform aggregation |
| 200 External Managed Account limit | Do not design HQ storefront admin around account switcher |

**Named Salesforce limits to track in the design review**

- ≥ 10,000 children per parent = data skew guidance  
- 50,000 Experience account roles (default)  
- 200 External Managed Accounts per user  
- Sharing Set objects / access mappings (plan Account, Order, Contact, custom Delivery_Schedule__c)  
- Price Adjustment Tiers: keep modest per SKU; Subscription Management docs cite a 25-tier cap in that product — keep Commerce tiers similarly small  
- Buyer Group Extension governor limits on storefront traffic  
- Store: one catalog per store  
- B2B: multiple entitlement policies per store  

---

## 16. Implementation sequence

1. **Foundation:** Org, LWR B2B store, OWD, identity, Product catalog, standard wholesale price book.  
2. **Party model:** Record types Corporate / Region / Branch; External ID Location Code; Ultimate Parent stamp; Bulk API pattern.  
3. **MSA path:** Contract layout, approval, Flow to create Buyer Group + Price Book + Entitlement Policy.  
4. **Pilot enterprise (≤ 200 branches):** Stored BuyerGroupMember OK; Sharing Sets; one CCP admin per branch; OOTB checkout with DesiredDeliveryDate.  
5. **Registration:** Custom LWR component + handler; domain object; OTP; negative tests (wrong domain, expired contract).  
6. **Delivery schedules:** Custom object + calculator.  
7. **Scale-up:** Buyer Group Extension; region sharding for the 15k client; HVPU conversion confirmed; archive strategy.  
8. **Rebates:** Manufacturing Cloud program on Corporate member.  
9. **SSO:** JIT for the largest client.  
10. **Standing orders:** After checkout is stable.  
11. **OMS + MuleSoft:** Async fulfillment; performance test 50k orders/day (burst).  

Do not start with Apex sharing or a custom cart. Those are the usual over-builds for this requirement.

---

## 17. Acceptance criteria (solution-level)

1. An Activated Contract on Corporate Account causes all in-term Branch Buyer Accounts to see **only** the entitled catalog and contracted price book.  
2. A chef registering with `name@acmecorporate.com` and a valid location code becomes a Contact **on that Branch**, not on Corporate, and can check out.  
3. The same email domain with another location code lands on the other Branch; orders are invisible across branches.  
4. A Gmail address cannot enter the corporate catalog.  
5. The designated Branch Admin can create/deactivate users on that Branch and **cannot** see the user list of a sibling Branch.  
6. Cart quantity breaks apply via Price Adjustment Tiers; quarterly enterprise rebate accrues at Corporate, not as a cart discount.  
7. Desired delivery dates outside the contracted window are rejected in the buyer’s DC timezone.  
8. 15,000-branch client: no Account has ≥ 10,000 direct children; chefs have no roles; storefront buyer groups resolve without a 15,000-row member insert at login.  
9. Contract end date reached: storefront place-order is blocked the next day in the Contract’s defined timezone/date semantics.  
10. Peak order test: Place Order succeeds without a synchronous ERP round trip.

---

## 18. Worked example — 15,000-location enterprise (“Acme Dining”)

1. AE closes Opportunity; Legal activates Contract `MSA-ACME-2026` (3-year), Price Book `PB-ACME-2026`, Entitlement Policy `EP-ACME-2026` (2,400 SKUs), Buyer Group `BG-ACME-2026`, Rebate Program quarterly 2%/3%/4% by total lbs.  
2. Integration loads 15,000 Branch Accounts under 8 Region Accounts (~1,875 children each), each with Location Code, ship-to, DC, delivery schedule.  
3. `Email_Domain__c`: `acmedining.com` → Acme Corporate.  
4. Chef at store `ADX-14821` verifies email OTP, enters location code, is provisioned as HVPU Buyer on Branch “Acme #14821 – Austin”.  
5. Storefront Buyer Group Extension returns `BG-ACME-2026` + `BG-AMER-CHILL`. Catalog and prices are Acme’s.  
6. Chef adds 40 cases; Price Adjustment Tier 25–99 cases applies 8% off that SKU.  
7. Checkout offers Tue/Thu dates only; Monday is rejected.  
8. General Manager (first user) is CCP Branch Admin, invites two sous-chefs, resets a password; cannot open Acme #14822.  
9. Orders flow to OMS → Dallas DC. Quarterly DPE aggregates all Acme branches for rebate accrual on the Corporate Account.

---

## 19. Salesforce documentation map

Use these as the compliance checklist in design review:

| Topic | Reference |
|---|---|
| B2B data model (Store, Catalog, Entitlement, Buyer Group, Price Book) | [B2B Commerce Data Model](https://developer.salesforce.com/docs/commerce/salesforce-commerce/guide/b2b-b2c-dev-data-model.html) |
| Store access, buyer accounts, self-registration, Buyer Group Extension | [Access to a B2B Store](https://help.salesforce.com/s/articleView?id=commerce.comm_access.htm) |
| Commerce key concepts (buyer group, entitlement, price adjustment schedule, store) | [Commerce Key Concepts](https://help.salesforce.com/s/articleView?id=commerce.comm_key_concepts.htm) |
| Buyer group price books and priority | [BuyerGroupPricebook](https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/sforce_api_objects_buyergrouppricebook.htm) |
| Volume tiers | [PriceAdjustmentSchedule](https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/sforce_api_objects_priceadjustmentschedule.htm), [PriceAdjustmentTier](https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/sforce_api_objects_priceadjustmenttier.htm) |
| LWR B2B template | [Create a Store with the B2B Commerce (LWR) Template](https://developer.salesforce.com/docs/commerce/lwr-migration/guide/create-lwr-template.html) |
| Custom B2B self-registration | [Implement Custom Self-Registration for a B2B Store](https://developer.salesforce.com/docs/commerce/salesforce-commerce/guide/b2b-comm-custom-self-registration.html) |
| Configurable self-reg handler & email OTP | [Auth.ConfigurableSelfRegHandler](https://developer.salesforce.com/docs/atlas.en-us.apexref.meta/apexref/apex_interface_Auth_ConfigurableSelfRegHandler.htm) |
| Default self-reg Account | [NetworkSelfRegistration](https://developer.salesforce.com/docs/atlas.en-us.sfFieldRef.meta/sfFieldRef/salesforce_field_reference_NetworkSelfRegistration.htm) |
| Buyer Manager / buy-on-behalf / effectiveAccountId | [Grant Buyers Access to External Accounts](https://help.salesforce.com/s/articleView?id=sf.comm_buy_on_behalf.htm) |
| Delegated External User Administration | Experience Cloud Help: Delegate External User Administration |
| Cart delivery date & methods | [CartDeliveryGroup](https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/sforce_api_objects_cartdeliverygroup.htm), Commerce Cart APIs |
| Contract | [Contract object](https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/sforce_api_objects_contract.htm) |
| Contract-based pricing | Trailhead: Configure Contract-Based Pricing (Revenue Cloud) |
| Account contracted prices (CPQ) | Trailhead: Account-Based Contracted Pricing |
| Rebate programs | [Create a Rebate Program](https://help.salesforce.com/s/articleView?id=xcloud.user_rebates_create_rebate_program.htm) |
| Parent-child data skew | [Parent-Child Data Skew](https://developer.salesforce.com/docs/atlas.en-us.draes.meta/draes/draes_object_relationships_parent_child_data_skew.htm) |
| LDV / 10k child guidance | Trailhead: Optimize Large Data Volumes |
| Experience Cloud account roles | Trailhead: Optimizing Role Hierarchy and Account Roles |
| Contacts to Multiple Accounts + sharing sets | [CTMA considerations](https://help.salesforce.com/s/articleView?id=sales.shared_contacts_considerations.htm) |
| Account Relationship Data Sharing Rules | [Account Relationships and Data Sharing Rules](https://help.salesforce.com/s/articleView?id=platform.networks_partner_account_relationships_and_sharing.htm) |
| Buyer Group Extension point | B2B Commerce Developer Guide: Available Extensions (`Commerce_Domain_BuyerGroup_EvaluationService`) |

---

## 20. Summary for architecture review

Corporate Ordering is a **standard B2B Commerce entitlement problem** plus a **non-standard identity-resolution problem** at extreme account fan-out.

- **OOTB** already provides the store, catalog isolation, contracted price books, volume tiers, delivery-date capture, branch-scoped delegated user admin, contracts, and (with add-on clouds) contract-based pricing and rebate aggregation.  
- **Custom** is justified only to (1) register a chef onto the correct Branch using corporate email + location code, (2) evaluate buyer groups without 15,000-row membership skew, (3) enforce contracted delivery calendars and standing orders, and (4) keep the 15,000-location hierarchy below skew and role limits.

If those four extensions are done on the documented Commerce / Identity extension points, FSG does not need a custom storefront, custom sharing engine, or per-branch Contract.
