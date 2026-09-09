/**
 * Delayed republish of outbox rows. Does not retry inside the publish callback.
 */
public without sharing class ContactSyncRetryQueueable implements Queueable {
    @TestVisible
    static Boolean skipEnqueue = false;

    public static void enqueue(Integer delayMinutes) {
        if (skipEnqueue) {
            return;
        }
        try {
            Integer delay = delayMinutes == null || delayMinutes < 0 ? 0 : Math.min(delayMinutes, 10);
            System.enqueueJob(new ContactSyncRetryQueueable(), delay);
        } catch (Exception ex) {
            System.debug(LoggingLevel.WARN, 'ContactSyncRetryQueueable enqueue skipped: ' + ex.getMessage());
        }
    }

    public void execute(QueueableContext context) {
        List<Contact_Sync_Outbox__c> rows = ContactSyncOutboxService.claimDue();
        if (rows.isEmpty()) {
            return;
        }
        List<Contact_Sync__e> events = new List<Contact_Sync__e>();
        Map<String, Id> uuidToOutboxId = new Map<String, Id>();
        hydrateMissingPayloads(rows);
        for (Contact_Sync_Outbox__c row : rows) {
            Contact_Sync__e event = ContactSyncEventMapper.fromOutbox(row);
            events.add(event);
            uuidToOutboxId.put(event.EventUuid, row.Id);
            row.Event_Uuid__c = event.EventUuid;
        }
        update rows;

        List<Database.SaveResult> results = EventBus.publish(
            events,
            ContactSyncPublishCallback.forRetry(uuidToOutboxId)
        );
        List<String> failedUuids = new List<String>();
        for (Integer i = 0; i < results.size(); i++) {
            if (!results[i].isSuccess()) {
                failedUuids.add(events[i].EventUuid);
            }
        }
        if (!failedUuids.isEmpty()) {
            ContactSyncOutboxService.markRetryFailures(
                uuidToOutboxId,
                failedUuids,
                'Synchronous EventBus publish failed on retry'
            );
        }
        if (rows.size() == ContactSyncConstants.RETRY_BATCH_SIZE) {
            enqueue(1);
        }
    }

    private static void hydrateMissingPayloads(List<Contact_Sync_Outbox__c> rows) {
        Set<Id> contactIds = new Set<Id>();
        for (Contact_Sync_Outbox__c row : rows) {
            if (String.isBlank(row.Payload__c) && String.isNotBlank(row.Contact_Id__c)
                && row.Change_Type__c != ContactSyncConstants.CHANGE_DELETE) {
                contactIds.add(row.Contact_Id__c);
            }
        }
        if (contactIds.isEmpty()) {
            return;
        }
        Map<Id, Contact> contacts = new Map<Id, Contact>(
            [
                SELECT Id, FirstName, LastName, Email, Phone, AccountId, SystemModstamp
                FROM Contact
                WHERE Id IN :contactIds
                ALL ROWS
            ]
        );
        for (Contact_Sync_Outbox__c row : rows) {
            if (String.isNotBlank(row.Payload__c) || row.Change_Type__c == ContactSyncConstants.CHANGE_DELETE) {
                continue;
            }
            Contact record = contacts.get(row.Contact_Id__c);
            if (record != null) {
                row.Payload__c = ContactSyncEventMapper.serialize(
                    ContactSyncEventMapper.toSnapshot(record, row.Change_Type__c)
                );
                row.Idempotency_Key__c = ContactSyncEventMapper.buildIdempotencyKey(record, row.Change_Type__c);
            }
        }
    }
}
