# AppGallery privacy tags — the real taxonomy

Console-only. Required since 2022-07-28 for any app that collects personal data or embeds an
SDK that does. Lives on the **version** page (`#/myApp/<appId>/v<versionId>`), not App
information, and blocks `app-submit`.

## Do not try to look this up on the web

Measured 2026-08-19, all dead ends:

- `developer.huawei.com/consumer/en/doc/app/privacy-label` — Angular SPA, returns a **1824-byte
  shell**; content is fetched by JS. `curl`/WebFetch get nothing. WebFetch also timed out at 60 s.
- The `<link rel="alternate" type="text/markdown">` in that shell is filled in by JS. Probed
  `.md`, `/doc/md/...`, `/doc/.../md`, `/consumer/doc/md/en/...` — all either 404 or the same
  shell. One returned 110 KB but it was an unrelated zh-CN landing page with no item text.
- `orangeoma.zendesk.com` write-up on setting privacy tags — **HTTP 403**.
- Web search returns policy prose ("you must set privacy tags", timelines, liability) and
  OAID/SSID definitions, never the enumerated item list.

**The console dialog is the source of truth.** Screenshot each tab and read it. Do NOT infer
item names — the taxonomy is idiosyncratic (bundled items, pre-Android-10 identifiers), and a
guessed name leads to advising a tick on something that does not exist, or missing one that does.

## Service scenarios (VERIFIED — complete, 7 of them)

`Collect personal data: Yes` reveals these as checkboxes:

| Scenario |
|---|
| App functionality |
| Product personalization |
| Analytics |
| Advertising and marketing |
| Disclosure to third parties |
| Cross-border transfer |
| Others |

Each **ticked** scenario gets its own tab with its own `+ Add` → "Add data items" dialog, and
each shows a red dot until it has at least one item ("Add data items for the selected
scenarios."). A `Summary` tab aggregates them.

Declare items **per purpose**, not once globally: the analytics payload is usually a small
subset of what the app collects, and `Disclosure to third parties` / `Cross-border transfer`
normally mirror `Analytics` exactly (the analytics SDK is the third party, and it is what
leaves the country).

## Data item tabs (VERIFIED — 12, in this left-to-right order)

1. Contact information
2. Fitness and health information
3. Financial information
4. Transaction information
5. Location information
6. Special category data
7. Identifiers
8. Basic information
9. User content
10. App information
11. Device information
12. Other personal data

The tab strip scrolls with `<` / `>` arrows and **each tab's item list scrolls independently** —
items are easily missed above and below the fold. Scroll each list to both ends.

## Items per tab

Verbatim from the console, 2026-08-19. All 12 tabs observed. Lists scroll independently — a
"(order)" note means the on-screen order was reconstructed from overlapping screenshots.

### Contact information (complete, 3)
- **Contact list** — Including contacts and friends list.
- **Social media accounts** — Contacts in social media apps such as Facebook, Twitter, WeChat, QQ, and Weibo.
- **Other contact information** — Including fax number.

This tab means the **device address book**, not the email/phone a user types into a signup
form. Those live under `Basic information`.

### Fitness and health information (4 seen, list scrolls)
- **Fitness information** — Including walking/running route, duration, and other exercise data.
- **Heart rate**
- **Blood pressure**
- **Other health information** — Personal medical records, including illness, medical advice, test reports, operation and anesthesia records, medication records, drug and food allergies, childbirth information, medical history, diagnosis and treatment information, and family medical history / Personal health information, including weight, height, and lung capacity

### Financial information (complete, 4)
- **Bank account information** — Including bank account number, password, and expiry date.
- **Other financial account information**
- **Asset information** — Including credit rating, consumption, income, savings, investments, HUAWEI Points, digital currencies, and coupons.
- **Other financial information** — Including property and tax information.

`Asset information` is the item that covers **income**, so a payslip feature lands here — not
`Bank account information` unless the app actually shows account numbers.

### Transaction information (complete, 4)
- **Transaction records** — Including payment account, receiving account, payment method, and payment information.
- **Order information** — Including order number, product information, and subscription information.
- **Package delivery information** — Including tracking number, sender and recipient information, and item information.
- **Other transaction information**

`Package delivery information` is the logistics/shipment-tracking item.

### Location information (complete, 4)
- **GPS location** — Including precise GPS coordinates
- **Network location** — Including MAC and IP addresses of nearby Wi-Fi devices.
- **Other precise location information** — Including GPS routes
- **Other approximate location information** — Including location in terms of administrative region and approximate GPS coordinates

`Other precise location information` (GPS routes) means path tracking — a single fix per user
action is `GPS location` only.

### Special category data (complete, 5)
- **Fingerprint information**
- **Voiceprint information**
- **Facial recognition features**
- **Other biometric features** — Including palm print information, auricle information, iris information, and genetic information
- **Other special category data** — Including race or ethnicity, sexual orientation, religious or philosophical beliefs, trade union membership, and political views.

**OS-mediated biometric auth does NOT belong here.** `local_auth` /
Android BiometricPrompt / Face ID return only a pass-fail boolean; the app never receives
fingerprint or face data. Ticking `Fingerprint information` for a biometric-login feature is
the single most common over-declaration on this tab, and special-category declarations invite
extra scrutiny.

### Identifiers (complete, 14) (order)
- **User identifiers** — Including UID, account ID, assigned user ID, customer number, or other user-level or account-level IDs that can be used to identify a specific user or account (such as Samba account, PPP account, or FTP account).
- **ID card**
- **OAID**
- **ODID**
- **SSID**
- **BSSID**
- **SN**
- **IMEI**
- **IMSI**
- **MAC**
- **MEID**
- **Chip ID**
- **Other identity information** — Including information about passport, driver's license, work permit, entry/exit permit, social security card, residence permit, visa, and military ID
- **Other device identifiers** — Including vehicle identification number, engine serial number, license plate number, and device authentication credentials

Typical Flutter/Android answers: `User identifiers` under App functionality (the login
account), `OAID` under Analytics / Disclosure / Cross-border (Huawei's advertising ID, the
AAID/GAID equivalent). SN/IMEI/IMSI/MAC/MEID/Chip ID need privileged or legacy telephony
permissions modern Android denies. `ODID` is HMS-only.

### Basic information (12 seen) (order)
- **Name** — Including name and surname.
- **Gender**
- **Age**
- **Date of birth**
- **Account information** — Including profile picture, nickname, and password.
- **Education information** — Including education level, education history, training history, education transcripts, professional background, and professional achievements.
- **Home information** — Including marital status and family member information.
- **Address** — Including home address, mailing address, and shipping address.
- **Phone number** — Including mobile and landline numbers.
- **Email address** — Including sender and recipient email addresses.
- **Calendar and schedule**
- **Other personal information** — Including nationality, place of birth, height, and weight

There may be items between `Education information` and `Home information` — that gap was not
directly observed.

`Calendar and schedule` means the **device** calendar. An in-app leave/shift calendar built
with a UI package such as `table_calendar` is the app's own data, not this — check for a
`device_calendar` / `add_2_calendar` plugin before ticking.

Any HR or employee-directory feature usually lands `Gender`, `Date of birth`,
`Education information`, `Home information` (marital status) and
`Other personal information` (nationality) — grep the models rather than assuming a
business app collects no demographics.

### User content (12 seen) (order)
- **Image or video** — Including photos and videos.
- **Audio** — Including voice interactions and video audio tracks
- **Text information** — Including feedback and suggestions.
- **Search keywords** — Search terms entered or touched in apps.
- **Social interactions** — Including posts, comments, and likes.
- **Game statistics**
- **Audio recording** — Including microphone recordings
- **SMS messages**
- **Call logs**
- **Other communication content** — Including email and call contents
- **Software installation list** — Including app installation status retrieved from the API interface or analyzed based on running processes.
- **Other user content** — Including contract information, Word documents, and PDF files.

`Other user content` covers user-supplied documents. Only tick it if the app **uploads** them
(`file_picker` and similar). An app that merely **downloads** a generated PDF (e.g. an invoice
via a `/pdf` endpoint) is not collecting user content.

### App information (7 seen) (order)
- **Browsing history** — Including page clicks and content exposure records.
- **Favorites** — Content added to favorites.
- **Basic app information** — Including package name, version number, and developer.
- **App run logs** — Including crash logs, startup logs, power consumption logs, and diagnostic logs.
- **App settings** — Including app and feature settings
- **App running status** — Including playing/pausing music, accessing location, and running in the background
- **App usage information** — Interaction information, including user-initiated playback, and opening and closing of apps.

Firebase Analytics + Crashlytics maps to `Basic app information` + `App run logs` +
**`App usage information`** (Firebase auto-collects `first_open`, `session_start` and
app-open/close events with no code at all).

`Browsing history` needs real page/click telemetry. A Flutter app with `firebase_analytics`
but **no** `FirebaseAnalyticsObserver`, `logScreenView`, `setCurrentScreen` or `logEvent`
does not have it — Flutter renders every route inside one Android Activity, so Firebase
cannot see routes by itself.

`App run logs` is a bundle; it nominally includes power-consumption logs you probably do not
collect, and there is no finer-grained option.

### Device information (12 seen) (order)
- **Screen orientation sensor**
- **Gravity sensor**
- **OS information**
- **Device status** — Including device battery status, charging status, and storage status
- **Gyroscope**
- **Acceleration sensor**
- **IP address**
- **Light sensor**
- **Barometer**
- **Rotation vector sensor**
- **Other hardware and software parameters/System settings** — Including device model, display resolution, language, country/region, and software version
- **Other device information** — Including screen touch position.

**There is no standalone "Device model" item** — device model, language and country/region all
live inside `Other hardware and software parameters/System settings`. For a Firebase app the
analytics trio here is `OS information` + `Other hardware and software parameters/System
settings` + `IP address` (Firebase resolves coarse geography from IP).

Sensors are the classic over-declaration. A Flutter app touches none of them unless a plugin does.

### Other personal data (complete, 1)
- **Other personal data** — Other data not listed above.

## Deciding a tick: direction of flow, not field presence

Grep finds a field; only the call site says which way the data moves. Data the app **renders**
from your own backend is not data it **collects** from the user.

Real example: a logistics app had `plateNumber` in a tracking model, which matches
`Other device identifiers` ("license plate number"). But it was display-only — the API sends
fleet telemetry and the client screen renders it. Not collected from the user or the device, so
not declared.

Equally, one absent call flips an answer: with no `setUserId` / `setUserProperty` /
`setCustomKey`, Firebase is pseudonymous, so `User identifiers` belongs under App functionality
but **not** under Disclosure or Cross-border. Grep for those three before deciding.

## Evidence to gather before filling any of this in

```bash
aapt2 dump permissions <apk> | sort -u          # capability — what the app CAN touch
grep -rn 'setUserId\|logEvent\|FirebaseAnalyticsObserver' lib/
grep -rniE 'passport|national_?id|visa|work_?permit' lib/    # identity docs
grep -rnoE 'pickImage|pickVideo|ImageSource\.[a-z]+' lib/    # photos vs video
grep -rhoE "'(search|q|keyword)'" lib/                       # are search terms sent?
```

Permissions show capability; the call sites show intent. AGC is asking about intent, and a
declaration that contradicts the manifest is the thing reviewers actually catch.

## The privacy policy must be at least as broad as these tags

Reviewers compare the tags against the linked policy URL. A website-only policy behind an app
that collects location, camera, notification tokens, and analytics identifiers is a documented
rejection reason. Read the live policy before ticking, and widen it first if needed.

## Console edits can silently destroy API-set data

Observed live, 2026-08-19, mid-session while a user worked the console:

- The **`en-US` language entry vanished entirely** — `GET app-info` went from
  `languages: [ar, en-US]` back to `[ar]`, deleting listing text written minutes earlier.
- The **package came off the version draft** — the version page showed
  "Select an app package" and `One or more errors found in the settings ... App version`, and
  its title lost the `1.0.8` prefix. Note `app-info` **still reported `versionNumber 1.0.8 /
  versionCode 8`** the whole time: the app-level readback does NOT prove the version draft
  still has a package attached. Trust the version page, or re-upload.

Both were fixed by simply re-running `upload` and `listing <spec>`; the recreated language
needed its **screenshots re-uploaded** too.

**So: re-read state after any console session, do not assume earlier API writes survived.**

### Screenshots do NOT reliably propagate across languages

Earlier in the same session, uploading 4 screenshots for `ar` left `en-US` also showing 4 —
which looked like propagation. After the language was recreated, `en-US` came back with
**0 screenshots** and needed an explicit upload. Treat screenshots as **per-language** and
verify each entry.

`agc.py screenshots` has no `--lang` flag and always targets `defaultLang`. For another
language, call the method directly:

```python
c.screenshots(app_id, shots, lang="en-US")
```

### The upload path changes once publishCountry is set

First upload (no countries yet) fell back to the classic endpoint
(`204144694 distContryList is empty`). After `publishCountry` was set, the same command took
the direct-to-OBS path. Both bind correctly — do not read the path switch as an error.
