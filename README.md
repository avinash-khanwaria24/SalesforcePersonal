# SalesforcePersonal

## Contact sync (Platform Events)

High-volume `Contact_Sync__e` fans out each Contact change to three systems with:

- Publish-after-commit and Apex publish callbacks
- Failure-only outbox retry (not in-callback republish)
- Per-subscriber unique `EventUuid` + business-key idempotency
- Bounded `EventBus.RetryableException` then DLQ

Architecture: [docs/contact-sync-platform-events-hld.md](docs/contact-sync-platform-events-hld.md)

Schedule the outbox sweeper after deploy:

```apex
System.schedule('Contact Sync Outbox Retry', '0 0/5 * * * ?', new ContactSyncRetrySchedulable());
```
