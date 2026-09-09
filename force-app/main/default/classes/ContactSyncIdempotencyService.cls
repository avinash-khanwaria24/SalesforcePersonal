/**
 * Claim-then-process idempotency. Unique Dedup_Key (subscriber + EventUuid) stops
 * at-least-once redeliveries. Unique Business_Key (subscriber + idempotency key)
 * stops republishes of the same Contact change.
 */
public without sharing class ContactSyncIdempotencyService {
    public class ClaimResult {
        public List<Contact_Sync__e> owned = new List<Contact_Sync__e>();
        public List<Contact_Sync__e> duplicates = new List<Contact_Sync__e>();
    }

    public static ClaimResult claim(List<Contact_Sync__e> events, String subscriberName) {
        ClaimResult result = new ClaimResult();
        if (events == null || events.isEmpty()) {
            return result;
        }
        List<Processed_Event__c> rows = new List<Processed_Event__c>();
        for (Contact_Sync__e event : events) {
            rows.add(
                new Processed_Event__c(
                    Dedup_Key__c = toDedupKey(subscriberName, event.EventUuid),
                    Business_Key__c = toBusinessKey(subscriberName, event.Idempotency_Key__c),
                    Event_Uuid__c = event.EventUuid,
                    Idempotency_Key__c = event.Idempotency_Key__c,
                    Subscriber_Name__c = subscriberName,
                    Contact_Id__c = event.Contact_Id__c
                )
            );
        }
        List<Database.SaveResult> results = Database.insert(rows, false);
        for (Integer i = 0; i < results.size(); i++) {
            if (results[i].isSuccess()) {
                result.owned.add(events[i]);
            } else if (isDuplicate(results[i])) {
                result.duplicates.add(events[i]);
            } else {
                String message = results[i].getErrors().isEmpty()
                    ? 'Processed_Event insert failed'
                    : results[i].getErrors()[0].getMessage();
                throw new ContactSyncException(message);
            }
        }
        return result;
    }

    public static String toDedupKey(String subscriberName, String eventUuid) {
        return subscriberName + ':' + eventUuid;
    }

    public static String toBusinessKey(String subscriberName, String idempotencyKey) {
        return subscriberName + ':' + idempotencyKey;
    }

    private static Boolean isDuplicate(Database.SaveResult result) {
        for (Database.Error error : result.getErrors()) {
            if (error.getStatusCode() == StatusCode.DUPLICATE_VALUE) {
                return true;
            }
        }
        return false;
    }
}
