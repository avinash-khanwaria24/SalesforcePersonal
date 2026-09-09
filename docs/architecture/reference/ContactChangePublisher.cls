/**
 * Contact after-save publisher. Writes an outbox row in the SAME transaction
 * as the Contact DML. Does not call EventBus.publish here — queuing on the bus
 * is not a commit-durable guarantee.
 *
 * Skip when:
 *  - running user is the integration user applying inbound events
 *  - payload hash matches Last_Sync_Hash__c
 *  - static recursion flag is set
 */
public with sharing class ContactChangePublisher {
    public static Boolean suppressOutbound = false;

    public static void enqueue(List<Contact> news, Map<Id, Contact> olds, Boolean isDelete) {
        if (suppressOutbound || ContactChangePublisher.isIntegrationUser()) {
            return;
        }

        List<Contact_Outbox__c> rows = new List<Contact_Outbox__c>();
        for (Contact record : news) {
            Contact prior = olds == null ? null : olds.get(record.Id);
            if (!isDelete && !ContactChangePublisher.mappedFieldsChanged(record, prior)) {
                continue;
            }
            String hash = ContactChangePublisher.hashOf(record);
            if (!isDelete && hash == record.Last_Sync_Hash__c) {
                continue;
            }
            Contact_Outbox__c outbox = new Contact_Outbox__c();
            outbox.Message_Id__c = EncodingUtil.convertToHex(Crypto.generateAesKey(128));
            outbox.Contact_Key__c = String.valueOf(record.Id);
            outbox.Salesforce_Contact_Id__c = record.Id;
            outbox.Operation__c = isDelete ? 'DELETE' : (prior == null ? 'CREATE' : 'UPDATE');
            outbox.Payload_Hash__c = hash;
            outbox.Payload_Json__c = ContactChangePublisher.toJson(record);
            outbox.Status__c = 'Pending';
            outbox.Attempt__c = 0;
            outbox.Next_Attempt_At__c = System.now();
            rows.add(outbox);
        }
        if (!rows.isEmpty()) {
            insert rows;
            if (!Test.isRunningTest() && !System.isQueueable() && !System.isFuture() && !System.isBatch()) {
                System.enqueueJob(new OutboxPublishQueueable());
            }
        }
    }

    private static Boolean isIntegrationUser() {
        return UserInfo.getUserName() != null
            && UserInfo.getUserName().startsWith('svc-contact-sync');
    }

    private static Boolean mappedFieldsChanged(Contact record, Contact prior) {
        if (prior == null) {
            return true;
        }
        return record.FirstName != prior.FirstName
            || record.LastName != prior.LastName
            || record.Email != prior.Email
            || record.Phone != prior.Phone
            || record.MailingPostalCode != prior.MailingPostalCode;
    }

    private static String hashOf(Contact record) {
        return EncodingUtil.convertToHex(
            Crypto.generateDigest('SHA-256', Blob.valueOf(ContactChangePublisher.toJson(record)))
        );
    }

    private static String toJson(Contact record) {
        Map<String, Object> body = new Map<String, Object>{
            'firstName' => record.FirstName,
            'lastName' => record.LastName,
            'email' => record.Email == null ? null : record.Email.toLowerCase().trim(),
            'phone' => record.Phone,
            'mailingPostalCode' => record.MailingPostalCode
        };
        return JSON.serialize(body);
    }
}
