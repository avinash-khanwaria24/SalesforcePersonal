trigger ContactChangedTrigger on Contact_Changed__e (after insert) {
    ContactChangedInboundService.handle(Trigger.New);
}
