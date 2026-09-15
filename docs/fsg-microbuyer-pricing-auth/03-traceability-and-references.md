# 03 — OOTB vs Custom, Scale, Risks, and Salesforce References

Companion to [01-foundation.md](./01-foundation.md) and [02-requirements.md](./02-requirements.md).

---

## 1. OOTB vs custom decision matrix

Legend: **OOTB** = configure only. **Ext** = documented extension point (Apex interface Salesforce ships for this purpose). **Cust** = FSG-specific object/field/LWC.

| Capability | Mechanism | Type | Why not the alternative |
| --- | --- | --- | --- |
| Business Account + Contact + User | Standard objects, Experience Cloud | OOTB | Person Accounts are the D2C model. |
| Enable purchasing | `BuyerAccount`, Buyer Group, Entitlement Policy, Buyer permission set | OOTB | Custom “customer” object would break Commerce. |
| B2B self-registration | Experience Builder page + `Site.createExternalUser` + Salesforce sample controller pattern | Ext | Configurable self-reg does not create BuyerAccount / BuyerGroupMember. |
| Guest regional browse | Guest Buyer Group + Entitlement + guest browsing | OOTB | Custom catalog service is unnecessary. |
| Regional catalog | `ProductCategory` + Entitlement Policy + 3 WebStores | OOTB | 14 stores for 14 time zones over-fit locale. |
| Wholesale cart/checkout | LWR B2B Commerce | OOTB | Headless-only is optional later, not required for MVP. |
| List vs contracted unit price | Price Books + `BuyerGroupPricebook` | OOTB | Per-account catalog clone will not scale to 1,200 parents. |
| Volume unit discount | `PriceAdjustmentSchedule` / `PriceAdjustmentTier` | OOTB | Custom discount Apex fights the pricing calculator. |
| Period-end rebates | `Contract` + ERP or thin accrual object | OOTB + Cust | Rebates are financial SoR, not cart promotions. |
| Three service tiers | `OrderDeliveryMethod` + charge `Product2` | OOTB | Three SKUs-as-products without delivery methods lose OMS delivery grouping. |
| Fee by weight × temp × urgency × region × contract | `ShippingCartCalculator` + `Service_Tier_Rate__c` | Ext + Cust | No OOTB rate card has this many dimensions. |
| Hide Ground for chilled carts | Same calculator eligibility | Ext | Delivery procedure metadata cannot express max(temp class). |
| Catch-weight true-up | OMS adjustments after WMS weigh-in | OOTB | Recalculating in the original cart is too late. |
| Order history | `OrderSummary` + Commerce Order Summary APIs | OOTB | Custom Order__c duplicates OMS. |
| Carrier tracking | `Shipment` + storefront shipments API | OOTB | |
| Temperature timeline | Named Credential to IoT/Data Cloud; `Cold_Chain_Alert__c` for excursions only | Cust | IoT on a custom object violates LDV. |
| Invoices | OMS `Invoice` and/or Salesforce Connect | OOTB | Copying years of invoices into Salesforce is LDV. |
| Social buttons | Auth Providers + site Login & Registration | OOTB | Homegrown OAuth in LWC. |
| JIT + email match + domain deny | `Auth.RegistrationHandler` | Ext | OOTB template creates the wrong license and skips Commerce. |
| Confirm IdP mapping | `Auth.ConfirmUserRegistrationHandler` | Ext | Optional hardening. |
| Bind social to existing password user | `/services/auth/link/` + `ThirdPartyAccountLink` | OOTB | |
| Branch user admin **only on that branch** | Users on branch Account + Delegated External User Administration | OOTB | Custom LWC user-admin is a last resort. |
| HQ sees descendants | External Account Hierarchy + CC+ roles | OOTB | Sharing Sets do not roll up. |
| Chefs cannot see sibling branches | OWD Private + Sharing Set on branch Account | OOTB | |
| Q&C officers | Salesforce license, regional Public Groups, Case | OOTB | Do not put inspectors on Experience Cloud. |
| Internal SSO | Okta SAML + SCIM | OOTB | |
| Same-day zone table | `Same_Day_Zone__mdt` or TMS callout | Cust | |
| Complete-profile after social | LWC + Flow | Cust | Auth Provider does not collect tax ID. |

---

## 2. Custom inventory (keep it small)

### 2.1 Custom objects

| API name | Volume | Audience | Justification |
| --- | --- | --- | --- |
| `Service_Tier_Rate__c` | hundreds of rows | Internal calculator | Multi-dimensional fulfillment rate card |
| `Cold_Chain_Alert__c` | exceptions only | Buyer (read) + Q&C | Threshold breaches, not pings |
| `Rebate_Accrual__c` | one per contract per period | HQ + finance | If ERP does not expose rebate balances |
| `Inspection__c` | Q&C operational | Internal | No standard Inspection in core Sales/Service |
| `Certification__c` | per farm | Internal + supplier portal | Certificate register |
| `Lot_Batch__c` | thin, external id | Internal | Food-safety registry pointer |

Customer Community licenses include a **small custom object allowance** for portal users. Buyer-facing custom objects must stay in that budget: ideally only `Cold_Chain_Alert__c` (and invoices as standard/external). Rate cards are **not** on the portal.

### 2.2 Custom Apex / LWC

| Component | Interface / host | Requirement |
| --- | --- | --- |
| `FSG_CommerceSelfRegController` | `@AuraEnabled` + `Site.createExternalUser` | R1 |
| `fsgMicroBuyerRegister` LWC | Self-registration page | R1 |
| `fsgCompleteBusinessProfile` LWC + Flow | Authenticated home | R1 / R3 |
| `FSG_ShippingCartCalculator` | `CartExtension.ShippingCartCalculator` | R2 |
| `FSG_MicroBuyerRegHandler` | `Auth.RegistrationHandler` | R3 |
| `FSG_ConfirmUserRegHandler` | `Auth.ConfirmUserRegistrationHandler` | R3 optional |
| `fsgColdChainTracking` LWC | Order Summary record page | R1 |
| Buyer Group Extension class | Commerce Buyer Group Extension | R1 region moves |

All calculator/handler classes are **with sharing** except the minimum insert path for guest registration, which runs as guest and must only create the caller’s records.

---

## 3. Scale and LDV (50k orders/day)

| Fact | Implication for this design |
| --- | --- |
| ~18M order headers / year | OMS Order Summary is the buyer UX; archive or Connect after ~90 days. Do not add roll-up summaries from OrderItem to Account. |
| Branch fan-out up to 15,000 | Intermediate Region Accounts. No parent with > ~2,000–3,000 children. |
| 150,000 chefs | Customer Community (high volume), not CC+ roles. |
| IoT temperature | Data Cloud / lake; Salesforce gets alerts. |
| Rate card | Cache in `Cache.Org`; calculator must be bulk-safe (one cart, many items, zero SOQL in item loops). |
| Sharing Sets | Preferred for high-volume users; they do not count against role limits. |

Salesforce LDV guidance: avoid **data skew** (>10k children per parent) and **ownership skew**. New micro Accounts should be owned by a **regional owner pool** (several users), not one “Integration” user owning millions of Accounts.

---

## 4. Identity and license anti-patterns to refuse

1. **Social login creating Standard Users** — the OOTB handler template does this if you leave `INTERNAL_USER_PROFILE` in place.
2. **Enterprise Google Workspace** JIT into `Micro_Buyer` Accounts — domain denylist + separate enterprise login.
3. **All 150,000 chefs on CC+** — hits the ~50,000 role limit.
4. **Branch admins as Contacts on HQ** — delegated admin would span the chain; violates “only their branch.”
5. **Person Accounts for caterers** — blocks multi-user wholesale and Buyer Manager.
6. **B2C SLAS as the portal IdP** — wrong party model (shopper vs Account-Contact).
7. **Storing cold-chain pings on `CustomObject__c`** — org storage and sharing recalculation risk.

---

## 5. Security, privacy, and compliance

| Topic | Design |
| --- | --- |
| PII | Contact/User; Shield Platform Encryption on Tax ID and optional national IDs. |
| Guest | Secure Guest User Record Access; no sharing rules to guest; Apex whitelist. |
| Auth secrets | Auth Provider consumer secrets in Setup, not custom metadata. Named Credentials for IoT API. |
| Session | Site-level timeout; lock sessions to the domain. |
| GDPR / privacy | Experience Cloud consent; Individual object if marketing; regional Hyperforce residency for EMEA if required. |
| Food safety | Lots and certificates; not in the buyer registration path except hold flags that hide SKUs via entitlement or inventory. |
| PCI | Never store PAN; Salesforce Payments or hosted gateway. |

---

## 6. Implementation sequence

| Phase | Outcome | Requirements |
| --- | --- | --- |
| **P0 — Foundation** | Org, 3 WebStores, catalog, OWD, Sharing Sets, licenses, Order Delivery Methods, list price books | All |
| **P1 — Micro-buyer password path** | Self-reg LWC, BuyerAccount, regional groups, checkout, Order Summary, OMS invoice | R1 |
| **P2 — Service tiers** | Rate card, ShippingCartCalculator, eligibility, OMS routing to refrigerated locations | R2 |
| **P3 — Social login** | Google, then Apple, then LinkedIn; handler; account linking; complete-profile | R3 |
| **P4 — Enterprise overlay** | Contracts, contracted books, branch CC users, delegated admin, rebates | Scenario (branch admin + contract discounts) |
| **P5 — Cold-chain UX** | Shipment API page + IoT overlay + alerts | R1 tracking |
| **P6 — Hardening** | ConfirmUser handler, Event Monitoring, archive, Connect for old invoices | All |

P2 can start in parallel with P1 once delivery methods exist. Do not enable social JIT (P3) before complete-profile and domain denylist exist.

---

## 7. Risks and trades

| Risk | Mitigation |
| --- | --- |
| Social JIT creates duplicate businesses (no tax ID at login) | Shell Account + mandatory complete-profile before BuyerAccount Active; Duplicate Rules on tax ID |
| Apple Hide My Email | Billing email on Account; User.Email may be relay |
| Shipping calculator CPU on large carts | Pre-sum weights; org cache rate card; no per-line SOQL |
| Same-day promised but RDC capacity gone | Fail-closed: hide Ultra-Fresh when inventory/capacity API says no; never sell a tier OMS cannot fulfill |
| 50k orders/day sharing recalculation | High-volume licenses + Sharing Sets; no implicit parent-child on Order to HQ |
| Contracted price book proliferation | Tier books (Gold/Silver) not 1,200 unique books unless prices are truly unique |
| Guest registration abuse | reCAPTCHA on LWC, rate limit, Duplicate Rules, optional KYC |
| CC+ role limit if Branch Admin assigned too broadly | One CC+ admin per branch that **asks** for self-admin; chefs stay Customer Community |

---

## 8. Requirements traceability

| ID | Statement | Design section | Primary OOTB | Custom |
| --- | --- | --- | --- | --- |
| R1 | Micro-buyers register, browse regional produce, wholesale order, track cold-chain, view invoices | [02 § R1](./02-requirements.md#requirement-1--micro-buyer-registration) | Experience Cloud, B2B Commerce, OMS Order Summary / Shipment / Invoice, Entitlement Policies | Self-reg LWC/Apex, complete-profile, tracking LWC, optional Connect |
| R2 | Three tiers; price by weight, temperature, urgency, corporate contract discounts | [02 § R2](./02-requirements.md#requirement-2--pricing-and-service-tiers) | OrderDeliveryMethod, Price Books, Buyer Groups, PriceAdjustmentSchedule, Cart Calculate | ShippingCartCalculator, Service_Tier_Rate__c, Product temperature fields |
| R3 | Login with Google, LinkedIn, Apple ID | [02 § R3](./02-requirements.md#requirement-3--customer-authentication-social-identity) | Auth Providers, Login & Registration, ThirdPartyAccountLink | Registration Handler, domain denylist, confirm-user |
| S1 | Branch user manages users only in their branch | [01 § 5.3](./01-foundation.md#53-enterprise-branches--isolation--branch-only-user-admin) | Delegated External User Administration, Account-scoped users | None |
| S2 | Enterprise contracted catalogs and rebates | [02 § 2.5](./02-requirements.md#25-enterprise-contracted-catalogs-context-for-r2) | Contract, Buyer Groups, Price Books | Rebate accrual if ERP lacks it |
| S3 | Q&C officers, perishable inspections, RDCs | [01 § 1.2](./01-foundation.md#12-internal-fsg-personas), [01 § 4.6](./01-foundation.md#46-quality--compliance-supporting-not-r1r3) | Service Cloud, Location, Case | Inspection__c, Certification__c |
| S4 | 50k orders/day, 14 time zones, 8,000 farms | [03 § 3](./03-traceability-and-references.md#3-scale-and-ldv-50k-ordersday) | Hyperforce, OMS, Sharing Sets | Archive policy, Data Cloud telemetry |

---

## 9. Salesforce documentation (authoritative)

### Experience Cloud, identity, licenses

- [Experience Cloud user licenses](https://help.salesforce.com/s/articleView?id=users_license_types_communities.htm)
- [Authentication providers (Salesforce as RP)](https://developer.salesforce.com/docs/platform/mobile-sdk/guide/sso-authentication-providers.html)
- [OpenID Connect Auth Provider](https://developer.salesforce.com/docs/platform/mobile-sdk/guide/sso-provider-openid-connect.html)
- [Add an Auth Provider to an Experience Cloud login page](https://developer.salesforce.com/docs/platform/mobile-sdk/guide/communities-configure-community-auth.html)
- [Social sign-on (Trailhead)](https://trailhead.salesforce.com/content/learn/modules/identity_external/identity_external_social)
- [Auth namespace (`RegistrationHandler`, `ConfigurableSelfRegHandler`)](https://developer.salesforce.com/docs/atlas.en-us.apexref.meta/apexref/apex_namespace_Auth.htm)
- [ConfirmUserRegistrationHandler](https://developer.salesforce.com/docs/atlas.en-us.apexref.meta/apexref/apex_interface_Auth_ConfirmUserRegistrationHandler.htm)
- [ThirdPartyAccountLink](https://developer.salesforce.com/docs/atlas.en-us.sfFieldRef.meta/sfFieldRef/salesforce_field_reference_ThirdPartyAccountLink.htm)
- [Site class (`createExternalUser`, `setPortalUserAsAuthProvider`)](https://developer.salesforce.com/docs/atlas.en-us.apexref.meta/apexref/apex_classes_sites.htm)
- [LinkedIn Auth Provider](https://help.salesforce.com/s/articleView?id=xcloud.sso_provider_linkedin.htm)
- [Sharing Sets / external user sharing (Trailhead)](https://trailhead.salesforce.com/content/learn/projects/communities_share_crm_data/external_user_sharing)
- [Delegate External User Administration](https://help.salesforce.com/s/articleView?id=sf.networks_delegate_external_user_administration.htm)
- [Account Switcher permission set](https://help.salesforce.com/s/articleView?id=platform.networks_account_switcher_permissions.htm)
- [Platform sharing architecture](https://architect.salesforce.com/docs/architect/fundamentals/guide/platform-sharing-architecture)

### B2B Commerce and pricing

- [B2B Commerce data model](https://developer.salesforce.com/docs/commerce/salesforce-commerce/guide/b2b-b2c-dev-data-model.html)
- [Commerce key concepts (Buyer Group, Entitlement, Price Book, PAS)](https://help.salesforce.com/s/articleView?id=commerce.comm_key_concepts.htm)
- [Access to a B2B store](https://help.salesforce.com/s/articleView?id=commerce.comm_access.htm)
- [Custom self-registration for a B2B store](https://developer.salesforce.com/docs/commerce/salesforce-commerce/guide/b2b-comm-custom-self-registration.html)
- [Grant buyers access to external accounts (Buyer Manager)](https://help.salesforce.com/s/articleView?id=commerce.comm_buy_on_behalf.htm)
- [Pricing and Promotions APIs](https://developer.salesforce.com/docs/commerce/salesforce-commerce/guide/b2b-d2c-comm-pricing-promotions-apis.html)
- [PriceAdjustmentSchedule](https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/sforce_api_objects_priceadjustmentschedule.htm)
- [Cart Calculate API / calculator order](https://developer.salesforce.com/docs/commerce/salesforce-commerce/guide/cart-calculate-api.html)
- [ShippingCartCalculator](https://developer.salesforce.com/docs/commerce/salesforce-commerce/references/comm-apex-reference/ShippingCartCalculator.html)
- [PricingService](https://developer.salesforce.com/docs/commerce/salesforce-commerce/references/comm-apex-reference/PricingService.html)
- [Order Summary APIs (history, reorder, shipments)](https://developer.salesforce.com/docs/commerce/salesforce-commerce/guide/b2b-d2c-comm-order-summaries-apis.html)

### Order Management and delivery

- [Order Delivery Method fields](https://help.salesforce.com/s/articleView?id=commerce.om_order_delivery_method_fields.htm)
- [FulfillmentOrder](https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/sforce_api_objects_fulfillmentorder.htm)
- [OMS fulfillment and invoices (Trailhead)](https://trailhead.salesforce.com/content/learn/modules/om-salesforce-order-management/om-streamline-order-fulfillment-payment)
- [Distributed order routing (Trailhead)](https://trailhead.salesforce.com/content/learn/modules/om-salesforce-order-management/om-implement-distributed-order-management)

### Do not confuse with B2C shopper identity

- [SLAS identity providers](https://developer.salesforce.com/docs/commerce/b2c-commerce/guide/slas-identity-providers.html) — applicable only if FSG also launched a **consumer** composable storefront. Not the micro-buyer B2B portal.

---

## 10. Success criteria (architecture acceptance)

1. A guest can browse the regional catalog and cannot see another region’s entitled SKUs or any invoice.
2. Password registration creates Account (Micro_Buyer) + Contact + User + BuyerAccount + BuyerGroupMember in one transaction path and lands in the store.
3. Google / LinkedIn / Apple login reuses an existing User on verified email, never creates an internal license, and blocks enterprise domains.
4. A chilled cart never offers Standard Ground; fees change with weight band, temperature class, tier, region, and contract multiplier.
5. A branch admin can reset a chef on **their** branch and cannot see or manage a sibling branch.
6. Order Detail shows OMS shipment tracking; temperature history is an API overlay; excursions only persist as alerts.
7. Invoices render from OMS or Connect without copying the full ERP history into custom objects.
