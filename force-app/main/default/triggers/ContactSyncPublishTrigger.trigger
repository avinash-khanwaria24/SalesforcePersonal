trigger ContactSyncPublishTrigger on Contact (after insert, after update, after delete, after undelete) {
    ContactSyncTriggerHandler.handle();
}
