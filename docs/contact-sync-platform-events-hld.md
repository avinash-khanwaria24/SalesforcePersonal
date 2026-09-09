# Contact Sync via Platform Events — High-Level Design

## 1. Goal

Sync Contact create, update, and delete changes from Salesforce to **three downstream systems** with:

- Successful publish to the event bus, with **bounded retry** when publish fails
- **At-least-once** delivery without duplicate business side effects
- Subscriber **idempotency on `EventUuid`** (and on a business key when a retry allocates a new UUID)
- **Retry of transient processing errors**, and a **dead-letter queue (DLQ)** for poison events
- High throughput: one publish fans out to all three systems; hot path stays off custom objects

Salesforce High-Volume Platform Events (HVPE) are **at-least-once**, not exactly-once. Duplicates keep the **same `EventUuid`**, a **different `ReplayId`**, and the same payload. The design makes that explicit and cheap to ignore.

## 2. Recommended pattern (summary)

| Concern | Choice | Why |
|---|---|---|
| Event type | One HVPE: `Contact_Sync__e` | Default for new events; millions/day; 72-hour replay |
| Fan-out | **One event, three subscribers** | Do not publish per system; delivery is independent |
| Publish timing | `PublishAfterCommit` | Never emit if the Contact transaction rolls back |
| Publish confirmation | `SaveResult` **plus** Apex publish callbacks | `SaveResult` is only the queueing result; the callback is the final persist result |
| Failed publish | Compact **outbox** + delayed Queueable + scheduled sweeper | Durable retry without burning the 10-deep recursive publish limit |
| Apex subscriber retry | `EventBus.RetryableException` (cap 6 of 9) | Platform backoff; avoid trigger **error state** |
| Duplicate suppression | Unique insert on `subscriber + EventUuid` | O(1), race-safe, no pre-query |
| Republish suppression | Unique insert on `subscriber + Idempotency_Key` | Outbox retry creates a **new** `EventUuid` |
| External systems | Pub/Sub API (gRPC), persist ReplayId | Replaces CometD; 72-hour catch-up |
| Poison events | DLQ, then checkpoint/ack | Keep the bus and other events moving |

```text
                    Contact DML (after insert/update/delete/undelete)
                                      |
                                      v
                         filter synced fields only
                                      |
                                      v
                    EventBus.publish(Contact_Sync__e)   [PublishAfterCommit, HVPE]
                         |                      |
              SaveResult fail            async persist fail (callback)
                         |                      |
                         +----------+-----------+
                                    v
                         Contact_Sync_Outbox__c
                         delayed Queueable retry
                         (1,2,4,8,10 min) then DLQ
                                    |
                                    v
                         Salesforce Event Bus (72h)
                                    |
              +---------------------+---------------------+
              |                     |                     |
              v                     v                     v
         System A              System B              System C
      (Pub/Sub API)         (Pub/Sub API)      (Apex trigger and/or Pub/Sub)
              |                     |                     |
              v                     v                     v
     claim EventUuid         claim EventUuid         claim EventUuid
     apply / retry / DLQ     apply / retry / DLQ     apply / retry / DLQ
```

## 3. Delivery semantics (non-negotiable)

1. **Publishing is asynchronous.** `EventBus.publish` returning success means the event was **queued**, not that it is durable on the bus.
2. **Final publish result** arrives in `EventBus.EventPublishSuccessCallback` / `EventBus.EventPublishFailureCallback`, correlated by `EventUuid`.
3. **HVPE uses at-least-once.** Internal bus retries can deliver the same `EventUuid` more than once with a new `ReplayId`.
4. **Apex trigger retries** (`RetryableException`) resend the **entire prior batch** (ReplayIds unchanged; batch size may grow). DML in that trigger execution is rolled back.
5. **Replay is not idempotency.** `ReplayId` is a stream cursor. Dedup must use `EventUuid` (and a business key).
6. After **9** `RetryableException` retries the Apex subscriber enters **error state** and **drops events** until the trigger is redeployed. Never rely on the 9th retry.

Therefore: **exactly-once processing is an application property**, implemented with a unique claim store per subscriber.

## 4. Event contract

`Contact_Sync__e` (High Volume, `PublishAfterCommit`):

| Field | Role |
|---|---|
| `EventUuid` (system) | Stable duplicate identity for a single publish |
| `ReplayId` (system) | Subscriber cursor; do not use for dedup |
| `Contact_Id__c` | Target record |
| `Change_Type__c` | `CREATE` / `UPDATE` / `DELETE` |
| `Idempotency_Key__c` | `{ContactId}:{SystemModstampMs}:{ChangeType}` |
| Name, email, phone, account | Compact passed-message payload (no extra SOQL on the hot path) |
| `System_Modstamp__c` | Last-write-wins if events arrive out of order |

**Create the event with `sObjectType.newSObject(null, true)`**, not `new Contact_Sync__e()`. Only `newSObject` populates `EventUuid` *before* publish, which is required to correlate Apex callbacks.

Do **not** put large blobs or related-record graphs on the event. Enrich in the subscriber (or middleware) if a system needs more than the sync fields.

## 5. Publisher: successful delivery and retry

### 5.1 Hot path (happy case)

1. After-save Contact trigger, re-entrancy guarded.
2. Publish **only** when a synced field changed (`FirstName`, `LastName`, `Email`, `Phone`, `AccountId`) or on insert/delete/undelete.
3. Map Contacts to events in memory; publish in chunks of **150** (Apex HVPE publish limit per transaction).
4. Pass a **compact** callback: `Map<EventUuid, correlation>` only. Do not store full payloads on the callback instance (5 MB / 30 min callback heap budget).
5. If every `SaveResult` succeeds, **do not write custom objects**. Outbox is failure-only.

This keeps the 99%+ path to: Contact DML → `EventBus.publish` → bus → three subscribers.

### 5.2 Two failure layers

| Layer | API | Meaning | Action |
|---|---|---|---|
| Synchronous queueing | `Database.SaveResult` | Could not enqueue (validation, limits) | Write outbox immediately |
| Asynchronous persist | `EventPublishFailureCallback.getEventUuids()` | Queued but not durable on the distributed bus | Write outbox from the correlation map |

**Do not republish inside the callback.** Nested `EventBus.publish` from a callback counts toward a **10-level** recursive publish limit and can starve the org. Callbacks only persist outbox rows and enqueue a **delayed** Queueable.

### 5.3 Outbox retry

`Contact_Sync_Outbox__c` is the durable retry buffer:

- Status: `Pending` → `Publishing` (`FOR UPDATE` claim) → delete on success, or `Pending` with backoff, or `DLQ`
- `Next_Attempt_At__c` + exponential backoff `1, 2, 4, 8, 10` minutes (Queueable delay cap is 10 minutes)
- Max **5** publish attempts, then `Contact_Sync_DLQ__c` (`Source = Publish`)
- `ContactSyncRetryQueueable` for prompt retry; `ContactSyncRetrySchedulable` every 5 minutes as a sweeper (covers lost Queueables, stale `Publishing` rows)
- Stale `Publishing` rows older than 15 minutes are reclaimed (callback never returned)

A republish **must** allocate a new `EventUuid` (`newSObject` again). Keep the original **`Idempotency_Key__c`** so subscribers treat it as the same business change.

### 5.4 Why not a full transactional outbox on every Contact?

Writing an outbox row on every successful Contact change doubles DML on the hottest object in the org and is unnecessary: HVPE publish-after-commit already queues only if the transaction commits. Persist an outbox row **only when publish confirmation fails**. That is the high-performance variant of the outbox pattern.

## 6. Fan-out to three systems

Publish **once**. Each system is an independent consumer of the same channel.

| Subscriber | Transport | Replay / ack | Idempotency store |
|---|---|---|---|
| System A (external) | Pub/Sub API `Subscribe` or `ManagedSubscribe` | Persist last processed `ReplayId` (or server-side managed commit) | Unique `(EventUuid)` in that system’s DB |
| System B (external) | Same | Same | Same, isolated |
| System C (Salesforce or middleware) | Apex `after insert` on `Contact_Sync__e` and/or Pub/Sub | `setResumeCheckpoint(ReplayId)` | `Processed_Event__c` keyed by subscriber name |

Isolation rules:

- Each subscriber has its **own** processed-event store (or `Subscriber_Name__c` partition).
- Success or failure of System A must not block B or C.
- Do not wait for downstream HTTP inside the publish transaction.

If a system cannot keep up, scale **that consumer** (more Pub/Sub clients, Queueable hand-off). Do not slow the publisher.

## 7. Subscriber: EventUuid idempotency and processing retry

### 7.1 Claim-then-process (all subscribers)

For every delivered event, **atomically claim** before side effects:

```text
INSERT processed_event(dedup_key = subscriber + EventUuid,
                       business_key = subscriber + Idempotency_Key)
ON DUPLICATE → skip (already processed or in-flight)
ON INSERT OK → this subscriber now owns the event → apply change
```

In Salesforce this is `Database.insert(..., false)` against `Processed_Event__c` with two unique fields:

- `Dedup_Key__c` = `{Subscriber}:{EventUuid}` — suppresses bus duplicates (same UUID, new ReplayId)
- `Business_Key__c` = `{Subscriber}:{Idempotency_Key}` — suppresses outbox republishes (new UUID, same contact change)

No `SELECT` before insert. Unique-index violations are the dedup mechanism. That is the fastest race-safe pattern under concurrent consumers.

Three systems processing the **same** `EventUuid` insert three rows (different `Subscriber_Name__c`). That is required fan-out, not a duplicate.

### 7.2 Apex trigger retry

```text
claim batch (one DML)
if owned is empty → setResumeCheckpoint(last ReplayId); return
try
    process owned (bulkified; callouts via Queueable after a successful claim)
    setResumeCheckpoint(last ReplayId)
catch
    if retries < 6
        throw EventBus.RetryableException   // rolls back the claim; platform retries the batch
    else
        write DLQ (Source = Subscribe)
        keep the claim so the poison EventUuid is never applied
        setResumeCheckpoint(last ReplayId)  // do not throw; never enter error state
```

Why this mix:

- `RetryableException` is for **transient** errors (row lock, timeout, downstream 503). Salesforce resends with increasing delay. Claims roll back, so a later attempt can succeed.
- Cap at **6** (platform max is 9) so a poison event cannot disable the subscriber for the whole org.
- `setResumeCheckpoint` is for **committed progress** so an unhandled limit exception does not replay already-applied events.
- Unique claim makes full-batch resend cheap: duplicate inserts return `DUPLICATE_VALUE` and are skipped.

Callouts: the platform event trigger cannot reliably call out after DML. After a successful claim, enqueue a Queueable/middleware job. If that async job fails, retry **in the job** (not via `RetryableException`); the claim already prevents a second apply. Put exhausted async failures in the DLQ and alert.

### 7.3 External Pub/Sub subscribers

Each of the three clients:

1. Subscribe from stored `ReplayId` (`CUSTOM` replay) or `ManagedSubscribe`.
2. For each event, insert `EventUuid` into a unique table (and the business key).
3. Apply the Contact upsert/delete using `System_Modstamp__c` last-write-wins.
4. Commit the ReplayId / ack **only after** successful apply (or after DLQ for poison).
5. On disconnect, resume from the last committed ReplayId within **72 hours**. Alert if lag approaches the retention window.
6. Treat HTTP 429/5xx as retryable; 4xx schema/data errors as DLQ.

Never compute ReplayIds. Never ack before the unique insert.

## 8. Ordering and last-write-wins

HVPE does not give a global per-Contact lock across subscribers. Possible outcomes:

- Create then update can be processed as update then create
- Two updates can arrive reversed

Rule: store `System_Modstamp__c` on the target. Apply an event only if `incoming.modstamp >= stored.modstamp` (deletes are terminal). The idempotency key already includes modstamp, so a stale republish of an older version is a different key and is applied only if it wins LWW — typically it does not.

This avoids per-Contact serialization on the bus, which would destroy throughput.

## 9. Performance optimizations

1. **One event, three consumers** — 3× fewer publishes and 3× fewer outbox rows than per-system events.
2. **Failure-only outbox** — zero extra DML on successful publish.
3. **Synced-field filter** — ignore Description, Owner, and other noise.
4. **Chunk size 150** — stay under the Apex HVPE publish governor.
5. **Tiny callbacks** — UUID → `ContactId|ChangeType|IdempotencyKey` string only.
6. **No in-callback retry** — delayed Queueable instead of recursive publish.
7. **Unique insert, not query-then-insert** — one DML, index-backed, safe under overlap.
8. **Bulk claim** — one `insert` for the whole trigger batch.
9. **Compact payload** — passed-message for the five sync fields; no SOQL in the publisher.
10. **Outbox claim `FOR UPDATE` + batch 200** — single-flight retries; sweeper handles the rest.
11. **Hot success callback is a no-op** for initial publishes (delete outbox only on retry success).
12. **TTL the processed-event store** after > 72 hours (bus retention). Keep DLQ longer for audit.

Optional later: Platform Cache in front of `Processed_Event__c` is usually **not** worth it; the unique index is already O(1) and is the source of truth.

## 10. Data model

| Object | Write path | Cardinality | Purpose |
|---|---|---|---|
| `Contact_Sync__e` | Publisher | 1 per Contact change | Contract on the bus |
| `Contact_Sync_Outbox__c` | Publish failure / retry | Failure-only, short-lived | Durable publish retry |
| `Processed_Event__c` | Each subscriber | 1 per (subscriber, event) | Idempotency |
| `Contact_Sync_DLQ__c` | Exhausted retries | Rare | Human replay / alerting |

Operational queries:

- Outbox `Pending` older than next-attempt → sweeper health
- DLQ created today → page the on-call
- `EventBusSubscriber` retries / status → Apex trigger health
- Pub/Sub lag vs 72-hour retention → external consumer health

## 11. Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| `SaveResult` false | Publisher loop | Outbox + delayed retry |
| Async persist fail | Failure callback | Outbox from correlation; hydrate Contact if payload missing |
| Callback never fires | Stale `Publishing` > 15 min | Sweeper reclaims |
| Duplicate EventUuid | Unique `Dedup_Key__c` | Skip |
| Republish new UUID | Unique `Business_Key__c` | Skip |
| Transient apply error | Catch in subscriber | `RetryableException` / client nack |
| Poison event | Retry cap | DLQ + claim + checkpoint |
| Apex trigger error state | 9 retries exceeded | Avoid by capping at 6; fix and redeploy if it still happens |
| Consumer down > 72 h | Replay gap | Replay from source of truth (SOQL/CDC backfill), not the bus |
| Partial downstream timeout after apply | Unique claim already committed | Treat as success; do not re-apply |

## 12. Alternatives considered

| Option | Verdict |
|---|---|
| Contact Change Data Capture instead of custom PE | Good for raw replication; weaker as a **sync contract** (no `Idempotency_Key__c`, no field subset, harder publish retry). Keep custom PE. |
| One PE per downstream system | 3× publish volume and 3× failure handling. Reject. |
| Middleware-only (MuleSoft) as the only subscriber | Valid at very high volume if Apex triggers become the bottleneck. Still require EventUuid/business-key idempotency in Mule. This design allows that: Salesforce publishes once; Mule is System C. |
| CometD / empApi | Legacy. Use Pub/Sub API. |
| Query processed UUIDs then insert | Race and extra SOQL. Unique insert wins. |
| Retry publish inside the callback | Hits recursive publish limit. Outbox + delay wins. |
| Full outbox on every Contact write | Safer but slower. Failure-only outbox is the performance choice given `PublishAfterCommit`. |

## 13. Deployment and operations

1. Deploy objects, event, Apex, then schedule:

   `System.schedule('Contact Sync Outbox Retry', '0 0/5 * * * ?', new ContactSyncRetrySchedulable());`

2. Grant Pub/Sub API clients the event and a dedicated integration user.
3. Report on `Contact_Sync_DLQ__c` and outbox age; alert on Apex `EventBusSubscriber` error status.
4. Batch-delete `Processed_Event__c` older than 8 days.
5. Manual DLQ replay: republish from payload **with the same `Idempotency_Key__c`** so already-applied systems no-op.

## 14. Reference implementation (this repo)

| Component | Class / metadata |
|---|---|
| Event | `Contact_Sync__e` |
| Publish trigger | `ContactSyncPublishTrigger` → `ContactSyncTriggerHandler` → `ContactSyncPublisher` |
| EventUuid + payload | `ContactSyncEventMapper` |
| Callbacks | `ContactSyncPublishCallback` |
| Outbox / backoff | `ContactSyncOutboxService`, `ContactSyncRetryQueueable`, `ContactSyncRetrySchedulable` |
| Apex subscriber | `ContactSyncSubscribeTrigger` → `ContactSyncSubscriber` |
| Idempotency | `ContactSyncIdempotencyService` + `Processed_Event__c` |
| DLQ | `ContactSyncDlqService` + `Contact_Sync_DLQ__c` |
| Limits / names | `ContactSyncConstants` |

External systems A and B should copy the **claim-then-process** algorithm against their own unique store; they should not share `Processed_Event__c` unless they run inside this org with distinct `Subscriber_Name__c` values (`ERP`, `CRM`, `MARKETING`, …).
