# SalesforcePersonal

Supply Operations data model for Salesforce. The handwritten whiteboard ERD is converted into Salesforce DX metadata: standard objects where they already exist, custom objects and relationships everywhere else.

See **[docs/data-model.md](docs/data-model.md)** for the object map, ERD, and deploy steps.

## Quick start

```bash
python3 scripts/validate_data_model.py
sf project deploy start --source-dir force-app
sf org assign permset --name Supply_Operations_User
```

The Lightning app **Supply Operations** exposes Account, Contact, Contract, Order, Case, Entitlement, and the custom supply-chain objects.
