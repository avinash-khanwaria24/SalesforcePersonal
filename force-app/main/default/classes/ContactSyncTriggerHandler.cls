public with sharing class ContactSyncTriggerHandler {
    @TestVisible
    private static Boolean bypass = false;

    private static Boolean inProgress = false;

    public static void handle() {
        if (bypass || inProgress || Trigger.isExecuting == false) {
            return;
        }
        inProgress = true;
        try {
            if (Trigger.isAfter && (Trigger.isInsert || Trigger.isUndelete)) {
                ContactSyncPublisher.publish((List<Contact>) Trigger.new, ContactSyncConstants.CHANGE_CREATE);
            } else if (Trigger.isAfter && Trigger.isUpdate) {
                List<Contact> changed = ContactSyncPublisher.selectChanged(
                    (List<Contact>) Trigger.new,
                    (Map<Id, Contact>) Trigger.oldMap
                );
                if (!changed.isEmpty()) {
                    ContactSyncPublisher.publish(changed, ContactSyncConstants.CHANGE_UPDATE);
                }
            } else if (Trigger.isAfter && Trigger.isDelete) {
                ContactSyncPublisher.publish((List<Contact>) Trigger.old, ContactSyncConstants.CHANGE_DELETE);
            }
        } finally {
            inProgress = false;
        }
    }
}
