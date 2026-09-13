# FreshSource Global — Salesforce Enterprise Architecture

**Solution type:** End-to-end Salesforce Customer 360 architecture (no org configuration or code in this pack)  
**Primary products:** Experience Cloud, B2B Commerce on Lightning, Service Cloud, Agentforce, MuleSoft Anypoint, Salesforce Connect, Data Cloud  
**Design north star:** Salesforce is the system of engagement and operational CRM. SAP S/4HANA is the financial system of record. WMS/TMS is the inventory and capacity system of record. Cold-chain telemetry never lands as high-volume Salesforce records.

This pack answers the four evaluation pillars:

| Pillar | Document |
| --- | --- |
| Data architecture and LDV | [01-data-architecture.md](./01-data-architecture.md) |
| System landscape and integration | [02-system-landscape-and-integration.md](./02-system-landscape-and-integration.md) |
| Security, sharing, and licenses | [03-security-sharing-and-licenses.md](./03-security-sharing-and-licenses.md) |
| Governance and trade-offs | [04-governance-ldv-and-tradeoffs.md](./04-governance-ldv-and-tradeoffs.md) |
| Requirements coverage | [05-requirements-traceability.md](./05-requirements-traceability.md) |
| Board-ready artifacts (data model, landscape, matrix) | [ARTIFACTS.md](./ARTIFACTS.md) |

---

## Recommended target architecture (one paragraph)

FreshSource Global (FSG) runs a **single Salesforce Hyperforce org** with three Experience Cloud sites (Buyer Market, Grower Network, Support), **B2B Commerce** for catalog/cart/checkout, and **Service Cloud + Agentforce** for omnichannel support. Corporate contracted prices live in Salesforce Price Books / Buyer Groups. Spoilage-driven price overlays are retrieved at checkout through **MuleSoft (request-reply with circuit breaker)** to the SDPE, with a **cached contract-price fallback** so checkout never blocks. Order capture is Salesforce; allocation is an **asynchronous MuleSoft orchestration** against WMS capacity; exceptions route to Regional Fulfillment Directors via Omni-Channel. Historical invoices, payouts, and rebates are **virtualized from SAP** with Salesforce Connect. Internal staff authenticate with **Okta SSO + SCIM**. Micro-buyers use **social login**. Enterprise branch managers use **Customer Community Plus delegated administration** limited to their branch Account.

---

## Scale snapshot (used throughout)

| Metric | Value | Architectural implication |
| --- | --- | --- |
| Orders | 50,000 / day (~18.3M / year) | LDV on `Order` / `OrderItem`; 90-day hot store; archive + virtualize |
| Assumed line items | 12–20 per order (~250–365M / year) | Do not report on unbounded `OrderItem`; index + skinny tables + archive |
| Enterprise accounts | 1,200 HQ / ~150,000 branch users | Mixed Experience Cloud licenses; prevent 50k role-limit breach |
| Largest client | 15,000 branches under one master agreement | Parent-child skew risk; intermediate Regional Accounts required |
| Suppliers | 8,000 farms | Partner Community; farm-scoped sharing; separate Supplier PO object |
| Time zones | 14 | 24/7 Enterprise SLA business hours; multi-currency; regional stores |
| Support constraint | Cannot scale live agents | Agentforce Service Agent + Voice as tier-0; live agents for exceptions |

---

## Non-negotiable platform constraints this design respects

1. **Do not exceed ~10,000 child records per parent** (parent-child / lookup skew) — [Salesforce sharing performance](https://help.salesforce.com/s/articleView?id=platform.security_sharing_performance.htm).
2. **Do not put 15,000 branches directly under one HQ Account.**
3. **Customer Community Plus / Partner roles default cap is 50,000.** Use Account Role Optimization and mixed licenses so chefs are high-volume users without roles.
4. **Customer Community licenses include 10 custom objects and 0 API calls.** Buyer-facing data must stay on standard / Commerce objects; historical financials are external objects.
5. **Sharing Sets do not roll up account hierarchies.** HQ visibility uses External Account Hierarchy + CC+ roles, not Sharing Sets alone.
6. **IoT / cold-chain pings are not Salesforce records.** Only exceptions become Cases.
7. **Avoid point-to-point integrations.** MuleSoft is the system of interaction for SAP, SDPE, WMS, and the Food Safety Registry.
