# Identity & User Lifecycle Management

**Salesforce as Service Provider · Okta as Enterprise Identity Provider**

| Item | Value |
| --- | --- |
| Audience | Salesforce Architect, Identity Engineering, Security, Salesforce Admins |
| Scope | Internal staff (employees and contractors managed in Okta) |
| Salesforce role | Service Provider (SP) and entitlement store |
| Okta role | Identity Provider (IdP), source of truth for identity and group membership |
| Standards | SAML 2.0 (authentication), OAuth 2.0 + REST (lifecycle provisioning) |

Architecture diagrams, ERDs, and the field-level object model: [`architecture-and-object-data-model.md`](architecture-and-object-data-model.md).

---

## 1. Requirement interpretation

Internal staff records are mastered in Okta. Salesforce must not become a parallel identity directory.

The solution must deliver:

1. **Single Sign-On** so staff authenticate once in Okta and reach Salesforce without a Salesforce password.
2. **Automated provisioning** so assignment to the correct Okta directory group creates (or reactivates) the Salesforce user with the right license, profile, role, and entitlements.
3. **Automated de-provisioning** so removal from those groups, or Okta deactivation, immediately removes Salesforce login capability and releases licenses.
4. **Ongoing attribute and access sync** so job changes in Okta update Salesforce without manual Setup work.

Just-in-Time (JIT) SAML user creation is **not** sufficient. JIT cannot deactivate users when they leave a group, and combining JIT with API provisioning causes profile-mastering conflicts.

---

## 2. Architecture decisions (Salesforce-recommended)

| Decision | Choice | Why |
| --- | --- | --- |
| Identity source of truth | Okta | Requirement states staff details are managed in Okta. |
| Authentication protocol | SAML 2.0 | Salesforce-recommended enterprise SSO; Okta Salesforce OIN app is SAML-based. |
| User match key | `FederationIdentifier` | Stable IdP key. Username and email change; Federation ID should not. |
| Lifecycle protocol | Okta Salesforce.com OIN app via Salesforce REST API + OAuth 2.0 + PKCE | Official Okta integration. Supports create, update, deactivate, reactivate. Preferred over SOAP and over a custom SCIM app. |
| JIT provisioning | Disabled | Cannot deprovision; conflicts with API provisioning. |
| Salesforce Identity Connect | Do not use | Phased retirement / retired. |
| Connected App vs External Client App | External Client App | Salesforce is restricting new Connected Apps. Okta documents External Client Apps for provisioning OAuth. |
| Authorization model | Thin profile + Permission Set Groups | Salesforce Well-Architected: minimize profiles; grant capabilities via permission sets / permission set groups. |
| MFA | Okta MFA, signaled to Salesforce in the SAML assertion | Salesforce requires MFA on SSO logins. IdP MFA counts only when Salesforce receives recognized AMR / AuthnContext values. |
| Local Salesforce passwords | Disabled for staff; retained for named break-glass admins | Prevents bypass of Okta SSO and Okta MFA. Well-Architected requires some admins to retain direct login. |
| Deprovision action | Deactivate (`IsActive = false`), never delete | Salesforce does not delete users. Deactivation stops login and frees the user license. |

### 2.1 Target pattern

```
HR / IT joiner-mover-leaver
        |
        v
   Okta directory (source of truth)
        |  group membership
        +---------------------------+
        |                           |
        v                           v
 SAML 2.0 SSO                  REST provisioning
 (authentication)              (create / update / deactivate)
        |                           |
        +------------+--------------+
                     v
              Salesforce org
         User + Profile + Role
         Permission Set Groups
         Federation Identifier
```

---

## 3. Identity and access model

### 3.1 Personas and Salesforce objects

| Layer | Object | Purpose | Owner |
| --- | --- | --- | --- |
| Identity | Okta user | Legal identity, MFA, status | IAM |
| Access trigger | Okta group | Who gets Salesforce, and which persona | IAM + Salesforce Architect |
| Authentication | SAML IdP / SP | Login session | IAM + Salesforce Admin |
| Baseline access | Salesforce Profile | User license, login hours/IP, defaults | Salesforce Architect |
| Job access | Permission Set Group | Persona capabilities | Salesforce Architect |
| Extra access | Permission Set | Additive capabilities (export, integration ops) | Salesforce Architect |
| Data visibility | Role | Sharing hierarchy | Salesforce Architect |
| Collaboration | Public Group / Queue | Optional, group-driven | Salesforce Architect |

### 3.2 Recommended Okta group catalog

Name groups so Salesforce assignment is obvious and auditable.

| Okta group | Effect in Salesforce | Typical members |
| --- | --- | --- |
| `SF_ACCESS_INTERNAL` | Assigns the Salesforce app (creates/keeps the user active) | All staff who should have Salesforce |
| `SF_LIC_SALESFORCE` | Profile: `Minimum Access - Salesforce` (Salesforce license) | Full CRM users |
| `SF_LIC_PLATFORM` | Profile: `Minimum Access - Salesforce Platform` | Platform-only users |
| `SF_PERSONA_SALES_REP` | Permission Set Group `PSG_Sales_Rep` + Role `Sales Rep` | Account Executives |
| `SF_PERSONA_SALES_MGR` | Permission Set Group `PSG_Sales_Manager` + Role `Sales Manager` | Sales Managers |
| `SF_PERSONA_SERVICE` | Permission Set Group `PSG_Service_Agent` + Role `Support Agent` | Service agents |
| `SF_PERSONA_MARKETING` | Permission Set Group `PSG_Marketing` | Marketing users |
| `SF_CAP_REPORT_EXPORT` | Extra permission set `PS_Report_Export` | Users allowed to export |
| `SF_BREAKGLASS_ADMIN` | **Not** SSO-enforced; local login + Salesforce MFA | 2–4 named platform admins |

A user receives Salesforce only by group assignment. Individual Okta app assignments should be forbidden by IAM policy.

### 3.3 Attribute contract (Okta → Salesforce)

| Salesforce field | Source | Notes |
| --- | --- | --- |
| `Username` | `{email}` or `{email}.sfdc` | Must be unique across **all** Salesforce orgs worldwide. |
| `Email` | Okta email | Corporate mailbox. |
| `FirstName` / `LastName` | Okta | Required. |
| `Alias` | Derived (first 8 chars) | Required; keep deterministic. |
| `FederationIdentifier` | Okta user `id` or immutable employee number | SAML NameID must equal this value. |
| `Profile` | From license group | Determines user license. Use group priority (one profile only). |
| `UserRole` | From persona group | Use group priority (one role only). |
| `PermissionSets` / Permission Set Groups | From persona + capability groups | Use **Combine values across groups**. |
| `LocaleSidKey`, `LanguageLocaleKey`, `TimeZoneSidKey`, `EmailEncodingKey` | Defaults or Okta locale | REST create fails if required locale fields are empty. |
| `IsActive` | Okta user status + app assignment | Deactivation sets this to `false`. |
| `Department`, `Title`, `EmployeeNumber`, `ManagerId` | Okta | Optional but useful for sharing and User Access Policies. |

Add `FederationIdentifier`, locale, timezone, and email encoding in Okta Profile Editor if they are missing from the Salesforce app schema.

### 3.4 What must stay out of Okta provisioning

- Integration / API-only users (unique user per integration, API Only permission).
- Automated process users (Default Workflow User, Case assignment user, and similar).
- Partner or Experience Cloud users (separate identity design).
- Break-glass Salesforce admins (local credentials + Salesforce MFA).

---

## 4. Detailed implementation steps

Execute in this order. Do not enforce SSO or disable the Salesforce login form until SSO and provisioning are proven.

### Phase A — Salesforce foundation

#### A1. Enable My Domain

1. Setup → Company Settings → My Domain.
2. Deploy a corporate domain, for example `https://company.my.salesforce.com`.
3. Use this domain as the SAML Entity ID (Salesforce recommendation when My Domain is live).
4. Do **not** yet enable *Prevent login from https://login.salesforce.com*. Break-glass admins need that path.

#### A2. Design thin profiles and permission set groups

1. Clone or use `Minimum Access - Salesforce` (and Platform equivalent) as the only staff profiles.
2. Keep on the profile only: user license, default record type/page layout if still required, login IP ranges / hours if used.
3. Move object, field, app, and system permissions into permission sets.
4. Bundle permission sets into one Permission Set Group per persona (`PSG_Sales_Rep`, and so on).
5. Create a permission set `PS_SSO_Enforced` containing **Is Single Sign-On Enabled**. Assign it to all staff personas. Do **not** assign it to break-glass admins.

This follows Salesforce Well-Architected: minimize profiles; control metadata access with permission sets and permission set groups.

#### A3. Create the Okta provisioning integration user

1. Create a dedicated Salesforce user, for example `okta.provisioning@company.com`.
2. Do not use a shared human admin.
3. Create a custom profile (permissions must be on the **profile**, not a permission set):
   - API Enabled
   - Manage Users (this also enables Assign Permission Sets, Manage Internal Users, Manage Profiles and Permission Sets, Manage Roles, View All Users, and related user-admin permissions)
4. Assign no SSO-enforcement permission to this user.
5. Protect the account with Salesforce MFA and IP restrictions.

#### A4. Create an External Client App for Okta provisioning

Salesforce is restricting new Connected Apps. Okta recommends an External Client App.

1. Setup → App Manager → New External Client App (or migrate an existing Connected App).
2. Enable OAuth.
3. Callback URL: `https://{yourOktaDomain}/admin/app/generic/oauth20redirect`
4. OAuth scopes:
   - Manage user data via APIs (`api`)
   - Perform requests at any time (`refresh_token`, `offline_access`)
5. Security:
   - Require secret for Web Server Flow
   - Require secret for Refresh Token Flow
   - Require PKCE
   - Enable Refresh Token Rotation
6. Policies:
   - Permitted Users: Admin-approved users are pre-authorized (preferred) or All users can self-authorize during first setup
   - Refresh Token Policy: Refresh token is valid until revoked
   - Pre-authorize only the Okta provisioning user
7. Copy Consumer Key and Consumer Secret.
8. Wait up to 10 minutes for Salesforce to replicate the app before authenticating from Okta.

#### A5. Prepare SAML SSO settings (placeholder, complete in B2)

1. Setup → Identity → Single Sign-On Settings.
2. Enable SAML.
3. Leave JIT / User Provisioning **unchecked**.

---

### Phase B — Okta application and SSO

#### B1. Add the Salesforce.com OIN application

1. Okta Admin → Applications → Browse App Catalog → **Salesforce.com**.
2. Use the Federated ID variant / enable Federation ID for SAML.
3. Create **separate app instances** for Production and each persistent sandbox. Do not share one app across orgs.

#### B2. Configure SAML 2.0 (Salesforce as SP, Okta as IdP)

In Salesforce (Setup → Single Sign-On Settings → New):

| Field | Value |
| --- | --- |
| Name / API Name | `Okta_SSO` |
| Identity Provider Certificate | Okta IdP signing certificate |
| SAML Identity Type | **Assertion contains the Federation ID from the User object** |
| SAML Identity Location | Identity is in the NameIdentifier element of the Subject |
| Identity Provider Login URL | Okta SSO URL from the app Sign On instructions |
| Entity ID | `https://company.my.salesforce.com` |
| Service Provider Initiated Request Binding | HTTP POST |
| Custom Logout URL | Okta logout / Salesforce My Domain logout, as required |
| User Provisioning Enabled (JIT) | **Off** |

In Okta Sign On:

1. Sign-on method: SAML 2.0.
2. Enable **Use Fed ID for SAML**.
3. NameID = the same immutable value mapped to `FederationIdentifier`.
4. Audience / Entity ID = My Domain URL.
5. ACS / Login URL = Salesforce Login URL shown after the SAML config is saved.
6. Custom Salesforce domain = My Domain name.

This enables:

- **IdP-initiated SSO** from the Okta dashboard.
- **SP-initiated SSO** when the user opens My Domain.

#### B3. Signal MFA to Salesforce (mandatory)

Salesforce requires MFA for SSO logins. Completing MFA in Okta is not enough unless Salesforce can see it.

1. Enforce MFA (preferably phishing-resistant) on the Okta app sign-on policy for Salesforce.
2. Add a custom SAML attribute:
   - Name: `AMR`
   - Name format: Unspecified
   - Value: `session.amr`
3. Confirm Salesforce receives a recognized value such as `mfa`, `Okta_verify`, `swk`, `hwk`, `face`, or `fpt`, or a recognized AuthnContext (`MobileTwoFactorContract`, `Mfa`, `multipleauthn`).
4. In Salesforce Session Settings, keep the SSO method at Standard and Multi-Factor Authentication at High Assurance unless you intentionally use Salesforce-side MFA instead.
5. Do **not** enable “Use Salesforce MFA for this SSO Provider” if Okta is the MFA service. Enable it only if Salesforce itself must prompt for a second factor.

This avoids a double prompt (Okta MFA, then Salesforce device-activation email) on new devices.

#### B4. My Domain authentication configuration

1. Setup → My Domain → Authentication Configuration → Edit.
2. Select `Okta_SSO`.
3. Keep **Login Form** enabled during testing.
4. After go-live, hide Login Form for staff (Okta becomes the default). Keep `login.salesforce.com` available for break-glass admins.

---

### Phase C — Automated provisioning and de-provisioning

#### C1. Connect Okta provisioning (OAuth / REST)

1. Okta app → Provisioning → Configure API Integration → Enable API integration.
2. Enter Consumer Key and Secret.
3. Enable **PKCE**.
4. Authenticate with Salesforce as the provisioning user and Allow access.
5. Test API credentials.

Do not use legacy SOAP username/password provisioning for a new design.

#### C2. Enable lifecycle actions (To App)

Enable:

- **Create Users**
- **Update User Attributes**
- **Deactivate Users**
- **Reactivate Users** (if listed)

Disable:

- Sync Password (SSO users should not receive Salesforce passwords)
- Profile mastering of Okta from Salesforce (Salesforce is downstream)

#### C3. Attribute mappings

Map the contract in section 3.3.

Critical mapping rules:

| Attribute | Okta mapping rule |
| --- | --- |
| Profile | Group priority (user can have only one Salesforce profile/license) |
| Role | Group priority |
| Permission Sets | **Combine values across groups** |
| Public Groups | **Combine values across groups** |
| Federation ID | Immutable Okta identifier |
| Username | Stable unique value; do not change casually |

If a user is in several persona groups, combined permission sets are correct; colliding profiles are not. Keep license groups mutually exclusive.

#### C4. Assign the Salesforce app to Okta groups (the control plane)

1. Okta app → Assignments → Assign to Groups (not people).
2. For `SF_ACCESS_INTERNAL` + license group, set the baseline Profile.
3. For each persona group, set Role and Permission Set Group / Permission Sets.
4. For capability groups, set only the extra permission set.

**Provisioning behavior (this is the mandatory lifecycle):**

| Okta event | Salesforce result |
| --- | --- |
| User added to an assigned group | User created if new; `IsActive = true`; profile/role/permissions applied |
| User attributes change in Okta | User updated |
| User moved from persona A to persona B | Entitlements updated on next push |
| User removed from all Salesforce groups | User deactivated (`IsActive = false`); cannot log in; user license released |
| User deactivated / suspended in Okta | Same deactivation push |
| User restored to a Salesforce group | User reactivated and entitlements restored |

Salesforce never deletes the User record. That is expected and required for history, ownership, and audit.

#### C5. Import and match existing Salesforce users (if the org is not empty)

1. Run an import from Salesforce into Okta (To Okta / Import).
2. Match on Federation ID first, then username/email.
3. Stamp `FederationIdentifier` on every existing staff user before enforcing SSO.
4. Resolve duplicates before enabling Create Users, or Okta will fail on username uniqueness.

#### C6. Optional Salesforce-side safety net: User Access Policies

Use User Access Policies if some entitlements must be enforced inside Salesforce (for example, always grant `PS_SSO_Enforced` to users with a staff profile).

1. Setup → User Access Policies.
2. Criteria: Active = true, Profile in staff thin profiles.
3. Actions: Grant permission set groups / public groups / queues.
4. Automate on create and update.

Keep Okta as the primary entitlement driver. User Access Policies are a complement, not a second source of truth.

---

### Phase D — Enforce SSO and harden login

Do this only after successful tests in Phase E.

1. Assign `PS_SSO_Enforced` (**Is Single Sign-On Enabled**) to all staff.
2. Setup → Single Sign-On Settings → enable **Disable login with Salesforce credentials**.
   - This affects only users who have **Is Single Sign-On Enabled**.
   - Break-glass admins must not have that permission.
3. Hide the My Domain Login Form so staff are redirected to Okta.
4. Do **not** enable *Prevent login from https://login.salesforce.com* unless break-glass has a tested alternate path.
5. Session Settings:
   - Reasonable inactivity timeout
   - Lock sessions to the domain
   - Login History and Identity Verification History enabled
6. Require Okta MFA for the Salesforce app. Prefer phishing-resistant factors for admins.
7. API Access Control / External Client App policies: only the Okta provisioning app and approved integration apps may call the API.

---

## 5. Lifecycle runbooks

### 5.1 Joiner

1. HR / IT creates or activates the person in Okta.
2. Group rules add the user to `SF_ACCESS_INTERNAL`, a license group, and a persona group.
3. Okta provisioning creates the Salesforce user with Federation ID, thin profile, role, and permission set groups.
4. User opens `https://company.my.salesforce.com` or the Okta tile.
5. Okta authenticates + MFA; SAML assertion carries Federation ID and AMR.
6. Salesforce matches `FederationIdentifier` and starts the session.
7. No Salesforce password is issued.

### 5.2 Mover

1. Okta group membership changes (department, job, location).
2. Provisioning updates Profile (if license changes), Role, and permission sets.
3. Old combined permission sets are replaced by the new set of groups.
4. Next login uses the same Federation ID; no new user is created.

### 5.3 Leaver (mandatory de-provisioning)

1. Okta deactivates the user **or** removes all Salesforce group assignments.
2. Okta Push User Deactivation sets Salesforce `IsActive = false`.
3. User cannot authenticate via SSO (no app assignment) and cannot use a Salesforce password (SSO enforced, and account inactive).
4. Active UI sessions end; the user license is released.
5. If deactivation is blocked (user is Default Workflow User, in a custom hierarchy slot, and so on):
   - Freeze the user immediately (stops login, still consumes a license).
   - Reassign ownership / replace the process user.
   - Then deactivate.
6. Remove leftover permission set / permission set license assignments if the connector does not clear them (Winter ’26+ helps when permission sets are removed).
7. Confirm the user no longer appears as active in Salesforce and that Okta provisioning tasks succeeded.

### 5.4 Break-glass

1. Named admins retain Salesforce username/password and Salesforce MFA.
2. They log in at `https://login.salesforce.com` or My Domain with Login Form available to them.
3. Monitor Login History for any non-SSO admin login.
4. Rotate break-glass credentials on a schedule.

---

## 6. Environments

| Environment | Okta app | Salesforce domain | Notes |
| --- | --- | --- | --- |
| Production | `Salesforce-Prod` | `company.my.salesforce.com` | Authoritative lifecycle |
| Full / Partial sandbox | `Salesforce-UAT` (or similar) | `company--uat.sandbox.my.salesforce.com` | Separate OAuth app and SAML config |
| Dev sandboxes | Optional, often manual | Sandbox My Domain | Usernames gain a sandbox suffix after refresh |

After a sandbox refresh:

- Reconnect the External Client App / OAuth.
- Re-upload the Okta certificate if needed.
- Expect usernames to change (`user@company.com.uat`). Keep Federation ID stable so SSO still matches.
- Re-import users if Okta matching breaks.

---

## 7. Security, audit, and operations

| Control | Implementation |
| --- | --- |
| Least privilege | Thin profiles + persona permission set groups |
| No shared users | One Okta person = one Salesforce user |
| Integration isolation | Dedicated API-only users, not staff identities |
| Certificate rotation | Calendar reminder for Okta IdP cert; update Salesforce SSO settings before expiry |
| OAuth hygiene | PKCE, refresh token rotation, dedicated provisioning user |
| Monitoring | Okta System Log + Provisioning Tasks; Salesforce Login History, Setup Audit Trail, Identity Verification History; Event Monitoring if licensed |
| Failure alerting | Alert on failed Okta provisioning tasks (create/update/deactivate) |
| SAML cert emergency | Keep a second IdP certificate procedure documented |
| License hygiene | Weekly compare Okta Salesforce-assigned users vs Salesforce active users |

---

## 8. Test plan (must pass before enforcement)

| # | Scenario | Expected result |
| --- | --- | --- |
| 1 | Add user to `SF_ACCESS_INTERNAL` + license + persona | Salesforce user created, active, correct profile/role/PSG, Federation ID populated |
| 2 | IdP-initiated login from Okta tile | Session established, no Salesforce password prompt, no extra Salesforce MFA if AMR is valid |
| 3 | SP-initiated login via My Domain | Redirect to Okta, then back to Salesforce |
| 4 | Change persona groups | Permission sets update; old persona access removed |
| 5 | Change first name / department in Okta | Salesforce user updated |
| 6 | Remove user from all Salesforce groups | Salesforce user deactivated; login denied; license freed |
| 7 | Deactivate user in Okta | Same as (6) |
| 8 | Reactivate / re-add to groups | Salesforce user reactivated with correct entitlements |
| 9 | Staff tries username/password on My Domain | Rejected after SSO enforcement |
| 10 | Break-glass admin local login + Salesforce MFA | Succeeds |
| 11 | User in two capability groups | Both permission sets present (combine values) |
| 12 | User in two license groups | Must not happen; group design prevents it |
| 13 | Provisioning user credentials rotated | Tasks resume after re-auth |
| 14 | Sandbox refresh | SSO + provisioning re-established using Federation ID |

---

## 9. What this design does **not** use (and why)

| Approach | Why it is rejected for this requirement |
| --- | --- |
| SAML JIT as the provisioner | Creates users only at first login; cannot deprovision from group removal |
| JIT + API provisioning together | Profile-mastering conflicts; updates fail |
| SOAP provisioning | Legacy; REST/OAuth with PKCE is the current Okta/Salesforce path |
| Custom SCIM app against Salesforce SCIM 2.0 | Valid platform capability, but Okta is steering customers to the Salesforce OIN app (custom SCIM migration deadline published by Okta) |
| Salesforce Identity Connect | Retired |
| Mapping Okta groups directly to fat profiles | Violates Well-Architected; profiles should stay thin |
| Deleting Salesforce users | Not supported; deactivation is the documented model |

Salesforce SCIM 2.0 remains a documented platform API (`/services/scim/v2/Users`) that deactivates rather than deletes. It is a fallback if the OIN connector cannot meet a specific attribute need—not the primary design for an Okta enterprise.

---

## 10. Final outcome (brief)

- Okta is the source of truth for internal staff identity, MFA, and Salesforce access.
- Staff reach Salesforce through SAML 2.0 SSO (IdP- and SP-initiated) using My Domain and Federation ID.
- Staff do not use Salesforce passwords; named break-glass admins retain local login with Salesforce MFA.
- Okta directory group assignment is the only way to obtain a Salesforce user.
- The Okta Salesforce OIN app provisions users over REST + OAuth 2.0 + PKCE (External Client App).
- Create / update / deactivate / reactivate are automatic from group membership and Okta user status.
- Salesforce users are deactivated, not deleted; licenses are released on deactivation.
- Entitlements follow a thin profile + Permission Set Group model mapped from Okta groups.
- MFA is executed in Okta and signaled to Salesforce with `AMR` / AuthnContext so Salesforce’s SSO MFA requirement is met.
- JIT, Identity Connect, SOAP, and dual-provisioning are out of scope.
- Production and sandboxes use separate Okta apps; Federation ID remains the stable match key after sandbox refresh.
- Operations cover certificate rotation, provisioning-task alerts, login audit, and a freeze-then-deactivate path when Salesforce blocks deactivation.

---

## References (Salesforce and Okta documentation)

- Salesforce Help: *Manage Salesforce User Identities with SCIM* — deactivate rather than delete; `active = false`.
- Salesforce Help: *Set Up SSO with SAML 2.0*; *My Domain*; Entity ID should be the custom domain.
- Salesforce Help: *Multi-Factor Authentication (MFA) for Single Sign-On (SSO)*; Knowledge Article *Changes to Device Activation for Single Sign-On (SSO) Logins* (AMR / AuthnContext).
- Salesforce Architect: *Well-Architected — Secure / Trusted* — SSO, admin break-glass, permission sets over profiles, unique integration users.
- Salesforce Help: *Migrate from Profiles to Permission Sets*; *User Access Policies*.
- Okta Help: *Enable Salesforce single sign-on*; *Enable Salesforce provisioning*; *Configure OAuth and REST integration*; *Salesforce supported features* (push create/update/deactivate/reactivate).
- Okta Help: External Client App, PKCE, scopes `api` + `refresh_token` / `offline_access`.
- Okta Support: add SAML attribute `AMR` = `session.amr` for Salesforce SSO MFA signaling.
