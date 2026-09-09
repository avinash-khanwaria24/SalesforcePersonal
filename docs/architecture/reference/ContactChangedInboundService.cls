/**
 * Inbound subscriber. Default PE batch is 2000 — configure 200 via PlatformEventSubscriberConfig.
 * Partition by Contact_Key__c, not EventUuid, so one contact is never applied in parallel.
 *
 * Reliability:
 *  - Claim unique keys before DML
 *  - setResumeCheckpoint after each successful apply
 *  - RetryableException only for transient remainder, retries < 7
 *  - Poison messages go to DLQ and keep the claim
 */
public with sharing class ContactChangedInboundService {
    private static final Integer MAX_RETRIES = 7;

    public static void handle(List<Contact_Changed__e> events) {
        EventBus.TriggerContext ctx = EventBus.TriggerContext.currentContext();
        ContactEventIdempotency.ClaimResult claimed = ContactEventIdempotency.claim(events);
        Boolean checkpointed = false;

        Map<String, Contact> contactsByKey = ContactChangedInboundService.loadContacts(claimed.owned);

        for (Integer i = 0; i < claimed.owned.size(); i++) {
            Contact_Changed__e event = claimed.owned[i];
            Event_Processed__c claim = claimed.claims[i];
            try {
                if (event.Schema_Version__c == null
                    || event.Schema_Version__c.intValue() > ContactSyncContract.SCHEMA_VERSION) {
                    ContactChangedInboundService.poison(event, claim, 'Unsupported schema version');
                    ctx.setResumeCheckpoint(event.ReplayId);
                    checkpointed = true;
                    continue;
                }

                Contact current = contactsByKey.get(event.Contact_Key__c);
                if (!ContactLastWriteWins.isNewer(event, current)) {
                    ctx.setResumeCheckpoint(event.ReplayId);
                    checkpointed = true;
                    continue;
                }

                ContactChangedInboundService.apply(event, current);
                ctx.setResumeCheckpoint(event.ReplayId);
                checkpointed = true;
            } catch (Exception ex) {
                if (ContactChangedInboundService.isTransient(ex) && !checkpointed && ctx.retries < MAX_RETRIES) {
                    // RetryableException rolls back this invocation (including the claim).
                    // Only safe when nothing has been checkpointed yet.
                    throw new EventBus.RetryableException('Transient: ' + ex.getMessage());
                }
                if (ContactChangedInboundService.isTransient(ex) && checkpointed) {
                    // Do not mix RetryableException with checkpoints. Release this claim
                    // so the refire after the last checkpoint can reclaim it.
                    ContactEventIdempotency.release(new List<Event_Processed__c>{ claim });
                    return;
                }
                ContactChangedInboundService.poison(event, claim, ex.getMessage());
                ctx.setResumeCheckpoint(event.ReplayId);
                checkpointed = true;
            }
        }
    }

    private static Map<String, Contact> loadContacts(List<Contact_Changed__e> events) {
        Set<String> keys = new Set<String>();
        Set<String> aIds = new Set<String>();
        Set<String> bIds = new Set<String>();
        Set<Id> sfIds = new Set<Id>();
        for (Contact_Changed__e event : events) {
            keys.add(event.Contact_Key__c);
            if (!String.isBlank(event.System_A_Id__c)) {
                aIds.add(event.System_A_Id__c);
            }
            if (!String.isBlank(event.System_B_Id__c)) {
                bIds.add(event.System_B_Id__c);
            }
            if (!String.isBlank(event.Salesforce_Contact_Id__c)) {
                sfIds.add((Id) event.Salesforce_Contact_Id__c);
            }
        }
        Map<String, Contact> byKey = new Map<String, Contact>();
        if (keys.isEmpty() && aIds.isEmpty() && bIds.isEmpty() && sfIds.isEmpty()) {
            return byKey;
        }
        for (Contact row : [
            SELECT Id, Email, Last_Sync_Source__c, Last_Sync_Version__c, Last_Sync_Occurred_At__c,
                   Last_Sync_Hash__c, System_A_Id__c, System_B_Id__c
            FROM Contact
            WHERE Id IN :sfIds
               OR System_A_Id__c IN :aIds
               OR System_B_Id__c IN :bIds
        ]) {
            byKey.put(String.valueOf(row.Id), row);
            if (!String.isBlank(row.System_A_Id__c)) {
                byKey.put(ContactSyncContract.SYS_A + ':' + row.System_A_Id__c, row);
            }
            if (!String.isBlank(row.System_B_Id__c)) {
                byKey.put(ContactSyncContract.SYS_B + ':' + row.System_B_Id__c, row);
            }
        }
        return byKey;
    }

    private static void apply(Contact_Changed__e event, Contact current) {
        // Map Payload_Json__c onto Contact, set watermarks, upsert by the source external id.
        // Intentionally omitted field-by-field mapping — keep this class about reliability.
    }

    private static void poison(Contact_Changed__e event, Event_Processed__c claim, String error) {
        ContactEventIdempotency.markPoison(new List<Event_Processed__c>{ claim });
        Contact_DLQ__c dlq = new Contact_DLQ__c();
        dlq.Message_Id__c = event.Message_Id__c;
        dlq.Replay_Id__c = event.ReplayId;
        dlq.Error__c = error;
        dlq.Payload_Json__c = event.Payload_Json__c;
        insert dlq;
    }

    private static Boolean isTransient(Exception ex) {
        String message = ex.getMessage();
        if (message == null) {
            return false;
        }
        return message.contains('UNABLE_TO_LOCK_ROW') || message.contains('UNABLE_TO_LOCK');
    }
}
