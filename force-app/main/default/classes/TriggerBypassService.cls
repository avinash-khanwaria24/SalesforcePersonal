/**
 * Runtime switch for local Apex triggers.
 *
 * Evaluation order:
 * 1. Hierarchy custom setting Automation_Switch__c.Bypass_All_Triggers__c
 *    (user, then profile, then org) — intended for data loads.
 * 2. Custom metadata Trigger_Bypass__mdt whose DeveloperName matches triggerName.
 *
 * Packaged (namespaced) triggers cannot use this unless the package already
 * calls a similar API. This only wraps code you own.
 */
public with sharing class TriggerBypassService {
    @TestVisible
    private static Automation_Switch__c settingOverride;

    @TestVisible
    private static Map<String, Trigger_Bypass__mdt> metadataOverride;

    public static Boolean isBypassed(String triggerName) {
        if (String.isBlank(triggerName)) {
            return false;
        }

        Automation_Switch__c sw = settingOverride != null
            ? settingOverride
            : Automation_Switch__c.getInstance();
        if (sw != null && sw.Bypass_All_Triggers__c) {
            return true;
        }

        Map<String, Trigger_Bypass__mdt> byName = metadataOverride != null
            ? metadataOverride
            : Trigger_Bypass__mdt.getAll();
        Trigger_Bypass__mdt row = byName.get(triggerName);
        return row != null && row.Is_Disabled__c;
    }
}
