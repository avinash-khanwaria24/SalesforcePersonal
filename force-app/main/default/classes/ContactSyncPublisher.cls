/**
 * Bulk publisher for Contact_Sync__e. Immediate EventBus.publish after commit,
 * with SaveResult + async callback coverage and outbox fallback.
 */
public with sharing class ContactSyncPublisher {
    public static List<Contact> selectChanged(List<Contact> newRecords, Map<Id, Contact> oldMap) {
        List<Contact> changed = new List<Contact>();
        if (newRecords == null || newRecords.isEmpty()) {
            return changed;
        }
        for (Contact record : newRecords) {
            Contact prior = oldMap == null ? null : oldMap.get(record.Id);
            if (prior == null || hasSyncedFieldChange(record, prior)) {
                changed.add(record);
            }
        }
        return changed;
    }

    public static void publish(List<Contact> contacts, String changeType) {
        if (contacts == null || contacts.isEmpty()) {
            return;
        }
        List<Contact_Sync__e> events = new List<Contact_Sync__e>();
        for (Contact record : contacts) {
            events.add(ContactSyncEventMapper.fromContact(record, changeType));
        }
        publishEvents(events);
    }

    public static void publishEvents(List<Contact_Sync__e> events) {
        if (events == null || events.isEmpty()) {
            return;
        }
        for (Integer start = 0; start < events.size(); start += ContactSyncConstants.PUBLISH_CHUNK_SIZE) {
            Integer stop = Math.min(start + ContactSyncConstants.PUBLISH_CHUNK_SIZE, events.size());
            List<Contact_Sync__e> chunk = new List<Contact_Sync__e>();
            for (Integer i = start; i < stop; i++) {
                chunk.add(events[i]);
            }
            publishChunk(chunk);
        }
    }

    private static void publishChunk(List<Contact_Sync__e> events) {
        Map<String, String> uuidToCorrelation = new Map<String, String>();
        for (Contact_Sync__e event : events) {
            uuidToCorrelation.put(event.EventUuid, ContactSyncEventMapper.toCorrelation(event));
        }
        List<Database.SaveResult> results = EventBus.publish(
            events,
            ContactSyncPublishCallback.forInitialPublish(uuidToCorrelation)
        );
        List<Contact_Sync__e> failed = new List<Contact_Sync__e>();
        List<String> errors = new List<String>();
        for (Integer i = 0; i < results.size(); i++) {
            if (!results[i].isSuccess()) {
                failed.add(events[i]);
                errors.add(toErrorMessage(results[i]));
            }
        }
        if (!failed.isEmpty()) {
            ContactSyncOutboxService.enqueueEvents(failed, errors);
        }
    }

    private static Boolean hasSyncedFieldChange(Contact current, Contact prior) {
        for (String fieldName : ContactSyncConstants.SYNC_FIELDS) {
            if (current.get(fieldName) != prior.get(fieldName)) {
                return true;
            }
        }
        return false;
    }

    private static String toErrorMessage(Database.SaveResult result) {
        List<String> messages = new List<String>();
        for (Database.Error error : result.getErrors()) {
            messages.add(error.getStatusCode() + ': ' + error.getMessage());
        }
        return messages.isEmpty() ? 'Unknown publish error' : String.join(messages, '; ');
    }
}
