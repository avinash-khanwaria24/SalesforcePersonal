# Reference implementation map

These sketches illustrate the design in `../contact-sync-platform-events.md`. They are not a deployable SFDX package: object metadata, permission sets, and field-by-field Contact mapping are omitted on purpose.

| File | Design section |
| --- | --- |
| `ContactSyncContract.cls` | Event contract, keys |
| `ContactEventIdempotency.cls` | Claim-then-act dedup |
| `ContactLastWriteWins.cls` | Out-of-order / conflict apply |
| `ContactChangedInboundService.cls` | Apex subscriber, checkpoint, retry, DLQ |
| `ContactChangedTrigger.trigger` | PE after insert |
| `ContactChangePublisher.cls` | Hash skip, loop skip, transactional outbox write |
| `OutboxPublishQueueable.cls` | Hourly publish headroom, batch publish |
| `OutboxPublishCallback.cls` | Lean success/failure callback |
| `ContactChangedInbound.platformEventSubscriberConfig-meta.xml` | Batch 200, partition by contact key |

## Objects the sketches assume

- Platform event `Contact_Changed__e` — Publish After Commit, high volume
- `Contact_Outbox__c`, `Event_Processed__c` (unique External Ids on `Dedup_Key__c`, `Message_Id__c`, `Event_Uuid__c`), `Contact_DLQ__c`
- Contact watermarks: `Last_Sync_Source__c`, `Last_Sync_Version__c`, `Last_Sync_Occurred_At__c`, `Last_Sync_Hash__c`, `System_A_Id__c`, `System_B_Id__c`

## Pub/Sub worker (external)

Not in Apex. Required behavior:

1. One subscriber (hub) or filtered custom channels per spoke.
2. Persist last **processed** `replay_id`; resume with `ReplayPreset.CUSTOM`.
3. Dedup on `event.id` (EventUuid) and `Message_Id__c`.
4. Commit cursor after spoke ACK or local outbox write.
5. Alert if cursor age exceeds 24h; page before 72h retention elapses.
