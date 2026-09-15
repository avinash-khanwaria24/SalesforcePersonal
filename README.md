# SalesforcePersonal

Salesforce design and metadata for **FreshSource Global (FSG)** product catalog: regional access for buyers and suppliers.

## Start here

- [Product Catalog Solution Architecture](docs/architecture/FSG_Product_Catalog_Architecture.md) — OOTB Commerce / Experience Cloud design, then custom sharing objects
- [Implementation Runbook](docs/architecture/FSG_Catalog_Implementation_Runbook.md) — deploy and org setup order

## Package

`force-app` contains the custom control plane (`Region__c`, `Product_Availability__c`, `Supplier_Product__c`, permission sets, sharing rules, queues). B2B Commerce stores, Markets, and Experience Cloud sharing sets are configured in the target org.

```bash
sf project deploy start --source-dir force-app --target-org <alias>
```
