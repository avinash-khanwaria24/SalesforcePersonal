# 5. Requirements Traceability

| ID | Requirement | Architecture response | Primary products |
| --- | --- | --- | --- |
| 1.1 | Supplier onboarding via public portal; QC vetting; localized catalogs and pickup | Guest form → `Supplier_Application__c` → Compliance Case → Partner Account; `Certification__c`; `Pickup_Schedule__c`; regional Commerce catalog | Experience Cloud, Service Cloud, Partner Community, Files, DocuSign |
| 1.2 | Corporate master agreements; branch users register with corporate email; pre-negotiated catalog; 15k locations | `Contract` + Buyer Groups; email-domain allowlist; intermediate Region/District Accounts; CC+ delegated admin | B2B Commerce, Experience Cloud, CC+ |
| 1.3 | Micro-buyer registration, regional produce, wholesale orders, tracking, invoices | Self-reg + social login; one Account per business; Sharing Set; invoices via Salesforce Connect | Customer Community Login, Commerce, Connect |
| 1.4 | Three service tiers; price by weight, temp, urgency, contract | Shipping methods + Product attributes + Price Books; SDPE overlay | Commerce PricingService extension, Price Books |
| 1.5 | Auto-allocate nearest RDC with inventory and cold capacity; else escalate to director / split | Async PE → MuleSoft → WMS; `Fulfillment_Allocation__c`; Omni-Channel Case to director; `OrderDeliveryGroup` | Platform Events, MuleSoft, Omni-Channel |
| 1.6 | Portal tickets; Salesforce handling; Enterprise 2h SLA; language + workload routing | Case from portal; Entitlements/Milestones 120 min 24/7; Omni-Channel skills + capacity | Service Cloud |
| 1.7 | Conversational containment on digital **and voice**; unified agent workspace; escalate complex | Agentforce Service Agent + Voice; SCV Unified Routing; Service Console; Trust Layer | Agentforce, SCV, Data Cloud, Knowledge |
| 2.1 | Checkout calls SDPE; resilient fallback | MuleSoft request-reply + circuit breaker + `Price_Snapshot__c` + contract price | Named Credentials, MuleSoft, Commerce extension |
| 2.2 | Bi-directional secure Food Safety Registry | CDC + webhooks; mTLS; thin `Lot_Batch__c` | MuleSoft, Shield as needed |
| 2.3 | Daily SAP sync of orders, invoices, payouts, rebates | CDC during day + regional EOD recon; Connect for UX | MuleSoft SAP connector, Bulk API 2.0, Connect |
| 3.1 | Farm users see only their farm POs/schedules/scores/payouts | Partner Community; OWD Private; Sharing Set on farm Account; separate `Supplier_PO__c` | Partner Community |
| 3.2 | Store users see only their store or corporate parent node | Sharing Sets at branch; External Account Hierarchy for HQ CC+ | CC + CC+ |
| 3.3 | Social login for micro-buyers | OIDC Auth Providers + Registration Handler | Identity |
| 3.4 | Okta SSO and automated provision/deprovision | SAML 2.0 + SCIM / Okta Salesforce app; groups → PSGs | Okta, Salesforce Identity |
| LDV | 50k orders/day; IoT; 15k hierarchy | Hot 90-day Orders; Big Object archive; no IoT objects; no flat 15k parent | Archive, Connect, WMS |
| Licenses | Fit for function and sharing | Mixed CC / CC+ / Partner / Salesforce / Integration | See license table |

---

## Diagram index

| Diagram | Location |
| --- | --- |
| Account topology | [01-data-architecture.md](./01-data-architecture.md) §1.2 |
| ERD | [01-data-architecture.md](./01-data-architecture.md) §1.3 |
| Persona → records | [01-data-architecture.md](./01-data-architecture.md) §1.5 |
| System landscape | [02-system-landscape-and-integration.md](./02-system-landscape-and-integration.md) §2.1 |
| SDPE sequence + fallback | [02-system-landscape-and-integration.md](./02-system-landscape-and-integration.md) §2.3.1 |
| Integration / security matrix | [02-system-landscape-and-integration.md](./02-system-landscape-and-integration.md) §2.4 |
| Sharing mechanisms | [03-security-sharing-and-licenses.md](./03-security-sharing-and-licenses.md) §3.4 |
| Support containment flow | [04-governance-ldv-and-tradeoffs.md](./04-governance-ldv-and-tradeoffs.md) §4.2 |
