/**
 * Shared contract for Contact sync platform events.
 * One high-volume event fans out to every subscriber; do not publish per system.
 */
public with sharing class ContactSyncConstants {
    public static final String CHANGE_CREATE = 'CREATE';
    public static final String CHANGE_UPDATE = 'UPDATE';
    public static final String CHANGE_DELETE = 'DELETE';

    public static final String STATUS_PENDING = 'Pending';
    public static final String STATUS_PUBLISHING = 'Publishing';
    public static final String STATUS_FAILED = 'Failed';
    public static final String STATUS_DLQ = 'DLQ';

    public static final String SOURCE_PUBLISH = 'Publish';
    public static final String SOURCE_SUBSCRIBE = 'Subscribe';

    /** Apex subscriber name; each of the 3 external systems must use its own name in its store. */
    public static final String APEX_SUBSCRIBER = 'SalesforceApex';

    /**
     * HVPE publish limit per Apex transaction is 150.
     * Keep callback state tiny: only EventUuid correlation strings, never full payloads.
     */
    public static final Integer PUBLISH_CHUNK_SIZE = 150;

    /** Leave headroom under Salesforce's 9 RetryableException retries so the trigger never enters error state. */
    public static final Integer MAX_SUBSCRIBER_RETRIES = 6;

    public static final Integer MAX_PUBLISH_RETRIES = 5;

    /** Queueable delay cap is 10 minutes. */
    public static final List<Integer> BACKOFF_MINUTES = new List<Integer>{ 1, 2, 4, 8, 10 };

    public static final Integer RETRY_BATCH_SIZE = 200;

    public static final Integer STALE_PUBLISHING_MINUTES = 15;

    public static final Set<String> SYNC_FIELDS = new Set<String>{
        'FirstName',
        'LastName',
        'Email',
        'Phone',
        'AccountId'
    };
}
