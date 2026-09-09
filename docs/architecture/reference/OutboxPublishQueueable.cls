/**
 * Drains Contact_Outbox__c in batches. Pauses when hourly publish remaining < 20%.
 * Callback instance MUST stay small (5 MB / 30 minutes org-wide allocation).
 */
public with sharing class OutboxPublishQueueable implements Queueable {
    private static final Integer BATCH_SIZE = 100;
    private static final Integer HEADROOM_PERCENT = 20;

    public void execute(QueueableContext context) {
        if (!OutboxPublishQueueable.hasPublishHeadroom()) {
            return;
        }

        List<Contact_Outbox__c> pending = [
            SELECT Id, Message_Id__c, Contact_Key__c, Salesforce_Contact_Id__c, Operation__c,
                   Payload_Json__c, Payload_Hash__c, Attempt__c
            FROM Contact_Outbox__c
            WHERE Status__c IN ('Pending', 'Failed')
              AND Next_Attempt_At__c <= :System.now()
            ORDER BY Next_Attempt_At__c
            LIMIT :BATCH_SIZE
            FOR UPDATE
        ];
        if (pending.isEmpty()) {
            return;
        }

        List<Contact_Changed__e> events = new List<Contact_Changed__e>();
        List<Id> outboxIds = new List<Id>();
        for (Contact_Outbox__c row : pending) {
            Contact_Changed__e event = new Contact_Changed__e();
            event.Message_Id__c = row.Message_Id__c;
            event.Correlation_Id__c = row.Message_Id__c;
            event.Source_System__c = ContactSyncContract.SYS_SALESFORCE;
            event.Operation__c = row.Operation__c;
            event.Schema_Version__c = ContactSyncContract.SCHEMA_VERSION;
            event.Contact_Key__c = row.Contact_Key__c;
            event.Salesforce_Contact_Id__c = row.Salesforce_Contact_Id__c;
            event.Occurred_At__c = System.now();
            event.Source_Version__c = row.Attempt__c;
            event.Payload_Hash__c = row.Payload_Hash__c;
            event.Payload_Json__c = row.Payload_Json__c;
            events.add(event);
            outboxIds.add(row.Id);
            row.Status__c = 'Publishing';
            row.Attempt__c = (row.Attempt__c == null ? 1 : row.Attempt__c + 1);
        }
        update pending;

        EventBus.publish(events, new OutboxPublishCallback(outboxIds));

        if (pending.size() == BATCH_SIZE && Limits.getQueueableJobs() < Limits.getLimitQueueableJobs()) {
            System.enqueueJob(new OutboxPublishQueueable());
        }
    }

    public static Boolean hasPublishHeadroom() {
        System.OrgLimit hourly = System.OrgLimits.getMap().get('HourlyPublishedPlatformEvents');
        if (hourly == null || hourly.getLimit() == 0) {
            return true;
        }
        Integer usedPct = (100 * hourly.getValue()) / hourly.getLimit();
        return usedPct < (100 - HEADROOM_PERCENT);
    }
}
