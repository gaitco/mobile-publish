# Huawei AppGallery

Artifact: `.apk` (`.aab` also accepted). Transport: `scripts/agc.py`, bundled with this
skill — a small python3 + curl + openssl CLI, no gems or plugins.

## The Huawei-specific risk: no Google Play Services

Huawei devices sold since 2019 ship without GMS. Anything routed through it is dead on
those devices — FCM push, Firebase Analytics, Play Core in-app updates, the fused location
provider. Check this **before** building, because the answer may change what ships.

The fatal case is a manifest entry that *requires* Play Services: AppGallery then filters
the app out of search entirely, so users don't see a broken app, they see no app. Inspect
the **merged** manifest inside a built APK, never the source manifest, since plugins inject
their own entries at merge time:

```bash
aapt2 dump xmltree <apk> --file AndroidManifest.xml | grep -iE "uses-feature|required"
```

Every GMS-related `uses-feature` must be `required=false`.

Then read the code for unguarded GMS calls — Firebase init, `getToken()`, Play Core update
checks, Google Sign-In. Each should sit inside a try/catch that lets the app continue. An
app that *degrades* (no push on Huawei) passes review; one that *crashes* does not.

Report what won't work so the user can decide between shipping degraded and investing in
HMS Push Kit. That is a business call — present the tradeoff, don't make it.

### In-app purchases are the exception: degrading is not enough

Grep `pubspec.yaml` for `in_app_purchase` and confirm whether it is actually wired up
(`grep -rln in_app_purchase lib`). On Android that package **is Google Play Billing**: it
needs Play Services *and* an install that originated from Play, so on a Huawei device from
AppGallery the billing connection never opens.

This is not the quiet degradation that push and ads get. The paywall still renders, now with
no products — a visibly broken purchase flow that a reviewer will tap, on a store that
requires Huawei IAP for purchases. Treat a live paywall as a **submission blocker**, not a
footnote.

The cheap fix is a build flag that hides the purchase surface on this store only:

```dart
static const String store = String.fromEnvironment('STORE', defaultValue: 'play');
static bool get supportsInAppPurchase => store != 'huawei';
```

Then `flutter build apk --release --flavor prod --dart-define=STORE=huawei`. Gate **both**
the visible entry point and the route — a hidden button still leaves the paywall reachable by
deep link or a restored route. Leave ads enabled: the "is premium" flag simply stays false.
The alternative is integrating HMS In-App Purchases, which is days of work plus server-side
receipt validation — present both and let the user choose.

### Content rating

The questionnaire computes a rating; you may self-select **higher** but never lower. Push the
rating up when the app surfaces content it does not curate — third-party news feeds, crawled
video, or ad networks — because "3+" promises *no* age-restricted content and one bad item in
a media tab means a bumped rating and a lost review cycle. Picking a low rating triggers a
"this app is intended only for kids" confirmation: answer **No** unless the app really is a
kids app, since Yes forces the Kids category and its children's-privacy rules, which are
incompatible with ads, analytics, and an advertising ID.

## Credentials

`scripts/agc.py` authenticates with an AGC **Service account** key (AGC console → Users
and permissions → API key → **Service account** tab). It looks for, in order:

1. `$AGC_KEY_FILE`
2. `agc-service-account.json` in the current directory — this is how the existing per-app
   setups store it, so running from a repo that already has one just works
3. `~/.config/agc/service-account.json` — the shared fallback

### How the auth actually works, and the trap in it

The obvious OAuth flow is a dead end. Exchanging the JWT at
`oauth-login.cloud.huawei.com/oauth2/v3/token` returns a real access token, and the
Publishing API then rejects it with `205524993 client token auth failed`. Huawei does not
support the jwt-bearer exchange grant here.

What works is using the **JWT itself as the Bearer token**, with no exchange:

```
header  {"alg":"PS256","typ":"JWT","kid":<key_id>}
payload {"iss":<sub_account>,"aud":<token_uri>,"iat":now,"exp":now+3600}
sign    openssl dgst -sha256 -binary \
          -sigopt rsa_padding_mode:pss -sigopt rsa_pss_saltlen:digest -sign key.pem
headers Authorization: Bearer <the JWT>   |   client_id: <sub_account>
```

`rsa_pss_saltlen` must be `digest`. Using `-1` produces a signature Huawei rejects with
`jwt verify error`, which reads like a bad credential rather than a padding mismatch.

A **Connect API client** (`client_id` + `client_secret`, client_credentials grant) is a
different, also-valid credential — but in practice it has shown *less* app visibility than
the service account, returning an empty `appid-list` for an app the service account
resolves fine. Prefer the service account.

## Publishing

The app is identified by package name; `agc.py` resolves the appId itself, so there is no
ID to look up or mistype.

```bash
export AGC_PACKAGE=com.x.y

python3 scripts/agc.py app-id                  # resolve and print the appId
python3 scripts/agc.py info                    # release state + versions
python3 scripts/agc.py upload <apk>            # upload only, no review submission
python3 scripts/agc.py listing spec.json       # listing text, privacy URL, country, category
python3 scripts/agc.py screenshots *.png       # 3-8 screenshots, uploaded via OBS
python3 scripts/agc.py ready                   # what still blocks submission
python3 scripts/agc.py submit --changelog f    # submit the uploaded build for review
python3 scripts/agc.py publish <apk>           # upload, wait, then submit
```

Use `upload` by default. Reach for `submit`/`publish` only when the user asks to release —
review is the outward-facing step.

Details worth knowing:

- **A fresh draft app has no package binding yet**, so lookup by package finds nothing on
  the very first upload. Set `AGC_APP_ID=<id>` for that one run. The appId is the **first**
  number in the console URL `#/myApp/<appId>/<projectId>` — roughly 9 digits, where the
  projectId is 17–19. Reading these backwards yields a 403 that looks exactly like a
  permissions failure.
- **The changelog (`remark`) must be 3–500 characters** or AGC rejects the submission.
- **AGC needs time to process an uploaded package.** `submit` retries 5× at 60 s intervals;
  do not interpret the first "not accepted yet" as a failure.

## Filling the listing from the API

Most of the store listing is writable, which matters because AGC blocks submission until the
required fields are set. Two calls cover the text (verified against a live draft):

```bash
# localized text — one call per language; lang matches appInfo.defaultLang
PUT app-language-info?appId=<id>
{"lang":"ar","appName":"...","appDesc":"<full intro>","briefInfo":"<=80 chars>","newFeatures":"..."}

# privacy policy URL lives on the app, not the language
PUT app-info?appId=<id>
{"privacyPolicy":"https://example.com/privacy"}
```

**Always read the listing back with `GET app-info?appId=<id>`.** It returns `appInfo` plus a
`languages` array, and it is the only proof the write landed: AGC answers `ret.code 0` for a
body whose field names it does not recognize, so an ignored write is indistinguishable from a
successful one at the call site. The same GET confirms the uploaded package —
`versionNumber` / `versionCode` should match the artifact you just pushed.

### Images: OBS upload only

Images attached through the **classic** `upload-url` endpoint are always rejected
(`204144641 The image's signature or data type is invalid`, or `sign is empty`) — that path is
for packages. Images must go through `upload-url/for-obs`, and the `objectId` it returns is
what `app-file-info` accepts:

```bash
GET  upload-url/for-obs?appId=<id>&fileName=shot.png&contentLength=<bytes>&suffix=png
PUT  <urlInfo.url>            # raw bytes, with urlInfo.headers
PUT  app-file-info?appId=<id> {"lang":"ar","fileType":2,"files":[{"fileName":"…","fileDestUrl":"<objectId>"}]}
```

`upload-url/for-obs` fails with `204144694 distContryList is empty` until `publishCountry` is
set — so set the country first and the OBS path starts working for packages too.

### Distribution countries

`publishCountry` is a comma-separated list on `app-info`, and **submission is refused until it
is set** (`distCountryList is empty`) — it also gates `upload-url/for-obs`, so set it first.

`references/appgallery-countries.txt` holds the **198 codes AppGallery actually accepts**,
derived by testing every ISO 3166-1 alpha-2 code one at a time. Use it instead of re-deriving:

```bash
curl -X PUT "$API/publish/v2/app-info?appId=$ID" ... \
  -d "$(jq -n --arg c "$(cat references/appgallery-countries.txt)" '{publishCountry:$c}')"
```

**`US` is rejected** — Huawei does not distribute into the United States, nor `GU`/`VI`/`MP`/`UM`.
If a user asks for "worldwide", say this out loud; it is not a gap in the list. The other 44
rejects are uninhabited territories (`AQ`, `BV`, `HM`, `GS`, `TF`) and dependencies Huawei folds
into a parent market (`JE`, `GG`, `IM`, `BL`, `MF`, `PM`).

Trap: **one error code, two meanings.** `204144651 publishCountry oversize` is returned both for
a genuinely over-long list *and* for a single invalid code. The message names the wrong cause, so
a binary search on list length converges on nonsense (it "proves" a max of 8 when the real
problem is `AQ` sitting at index 9). Test codes individually.

### fileType map (decoded from the API's own error messages)

| fileType | Slot | Constraint |
|---|---|---|
| 1 | Promo video | needs `videoShowType` |
| 2 | **Screenshots** | 3–8 files; lands in `deviceMaterials[].screenShots` |
| 3 | Video + cover | exactly 2 files, `.mov`/`.mp4` |
| 5 | App package | APK/AAB, classic upload path |
| 7 | Certificate | `.pdf` only |
| 10–15 | — | rejected for `deviceType 4` (phone) |

**The app icon has no working slot from the API.** `LanguageInfo.icon` is typed `String` and
silently drops an objectId; `fileType` 0/4/6/8/9 either error or accept-and-discard. Upload the
icon (216×216 PNG) in the console — everything else on the listing can be scripted.

### Submit is a blocker chain, and it validates in order

`app-submit` returns one missing field at a time as `204144660 [cds]submit failed, additional
msg is [X is necessary !]`. Expect to iterate: `distCountryList` → `ChildType` →
`GrandChildType` → `AppIcon`. Two traps: the `remark` is validated **before** the content
fields, so a too-short remark masks what is actually missing; and the real remark bound is
**10–300 characters**, not the 3–500 the older tooling assumed.

### Category ids

`parentType` / `childType` / `grandChildType` are numeric with no lookup endpoint and no
reachable published table. Copy the triple from a sibling app in the same developer account
that is already categorized correctly (`GET app-info` on its appId) — `parentType 13` is Apps,
`2` is Games. Do not invent a number; it sets a public category you cannot verify.

### Run `ready` before every submit

`agc.py ready` prints the stored state of each required field and names what is still missing.
Use it instead of a submit attempt to find blockers — submit reports one field at a time and
validates `remark` first, so it misleads.

A console save is **atomic across the whole App information page**: if any required field there
is still flagged (privacy tags, the rating questionnaire), clicking Save aborts and everything
else on that page — including a freshly picked icon — is discarded with it. Someone saying "I
saved it" is not evidence; `appInfo.updateTime` not moving is.

### Still console-only — measured, not assumed

Privacy tags (collect-personal-data), the **AI function declaration** (Generative AI service:
Not involved / Involved — a required field as of 2026), the content-rating questionnaire,
**Compatible devices**, the app icon, the category triple, and the review test account.

Verified two ways, so don't re-derive it:

- **Endpoint sweep — 30 paths, all 404.** Across `publish/v1`, `publish/v2`, `publish/v3` and
  `appinfo/v1`: `app-privacy`, `privacy-info`, `app-privacy-info`, `app-tag`, `app-tags`,
  `privacy-tag`, `privacy`, `privacy-label`, `app-privacy-label`, `privacy-declare`,
  `app-privacy-tag`, `data-security`, `app-data-security`, `ai-info`, `app-ai-info`,
  `app-content-rate`, `content-rate`, `app-rating`, `app-compliance`, `compliance-info`,
  `app-declaration`, `app-scenario`, `app-service-scenario`, `app-label`, `app-permission`.
  There is no privacy/AI/rating endpoint in any API family or version.

  The console UI does reach *some* backend, but that is AGC's internal web API on a different
  host, authenticated by a browser session cookie rather than a Connect API credential.
  Scripting it means cookie-driven console scraping — unsupported and brittle. Do not offer it;
  filling the form takes about two minutes.
- **Field probe on `app-info`** — `collectPersonalData`, `privacyTag`, `privacyTags`,
  `personalDataCollect`, `collectUserData`, `generativeAi`, `generativeAiService`, `aiService`,
  `aiFlag`, `aiFunctionFlag`, `genAiService`, `contentRate`, `appTag`, `hasAd` are all silently
  dropped.

`distributeDeviceTypes` is a special case: it is a *recognized* field that accepts
`[{"deviceType":4}]` with `ret.code 0` and **never persists** — readback stays `[]` for every
shape tried. Accept-and-discard, exactly like the icon. Set Compatible devices in the console.

### Enumerating the real writable surface

Unknown field names return `ret.code 0`, so a successful PUT proves nothing. To find out
whether a field exists, send it a **deliberately wrong-typed value**: a recognized field
errors and names itself, an unknown one is dropped silently.

```bash
curl -X PUT "$API/publish/v2/app-info?appId=$ID" ... -d '{"someField":"__zzz__"}'
#  ret.code 0        -> field does not exist
#  ret.code non-zero -> field exists, your value was just the wrong type
```

Recognized on `app-info` by this method: `deviceTypes`, `distributeDeviceTypes`,
`grandChildType`, `familyShareTag`, `kindSubTags` (plus the documented text/country fields).

**Known-good triple — copy it instead of probing.** Verified against a live app:
`Sports = parentType 13, childType 31, grandChildType 10007`.

If you need a category this doesn't cover: `childType` is validated on write and invalid values
do not stick, so the ID space is safe to enumerate — loop 1..300 and keep the codes returning 0
(under `parentType 13` = Apps, the valid ones are **23-31, 33, 35**). But enumeration yields
*IDs*, never *names*: there is no lookup endpoint and no reachable published table, so a probed
number is an unverifiable public category. Get the triple from a correctly-categorized sibling
app, or have the user pick in the console — which warns that the category cannot be changed
afterwards without contacting customer service.

### Readback trap

`app-info` fields live under `.appInfo`, not at the top level. Filtering the top-level object
(`jq '{deviceTypes,childType}'`) prints `null` for every field and looks exactly like data
loss. Always `jq '.appInfo | ...'` before concluding a write failed or a value was wiped.

Several apps: list them in `scripts/apps.tsv` as `<name>\t<package>\t<apk-path>` and run
`scripts/release-all.sh`. It uploads only, never submits, and continues past a failing app
so one stale build cannot block the rest.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `403` on `upload-url`, empty body | Wrong appId far more often than missing roles. Check URL order first. |
| `appid-list` returns `appids: []` | Client has no app permissions, or the app is under a different developer account. |
| `205524993 client token auth failed` | The JWT was exchanged for a token instead of being used directly as the Bearer. |
| Token succeeds, every call 403s | Credentials fine, authorization missing — roles or account mismatch. |
| Reports success, nothing appears | Check `.ret.code` in the body; AppGallery returns HTTP 200 on logical failures. A `ret.code 0` on a PUT proves only that the request parsed — unknown field names are dropped silently, so re-read with `GET app-info`. |
| `204144641 image's signature or data type is invalid` | Attaching screenshots through `app-file-info`. That path is for the icon; use the console. |
| `jwt verify error` | PSS salt length wrong — must be `rsa_pss_saltlen:digest`, not `-1`. |
| Submit rejected right after upload | AGC still processing the package; `agc.py submit` retries 5× at 60 s. |
