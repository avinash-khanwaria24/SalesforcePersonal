@IsTest
private class ContactSyncPublisherTest {
    @IsTest
    static void insertContactPublishesCreateEvent() {
        ContactSyncRetryQueueable.skipEnqueue = true;

        Test.startTest();
        Contact record = new Contact(FirstName = 'Ada', LastName = 'Lovelace', Email = 'ada@example.com');
        insert record;
        Test.getEventBus().deliver();
        Test.stopTest();

        List<Processed_Event__c> processed = [
            SELECT Event_Uuid__c, Idempotency_Key__c, Contact_Id__c, Subscriber_Name__c
            FROM Processed_Event__c
        ];
        System.assertEquals(1, processed.size(), 'Subscriber should claim the published event');
        System.assertEquals(record.Id, processed[0].Contact_Id__c);
        System.assertEquals(ContactSyncConstants.APEX_SUBSCRIBER, processed[0].Subscriber_Name__c);
        System.assert(processed[0].Idempotency_Key__c.contains(ContactSyncConstants.CHANGE_CREATE));
    }

    @IsTest
    static void updateWithoutSyncedFieldChangeDoesNotRepublish() {
        ContactSyncRetryQueueable.skipEnqueue = true;
        Contact record = new Contact(LastName = 'Hopper');
        insert record;
        Test.getEventBus().deliver();
        Integer afterInsert = [SELECT COUNT() FROM Processed_Event__c];

        Test.startTest();
        record.Description = 'Internal note only';
        update record;
        Test.getEventBus().deliver();
        Test.stopTest();

        System.assertEquals(
            afterInsert,
            [SELECT COUNT() FROM Processed_Event__c],
            'Description is not a synced field'
        );
    }

    @IsTest
    static void updateSyncedFieldPublishesUpdateEvent() {
        ContactSyncRetryQueueable.skipEnqueue = true;
        Contact record = new Contact(LastName = 'Hopper', Email = 'grace@example.com');
        insert record;
        Test.getEventBus().deliver();

        Test.startTest();
        record.Email = 'grace.hopper@example.com';
        update record;
        Test.getEventBus().deliver();
        Test.stopTest();

        List<Processed_Event__c> processed = [SELECT Idempotency_Key__c FROM Processed_Event__c];
        System.assertEquals(2, processed.size(), 'Create and update should both be claimed');
        Boolean sawUpdate = false;
        for (Processed_Event__c row : processed) {
            if (row.Idempotency_Key__c.contains(ContactSyncConstants.CHANGE_UPDATE)) {
                sawUpdate = true;
            }
        }
        System.assert(sawUpdate, 'Expected an UPDATE idempotency key');
    }

    @IsTest
    static void asyncPublishFailureWritesOutbox() {
        ContactSyncRetryQueueable.skipEnqueue = true;

        Test.startTest();
        insert new Contact(LastName = 'Babbage');
        Test.getEventBus().fail();
        Test.stopTest();

        List<Contact_Sync_Outbox__c> outbox = [
            SELECT Contact_Id__c, Change_Type__c, Status__c, Idempotency_Key__c
            FROM Contact_Sync_Outbox__c
        ];
        System.assertEquals(1, outbox.size(), 'Failure callback should persist an outbox row');
        System.assertEquals(ContactSyncConstants.STATUS_PENDING, outbox[0].Status__c);
        System.assertEquals(ContactSyncConstants.CHANGE_CREATE, outbox[0].Change_Type__c);
        System.assertEquals(0, [SELECT COUNT() FROM Processed_Event__c], 'Failed publishes must not be processed');
    }

    @IsTest
    static void selectChangedDetectsSyncedFieldsOnly() {
        Contact prior = new Contact(FirstName = 'A', LastName = 'One', Email = 'a@example.com', Phone = '1');
        Contact current = prior.clone(false, true, false, false);
        current.Email = 'b@example.com';
        List<Contact> changed = ContactSyncPublisher.selectChanged(
            new List<Contact>{ current },
            new Map<Id, Contact>{ current.Id => prior }
        );
        System.assertEquals(1, changed.size());

        current.Email = prior.Email;
        changed = ContactSyncPublisher.selectChanged(
            new List<Contact>{ current },
            new Map<Id, Contact>{ current.Id => prior }
        );
        System.assertEquals(0, changed.size());
    }

    @IsTest
    static void mapperBuildsEventUuidAndCorrelation() {
        Contact record = new Contact(LastName = 'Tesla');
        insert record;
        record = [SELECT Id, FirstName, LastName, Email, Phone, AccountId, SystemModstamp FROM Contact WHERE Id = :record.Id];

        Contact_Sync__e event = ContactSyncEventMapper.fromContact(record, ContactSyncConstants.CHANGE_UPDATE);
        System.assertNotEquals(null, event.EventUuid, 'newSObject must populate EventUuid before publish');
        System.assertEquals(record.Id, event.Contact_Id__c);
        System.assert(String.isNotBlank(event.Idempotency_Key__c));

        String correlation = ContactSyncEventMapper.toCorrelation(event);
        ContactSyncEventMapper.Snapshot snapshot = ContactSyncEventMapper.fromCorrelation(correlation);
        System.assertEquals(record.Id, snapshot.contactId);
        System.assertEquals(ContactSyncConstants.CHANGE_UPDATE, snapshot.changeType);
        System.assertEquals(event.Idempotency_Key__c, snapshot.idempotencyKey);
    }
}
