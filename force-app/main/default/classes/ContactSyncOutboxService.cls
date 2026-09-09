/**
 * Durable retry buffer for publishes that fail synchronously (SaveResult) or
 * asynchronously (EventPublishFailureCallback).
 */
public without sharing class ContactSyncOutboxService {
    public static void enqueueEvents(List<Contact_Sync__e> events, List<String> errors) {
        if (events == null || events.isEmpty()) {
            return;
        }
        List<Contact_Sync_Outbox__c> rows = new List<Contact_Sync_Outbox__c>();
        for (Integer i = 0; i < events.size(); i++) {
            Contact_Sync__e event = events[i];
            String errorMessage = errors != null && i < errors.size() ? errors[i] : 'Publish failed';
            rows.add(newOutbox(event, errorMessage, 0));
        }
        insert rows;
        ContactSyncRetryQueueable.enqueue(1);
    }

    public static void enqueueFromCorrelations(List<String> correlations, String errorMessage) {
        if (correlations == null || correlations.isEmpty()) {
            return;
        }
        List<Contact_Sync_Outbox__c> rows = new List<Contact_Sync_Outbox__c>();
        Datetime now = Datetime.now();
        for (String correlation : correlations) {
            ContactSyncEventMapper.Snapshot snapshot = ContactSyncEventMapper.fromCorrelation(correlation);
            Contact_Sync_Outbox__c row = new Contact_Sync_Outbox__c();
            row.Contact_Id__c = snapshot.contactId;
            row.Change_Type__c = snapshot.changeType;
            row.Idempotency_Key__c = snapshot.idempotencyKey;
            row.Payload__c = ContactSyncEventMapper.serialize(snapshot);
            row.Status__c = ContactSyncConstants.STATUS_PENDING;
            row.Attempt_Count__c = 0;
            row.Next_Attempt_At__c = now;
            row.Last_Error__c = truncate(errorMessage);
            rows.add(row);
        }
        insert rows;
        ContactSyncRetryQueueable.enqueue(1);
    }

    public static void markRetryFailures(Map<String, Id> uuidToOutboxId, List<String> failedUuids, String errorMessage) {
        if (failedUuids == null || failedUuids.isEmpty() || uuidToOutboxId == null) {
            return;
        }
        Set<Id> outboxIds = new Set<Id>();
        for (String eventUuid : failedUuids) {
            Id outboxId = uuidToOutboxId.get(eventUuid);
            if (outboxId != null) {
                outboxIds.add(outboxId);
            }
        }
        if (outboxIds.isEmpty()) {
            return;
        }
        List<Contact_Sync_Outbox__c> rows = [
            SELECT Id, Contact_Id__c, Event_Uuid__c, Idempotency_Key__c, Change_Type__c, Payload__c,
                Attempt_Count__c, Last_Error__c, Status__c, Next_Attempt_At__c
            FROM Contact_Sync_Outbox__c
            WHERE Id IN :outboxIds
        ];
        List<Contact_Sync_Outbox__c> retry = new List<Contact_Sync_Outbox__c>();
        List<Contact_Sync_Outbox__c> dead = new List<Contact_Sync_Outbox__c>();
        for (Contact_Sync_Outbox__c row : rows) {
            Decimal attempts = row.Attempt_Count__c == null ? 0 : row.Attempt_Count__c;
            row.Attempt_Count__c = attempts + 1;
            row.Last_Error__c = truncate(errorMessage);
            if (row.Attempt_Count__c >= ContactSyncConstants.MAX_PUBLISH_RETRIES) {
                row.Status__c = ContactSyncConstants.STATUS_DLQ;
                dead.add(row);
            } else {
                row.Status__c = ContactSyncConstants.STATUS_PENDING;
                row.Next_Attempt_At__c = Datetime.now()
                    .addMinutes(backoffMinutes(Integer.valueOf(row.Attempt_Count__c)));
                retry.add(row);
            }
        }
        List<Contact_Sync_Outbox__c> toUpdate = new List<Contact_Sync_Outbox__c>();
        toUpdate.addAll(retry);
        toUpdate.addAll(dead);
        if (!toUpdate.isEmpty()) {
            update toUpdate;
        }
        if (!dead.isEmpty()) {
            ContactSyncDlqService.recordPublishFailures(dead);
        }
        if (!retry.isEmpty()) {
            ContactSyncRetryQueueable.enqueue(backoffMinutes(1));
        }
    }

    public static void markPublished(Map<String, Id> uuidToOutboxId, List<String> successUuids) {
        if (successUuids == null || successUuids.isEmpty() || uuidToOutboxId == null || uuidToOutboxId.isEmpty()) {
            return;
        }
        Set<Id> outboxIds = new Set<Id>();
        for (String eventUuid : successUuids) {
            Id outboxId = uuidToOutboxId.get(eventUuid);
            if (outboxId != null) {
                outboxIds.add(outboxId);
            }
        }
        if (outboxIds.isEmpty()) {
            return;
        }
        delete [SELECT Id FROM Contact_Sync_Outbox__c WHERE Id IN :outboxIds];
    }

    public static List<Contact_Sync_Outbox__c> claimDue() {
        Datetime now = Datetime.now();
        Datetime staleBefore = now.addMinutes(-1 * ContactSyncConstants.STALE_PUBLISHING_MINUTES);
        List<Contact_Sync_Outbox__c> rows = [
            SELECT Id, Contact_Id__c, Event_Uuid__c, Idempotency_Key__c, Change_Type__c, Payload__c,
                Attempt_Count__c, Status__c, Next_Attempt_At__c
            FROM Contact_Sync_Outbox__c
            WHERE (
                    Status__c = :ContactSyncConstants.STATUS_PENDING
                    AND Next_Attempt_At__c <= :now
                )
                OR (
                    Status__c = :ContactSyncConstants.STATUS_PUBLISHING
                    AND LastModifiedDate <= :staleBefore
                )
            ORDER BY Next_Attempt_At__c ASC NULLS FIRST
            LIMIT :ContactSyncConstants.RETRY_BATCH_SIZE
            FOR UPDATE
        ];
        if (rows.isEmpty()) {
            return rows;
        }
        for (Contact_Sync_Outbox__c row : rows) {
            row.Status__c = ContactSyncConstants.STATUS_PUBLISHING;
        }
        update rows;
        return rows;
    }

    private static Contact_Sync_Outbox__c newOutbox(Contact_Sync__e event, String errorMessage, Integer attemptCount) {
        Contact_Sync_Outbox__c row = new Contact_Sync_Outbox__c();
        row.Contact_Id__c = event.Contact_Id__c;
        row.Event_Uuid__c = event.EventUuid;
        row.Idempotency_Key__c = event.Idempotency_Key__c;
        row.Change_Type__c = event.Change_Type__c;
        row.Payload__c = ContactSyncEventMapper.serialize(event);
        row.Status__c = ContactSyncConstants.STATUS_PENDING;
        row.Attempt_Count__c = attemptCount;
        row.Next_Attempt_At__c = Datetime.now();
        row.Last_Error__c = truncate(errorMessage);
        return row;
    }

    private static Integer backoffMinutes(Integer attemptCount) {
        Integer index = Math.max(attemptCount - 1, 0);
        if (index >= ContactSyncConstants.BACKOFF_MINUTES.size()) {
            return ContactSyncConstants.BACKOFF_MINUTES[ContactSyncConstants.BACKOFF_MINUTES.size() - 1];
        }
        return ContactSyncConstants.BACKOFF_MINUTES[index];
    }

    private static String truncate(String value) {
        if (String.isBlank(value)) {
            return value;
        }
        return value.length() <= 255 ? value : value.substring(0, 255);
    }
}
