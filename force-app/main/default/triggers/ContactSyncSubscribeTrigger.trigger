trigger ContactSyncSubscribeTrigger on Contact_Sync__e (after insert) {
    ContactSyncSubscriber.handle(Trigger.new);
}
