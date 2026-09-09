/**
 * Lean publish callback. Store only outbox Ids in publish order.
 * Do not hold event payloads here — they count toward PublishCallbackUsageInApex (5 MB / 30 min).
 */
public with sharing class OutboxPublishCallback implements
    EventBus.EventPublishSuccessCallback,
    EventBus.EventPublishFailureCallback {
    private List<Id> outboxIdsInPublishOrder;

    public OutboxPublishCallback(List<Id> outboxIdsInPublishOrder) {
        this.outboxIdsInPublishOrder = outboxIdsInPublishOrder;
    }

    public void onSuccess(EventBus.SuccessResult result) {
        List<String> uuids = result.getEventUuids();
        List<Contact_Outbox__c> updates = new List<Contact_Outbox__c>();
        Integer n = Math.min(uuids.size(), this.outboxIdsInPublishOrder.size());
        for (Integer i = 0; i < n; i++) {
            updates.add(new Contact_Outbox__c(
                Id = this.outboxIdsInPublishOrder[i],
                Status__c = 'Published',
                Event_Uuid__c = uuids[i],
                Published_At__c = System.now()
            ));
        }
        if (!updates.isEmpty()) {
            Database.update(updates, false);
        }
    }

    public void onFailure(EventBus.FailureResult result) {
        List<String> uuids = result.getEventUuids();
        List<Contact_Outbox__c> updates = new List<Contact_Outbox__c>();
        Integer n = Math.min(uuids.size(), this.outboxIdsInPublishOrder.size());
        if (n == 0) {
            n = this.outboxIdsInPublishOrder.size();
        }
        for (Integer i = 0; i < n; i++) {
            Contact_Outbox__c row = new Contact_Outbox__c(Id = this.outboxIdsInPublishOrder[i]);
            row.Status__c = 'Failed';
            row.Last_Error__c = 'Publish failed';
            row.Next_Attempt_At__c = System.now().addMinutes(5);
            updates.add(row);
        }
        if (!updates.isEmpty()) {
            Database.update(updates, false);
        }
    }
}
