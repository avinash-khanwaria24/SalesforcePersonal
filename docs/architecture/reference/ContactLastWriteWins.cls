/**
 * Last-write-wins + source-priority tie break.
 * Apply inbound Contact changes only when the event is newer than Contact watermarks.
 */
public with sharing class ContactLastWriteWins {
    private static final Map<String, Integer> PRIORITY = new Map<String, Integer>{
        ContactSyncContract.SYS_SALESFORCE => 30,
        ContactSyncContract.SYS_A => 20,
        ContactSyncContract.SYS_B => 10
    };

    public static Boolean isNewer(Contact_Changed__e event, Contact existing) {
        if (existing == null || existing.Last_Sync_Occurred_At__c == null) {
            return true;
        }
        if (event.Occurred_At__c > existing.Last_Sync_Occurred_At__c) {
            return true;
        }
        if (event.Occurred_At__c < existing.Last_Sync_Occurred_At__c) {
            return false;
        }
        Decimal incomingVersion = event.Source_Version__c == null ? 0 : event.Source_Version__c;
        Decimal currentVersion = existing.Last_Sync_Version__c == null ? 0 : existing.Last_Sync_Version__c;
        if (incomingVersion > currentVersion) {
            return true;
        }
        if (incomingVersion < currentVersion) {
            return false;
        }
        Integer incomingPri = PRIORITY.containsKey(event.Source_System__c)
            ? PRIORITY.get(event.Source_System__c)
            : 0;
        Integer currentPri = PRIORITY.containsKey(existing.Last_Sync_Source__c)
            ? PRIORITY.get(existing.Last_Sync_Source__c)
            : 0;
        return incomingPri >= currentPri;
    }
}
