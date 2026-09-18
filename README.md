# SalesforcePersonal

Working notes and Salesforce reference implementations.

## SF Switch — Apex trigger “insufficient access on cross-reference id”

SF Switch cannot always deactivate Apex triggers. Salesforce returns `INSUFFICIENT_ACCESS_ON_CROSS_REFERENCE_ENTITY` when the trigger is packaged, the user cannot deploy Apex, or a production `RunLocalTests` deploy fails.

Resolution guide: [`docs/sf-switch-deactivate-trigger-cross-reference.md`](docs/sf-switch-deactivate-trigger-cross-reference.md)

Runtime bypass (preferred over flipping trigger `Status`): `TriggerBypassService` in `force-app/main/default/classes/`.
