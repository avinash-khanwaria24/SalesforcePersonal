@IsTest
private class TriggerBypassServiceTest {
    @IsTest
    static void blankNameIsNotBypassed() {
        System.assertEquals(false, TriggerBypassService.isBypassed(null));
        System.assertEquals(false, TriggerBypassService.isBypassed(''));
        System.assertEquals(false, TriggerBypassService.isBypassed('   '));
    }

    @IsTest
    static void unknownTriggerIsNotBypassed() {
        TriggerBypassService.metadataOverride = new Map<String, Trigger_Bypass__mdt>();
        TriggerBypassService.settingOverride = new Automation_Switch__c(
            Bypass_All_Triggers__c = false
        );

        System.assertEquals(
            false,
            TriggerBypassService.isBypassed('DoesNotExist')
        );
    }

    @IsTest
    static void hierarchySettingBypassesEveryTrigger() {
        TriggerBypassService.metadataOverride = new Map<String, Trigger_Bypass__mdt>();
        TriggerBypassService.settingOverride = new Automation_Switch__c(
            Bypass_All_Triggers__c = true
        );

        System.assertEquals(
            true,
            TriggerBypassService.isBypassed('AccountTriggerBypassExample')
        );
        System.assertEquals(true, TriggerBypassService.isBypassed('AnyOtherTrigger'));
    }

    @IsTest
    static void customMetadataDisablesNamedTriggerOnly() {
        TriggerBypassService.settingOverride = new Automation_Switch__c(
            Bypass_All_Triggers__c = false
        );
        TriggerBypassService.metadataOverride = new Map<String, Trigger_Bypass__mdt>{
            'AccountTriggerBypassExample' => new Trigger_Bypass__mdt(
                DeveloperName = 'AccountTriggerBypassExample',
                Is_Disabled__c = true
            )
        };

        System.assertEquals(
            true,
            TriggerBypassService.isBypassed('AccountTriggerBypassExample')
        );
        System.assertEquals(false, TriggerBypassService.isBypassed('SomeOtherTrigger'));
    }

    @IsTest
    static void customMetadataEnabledRecordDoesNotBypass() {
        TriggerBypassService.settingOverride = new Automation_Switch__c(
            Bypass_All_Triggers__c = false
        );
        TriggerBypassService.metadataOverride = new Map<String, Trigger_Bypass__mdt>{
            'AccountTriggerBypassExample' => new Trigger_Bypass__mdt(
                DeveloperName = 'AccountTriggerBypassExample',
                Is_Disabled__c = false
            )
        };

        System.assertEquals(
            false,
            TriggerBypassService.isBypassed('AccountTriggerBypassExample')
        );
    }

    @IsTest
    static void exampleTriggerHonorsBypass() {
        TriggerBypassService.settingOverride = new Automation_Switch__c(
            Bypass_All_Triggers__c = true
        );

        Account record = new Account(Name = 'Bypass Probe');

        Test.startTest();
        insert record;
        Test.stopTest();

        Account stored = [
            SELECT Description
            FROM Account
            WHERE Id = :record.Id
        ];
        System.assertEquals(
            null,
            stored.Description,
            'Bypassed trigger must not stamp Description'
        );
    }

    @IsTest
    static void exampleTriggerRunsWhenNotBypassed() {
        TriggerBypassService.settingOverride = new Automation_Switch__c(
            Bypass_All_Triggers__c = false
        );
        TriggerBypassService.metadataOverride = new Map<String, Trigger_Bypass__mdt>();

        Account record = new Account(Name = 'Active Probe');

        Test.startTest();
        insert record;
        Test.stopTest();

        Account stored = [
            SELECT Description
            FROM Account
            WHERE Id = :record.Id
        ];
        System.assertEquals(
            'TriggerBypassService example ran',
            stored.Description
        );
    }
}
