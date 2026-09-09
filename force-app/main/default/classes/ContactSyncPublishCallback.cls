/**
 * Compact publish callback. Stores only EventUuid correlation data so the 5 MB / 30 min
 * callback allocation stays small. Does not retry in-callback (that burns the 10-deep
 * recursive publish limit); failed events go to the outbox for delayed retry.
 */
public without sharing class ContactSyncPublishCallback implements
    EventBus.EventPublishFailureCallback,
    EventBus.EventPublishSuccessCallback {

    private Map<String, String> uuidToCorrelation;
    private Map<String, Id> uuidToOutboxId;

    public static ContactSyncPublishCallback forInitialPublish(Map<String, String> uuidToCorrelation) {
        ContactSyncPublishCallback callback = new ContactSyncPublishCallback();
        callback.uuidToCorrelation = uuidToCorrelation == null
            ? new Map<String, String>()
            : uuidToCorrelation;
        callback.uuidToOutboxId = new Map<String, Id>();
        return callback;
    }

    public static ContactSyncPublishCallback forRetry(Map<String, Id> uuidToOutboxId) {
        ContactSyncPublishCallback callback = new ContactSyncPublishCallback();
        callback.uuidToCorrelation = new Map<String, String>();
        callback.uuidToOutboxId = uuidToOutboxId == null ? new Map<String, Id>() : uuidToOutboxId;
        return callback;
    }

    public void onFailure(EventBus.FailureResult result) {
        List<String> failedUuids = result.getEventUuids();
        if (failedUuids == null || failedUuids.isEmpty()) {
            return;
        }
        if (uuidToOutboxId != null && !uuidToOutboxId.isEmpty()) {
            ContactSyncOutboxService.markRetryFailures(
                uuidToOutboxId,
                failedUuids,
                'Asynchronous EventBus publish failed'
            );
            return;
        }
        List<String> correlations = new List<String>();
        for (String eventUuid : failedUuids) {
            String correlation = uuidToCorrelation == null ? null : uuidToCorrelation.get(eventUuid);
            if (String.isNotBlank(correlation)) {
                correlations.add(correlation);
            }
        }
        ContactSyncOutboxService.enqueueFromCorrelations(
            correlations,
            'Asynchronous EventBus publish failed'
        );
    }

    public void onSuccess(EventBus.SuccessResult result) {
        // Skip work on the hot success path unless this was an outbox retry.
        if (uuidToOutboxId == null || uuidToOutboxId.isEmpty()) {
            return;
        }
        List<String> successUuids = result.getEventUuids();
        ContactSyncOutboxService.markPublished(uuidToOutboxId, successUuids);
    }
}
