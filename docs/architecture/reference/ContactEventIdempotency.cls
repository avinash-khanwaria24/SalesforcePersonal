/**
 * Claim-then-act idempotency. Unique External Ids on Event_Processed__c:
 *   Dedup_Key__c, Message_Id__c, Event_Uuid__c
 *
 * Insert-first is the race-safe pattern: two overlapping PE trigger
 * invocations cannot both process the same business event.
 */
public with sharing class ContactEventIdempotency {
    public class ClaimResult {
        public List<Contact_Changed__e> owned = new List<Contact_Changed__e>();
        public List<Event_Processed__c> claims = new List<Event_Processed__c>();
    }

    public static ClaimResult claim(List<Contact_Changed__e> events) {
        ClaimResult result = new ClaimResult();
        List<Event_Processed__c> toInsert = new List<Event_Processed__c>();
        List<Contact_Changed__e> aligned = new List<Contact_Changed__e>();

        for (Contact_Changed__e event : events) {
            if (event.Source_System__c == ContactSyncContract.SYS_SALESFORCE) {
                continue;
            }
            Event_Processed__c row = new Event_Processed__c();
            row.Dedup_Key__c = ContactSyncContract.dedupKey(
                event.Source_System__c,
                event.Contact_Key__c,
                event.Source_Version__c == null ? 0 : event.Source_Version__c.longValue(),
                event.Operation__c
            );
            row.Message_Id__c = event.Message_Id__c;
            row.Event_Uuid__c = event.EventUuid;
            row.Replay_Id__c = event.ReplayId;
            row.Source_System__c = event.Source_System__c;
            row.Status__c = 'CLAIMED';
            row.Processed_At__c = System.now();
            toInsert.add(row);
            aligned.add(event);
        }

        if (toInsert.isEmpty()) {
            return result;
        }

        Database.SaveResult[] saves = Database.insert(toInsert, false);
        for (Integer i = 0; i < saves.size(); i++) {
            if (saves[i].isSuccess()) {
                result.owned.add(aligned[i]);
                result.claims.add(toInsert[i]);
            }
            // DUPLICATE_VALUE → already claimed or processed; skip safely
        }
        return result;
    }

    public static void release(List<Event_Processed__c> claims) {
        if (claims == null || claims.isEmpty()) {
            return;
        }
        Database.delete(claims, false);
    }

    public static void markPoison(List<Event_Processed__c> claims) {
        for (Event_Processed__c row : claims) {
            row.Status__c = 'POISON';
        }
        Database.update(claims, false);
    }
}
