/**
 * Terminal store after bounded retries. Keeps the event bus and Apex trigger moving.
 */
public without sharing class ContactSyncDlqService {
    public static void recordPublishFailures(List<Contact_Sync_Outbox__c> rows) {
        if (rows == null || rows.isEmpty()) {
            return;
        }
        List<Contact_Sync_DLQ__c> dlq = new List<Contact_Sync_DLQ__c>();
        for (Contact_Sync_Outbox__c row : rows) {
            dlq.add(
                new Contact_Sync_DLQ__c(
                    Contact_Id__c = row.Contact_Id__c,
                    Event_Uuid__c = row.Event_Uuid__c,
                    Idempotency_Key__c = row.Idempotency_Key__c,
                    Change_Type__c = row.Change_Type__c,
                    Source__c = ContactSyncConstants.SOURCE_PUBLISH,
                    Payload__c = row.Payload__c,
                    Error_Message__c = row.Last_Error__c,
                    Attempt_Count__c = row.Attempt_Count__c
                )
            );
        }
        insert dlq;
    }

    public static void recordSubscribeFailures(List<Contact_Sync__e> events, String errorMessage, String subscriberName) {
        if (events == null || events.isEmpty()) {
            return;
        }
        List<Contact_Sync_DLQ__c> dlq = new List<Contact_Sync_DLQ__c>();
        for (Contact_Sync__e event : events) {
            dlq.add(
                new Contact_Sync_DLQ__c(
                    Contact_Id__c = event.Contact_Id__c,
                    Event_Uuid__c = event.EventUuid,
                    Idempotency_Key__c = event.Idempotency_Key__c,
                    Change_Type__c = event.Change_Type__c,
                    Source__c = ContactSyncConstants.SOURCE_SUBSCRIBE,
                    Subscriber_Name__c = subscriberName,
                    Payload__c = ContactSyncEventMapper.serialize(event),
                    Error_Message__c = errorMessage,
                    Replay_Id__c = event.ReplayId
                )
            );
        }
        insert dlq;
    }
}
