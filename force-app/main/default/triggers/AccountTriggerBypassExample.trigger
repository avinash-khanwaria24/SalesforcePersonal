trigger AccountTriggerBypassExample on Account (before insert, before update) {
    if (TriggerBypassService.isBypassed('AccountTriggerBypassExample')) {
        return;
    }

    for (Account record : Trigger.new) {
        if (String.isBlank(record.Description)) {
            record.Description = 'TriggerBypassService example ran';
        }
    }
}
