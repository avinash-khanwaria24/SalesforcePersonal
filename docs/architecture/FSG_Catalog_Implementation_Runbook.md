# FSG Catalog — Implementation Runbook

Deploy and configure in this order. The architecture is in `FSG_Product_Catalog_Architecture.md`.

## 0. Prerequisites

- Enterprise or Unlimited edition
- B2B Commerce and Experience Cloud enabled
- New B2B store uses the **LWR** template
- Multi-currency enabled if you sell in more than one currency
- A Salesforce DX alias, for example `fsg-dev`

## 1. Baseline sharing (OOTB)

1. Setup → Digital Experiences → Enable.
2. Setup → Commerce → run **Commerce Setup Assistant**.
3. Setup → Sharing Settings:
   - Product: Internal **Public Read Only**, External **Private**
   - Account, Case: Internal **Private**, External **Private**
   - Confirm Catalog, Entitlement Policy, Buyer Group external access is **Private**
4. Do not grant Product, Catalog, or Entitlement Policy CRUD on the base Experience Cloud profile.

## 2. Deploy this package

```bash
sf project deploy start --source-dir force-app --target-org fsg-dev
```

Creates:

- `Region__c`, `Product_Availability__c`, `Supplier_Product__c`
- Account / Product2 / User / Case fields
- `Region_Commerce_Map__mdt` (NA, EMEA, APAC, LATAM)
- Permission sets, public groups, queues, sharing rules, FSG Catalog app

## 3. Load regions

Create `Region__c` records that match the custom metadata `Region_Code__c` values:

| Region Name | Region Code | Currency | Locale example |
| --- | --- | --- | --- |
| North America | NA | USD | en_US |
| Europe Middle East Africa | EMEA | EUR | en_GB |
| Asia Pacific | APAC | USD | en_AU |
| Latin America | LATAM | USD | es_MX |

Add country-level child regions later (`Parent_Region__c`) if Markets are per country. If you add countries, add matching `Region_Commerce_Map__mdt` rows and sharing rules.

## 4. Commerce catalog (OOTB UI)

1. App Launcher → Catalogs → create **FSG Master Catalog** (or use the store default).
2. Build categories (max five levels). Assign products only after they exist.
3. Create or open the LWR B2B store. Assign the catalog (one catalog per store).
4. Create Price Books: `FSG NA USD`, `FSG EMEA EUR`, `FSG APAC USD`, `FSG LATAM USD`. Add entries from the standard price book.
5. Create Buyer Groups and Entitlement Policies using the **exact names** in `Region_Commerce_Map__mdt`.
6. Create Commerce **Markets** (`FSG North America`, `FSG EMEA`, `FSG APAC`, `FSG LATAM`):
   - Ship-to country / locale / currency / price book
   - Assign the regional entitlement policy to the **Market** (Market policies override Buyer Group policies)
7. Associate Buyer Groups with the store.
8. Guest browsing: off.

After any entitlement or category change: Setup → B2B Commerce → store → **rebuild search index**.

## 5. Experience Cloud

### Buyer site

- LWR store community
- Members: buyer profile + Salesforce Buyer / Buyer Manager permission sets + `FSG_Buyer_Portal`
- Enable Accounts as buyers and add them to the regional Buyer Group (Flow, section 7)

### Supplier site

- Separate Experience Cloud site
- Members: supplier profile + `FSG_Supplier_Portal`
- Digital Experiences → Settings → **Sharing Sets**:
  - Label: FSG Supplier Listings
  - Profile: supplier profile
  - Object: Supplier Product
  - User: Account → Target: Supplier Account
  - Access: Read/Write
- Do not grant Product2 Read

## 6. Internal users

1. Build the role hierarchy (Global Catalog Director → regional managers → merchandisers).
2. Set `User.Operating_Region__c`.
3. Add merchandisers to `FSG_NA_Merchandisers` (and EMEA / APAC / LATAM) public groups.
4. Assign `FSG_Regional_Merchandiser` or `FSG_Catalog_Admin`.
5. Grant **Use** on the regional Price Book to the regional role (Price Book Sharing).
6. Add merchandisers to the matching Case queue.

## 7. Assignment and automation (OOTB)

Configure in Setup (not in this package):

1. Case record type **Product Onboarding**.
2. Case assignment rules:
   - `Catalog_Region__c` equals the NA region Id → `FSG_NA_Merchandising`
   - Repeat for EMEA, APAC, LATAM
3. Approval process on `Supplier_Product__c` (Submitted → regional merchandiser).
4. Before-save Flow: stamp `Region_Code__c`, `Product_Region_Key__c`, `Supplier_SKU_Key__c`.
5. After-save Flow: Status = Submitted → create Case, set Catalog Region, `Supplier_Product__c`.
6. After-save Flow: Account buyer + region change → BuyerGroupMember from `Region_Commerce_Map__mdt`.
7. After-save Flow: Product Availability Published / Suspended → create or delete `CommerceEntitlementProduct` for the mapped policy.

## 8. Pilot

Use one region (EMEA) with a small set of suppliers and buyers. Run the testing matrix in the architecture document before loading 8,000 farms.

## 9. Optional later

- Country-level Markets instead of four regions
- Revenue Cloud qualification rules for internal quoting
- Omnichannel Inventory Location Groups per region
- Commerce Buyer Group Extensibility Apex only if a buyer must switch ship-to country in-session
- Data Cloud segments for merchandising analytics
