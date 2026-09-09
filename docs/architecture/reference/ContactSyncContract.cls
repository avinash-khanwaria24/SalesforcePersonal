/**
 * Builds Contact_Changed__e envelopes and the business dedup key.
 * Keep hashing deterministic: trim, lower-case email, sorted JSON keys, no audit fields.
 */
public with sharing class ContactSyncContract {
    public static final String SYS_SALESFORCE = 'SALESFORCE';
    public static final String SYS_A = 'SYS_A';
    public static final String SYS_B = 'SYS_B';
    public static final Integer SCHEMA_VERSION = 1;

    public static String dedupKey(String sourceSystem, String contactKey, Long sourceVersion, String operation) {
        return sourceSystem + '#' + contactKey + '#' + String.valueOf(sourceVersion) + '#' + operation;
    }

    public static String contactKey(Id salesforceId, String systemAId, String systemBId) {
        if (salesforceId != null) {
            return String.valueOf(salesforceId);
        }
        if (!String.isBlank(systemAId)) {
            return SYS_A + ':' + systemAId;
        }
        if (!String.isBlank(systemBId)) {
            return SYS_B + ':' + systemBId;
        }
        throw new ContactSyncException('Contact_Key cannot be derived');
    }

    public class ContactSyncException extends Exception {
    }
}
