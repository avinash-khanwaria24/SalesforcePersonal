/**
 * Builds Contact_Sync__e instances with EventUuid populated before publish
 * so Apex publish callbacks can correlate failures.
 */
public with sharing class ContactSyncEventMapper {
    public class Snapshot {
        public String contactId;
        public String changeType;
        public String idempotencyKey;
        public String firstName;
        public String lastName;
        public String email;
        public String phone;
        public String accountId;
        public Long systemModstampMs;
    }

    public static Contact_Sync__e fromContact(Contact record, String changeType) {
        Contact_Sync__e event = (Contact_Sync__e) Contact_Sync__e.sObjectType.newSObject(null, true);
        applySnapshot(event, toSnapshot(record, changeType));
        return event;
    }

    public static Contact_Sync__e fromSnapshot(Snapshot snapshot) {
        Contact_Sync__e event = (Contact_Sync__e) Contact_Sync__e.sObjectType.newSObject(null, true);
        applySnapshot(event, snapshot);
        return event;
    }

    public static Contact_Sync__e fromOutbox(Contact_Sync_Outbox__c row) {
        Snapshot snapshot;
        if (String.isNotBlank(row.Payload__c)) {
            snapshot = (Snapshot) JSON.deserialize(row.Payload__c, Snapshot.class);
        } else {
            snapshot = new Snapshot();
            snapshot.contactId = row.Contact_Id__c;
            snapshot.changeType = row.Change_Type__c;
            snapshot.idempotencyKey = row.Idempotency_Key__c;
        }
        return fromSnapshot(snapshot);
    }

    public static Snapshot toSnapshot(Contact record, String changeType) {
        Snapshot snapshot = new Snapshot();
        snapshot.contactId = record.Id;
        snapshot.changeType = changeType;
        snapshot.idempotencyKey = buildIdempotencyKey(record, changeType);
        snapshot.firstName = record.FirstName;
        snapshot.lastName = record.LastName;
        snapshot.email = record.Email;
        snapshot.phone = record.Phone;
        snapshot.accountId = record.AccountId;
        snapshot.systemModstampMs = record.SystemModstamp == null
            ? Datetime.now().getTime()
            : record.SystemModstamp.getTime();
        return snapshot;
    }

    public static String buildIdempotencyKey(Contact record, String changeType) {
        Long ts = record.SystemModstamp == null
            ? Datetime.now().getTime()
            : record.SystemModstamp.getTime();
        return record.Id + ':' + String.valueOf(ts) + ':' + changeType;
    }

    public static String toCorrelation(Contact_Sync__e event) {
        return event.Contact_Id__c + '|' + event.Change_Type__c + '|' + event.Idempotency_Key__c;
    }

    public static Snapshot fromCorrelation(String correlation) {
        Snapshot snapshot = new Snapshot();
        if (String.isBlank(correlation)) {
            return snapshot;
        }
        List<String> parts = correlation.split('\\|', 3);
        snapshot.contactId = parts.size() > 0 ? parts[0] : null;
        snapshot.changeType = parts.size() > 1 ? parts[1] : null;
        snapshot.idempotencyKey = parts.size() > 2 ? parts[2] : null;
        return snapshot;
    }

    public static String serialize(Snapshot snapshot) {
        return JSON.serialize(snapshot);
    }

    public static String serialize(Contact_Sync__e event) {
        Snapshot snapshot = new Snapshot();
        snapshot.contactId = event.Contact_Id__c;
        snapshot.changeType = event.Change_Type__c;
        snapshot.idempotencyKey = event.Idempotency_Key__c;
        snapshot.firstName = event.First_Name__c;
        snapshot.lastName = event.Last_Name__c;
        snapshot.email = event.Email__c;
        snapshot.phone = event.Phone__c;
        snapshot.accountId = event.Account_Id__c;
        snapshot.systemModstampMs = event.System_Modstamp__c == null
            ? null
            : event.System_Modstamp__c.getTime();
        return JSON.serialize(snapshot);
    }

    private static void applySnapshot(Contact_Sync__e event, Snapshot snapshot) {
        event.Contact_Id__c = snapshot.contactId;
        event.Change_Type__c = snapshot.changeType;
        event.Idempotency_Key__c = String.isBlank(snapshot.idempotencyKey)
            ? snapshot.contactId + ':' + String.valueOf(Datetime.now().getTime()) + ':' + snapshot.changeType
            : snapshot.idempotencyKey;
        event.First_Name__c = snapshot.firstName;
        event.Last_Name__c = snapshot.lastName;
        event.Email__c = snapshot.email;
        event.Phone__c = snapshot.phone;
        event.Account_Id__c = snapshot.accountId;
        if (snapshot.systemModstampMs != null) {
            event.System_Modstamp__c = Datetime.newInstance(snapshot.systemModstampMs);
        }
    }
}
