/**
 * Sweeper for due outbox rows. Schedule every 5 minutes:
 * System.schedule('Contact Sync Outbox Retry', '0 0/5 * * * ?', new ContactSyncRetrySchedulable());
 */
public without sharing class ContactSyncRetrySchedulable implements Schedulable {
    public void execute(SchedulableContext context) {
        ContactSyncRetryQueueable.enqueue(0);
    }
}
