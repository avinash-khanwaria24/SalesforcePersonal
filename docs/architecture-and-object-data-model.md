# Architecture and Object Data Model

**Identity & User Lifecycle Management — Okta (IdP) + Salesforce (SP)**

This document is the architecture and canonical data model for the requirements in `identity-user-lifecycle-okta-salesforce.md`.

| Requirement | Architecture response | Data-model response |
| --- | --- | --- |
| Staff details mastered in Okta | Okta is the system of record; Salesforce is a downstream replica of identity | `Okta User` masters attributes; Salesforce `User` stores a projected copy |
| Single Sign-On | SAML 2.0, Salesforce as SP, Okta as IdP, My Domain | `SamlSsoConfig` + `User.FederationIdentifier` = SAML NameID |
| Automated provisioning from Okta groups | Okta group assignment to the Salesforce app triggers REST create/update | Group → Profile / Role / Permission Set Group mappings |
| Automated de-provisioning from group removal | Okta unassignment or user deactivate pushes `IsActive = false` | Salesforce `User` is deactivated, never deleted |
| Entitlements aligned to job | Thin profile + permission set groups | `Profile`, `PermissionSetGroup`, `PermissionSetAssignment`, `UserRole` |

No custom Salesforce objects are required for the core design. Identity, access, and lifecycle all use standard Salesforce identity objects plus Okta directory objects. Optional custom objects are listed only for audit mirroring.

---

## 1. Logical architecture

Four layers. Data ownership is strict: identity and group membership live only in Okta; Salesforce stores the projected user and the entitlement catalog.

```mermaid
flowchart TB
  subgraph ENTERPRISE["Enterprise identity"]
    HR["HR / IT joiner-mover-leaver"]
    OKTA_U["Okta User"]
    OKTA_G["Okta Groups"]
    OKTA_APP["Okta Salesforce App"]
    MFA["Okta MFA / AuthN policy"]
    HR --> OKTA_U
    OKTA_U --> OKTA_G
    OKTA_G --> OKTA_APP
    OKTA_U --> MFA
  end

  subgraph AUTH["Authentication plane — SAML 2.0"]
    SAML["SAML Assertion<br/>NameID = Federation ID<br/>AMR = session.amr"]
    MYD["Salesforce My Domain"]
    SSOCFG["SamlSsoConfig"]
  end

  subgraph LCM["Lifecycle plane — REST + OAuth 2.0"]
    ECA["External Client App"]
    REST["Salesforce User REST API"]
  end

  subgraph SF["Salesforce identity store"]
    USER["User"]
    PROF["Profile + UserLicense"]
    ROLE["UserRole"]
    PSG["PermissionSetGroup"]
    PS["PermissionSet"]
    PSA["PermissionSetAssignment"]
    UG["Group / GroupMember"]
  end

  MFA --> SAML
  OKTA_APP --> SAML
  SAML --> MYD
  MYD --> SSOCFG
  SSOCFG --> USER

  OKTA_APP --> ECA
  ECA --> REST
  REST --> USER
  REST --> PSA
  USER --> PROF
  USER --> ROLE
  USER --> PSA
  PSA --> PSG
  PSG --> PS
  USER --> UG
```

### 1.1 Control vs data vs session

| Plane | What it moves | Protocol | Source object | Target object |
| --- | --- | --- | --- | --- |
| Control | Who should have Salesforce | Okta group assignment | `Okta Group` | Okta app assignment |
| Data / lifecycle | Create, update, deactivate User | REST + OAuth 2.0 + PKCE | Okta user + group entitlements | `User`, `PermissionSetAssignment`, `GroupMember` |
| Session | Prove identity and start a Salesforce session | SAML 2.0 | Okta session + MFA | `AuthSession` matched via `User.FederationIdentifier` |
| Entitlement catalog | What a persona is allowed to do | Manual design, versioned in Salesforce | Architect-defined | `Profile`, `PermissionSet`, `PermissionSetGroup`, `UserRole` |

Salesforce does not invent staff identity. It only:

1. Holds a `User` row keyed by Federation ID.
2. Holds the entitlement catalog (profiles, permission set groups, roles).
3. Issues a session after a valid SAML assertion.

---

## 2. Physical / integration architecture

```mermaid
flowchart LR
  subgraph OKTA["Okta org"]
    DIR["Directory<br/>Users + Groups"]
    APP["Salesforce.com OIN app"]
    POL["App sign-on policy<br/>MFA required"]
    PROV["Provisioning engine"]
  end

  subgraph NET["Trust"]
    CERT["IdP signing certificate"]
    OAUTH["OAuth client<br/>Consumer Key/Secret + PKCE"]
  end

  subgraph SFORG["Salesforce org"]
    MD["My Domain"]
    SAML["SamlSsoConfig"]
    ECA["External Client App"]
    API["REST /services/data"]
    ID["Identity objects"]
  end

  DIR --> APP
  POL --> APP
  APP -- "SAML 2.0 POST<br/>ACS = Salesforce Login URL" --> MD
  CERT --> SAML
  MD --> SAML
  SAML --> ID

  APP --> PROV
  PROV -- "OAuth 2.0 auth code + PKCE" --> ECA
  ECA --> OAUTH
  PROV -- "User CRUD + assignments" --> API
  API --> ID
```

Separate Okta app instances (and therefore separate SAML configs and External Client Apps) exist for Production and each persistent sandbox.

### 2.1 Runtime flows

**SSO (staff login)**

```mermaid
sequenceDiagram
  actor Staff
  participant Browser
  participant SF as Salesforce My Domain
  participant Okta
  participant MFA as Okta MFA
  participant User as Salesforce User

  Staff->>Browser: Open https://company.my.salesforce.com
  Browser->>SF: SP-initiated SAML request
  SF->>Okta: Redirect to IdP SSO URL
  Staff->>Okta: Authenticate
  Okta->>MFA: Challenge
  MFA-->>Okta: Success
  Okta->>SF: SAML Response<br/>NameID = FederationIdentifier<br/>AMR = mfa / Okta_verify / ...
  SF->>User: Match FederationIdentifier
  alt User.IsActive = true
    SF-->>Staff: AuthSession created
  else User missing or IsActive = false
    SF-->>Staff: Login denied
  end
```

**Provision / de-provision (no login required)**

```mermaid
sequenceDiagram
  participant IAM as Okta group change
  participant Prov as Okta provisioning
  participant ECA as External Client App
  participant API as Salesforce REST
  participant User as User
  participant PSA as PermissionSetAssignment

  IAM->>Prov: Add / move / remove group membership
  Prov->>ECA: OAuth access token (refresh + PKCE)
  alt Joiner
    Prov->>API: POST User
    API->>User: Insert IsActive=true, FederationIdentifier, ProfileId, UserRoleId
    Prov->>API: Assign permission set groups
    API->>PSA: Insert assignments
  else Mover
    Prov->>API: PATCH User + replace assignments
    API->>User: Update Profile/Role/attributes
    API->>PSA: Add/remove assignments
  else Leaver
    Prov->>API: PATCH User IsActive=false
    API->>User: Deactivate — license released, login blocked
  end
```

---

## 3. Object data model — systems of record

Two bounded contexts. Correlation is a single key: **Okta User ID (or immutable employee number) = Salesforce `User.FederationIdentifier` = SAML NameID**.

```mermaid
flowchart TB
  subgraph OKTA_CTX["Okta — master"]
    OU["OktaUser"]
    OG["OktaGroup"]
    OM["OktaGroupMembership"]
    OA["OktaApplication"]
    OGA["OktaAppGroupAssignment"]
    OU --> OM
    OG --> OM
    OG --> OGA
    OA --> OGA
  end

  subgraph CORR["Correlation"]
    KEY["FederationIdentifier<br/>= Okta user id<br/>= SAML NameID"]
  end

  subgraph SF_CTX["Salesforce — replica + entitlement catalog"]
    U["User"]
    P["Profile"]
    UL["UserLicense"]
    R["UserRole"]
    PSG["PermissionSetGroup"]
    PS["PermissionSet"]
    PSC["PermissionSetGroupComponent"]
    PSA["PermissionSetAssignment"]
    GR["Group"]
    GM["GroupMember"]
    U --> P
    P --> UL
    U --> R
    U --> PSA
    PSA --> PS
    PSA --> PSG
    PSG --> PSC
    PSC --> PS
    U --> GM
    GR --> GM
  end

  OU --> KEY
  KEY --> U
  OGA -->|"maps Profile / Role / PSG names"| P
  OGA -->|"maps Profile / Role / PSG names"| R
  OGA -->|"maps Profile / Role / PSG names"| PSG
```

---

## 4. Okta directory model

These are Okta entities, not Salesforce objects. They are the masters.

```mermaid
erDiagram
  OKTA_USER ||--o{ OKTA_GROUP_MEMBERSHIP : "member of"
  OKTA_GROUP ||--o{ OKTA_GROUP_MEMBERSHIP : "contains"
  OKTA_GROUP ||--o{ OKTA_APP_GROUP_ASSIGNMENT : "assigned as"
  OKTA_APPLICATION ||--o{ OKTA_APP_GROUP_ASSIGNMENT : "grants Salesforce via"
  OKTA_APPLICATION ||--|| OKTA_SAML_CONFIG : "has"
  OKTA_APPLICATION ||--|| OKTA_PROVISIONING_CONFIG : "has"
  OKTA_USER ||--o{ OKTA_AUTH_SESSION : "authenticates"

  OKTA_USER {
    string id PK "immutable correlation key"
    string employeeNumber UK "optional alternate key"
    string login
    string email
    string firstName
    string lastName
    string status "ACTIVE STAGED DEPROVISIONED"
    string department
    string title
    string managerId FK
    string locale
    string timezone
  }

  OKTA_GROUP {
    string id PK
    string name UK "SF_ACCESS_INTERNAL SF_PERSONA_*"
    string description
    string type "OKTA_GROUP"
  }

  OKTA_GROUP_MEMBERSHIP {
    string id PK
    string userId FK
    string groupId FK
  }

  OKTA_APPLICATION {
    string id PK
    string label "Salesforce-Prod"
    string signOnMode "SAML_2_0"
  }

  OKTA_APP_GROUP_ASSIGNMENT {
    string id PK
    string applicationId FK
    string groupId FK
    string profileName "Salesforce Profile API name"
    string roleName "Salesforce Role label"
    string permissionSets "comma/combined PSG or PS names"
    string federationIdMapping "user.id"
  }

  OKTA_SAML_CONFIG {
    string audience "https://company.my.salesforce.com"
    string acsUrl "Salesforce Login URL"
    string nameId "user.id"
    string nameIdFormat "unspecified"
    string amrAttribute "session.amr"
    boolean useFedId "true"
  }

  OKTA_PROVISIONING_CONFIG {
    boolean createUsers "true"
    boolean updateUserAttributes "true"
    boolean deactivateUsers "true"
    boolean reactivateUsers "true"
    boolean syncPassword "false"
    string auth "OAuth2_PKCE"
  }
```

### 4.1 Group catalog as data

| `OktaGroup.name` | Cardinality vs user | Writes to Salesforce |
| --- | --- | --- |
| `SF_ACCESS_INTERNAL` | 0..1 (required for access) | App assignment present → User exists and is active |
| `SF_LIC_SALESFORCE` | 0..1 exclusive with Platform | `User.ProfileId` → Minimum Access - Salesforce |
| `SF_LIC_PLATFORM` | 0..1 exclusive with Salesforce | `User.ProfileId` → Minimum Access - Salesforce Platform |
| `SF_PERSONA_SALES_REP` | 0..1 persona (priority if multiple) | `User.UserRoleId` + PSG assignment `PSG_Sales_Rep` |
| `SF_PERSONA_SALES_MGR` | 0..1 | Role + `PSG_Sales_Manager` |
| `SF_PERSONA_SERVICE` | 0..1 | Role + `PSG_Service_Agent` |
| `SF_PERSONA_MARKETING` | 0..1 | `PSG_Marketing` |
| `SF_CAP_REPORT_EXPORT` | 0..1 additive | Extra `PermissionSetAssignment` for `PS_Report_Export` |
| `SF_BREAKGLASS_ADMIN` | 0..n named people | **No** staff SSO enforcement; not provisioned as SSO-only |

License groups are mutually exclusive. Persona groups should be mutually exclusive. Capability groups may stack.

---

## 5. Salesforce identity object model

Standard objects only. This is the org’s identity schema for staff.

```mermaid
erDiagram
  UserLicense ||--o{ Profile : "licenses"
  Profile ||--o{ User : "assigned to"
  UserRole ||--o{ UserRole : "parent of"
  UserRole ||--o{ User : "assigned to"
  User ||--o{ User : "manager of"
  User ||--o{ PermissionSetAssignment : "has"
  User ||--o{ GroupMember : "member of"
  User ||--o{ UserLogin : "freeze state"
  User ||--o{ AuthSession : "open sessions"
  User ||--o{ LoginHistory : "login attempts"

  PermissionSet ||--o{ PermissionSetAssignment : "granted by"
  PermissionSetGroup ||--o{ PermissionSetAssignment : "granted by"
  PermissionSetGroup ||--o{ PermissionSetGroupComponent : "contains"
  PermissionSet ||--o{ PermissionSetGroupComponent : "included in"
  PermissionSetLicense ||--o{ PermissionSetLicenseAssign : "consumed by"
  User ||--o{ PermissionSetLicenseAssign : "holds"

  Group ||--o{ GroupMember : "has"
  Group ||--o{ Group : "role/queue hierarchy"

  SamlSsoConfig ||--o{ AuthSession : "authenticates via"
  ExternalClientApplication ||--o{ OauthToken : "issues"
  User ||--o{ OauthToken : "integration user only"

  User {
    id Id PK
    string Username UK "globally unique"
    string Email
    string FirstName
    string LastName
    string Alias
    string FederationIdentifier UK "Okta user id"
    id ProfileId FK
    id UserRoleId FK
    id ManagerId FK
    boolean IsActive "false = deprovisioned"
    string UserType "Standard"
    string EmailEncodingKey
    string LanguageLocaleKey
    string LocaleSidKey
    string TimeZoneSidKey
    string Department
    string Title
    string EmployeeNumber
    string CompanyName
  }

  Profile {
    id Id PK
    string Name "Minimum Access - Salesforce"
    id UserLicenseId FK
    boolean PermissionsApiEnabled
  }

  UserLicense {
    id Id PK
    string Name "Salesforce / Salesforce Platform"
    int TotalLicenses
    int UsedLicenses
  }

  UserRole {
    id Id PK
    string Name
    id ParentRoleId FK
    string DeveloperName
  }

  PermissionSet {
    id Id PK
    string Name "PS_SSO_Enforced PS_Report_Export"
    string Label
    string Type "Regular / Group / Session"
    id ProfileId "null for true permission sets"
  }

  PermissionSetGroup {
    id Id PK
    string DeveloperName "PSG_Sales_Rep"
    string MasterLabel
    string Status "Updated"
  }

  PermissionSetGroupComponent {
    id Id PK
    id PermissionSetGroupId FK
    id PermissionSetId FK
  }

  PermissionSetAssignment {
    id Id PK
    id AssigneeId FK "User"
    id PermissionSetId FK
    id PermissionSetGroupId FK
  }

  Group {
    id Id PK
    string Name
    string Type "Regular / Role / Queue / Organization"
    id RelatedId "Role or Queue"
  }

  GroupMember {
    id Id PK
    id GroupId FK
    id UserOrGroupId FK
  }

  UserLogin {
    id Id PK
    id UserId FK
    boolean IsFrozen
  }

  SamlSsoConfig {
    id Id PK
    string DeveloperName "Okta_SSO"
    string Issuer
    string EntityId "https://company.my.salesforce.com"
    string IdentityType "FederationId"
    string IdentityLocation "SubjectNameId"
    boolean IsJitEnabled "false"
  }

  ExternalClientApplication {
    id Id PK
    string Name "Okta Provisioning"
    string ConsumerKey
    string CallbackUrl
  }
```

### 5.1 Object responsibility

| Salesforce object | Requirement it serves | Mastered in | Notes |
| --- | --- | --- | --- |
| `User` | Staff record in Salesforce | Okta (attributes and active flag) | Projection only |
| `User.FederationIdentifier` | SSO match + correlation | Okta user id | Must equal SAML NameID |
| `User.IsActive` | De-provisioning | Okta assignment + status | `false` = leaver; never delete |
| `Profile` | License + login defaults | Salesforce catalog | Thin; one per user |
| `UserLicense` | Commercial license consumption | Salesforce | Released when `IsActive = false` |
| `UserRole` | Sharing hierarchy | Salesforce catalog; assignment from Okta | One per user |
| `PermissionSetGroup` | Persona bundle | Salesforce catalog | One primary PSG per persona |
| `PermissionSet` | Atomic capability | Salesforce catalog | SSO enforce, export, etc. |
| `PermissionSetGroupComponent` | PSG membership | Salesforce | Design-time |
| `PermissionSetAssignment` | Runtime grant | Okta group assignment | Combined across groups |
| `PermissionSetLicense` / `PermissionSetLicenseAssign` | Add-on licenses | Salesforce / Okta if mapped | Remove on leaver |
| `Group` / `GroupMember` | Public groups / queues | Optional Okta mapping | Combine across groups |
| `SamlSsoConfig` | SSO | Salesforce + Okta cert | JIT off |
| `Domain` / My Domain | SP-initiated SSO | Salesforce | Entity ID |
| `ExternalClientApplication` | Provisioning trust | Salesforce | Dedicated provisioning user |
| `OauthToken` | Provisioning API session | Salesforce | Belongs to integration user |
| `UserLogin` | Freeze when deactivate is blocked | Salesforce ops | Temporary |
| `AuthSession` | Live SSO session | Salesforce | Ends on deactivate |
| `LoginHistory` | Audit of SSO vs local | Salesforce | Break-glass monitoring |
| `UserAccessPolicy` | Optional Salesforce-side safety net | Salesforce | Complement, not SoT |

### 5.2 Cardinality rules (enforced by platform + mapping)

| Relationship | Cardinality | Enforced by |
| --- | --- | --- |
| User → Profile | N : 1, required | Salesforce |
| Profile → UserLicense | N : 1, required | Salesforce |
| User → UserRole | N : 0..1 | Salesforce |
| User → PermissionSetAssignment | 1 : 0..N | Salesforce |
| PermissionSetGroup → PermissionSet | 1 : 1..N via Component | Salesforce |
| User → FederationIdentifier | 1 : 1 unique | Salesforce unique field + Okta mapping |
| Okta User → Salesforce User | 1 : 0..1 | Provisioning match on Federation ID / username |
| Okta Group (license) → Profile | N : 1 | Okta assignment attribute, group priority |
| Okta Group (persona) → PSG | N : 1 | Okta assignment, combine values for extras |
| Staff User → Salesforce password login | 1 : 0 | `Is Single Sign-On Enabled` on `PS_SSO_Enforced` |

---

## 6. Canonical attribute map (field-level data contract)

Master column is the only writer. Salesforce values for staff must not be edited in Setup except break-glass and integration users.

| Salesforce field / related record | Datatype | Okta source | Master | Create | Update | Deactivate |
| --- | --- | --- | --- | --- | --- | --- |
| `User.FederationIdentifier` | Text(512), unique | `user.id` | Okta | Set once | Never | Keep |
| `User.Username` | Email, globally unique | `email` or `email + ".sfdc"` | Okta | Set | Rare | Keep |
| `User.Email` | Email | `email` | Okta | Set | Yes | Keep |
| `User.FirstName` | Text | `firstName` | Okta | Set | Yes | Keep |
| `User.LastName` | Text | `lastName` | Okta | Set | Yes | Keep |
| `User.Alias` | Text(8) | derived from name | Okta | Set | Yes | Keep |
| `User.EmployeeNumber` | Text | `employeeNumber` | Okta | Set | Yes | Keep |
| `User.Department` | Text | `department` | Okta | Set | Yes | Keep |
| `User.Title` | Text | `title` | Okta | Set | Yes | Keep |
| `User.ManagerId` | Lookup(User) | manager’s Federation ID | Okta | Set if manager exists | Yes | Keep |
| `User.ProfileId` | Lookup(Profile) | license group | Okta | Set | Yes (priority) | Keep |
| `User.UserRoleId` | Lookup(UserRole) | persona group | Okta | Set | Yes (priority) | Keep |
| `User.LocaleSidKey` | Picklist | locale / default `en_US` | Okta | Set | Yes | Keep |
| `User.LanguageLocaleKey` | Picklist | locale / default `en_US` | Okta | Set | Yes | Keep |
| `User.TimeZoneSidKey` | Picklist | timezone / default | Okta | Set | Yes | Keep |
| `User.EmailEncodingKey` | Picklist | default `UTF-8` | Okta | Set | Yes | Keep |
| `User.IsActive` | Checkbox | status + app assignment | Okta | `true` | `true/false` | `false` |
| `PermissionSetAssignment` (PSG) | Junction | persona groups | Okta | Insert | Replace set | Remove or leave; user inactive |
| `PermissionSetAssignment` (`PS_SSO_Enforced`) | Junction | all staff personas | Okta or User Access Policy | Insert | Keep | Inactive user |
| `PermissionSetAssignment` (`PS_Report_Export`) | Junction | capability group | Okta combine | Insert | Add/remove | Inactive user |
| `GroupMember` | Junction | public-group mapping | Okta combine | Insert | Add/remove | Inactive user |
| `UserLogin.IsFrozen` | Checkbox | ops exception | Salesforce | — | Manual if deactivate blocked | Unfreeze after deactivate |

### 6.1 Records that are not staff-mastered in Okta

| Record | Owner | Why excluded from the staff connector |
| --- | --- | --- |
| Integration `User` (API Only) | Salesforce platform team | Unique user per integration |
| Default Workflow / Case owner users | Salesforce admins | Deactivation blockers |
| Break-glass admin `User` | Security | Local password + Salesforce MFA |
| `Profile`, `PermissionSet`, `PermissionSetGroup`, `UserRole` definitions | Salesforce Architect | Entitlement catalog, not identity |
| `SamlSsoConfig`, `ExternalClientApplication` | IAM + Salesforce Admin | Trust configuration |

---

## 7. Entitlement catalog model (Salesforce-designed, Okta-assigned)

Persona access is a designed catalog in Salesforce. Okta only stores **names** of those catalog rows on group assignments.

```mermaid
flowchart TB
  subgraph CATALOG["Salesforce catalog — design time"]
    P1["Profile: Minimum Access - Salesforce"]
    P2["Profile: Minimum Access - Salesforce Platform"]
    SSO["PS_SSO_Enforced<br/>Is Single Sign-On Enabled"]
    EXP["PS_Report_Export"]
    PS_SALES["PS_Sales_Core / PS_Accounts / ..."]
    PSG_R["PSG_Sales_Rep"]
    PSG_M["PSG_Sales_Manager"]
    PSG_SVC["PSG_Service_Agent"]
    PSG_MKT["PSG_Marketing"]
    R1["Role: Sales Rep"]
    R2["Role: Sales Manager"]
    R3["Role: Support Agent"]
    PSG_R --> PS_SALES
    PSG_R --> SSO
    PSG_M --> SSO
    PSG_SVC --> SSO
    PSG_MKT --> SSO
  end

  subgraph ASSIGN["Runtime — one staff user"]
    U["User<br/>FederationIdentifier = 00u..."]
    U --> P1
    U --> R1
    U --> PSG_R
    U --> EXP
  end
```

### 7.1 Instance example

Okta user `00u1abc` is in groups `SF_ACCESS_INTERNAL`, `SF_LIC_SALESFORCE`, `SF_PERSONA_SALES_REP`, `SF_CAP_REPORT_EXPORT`.

| Salesforce row | Value |
| --- | --- |
| `User.Id` | `005...` |
| `User.FederationIdentifier` | `00u1abc` |
| `User.Username` | `alex.reese@company.com` |
| `User.IsActive` | `true` |
| `User.ProfileId` | Minimum Access - Salesforce |
| `User.UserRoleId` | Sales Rep |
| `PermissionSetAssignment` | `PSG_Sales_Rep` (includes `PS_SSO_Enforced`) |
| `PermissionSetAssignment` | `PS_Report_Export` |

If the same user is later removed from all Salesforce groups:

| Salesforce row | Value |
| --- | --- |
| Same `User.Id` / `FederationIdentifier` | Unchanged (row retained) |
| `User.IsActive` | `false` |
| User license | Released |
| SSO | Denied (inactive + no Okta assignment) |

---

## 8. Trust and session objects

These objects complete SSO and provisioning but are not staff identity.

```mermaid
erDiagram
  Domain ||--|| SamlSsoConfig : "EntityId uses My Domain"
  SamlSsoConfig ||--o{ AuthSession : "SSO login"
  User ||--o{ AuthSession : "owns"
  User ||--o{ LoginHistory : "audited by"
  ExternalClientApplication ||--o{ OauthToken : "refresh token"
  ProvisioningUser["User okta.provisioning"] ||--o{ OauthToken : "authorized"
  ProvisioningUser ||--o{ User : "API creates/updates"

  Domain {
    string Domain "company.my.salesforce.com"
    boolean LoginFormVisible "false after go-live"
    boolean OktaAuthService "true"
  }

  AuthSession {
    id Id PK
    id UsersId FK
    string SessionType "Oauth2 / UI"
    string LoginType "SAML S"
    datetime CreatedDate
  }

  LoginHistory {
    id Id PK
    id UserId FK
    string Status "Success / Failed"
    string LoginType "SAML S / Application"
    string SsoType
    string TlsProtocol
  }

  OauthToken {
    id Id PK
    id AppId FK
    id UserId FK
    datetime LastUsedDate
  }
```

---

## 9. Optional custom objects (not required)

Use only if Compliance needs a Salesforce-visible mapping or provisioning audit that is not satisfied by Okta System Log + Setup Audit Trail.

| Custom object | Purpose | Master |
| --- | --- | --- |
| `Identity_Group_Map__c` | Documents Okta group → Profile / PSG / Role | Architect (reference data) |
| `Identity_Provisioning_Event__c` | Stores failed/success pushes if middleware is added | Integration |

Recommended: **do not create them** for the baseline. They become a second mapping source and drift from Okta.

If `Identity_Group_Map__c` is added:

| Field | Type | Example |
| --- | --- | --- |
| `Okta_Group_Name__c` | Text(80), unique | `SF_PERSONA_SALES_REP` |
| `Salesforce_Profile_Name__c` | Text | `Minimum Access - Salesforce` |
| `Permission_Set_Group__c` | Text | `PSG_Sales_Rep` |
| `User_Role_Name__c` | Text | `Sales Rep` |
| `Is_License_Group__c` | Checkbox | false |
| `Is_Additive__c` | Checkbox | false |

This table is documentation in the org, not a provisioning engine.

---

## 10. Data-ownership matrix

| Data class | Create | Read | Update | Deactivate/Delete |
| --- | --- | --- | --- | --- |
| Legal identity (name, email, employee id) | Okta | Both | Okta | Okta |
| Salesforce access flag | Okta groups | Both | Okta groups | Okta groups |
| Federation ID | Okta, written once | Both | None | Never delete |
| Persona entitlements | Salesforce catalog + Okta assignment | Both | Okta assignment | Okta assignment |
| Sharing role tree | Salesforce | Both | Salesforce structure / Okta assignment | Salesforce |
| Passwords / MFA for staff | Okta | Okta | Okta | Okta |
| Break-glass password / MFA | Salesforce | Salesforce | Salesforce | Salesforce |
| SAML certificate | Okta issues, Salesforce stores | Both | IAM rotation | IAM |
| OAuth client for provisioning | Salesforce issues, Okta stores | Both | IAM rotation | IAM |
| Login audit | Salesforce `LoginHistory`, Okta System Log | Security | Append-only | Retention policy |

---

## 11. What the model explicitly excludes

| Object / pattern | Reason |
| --- | --- |
| SAML JIT-created `User` | No deactivation path; conflicts with REST mastering |
| Custom `Staff__c` identity object | Duplicates `User`; Salesforce login requires `User` |
| Fat profiles as persona store | Violates Well-Architected; one profile per license only |
| Deleting `User` | Not supported; audit and ownership require the row |
| One Okta app for prod + sandbox | Different My Domain, usernames, OAuth clients |
| Experience Cloud / `NetworkMember` | Different identity domain (customers/partners) |

---

## 12. Architecture outcomes (brief)

- Two systems, one correlation key: Okta user id = `User.FederationIdentifier` = SAML NameID.
- Two planes: SAML for session, REST/OAuth for lifecycle. They share the `User` row and must not both master it.
- Okta objects (`User`, `Group`, `AppGroupAssignment`) are the source of truth for who exists and who has Salesforce.
- Salesforce objects (`User`, `Profile`, `UserLicense`, `UserRole`, `PermissionSet`, `PermissionSetGroup`, `PermissionSetAssignment`, `GroupMember`) are the entitlement and session store.
- Trust objects (`SamlSsoConfig`, `Domain`, `ExternalClientApplication`, `OauthToken`) enable SSO and provisioning; they are not staff records.
- Group assignment is the only create/deactivate trigger; `User.IsActive` is the de-provision flag.
- No custom Salesforce objects are required for the requirement set.
- Catalog (what a persona can do) is designed in Salesforce; assignment (who gets it) is designed in Okta.
