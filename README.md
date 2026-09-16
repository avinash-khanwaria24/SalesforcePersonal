# SalesforcePersonal

Salesforce architecture designs and implementation notes.

## Identity & User Lifecycle Management

Internal staff identity is mastered in Okta. Salesforce is the service provider.

See [docs/identity-user-lifecycle-okta-salesforce.md](docs/identity-user-lifecycle-okta-salesforce.md) for the full design:

- SAML 2.0 SSO (Okta IdP, Salesforce SP)
- Automated provision / de-provision from Okta directory groups
- Thin profiles + permission set groups
- MFA signaling, break-glass, and operating model
