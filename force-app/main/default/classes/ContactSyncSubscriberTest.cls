@IsTest
private class ContactSyncSubscriberTest {
    @IsTest
    static void claimIsIdempotentOnEventUuid() {
        ContactSyncRetryQueueable.skipEnqueue = true;
        Contact record = new Contact(LastName = 'Idempotent');
        insert record;
        record = [SELECT Id, FirstName, LastName, Email, Phone, AccountId, SystemModstamp FROM Contact WHERE Id = :record.Id];

        Contact_Sync__e event = ContactSyncEventMapper.fromContact(record, ContactSyncConstants.CHANGE_UPDATE);
        ContactSyncIdempotencyService.ClaimResult first = ContactSyncIdempotencyService.claim(
            new List<Contact_Sync__e>{ event },
            'ERP'
        );
        ContactSyncIdempotencyService.ClaimResult second = ContactSyncIdempotencyService.claim(
            new List<Contact_Sync__e>{ event },
            'ERP'
        );

        System.assertEquals(1, first.owned.size());
        System.assertEquals(0, first.duplicates.size());
        System.assertEquals(0, second.owned.size());
        System.assertEquals(1, second.duplicates.size(), 'Same EventUuid must not be processed twice');
        System.assertEquals(1, [SELECT COUNT() FROM Processed_Event__c WHERE Subscriber_Name__c = 'ERP']);
    }

    @IsTest
    static void claimIsIdempotentOnBusinessKeyForRepublish() {
        ContactSyncRetryQueueable.skipEnqueue = true;
        Contact record = new Contact(LastName = 'Republish');
        insert record;
        record = [SELECT Id, FirstName, LastName, Email, Phone, AccountId, SystemModstamp FROM Contact WHERE Id = :record.Id];

        Contact_Sync__e firstEvent = ContactSyncEventMapper.fromContact(record, ContactSyncConstants.CHANGE_UPDATE);
        Contact_Sync__e retryEvent = ContactSyncEventMapper.fromContact(record, ContactSyncConstants.CHANGE_UPDATE);
        retryEvent.Idempotency_Key__c = firstEvent.Idempotency_Key__c;
        System.assertNotEquals(firstEvent.EventUuid, retryEvent.EventUuid, 'Republish gets a new EventUuid');

        ContactSyncIdempotencyService.claim(new List<Contact_Sync__e>{ firstEvent }, 'CRM');
        ContactSyncIdempotencyService.ClaimResult retryClaim = ContactSyncIdempotencyService.claim(
            new List<Contact_Sync__e>{ retryEvent },
            'CRM'
        );

        System.assertEquals(1, retryClaim.duplicates.size(), 'Same idempotency key must be skipped');
        System.assertEquals(0, retryClaim.owned.size());
    }

    @IsTest
    static void threeSystemsCanProcessTheSameEventUuidIndependently() {
        ContactSyncRetryQueueable.skipEnqueue = true;
        Contact record = new Contact(LastName = 'Fanout');
        insert record;
        record = [SELECT Id, FirstName, LastName, Email, Phone, AccountId, SystemModstamp FROM Contact WHERE Id = :record.Id];
        Contact_Sync__e event = ContactSyncEventMapper.fromContact(record, ContactSyncConstants.CHANGE_CREATE);

        for (String systemName : new List<String>{ 'ERP', 'CRM', 'MARKETING' }) {
            ContactSyncIdempotencyService.ClaimResult claimed = ContactSyncIdempotencyService.claim(
                new List<Contact_Sync__e>{ event },
                systemName
            );
            System.assertEquals(1, claimed.owned.size(), systemName + ' should own its own claim');
        }
        System.assertEquals(3, [SELECT COUNT() FROM Processed_Event__c]);
    }

    @IsTest
    static void subscriberTriggerClaimsDeliveredEvent() {
        ContactSyncRetryQueueable.skipEnqueue = true;
        Contact record = new Contact(LastName = 'Delivered');
        insert record;
        record = [SELECT Id, FirstName, LastName, Email, Phone, AccountId, SystemModstamp FROM Contact WHERE Id = :record.Id];
        Contact_Sync__e event = ContactSyncEventMapper.fromContact(record, ContactSyncConstants.CHANGE_UPDATE);

        Test.startTest();
        EventBus.publish(event);
        Test.getEventBus().deliver();
        Test.stopTest();

        List<Processed_Event__c> processed = [
            SELECT Dedup_Key__c, Event_Uuid__c
            FROM Processed_Event__c
            WHERE Subscriber_Name__c = :ContactSyncConstants.APEX_SUBSCRIBER
        ];
        System.assertEquals(1, processed.size());
        System.assertEquals(event.EventUuid, processed[0].Event_Uuid__c);
    }

    @IsTest
    static void poisonPillGoesToDlq() {
        ContactSyncRetryQueueable.skipEnqueue = true;
        Contact record = new Contact(LastName = 'Poison');
        insert record;
        record = [SELECT Id, FirstName, LastName, Email, Phone, AccountId, SystemModstamp FROM Contact WHERE Id = :record.Id];
        Contact_Sync__e event = ContactSyncEventMapper.fromContact(record, ContactSyncConstants.CHANGE_UPDATE);

        ContactSyncDlqService.recordSubscribeFailures(
            new List<Contact_Sync__e>{ event },
            'Downstream timeout',
            'ERP'
        );

        List<Contact_Sync_DLQ__c> dlq = [
            SELECT Event_Uuid__c, Source__c, Subscriber_Name__c, Error_Message__c
            FROM Contact_Sync_DLQ__c
        ];
        System.assertEquals(1, dlq.size());
        System.assertEquals(ContactSyncConstants.SOURCE_SUBSCRIBE, dlq[0].Source__c);
        System.assertEquals('ERP', dlq[0].Subscriber_Name__c);
        System.assertEquals(event.EventUuid, dlq[0].Event_Uuid__c);
    }
}
