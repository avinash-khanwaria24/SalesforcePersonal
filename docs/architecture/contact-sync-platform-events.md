# Contact Sync Across Three Systems via Platform Events

**Role:** Salesforce Architect  
**Pattern:** Hub-and-spoke event mesh with Salesforce Event Bus as the contract  
**Guarantee:** At-least-once delivery + consumer idempotency (not exactly-once)  
**Edition assumed:** Enterprise or Unlimited, high-volume platform events only

---

## 1. Executive recommendation

Salesforce cannot give exactly-once platform event delivery. High-volume events are **at-least-once**, can be published twice with the same `EventUuid` and a different `ReplayId`, and in rare cases a queued publish never lands on the bus. The design therefore separates three concerns:

1. **Publish reliability** — transactional outbox + publish callbacks + replay + reconciliation.
2. **Consume reliability** — durable replay cursor, Apex resume checkpoints, dead-letter queue.
3. **Deduplication / idempotency** — claim-then-act on a business key, last-write-wins on a per-contact version, loop suppression by source system.

**Do not** let System A, System B, and Salesforce each subscribe to the unfiltered event topic. Delivery allocations are counted **per API subscriber**. The gold topology is:

- Salesforce Event Bus holds one canonical event: `Contact_Changed__e`.
- Salesforce consumes inbound events with an **Apex trigger** (does **not** count toward daily event delivery).
- **One** external subscriber (MuleSoft, Boomi, or a custom Pub/Sub API worker) is the only API consumer. It fans out to System A and System B.
- If A and B must subscribe directly, each uses a **filtered custom channel** that excludes its own `Source_System__c`, and the org buys the Platform Events add-on before volume exceeds the default 24-hour delivery cap.

Do **not** also stream Contact Change Data Capture to the same external clients. CDC shares the same delivery allocation as platform events.

---

## 2. Scope and topology

### 2.1 Systems

| Node | Role | How it talks to the bus |
| --- | --- | --- |
| Salesforce (CRM, system of record for many contact fields) | Hub. Publishes Contact mutations. Consumes A/B mutations. | Apex publish via outbox. Apex trigger subscribe. |
| System A (example: marketing / MAP) | Spoke | Publishes through Pub/Sub API. Receives from the hub subscriber or a filtered channel. |
| System B (example: ERP / support / identity) | Spoke | Same as A. |

Salesforce is the **canonical id issuer** (`Salesforce_Contact_Id__c`). A and B keep their own ids mapped through External Ids on Contact.

### 2.2 Why hub-and-spoke, not a mesh of three PE topics

A mesh (`Contact_From_A__e`, `Contact_From_B__e`, `Contact_From_SF__e`) multiplies event definitions, subscribers, and delivery counts. One event type with `Source_System__c` plus filtered channels is enough for routing, loop suppression, and schema evolution.

```text
                    ┌─────────────────────────────────────┐
                    │     Salesforce Event Bus (72h)      │
                    │         Contact_Changed__e          │
                    └──────────────┬──────────────────────┘
           publish ▲               │ subscribe
                   │               ▼
         ┌─────────┴────────┐   Apex trigger (no delivery count)
         │  SF Outbox +     │   claim key → upsert Contact → checkpoint
         │  publish callback│
         └─────────┬────────┘
                   │
     Pub/Sub API   │   one hub subscriber (counts once per event)
                   ▼
         ┌─────────────────┐
         │  iPaaS / worker │ ──fan-out (HTTPS/queue)──► System A
         │  durable cursor │ ──fan-out───────────────► System B
         └─────────────────┘
                   ▲
         A and B publish Contact_Changed__e
         (Pub/Sub Publish RPC; not REST if volume is material)
```

**Fallback (no iPaaS):** A and B subscribe to filtered custom channels `/event/Contact_For_A__chn` and `/event/Contact_For_B__chn`. Salesforce still uses the Apex trigger. Delivery count becomes **two times** published outbound volume.

---

## 3. Event contract

### 3.1 Platform event: `Contact_Changed__e`

| Decision | Choice | Why |
| --- | --- | --- |
| Volume | High-volume only | Standard-volume cannot be created anymore and retires Summer ’27. |
| Publish behavior | **Publish After Commit** | A rolled-back Contact DML must not emit an event. |
| Payload style | Discrete fields for routing/filter/identity + compact JSON for the rest | Filters need fields. 1 MB message cap. Avoid hundreds of custom fields. |
| Ordering | Per-contact, not global | Partition inbound Apex on `Contact_Key__c`. Consumers apply version checks. |

**Identity and routing fields (always populated):**

| Field | Type | Purpose |
| --- | --- | --- |
| `Message_Id__c` | Text(36), required | Publisher-generated UUID. Primary idempotency key. Stable across publisher retries. |
| `Correlation_Id__c` | Text(36) | Ties a saga / user action across retries and systems. |
| `Source_System__c` | Text(40), required | `SALESFORCE`, `SYS_A`, `SYS_B`. Loop suppression and channel filters. |
| `Operation__c` | Text(10), required | `CREATE`, `UPDATE`, `DELETE`, `MERGE`. |
| `Schema_Version__c` | Number(4,0), required | Additive evolution. Consumers upcast or DLQ unknown major versions. |
| `Contact_Key__c` | Text(64), required, External-Id style key | Golden key: Salesforce Id when known, else `SYS_A:{id}` / `SYS_B:{id}` until mapped. **Apex partition key.** |
| `Salesforce_Contact_Id__c` | Text(18) | Set once SF has created/matched the row. |
| `System_A_Id__c` | Text(64) | |
| `System_B_Id__c` | Text(64) | |
| `Occurred_At__c` | DateTime, required | Business time of the change in the source system (not publish time). |
| `Source_Version__c` | Number(18,0), required | Monotonic version **in the source system** for that contact. |
| `Payload_Hash__c` | Text(64) | SHA-256 of canonicalized business fields. Skip no-op publishes. |
| `Payload_Json__c` | Long Text Area(32768) | Remaining attributes. Keep well under 1 MB with the envelope. |

System fields you will also use: `ReplayId` (cursor, not identity), `EventUuid` (bus-level identity), `CreatedDate`.

**Never use `ReplayId` as a dedup key.** It is an opaque stream position, not unique across org migrations, and a duplicate publish gets a **new** `ReplayId`.

### 3.2 Canonical payload hash

Before publish, canonicalize business fields (trim, case-fold email, sorted JSON keys, exclude audit fields). Hash that. If the last successfully published hash for that `Contact_Key__c` is identical, **do not publish**. This is the cheapest limit protection you have.

### 3.3 Schema evolution

Treat the event as a public API:

- Add fields only. Never rename, change type, or reuse a field.
- Bump `Schema_Version__c`.
- Consumers ignore unknown fields and DLQ events below a minimum supported version.
- Keep at least two schema versions compatible.

### 3.4 Custom channels (when A/B subscribe directly)

| Channel | Filter |
| --- | --- |
| `Contact_For_A__chn` | `Source_System__c != 'SYS_A' AND Schema_Version__c >= 1` |
| `Contact_For_B__chn` | `Source_System__c != 'SYS_B' AND Schema_Version__c >= 1` |

Filtered events are **not delivered** to that client, so they do not consume that client’s slice of the daily delivery allocation. Apex triggers cannot subscribe to custom channels; they always see the full stream and must filter in code.

Limits: 100 custom PE channels; 50 distinct custom PE members across channels (Unlimited/Enterprise). One event in many channels still counts as one member.

---

## 4. Deduplication design (five layers)

Duplicates come from four different places. One mechanism cannot cover all of them.

| Layer | Duplicate type | Key | Store | Action |
| --- | --- | --- | --- | --- |
| 0 | No-op / echo of our own last write | `Payload_Hash__c` vs last applied hash | Contact fields | Do not publish; on consume, no-op. |
| 1 | Bus republish (at-least-once) | `EventUuid` (Pub/Sub `id`) | `Event_Processed__c` unique | Skip. |
| 2 | Publisher retry of the same business message | `Message_Id__c` | Same object, unique | Skip. |
| 3 | Logical re-delivery (replay from an earlier cursor, iPaaS retry) | `Source_System__c + Contact_Key__c + Source_Version__c` | Same object, unique `Dedup_Key__c` | Skip. |
| 4 | Concurrent / out-of-order updates | `(Occurred_At__c, Source_Version__c, Source_System__c)` | Fields on Contact | Last-write-wins or source-priority. |

### 4.1 Claim-then-act (authoritative)

`Event_Processed__c` is a short-lived custom object, **not** a Big Object (Big Objects have no unique index you can use for a race-safe insert).

Unique External Ids:

- `Dedup_Key__c` = `{Source_System}#{Contact_Key}#{Source_Version}#{Operation}`
- `Message_Id__c`
- `Event_Uuid__c` (nullable; fill when known)

**Algorithm (bulk-safe):**

1. Build keys for the batch.
2. Insert `Event_Processed__c` rows with `Status__c = CLAIMED` in one `Database.insert(..., false)`.
3. `SUCCESS` → this worker owns the message → process.
4. `DUPLICATE_VALUE` → already claimed or processed → skip.
5. After successful Contact upsert, update those rows to `PROCESSED` (optional; CLAIMED already prevents re-entry).
6. If processing fails with a **transient** error, **delete the claim** (or set `FAILED` without keeping the unique key) so retry can reclaim. If the error is **poison**, keep the claim and write `Contact_DLQ__c`.

Retention: 7 days (greater than the 72-hour bus window). Nightly batch deletes `Processed_At__c < LAST_N_DAYS:7`.

Do not use Platform Cache as the source of truth. Cache eviction would reprocess events.

### 4.2 Last-write-wins on Contact

Contact stores:

- `Last_Sync_Source__c`
- `Last_Sync_Version__c`
- `Last_Sync_Occurred_At__c`
- `Last_Sync_Hash__c`
- `Last_Sync_Message_Id__c`
- External Ids: `System_A_Id__c`, `System_B_Id__c`

Apply inbound change only if it is newer:

```text
incoming.Occurred_At > Last_Sync_Occurred_At
  OR (same Occurred_At AND incoming.Source_Version > Last_Sync_Version)
  OR (tie AND sourcePriority(incoming.Source) >= sourcePriority(current))
```

Suggested source priority if clocks disagree: `SALESFORCE > SYS_A > SYS_B` (adjust to the real system of record per field if you later move to **field-level merge**; start with record-level LWW to keep the v1 design operable).

### 4.3 Loop suppression (critical)

Without this, A→SF→event→A never stops and will burn publish **and** delivery allocations.

Rules:

1. Outbound from Salesforce **does not publish** when `Last_Sync_Source__c` is the destination and `Last_Sync_Hash__c` equals the new hash (the change was applied from that system).
2. Outbound events always set `Source_System__c = SALESFORCE`.
3. Filtered channels drop a system’s own events.
4. Apex inbound trigger ignores `Source_System__c = SALESFORCE` (those events exist for A/B, not for re-applying onto Contact).
5. Contact trigger runs in a static recursion guard and as a dedicated integration user when applying inbound events, so the outbound trigger can skip “changes made by the integration user in an inbound apply.”

Use **both** hash compare and integration-user skip. Either one alone eventually leaks an echo under merge, workflow, or duplicate rules.

---

## 5. Reliable delivery

Platform Events are not a queue with ACK/NACK per message in Apex. Reliability is built.

### 5.1 Salesforce → bus (outbound)

**Transactional outbox.** Contact after-insert/update/delete does **not** call `EventBus.publish` as the only persistence. In the **same** Contact transaction:

1. Compute hash; exit if unchanged.
2. Insert `Contact_Outbox__c` (`Pending`, payload, `Message_Id__c`).
3. After commit, a Queueable (or the PE trigger on a tiny internal `Outbox_Flush__e` if you want bus-backed drain) publishes **batches**.

Why not publish directly from the Contact trigger?

- `EventBus.publish` is asynchronous. `Database.SaveResult` only means **queued**, not persisted on the bus.
- In rare cases the queued publish is lost and is **not recoverable from the bus**.
- Direct publish in a trigger also makes retries and LIMIT_EXCEEDED handling awkward.

**Publish callbacks** (`EventBus.EventPublishSuccessCallback` / `FailureCallback`):

- Success: mark outbox `Published`, store `EventUuid`.
- Failure: increment `Attempt__c`, set `Failed`, enqueue retry with backoff.
- Keep callback instance **tiny**. Callback objects count toward **5 MB cumulative in the last 30 minutes**. Pass only `Map<String, Id>` of `EventUuid → OutboxId`, not the full payload. Cap recursive `EventBus.publish` from a callback at well below 10.

**Retry policy (outbox worker):**

| Attempt | Delay | Notes |
| --- | --- | --- |
| 1–3 | 1m, 5m, 15m | Transient / LIMIT_EXCEEDED |
| 4–6 | 1h, 4h, 12h | Still pending |
| 7 | DLQ + alert | Manual replay |

When `HourlyPublishedPlatformEvents` remaining < 20%, the worker **stops** and waits. Exceeding the hourly publish cap returns `LIMIT_EXCEEDED` and **drops** the publish (not queued). The outbox is what makes that safe.

**Publish API choice:** Apex or Pub/Sub API. Do **not** use REST/SOAP/Bulk to publish at volume; those also consume **daily API requests**.

### 5.2 Bus → Salesforce (inbound Apex)

Apex PE trigger defaults: runs as Automated Process, batch size up to **2,000**.

Configure `PlatformEventSubscriberConfig`:

| Setting | Recommended v1 | Why |
| --- | --- | --- |
| `batchSize` | 200 | Contact upsert + unique inserts + sharing stay inside CPU/DML/heap. Default 2000 is how teams hit uncatchable limit exceptions. |
| Running user | Dedicated `svc-contact-sync` | Sharing, field access, skip outbound echo, traceability. Not Automated Process. |
| `numPartitions` | 1 at go-live; scale to 4–8 | Parallelism. |
| `partitionKey` | `Contact_Changed__e.Contact_Key__c` | **Not `EventUuid`.** Same contact must hit the same partition or LWW races become lost updates. |

**Resume checkpoint + retry:**

- After each successfully claimed-and-applied event, `EventBus.TriggerContext.currentContext().setResumeCheckpoint(event.ReplayId)`.
- Transient failure (row lock, `UNABLE_TO_LOCK_ROW`): if **nothing** in this invocation has been checkpointed and `retries < 7`, throw `EventBus.RetryableException` (rolls back the invocation; max 1 + 9 retries then **error state**). If some events were already checkpointed, **return** instead of throwing — mixing a thrown `RetryableException` with earlier checkpoints is unsupported and can skip rolled-back work. The platform refires after the last checkpoint with governors reset.
- After 9 retries the trigger goes **error state** and **subsequent events are not replayed to the trigger**. That is a production incident. Alert on `EventBusSubscriber` state; fix and resume from Setup. Missed events during error state must be recovered from the 72-hour bus (Pub/Sub replay) or from the reconciliation job.

**Do not** `System.enqueueJob` and then consider the PE consumed. If the Queueable dies, the event is gone from the trigger’s point of view. If you need async enrichment, the trigger must write a **staging row in the same transaction** (the claim row is enough) and a separate worker processes staging.

**Callouts:** not in the PE trigger. Staging → Queueable/HTTP if you must call out.

### 5.3 Bus → System A / System B (Pub/Sub API)

- Use **Pub/Sub API** (gRPC), not CometD, for integration clients.
- Persist the last **successfully processed** `replay_id` (not the last received).
- On restart: subscribe `ReplayPreset.CUSTOM` from that id. Never default to `LATEST` after a crash (silent data loss) and never blindly use `EARLIEST` in production (reprocess up to 72 hours).
- `ManagedSubscribe` (beta) can store the cursor on the server; still keep your own cursor until GA and proven.
- Request batches with `num_requested` sized to processing capacity (backpressure). Do not pull 1000 if you can apply 50.
- Dedup with `event.id` (EventUuid) **and** `Message_Id__c`.
- Commit cursor **after** A/B acknowledge or after local outbox write, matching your fan-out guarantee.

Retention is **72 hours**. If a subscriber is down longer than that, events are gone. The **reconciliation job** (section 8) is mandatory, not optional.

### 5.4 Lost publish (the rare bus miss)

Because a queued publish can vanish:

1. Outbox stays `Pending` until **success callback**.
2. If callback never arrives within N minutes, republish **the same** `Message_Id__c` (consumers dedup).
3. Nightly reconciliation compares Contact watermarks across systems.

---

## 6. Limits, capacity, and how not to breach them

Figures below are **current default high-volume allocations** (no add-on), Winter ’27 docs. Confirm in Setup → Platform Events and `GET /services/data/v66.0/limits`.

### 6.1 Limits that actually bind this design

| Limit | UE / Performance | Enterprise | Counts |
| --- | --- | --- | --- |
| Event **publish** / rolling hour | 250,000 | 250,000 | Every publish method |
| Event **delivery** / rolling 24h | 50,000 | 25,000 | Pub/Sub, CometD, empApi, **Event Relay**. **Not** Apex/Flow. **Shared with CDC.** Per subscriber. |
| Add-on (each) | +100k delivery/day entitlement, +25k publish/hour | Same | Monthly entitlement + grace |
| Max event size | 1 MB | 1 MB | Publish fails for that message |
| PE definitions | 100 | 50 | One is enough here |
| Concurrent CometD clients | 2,000 | 1,000 | Avoid CometD for this |
| Custom PE channels | 100 | 100 | |
| Apex PE trigger batch | 1–2,000 (default 2,000) | | Configure 200 |
| Parallel trigger partitions | 1–10 | | Per-contact key |
| RetryableException | 1 + 9 retries then error state | | |
| Publish callbacks | 5 MB / 30 min; max 10 recursive publishes | | Keep callbacks lean |
| Apex DML / CPU / heap / SOQL | Standard governors per trigger invocation | | Batch size 200 |
| Daily **API requests** | Edition cap | | Burned by REST/SOAP publish and REST queries |
| Data storage | Edition cap | | `Event_Processed__c` + outbox + DLQ |
| Flow PE subscribers | Do not use at this volume | | |

Standard-volume: do not use. Publishing 100k/hour and 24h CometD delivery are the legacy table; retirement is Summer ’27.

### 6.2 Delivery math (the usual production surprise)

Delivery usage = `events_delivered_to_client_1 + client_2 + …` in the last 24 hours.

Example: 20,000 Contact events published in a few hours, **two** Pub/Sub subscribers:

`20,000 × 2 = 40,000` toward a 50,000 UE cap. A third subscriber (debug empApi, extra worker, Event Relay) finishes the org.

Apex trigger on the same 20,000 events: **+0 delivery**.

CDC on Contact plus PE on Contact to the same two clients: roughly **double**.

### 6.3 Capacity worksheet (fill with real volumes)

Let:

- `S` = SF-originated contact mutations/day that pass hash filter  
- `A`, `B` = mutations originating in A and B  
- `P = S + A + B` publishes/day (after hash filter and loop suppression)  
- `H` = peak hour publishes  
- `N` = number of **API** subscribers (Pub/Sub/CometD/empApi/Relay)

| Check | Formula | Gate |
| --- | --- | --- |
| Hourly publish | `H < 0.7 × 250,000` | Headroom for retries and other events |
| Daily delivery | `P × N < 0.7 × delivery_cap` | 0.7 is the alert line, not 1.0 |
| Apex inbound | `(A+B)` peak hour vs trigger throughput (`batchSize / duration`) | Watch lag to tip of stream |
| Storage | `P × 7 days` claim rows | Nightly purge |
| Callback heap | outbox flush rate × callback instance size | Stay under 5 MB / 30 min |

**Worked example**

| Item | Value |
| --- | --- |
| Mutations/day before filter | 90,000 |
| After hash + loop filter | 40,000 publishes (`P`) |
| Peak hour | 8,000 (`H`) |
| Topology gold (`N = 1` hub) | Delivery 40,000 — **fits UE 50k only barely**; alert at 35k; **buy add-on** before seasonal spikes |
| Topology direct A+B (`N = 2`), unfiltered | Delivery 80,000 — **breaches UE default** |
| Topology direct A+B, filtered (~⅔ of stream each) | ~53,000 — still add-on on UE |
| Hourly publish 8,000 | Comfortable vs 250k |

**Rule:** If `P × N` can exceed ~35k/day on UE or ~18k/day on EE, purchase the Platform Events add-on **before** go-live, and still keep `N = 1` if you can. The add-on also raises hourly publish by 25k per license and switches delivery to a monthly entitlement with grace — subscribers are less likely to be **disconnected** on a spike.

If delivery is exceeded **without** add-on: the Pub/Sub client is disconnected (`sfdc.platform.eventbus.grpc.subscription.limit.exceeded`). Events remain on the bus for 72 hours. Leave the client down until the rolling 24h window drops, then resume from stored replay id. Do not flap reconnect (it will fail immediately).

### 6.4 Other events in the same org

This design does not own the allocation. CDC, Experience Cloud, Order Management, other integrations, and Lightning `empApi` share delivery. Budget **≤ 50%** of the org cap for Contact sync unless you isolate with an add-on and usage metrics by client id.

### 6.5 What to do instead of “just publish more”

1. Hash-based no-op suppression (often 30–60% of CRM updates are non-material).
2. One API subscriber, fan-out off-platform.
3. Custom channel filters.
4. Do not subscribe in sandboxes to production-like volumes with extra debug clients.
5. Field-level sync later: only emit when mapped fields change (`Trigger.old` compare), not any Contact edit.
6. Burst control on the outbox worker.
7. Add-on license when the math says so — do not try to out-engineer a 50k cap at 100k real events.

---

## 7. Salesforce implementation

### 7.1 Objects

**`Contact_Outbox__c`** (outbound reliability)

- `Message_Id__c` (Unique External Id)
- `Contact_Key__c`, `Salesforce_Contact_Id__c`
- `Operation__c`, `Payload_Json__c`, `Payload_Hash__c`
- `Status__c`: Pending / Publishing / Published / Failed / DLQ
- `Attempt__c`, `Next_Attempt_At__c`, `Last_Error__c`
- `Event_Uuid__c`, `Published_At__c`

**`Event_Processed__c`** (inbound claim)

- Unique External Ids: `Dedup_Key__c`, `Message_Id__c`, `Event_Uuid__c`
- `Status__c`: CLAIMED / PROCESSED / POISON
- `Replay_Id__c`, `Source_System__c`, `Processed_At__c`

**`Contact_DLQ__c`**

- Full envelope, error, poison flag, `Replay_Id__c`, operator replay button (republish to inbound handler with a new claim? only after data fix; usually re-insert claim deleted)

**Contact** extra fields listed in §4.2. Matching: duplicate rules on Email + External Ids; inbound upsert `Database.upsert(..., Contact.Fields.System_A_Id__c)` when source is A, etc.

### 7.2 Outbound flow

```text
Contact after insert/update/delete
  → ContactChangePublisher (sync, no callouts)
      skip if integration user / recursion / hash unchanged / sync disabled
      insert Outbox Pending
  → OutboxPublishQueueable (after commit)
      guard HourlyPublishedPlatformEvents
      EventBus.publish(events, leanCallback)
  → Callback
      success: Outbox Published
      fail: retry / DLQ
```

Publish After Commit on `Contact_Changed__e` still matters for any residual direct publishes (tests, admin replay). Outbox rows are ordinary sObjects, so they commit or roll back with Contact.

### 7.3 Inbound flow

```text
Contact_Changed__e after insert (Apex)
  → drop Source_System = SALESFORCE
  → drop Schema_Version unsupported → DLQ
  → claim Event_Processed__c (partial insert)
  → LWW check on Contact
  → upsert Contact (external id) with integration user
  → setResumeCheckpoint
  → transient: RetryableException (bounded)
  → poison: DLQ + keep claim
```

Bulkify: one insert of claims, one query of Contacts by keys, one upsert. No SOQL in loops. No extra workflows on Contact that fan out more automation during inbound apply (set a custom `Sync_Applying__c` flag or use the integration user in workflow criteria).

### 7.4 Matching and MERGE

- First inbound create from A: upsert on `System_A_Id__c`; if email matches existing SF contact, attach the external id rather than inserting a duplicate (query-then-upsert, or duplicate rules with allow-save + merge job).
- `Operation__c = MERGE`: payload includes survivor and victim keys; Salesforce merge is a separate, carefully locked path (not a naive upsert). Process sequentially for that `Contact_Key__c` (partition key already serializes per key if partitions use it).
- DELETE: soft-delete policy preferred (`Is_Inactive__c`) unless all three systems agree on hard delete.

### 7.5 Security

- Integration user: CRUD on Contact (needed fields only), outbox, claim, DLQ. No extra objects.
- Named Principal for Pub/Sub (JWT or refresh token rotation).
- Event bus encryption at rest if Shield is in play.
- Do not put government IDs, payment data, or health data on the event unless every subscriber is in contract and encrypted in transit. Prefer a **pointer** (`Contact_Key__c`) plus a secured API fetch for sensitive fields (payload enrichment pattern) if PII minimization is required — that trades PE limits for API limits; use only for restricted fields.
- Store Pub/Sub secrets in a vault, not in custom settings in plaintext.

---

## 8. Reconciliation (covers the 72-hour hole)

A nightly (and on-demand) job, **not** on the event bus:

1. Export contacts changed in SF since watermark (`SystemModstamp`).
2. Each spoke provides changed ids since watermark via API/file.
3. Diff on `Contact_Key__c` + `Payload_Hash__c` (or field-level hash).
4. Repair by writing **outbox** rows (SF) or spoke APIs — still go through the same idempotent apply path.
5. This recovers: subscriber down > 72h, trigger error state, lost async publish, silently skipped poison after fix.

Without reconciliation, “reliable PE” is a 72-hour best effort.

---

## 9. Performance and optimization

| Technique | Effect |
| --- | --- |
| Field-level change detection on Contact | Cuts publishes |
| Payload hash | Cuts echoes and no-ops |
| Single API subscriber | Cuts delivery by factor of N |
| Channel filters | Cuts echo delivery |
| Batch publish (list of events, one `EventBus.publish`) | One DML-like publish call; better throughput |
| Outbox worker batch 50–200 | Balances callback size and hourly cap |
| PE trigger batch 200, partition by contact key | Throughput without governor deaths and lost ordering |
| Skip Flow/PB subscribers | They compete for processing and are hard to checkpoint |
| No debug `empApi` in prod | Each Lightning client is a delivery consumer |
| Lean callbacks | Stay under 5 MB / 30 min |
| Purge claims at 7 days | Storage |
| Compact JSON, no base64 blobs | 1 MB cap |
| `PlatformEventUsageMetric` by client id | Find the noisy subscriber |
| Disable sync for batch data loads | Use Bulk API + a single post-load reconciliation instead of 200k events |

**Throughput sketch:** 200 events/invocation × ~2s → ~100 events/s per partition → ~360k/hour theoretical. Real Contact upsert + duplicate rules is often 20–80 events/s per partition. Size partitions from measured duration, not from 2,000 batch folklore.

If inbound lag grows (subscriber not at tip of stream), add partitions **on Contact_Key__c**, then add-on/licenses, then consider moving heavy matching off-trigger into staging workers that still checkpoint only after staging insert.

---

## 10. Observability and operations

### 10.1 Metrics

- Setup → Platform Events → Event Allocations
- REST `/limits`: `HourlyPublishedPlatformEvents`, `DailyDeliveredPlatformEvents`, `MonthlyPlatformEventsUsageEntitlement`, `PublishCallbackUsageInApex`
- `PlatformEventUsageMetric` (by event name, client id, event type) — enhanced metrics
- Custom: outbox age, claim insert dup rate, DLQ count, trigger `EventBusSubscriber` status/retries, partition lag

### 10.2 Alerts

| Condition | Severity |
| --- | --- |
| Hourly publish > 70% | Warn; pause non-critical publishers |
| Hourly publish > 90% | Page; outbox pause |
| Daily delivery > 70% | Warn; shed extra subscribers |
| Daily delivery > 90% or disconnect error | Page |
| Callback usage > 70% of 5 MB | Warn; shrink callback state |
| Outbox `Pending` older than 15 min | Warn |
| Outbox / DLQ growth | Page |
| PE trigger Error state | Page (data loss window open) |
| Subscriber replay id older than 24h | Warn; 60h Page (72h cliff) |

### 10.3 Runbooks (short)

**Delivery cap hit:** Disconnect extra clients. Confirm `/limits`. Wait for rolling 24h decay **or** use add-on grace. Resume Pub/Sub from last processed replay id. Do not switch to `LATEST`.

**Trigger error state:** Fix Apex, save, resume subscription. For the gap: Pub/Sub replay as a privileged admin client into the same apply service, or reconciliation.

**Poison message:** Visible in DLQ. Fix data, delete claim if you want re-apply, republish from DLQ with same `Message_Id__c` only if the handler is now compatible; otherwise new `Message_Id__c` and bumped version.

**Duplicate contacts:** Stop inbound, run matching report, merge, emit `MERGE` once.

---

## 11. Testing strategy

| Layer | What |
| --- | --- |
| Apex unit | Claim-then-act duplicate insert; LWW; hash skip; `Test.getEventBus().deliver()`; publish callback tests |
| Bulk | 200 and 2,000 synthetic events; governor asserts |
| Duplicate / retry | Publish same `Message_Id__c` twice; replay same `EventUuid` with different replay ids |
| Loop | Inbound from A must not enqueue outbox for A’s own hash |
| Limit | Mock `OrgLimits` in the outbox worker; verify pause |
| Contract | JSON schema / Avro-style fixture shared with A and B |
| End-to-end | Three sandboxes or mocked Pub/Sub; kill subscriber for 10 minutes; confirm catch-up; kill for a simulated 73h and confirm reconciliation |
| Performance | Measure PE trigger duration and outbox drain vs peak `H` |

---

## 12. What not to do

- Exactly-once assumptions, or “the ReplayId is the unique id.”
- Flow/Process Builder as the production subscriber.
- REST publish at volume.
- CDC + PE for the same Contact stream to the same clients.
- `EventUuid` as Apex partition key for this domain.
- Queueable-only PE consumption without a staging write in the trigger transaction.
- Unbounded `RetryableException` until error state.
- Fat publish callbacks (full Contact payloads in callback fields).
- Extra production subscribers “just to watch events.”
- Putting the entire Contact history in one 1 MB event.

---

## 13. Implementation sequence

1. Confirm volumes (`S,A,B,H`) and existing CDC/PE usage. Decide add-on and whether an iPaaS hub exists.
2. Deploy event, Contact fields, outbox, claim, DLQ, integration user.
3. Inbound Apex with claim + LWW + checkpoint (no outbound yet).
4. Outbound outbox + callbacks + hash skip + integration-user guard.
5. Pub/Sub hub client with durable cursor and fan-out; or filtered channels.
6. Usage dashboards and alerts at 70%.
7. Reconciliation job.
8. Chaos: duplicate publish, replay, trigger exception, subscriber restart, hourly cap pause.
9. Only then enable parallel partitions if lag requires it.

---

## 14. Decision summary

| Question | Answer |
| --- | --- |
| How many PE types? | One: `Contact_Changed__e` |
| How to avoid delivery-limit breach? | Apex inbound; **one** API subscriber; filters; hash suppression; add-on when `P×N` needs it; no CDC overlap |
| How to dedup? | Unique-index claim on `Message_Id` + business `Dedup_Key`; `EventUuid` as secondary; LWW on version/time |
| How to deliver reliably? | Outbox + callbacks; 72h replay cursor; checkpoints; DLQ; nightly reconciliation |
| How to keep order? | Partition by `Contact_Key__c`; LWW; no global FIFO promise |
| How to stop loops? | Source system + hash + integration user + channel filters |

This is the production pattern: **at-least-once bus, exactly-once business effect**, with allocations treated as a first-class capacity problem rather than an afterthought.
