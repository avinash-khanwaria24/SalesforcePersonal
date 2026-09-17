# FreshSource Global — Integration System Landscape

Board-ready integration landscape for FreshSource Global (FSG), synthesized from the architecture packs already in this repository.

This pack answers four landscape questions:

| Question | Where |
| --- | --- |
| What sits in **Salesforce Core Cloud**? | [FSG_INTEGRATION_SYSTEM_LANDSCAPE.md](./FSG_INTEGRATION_SYSTEM_LANDSCAPE.md) §2 |
| How does **Experience Cloud** authenticate, including **social logins**? | Same document §3 |
| What are **all data entry points** into Salesforce? | Same document §4 |
| What are **all integrations through the ESB**? | Same document §5–6 |

Visual companion (open in a browser): [landscape.html](./landscape.html)

---

## North star

1. **Salesforce Core Cloud** is the system of engagement and operational CRM (parties, contracts, hot orders, cases, catalog experience).
2. **Experience Cloud (LWR)** is the digital front door for buyers and farms. **Google, Apple, and LinkedIn** OIDC social login is available for micro-buyers.
3. **Every business record has a named data entry point** — portal, channel, internal console, identity, or ESB inbound. Nothing is an undocumented side door.
4. **MuleSoft Anypoint is the ESB.** SAP, SDPE, WMS/TMS, the Food Safety Registry, IoT exceptions, DocuSign, tax, and payments do **not** call Salesforce point-to-point. They enter and leave through Experience, Process, and System APIs.

Identity (Okta SAML/SCIM and social OIDC) is a separate **identity plane**. It is not routed through the ESB.

---

## Source documents used

This landscape does not invent a new product stack. It unifies the already-read designs:

| Source | Branch / pack |
| --- | --- |
| Enterprise landscape + integration matrix | `docs/fsg-architecture/02-system-landscape-and-integration.md` |
| Core + LWR + Commerce + OM topology | `docs/fsg-architecture/FSG_ENTERPRISE_SOLUTION_ARCHITECTURE.md` |
| Customer 360 / API-led ESB stance | `docs/FreshSource_Global_Salesforce_Architecture_Design.md` |
| Social login (Google / Apple / LinkedIn) | `docs/fsg-microbuyer-pricing-auth/` |
| Okta staff SSO + lifecycle | `docs/identity-user-lifecycle-okta-salesforce.md` |
| Capability designs 1.1–1.7, 2.1–2.3 | `docs/architecture/` |
