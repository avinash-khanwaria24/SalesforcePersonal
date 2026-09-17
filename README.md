# SalesforcePersonal

Salesforce architecture designs and implementation notes.

## Identity & User Lifecycle Management

Internal staff identity is mastered in Okta. Salesforce is the service provider.

- [Identity & user lifecycle design](docs/identity-user-lifecycle-okta-salesforce.md) — SSO, group-driven provision/de-provision, MFA, operating model
- [Architecture and object data model](docs/architecture-and-object-data-model.md) — logical/physical architecture, Salesforce + Okta ERD, attribute contract
