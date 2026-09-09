/**
 * Apex subscriber template. Each of the 3 systems must run this algorithm independently
 * against its own processed-event store (or use subscriberName isolation in this object).
 *
 * Claim unique EventUuid + business idempotency key first, then process. Transient
 * failures throw EventBus.RetryableException (DML rolls back, so the claim is retried).
 * After MAX_SUBSCRIBER_RETRIES, write DLQ, keep the claim, checkpoint, and do not throw
 * so the trigger never enters the error state.
 */
public without sharing class ContactSyncSubscriber {
    @TestVisible
    static Boolean forceProcessingFailure = false;

    @TestVisible
    static String subscriberName = ContactSyncConstants.APEX_SUBSCRIBER;

    public static void handle(List<Contact_Sync__e> events) {
        if (events == null || events.isEmpty()) {
            return;
        }
        EventBus.TriggerContext context = EventBus.TriggerContext.currentContext();
        ContactSyncIdempotencyService.ClaimResult claimed = ContactSyncIdempotencyService.claim(
            events,
            subscriberName
        );
        if (claimed.owned.isEmpty()) {
            checkpointLast(context, events);
            return;
        }
        try {
            process(claimed.owned);
            checkpointLast(context, events);
        } catch (Exception ex) {
            if (context.retries < ContactSyncConstants.MAX_SUBSCRIBER_RETRIES) {
                throw new EventBus.RetryableException(
                    'Contact sync processing failed, retry ' +
                    (context.retries + 1) +
                    ': ' +
                    ex.getMessage()
                );
            }
            ContactSyncDlqService.recordSubscribeFailures(
                claimed.owned,
                ex.getMessage(),
                subscriberName
            );
            checkpointLast(context, events);
        }
    }

    /**
     * Replace this with the system-specific apply logic (or enqueue a Queueable for callouts).
     * Keep it bulkified. Callouts from this trigger require async hand-off after a successful claim.
     */
    @TestVisible
    static void process(List<Contact_Sync__e> events) {
        if (forceProcessingFailure) {
            throw new ContactSyncException('Forced subscriber processing failure');
        }
        // Default Apex subscriber records the claim only. External systems apply Contact upserts here.
        System.debug(LoggingLevel.INFO, 'Contact sync claimed ' + events.size() + ' event(s) for ' + subscriberName);
    }

    private static void checkpointLast(EventBus.TriggerContext context, List<Contact_Sync__e> events) {
        if (context == null || events == null || events.isEmpty()) {
            return;
        }
        Contact_Sync__e lastEvent = events[events.size() - 1];
        if (lastEvent.ReplayId != null) {
            context.setResumeCheckpoint(lastEvent.ReplayId);
        }
    }
}
