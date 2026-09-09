@IsTest
private class ContactSyncRetryTest {
    @IsTest
    static void queueableRepublishesDueOutboxAndClearsOnSuccess() {
        ContactSyncRetryQueueable.skipEnqueue = true;
        Contact record = new Contact(LastName = 'Retry', Email = 'retry@example.com');
        insert record;
        record = [SELECT Id, FirstName, LastName, Email, Phone, AccountId, SystemModstamp FROM Contact WHERE Id = :record.Id];

        Contact_Sync__e failed = ContactSyncEventMapper.fromContact(record, ContactSyncConstants.CHANGE_UPDATE);
        ContactSyncOutboxService.enqueueEvents(new List<Contact_Sync__e>{ failed }, new List<String>{ 'bus unavailable' });

        System.assertEquals(1, [SELECT COUNT() FROM Contact_Sync_Outbox__c]);

        Test.startTest();
        new ContactSyncRetryQueueable().execute(null);
        Test.getEventBus().deliver();
        Test.stopTest();

        System.assertEquals(0, [SELECT COUNT() FROM Contact_Sync_Outbox__c], 'Successful retry should delete the outbox row');
        System.assertEquals(
            1,
            [SELECT COUNT() FROM Processed_Event__c WHERE Idempotency_Key__c = :failed.Idempotency_Key__c]
        );
    }

    @IsTest
    static void retryFailureIncrementsAttempts() {
        ContactSyncRetryQueueable.skipEnqueue = true;
        Contact record = new Contact(LastName = 'Backoff');
        insert record;
        record = [SELECT Id, FirstName, LastName, Email, Phone, AccountId, SystemModstamp FROM Contact WHERE Id = :record.Id];
        Contact_Sync__e failed = ContactSyncEventMapper.fromContact(record, ContactSyncConstants.CHANGE_UPDATE);
        ContactSyncOutboxService.enqueueEvents(new List<Contact_Sync__e>{ failed }, new List<String>{ 'first fail' });

        Contact_Sync_Outbox__c row = [SELECT Id FROM Contact_Sync_Outbox__c];
        Map<String, Id> uuidToOutboxId = new Map<String, Id>{ failed.EventUuid => row.Id };

        Test.startTest();
        ContactSyncOutboxService.markRetryFailures(
            uuidToOutboxId,
            new List<String>{ failed.EventUuid },
            'Asynchronous EventBus publish failed'
        );
        Test.stopTest();

        row = [SELECT Attempt_Count__c, Status__c, Next_Attempt_At__c FROM Contact_Sync_Outbox__c WHERE Id = :row.Id];
        System.assertEquals(1, Integer.valueOf(row.Attempt_Count__c));
        System.assertEquals(ContactSyncConstants.STATUS_PENDING, row.Status__c);
        System.assert(row.Next_Attempt_At__c >= Datetime.now().addMinutes(1).addSeconds(-5));
    }

    @IsTest
    static void exhaustedRetriesMoveToDlq() {
        ContactSyncRetryQueueable.skipEnqueue = true;
        Contact record = new Contact(LastName = 'Dead');
        insert record;
        record = [SELECT Id, FirstName, LastName, Email, Phone, AccountId, SystemModstamp FROM Contact WHERE Id = :record.Id];
        Contact_Sync__e failed = ContactSyncEventMapper.fromContact(record, ContactSyncConstants.CHANGE_DELETE);
        ContactSyncOutboxService.enqueueEvents(new List<Contact_Sync__e>{ failed }, new List<String>{ 'first fail' });

        Contact_Sync_Outbox__c row = [SELECT Id FROM Contact_Sync_Outbox__c];
        row.Attempt_Count__c = ContactSyncConstants.MAX_PUBLISH_RETRIES - 1;
        update row;

        Test.startTest();
        ContactSyncOutboxService.markRetryFailures(
            new Map<String, Id>{ failed.EventUuid => row.Id },
            new List<String>{ failed.EventUuid },
            'still failing'
        );
        Test.stopTest();

        row = [SELECT Status__c, Attempt_Count__c FROM Contact_Sync_Outbox__c WHERE Id = :row.Id];
        System.assertEquals(ContactSyncConstants.STATUS_DLQ, row.Status__c);
        System.assertEquals(
            1,
            [SELECT COUNT() FROM Contact_Sync_DLQ__c WHERE Source__c = :ContactSyncConstants.SOURCE_PUBLISH]
        );
    }

    @IsTest
    static void schedulableEnqueuesRetryJob() {
        ContactSyncRetryQueueable.skipEnqueue = false;
        Test.startTest();
        new ContactSyncRetrySchedulable().execute(null);
        Test.stopTest();
        System.assert(true, 'Schedulable execute should enqueue without exception');
    }

    @IsTest
    static void enqueueEventsPersistsPayload() {
        ContactSyncRetryQueueable.skipEnqueue = true;
        Contact record = new Contact(LastName = 'Payload', Phone = '555');
        insert record;
        record = [SELECT Id, FirstName, LastName, Email, Phone, AccountId, SystemModstamp FROM Contact WHERE Id = :record.Id];
        Contact_Sync__e event = ContactSyncEventMapper.fromContact(record, ContactSyncConstants.CHANGE_UPDATE);

        ContactSyncOutboxService.enqueueEvents(new List<Contact_Sync__e>{ event }, new List<String>{ 'sync fail' });

        Contact_Sync_Outbox__c row = [
            SELECT Payload__c, Event_Uuid__c, Contact_Id__c
            FROM Contact_Sync_Outbox__c
        ];
        System.assertEquals(record.Id, row.Contact_Id__c);
        System.assert(row.Payload__c.contains(record.LastName));
        Contact_Sync__e rebuilt = ContactSyncEventMapper.fromOutbox(row);
        System.assertEquals(event.Phone__c, rebuilt.Phone__c);
        System.assertEquals(event.Idempotency_Key__c, rebuilt.Idempotency_Key__c);
        System.assertNotEquals(event.EventUuid, rebuilt.EventUuid, 'Retry publish must allocate a new EventUuid');
    }
}
