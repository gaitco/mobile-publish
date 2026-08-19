# Apple App Store

Artifact: `.ipa`. Transport: `xcrun altool` (ships with Xcode). Requires macOS with Xcode —
unlike the Android stores, there is no way to produce or upload the artifact elsewhere.

The **iOS bundle id is not the Android applicationId**. Ranisy, for example, is
`com.ghanemtech.ranisy_logistics` on Android and `com.ghanemtech.ranisyLogistics` on iOS.
Read `PRODUCT_BUNDLE_IDENTIFIER` from `ios/Runner.xcodeproj/project.pbxproj` and ignore the
`RunnerTests` entry.

## Credentials

An **App Store Connect API key** — three pieces, and only one of them is a secret:

| Piece | Where it lives |
|---|---|
| `.p8` private key | `~/.appstoreconnect/private_keys/AuthKey_<KEYID>.p8` |
| Key ID | the filename, and shown in App Store Connect |
| Issuer ID | App Store Connect → **Users and Access** → **Integrations** → App Store Connect API |

The `.p8` path is not a convention we chose — Apple's tools look there by name, which is why
`altool` needs only `--apiKey <KEYID>` rather than a path. A key downloaded to `~/Downloads`
must be moved there before anything works.

The Issuer ID is a single UUID for the whole team, shared by every key. It is an identifier,
not a secret, and it is **not** recoverable from the `.p8` file — it has to come from the
console once.

Store the non-secret halves centrally so no project ever asks again:

```bash
mkdir -p ~/.config/asc && chmod 700 ~/.config/asc
cat > ~/.config/asc/config <<'EOF'
ASC_KEY_ID=XXXXXXXXXX
ASC_ISSUER_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
EOF
```

Verify a key/issuer pair actually authenticates before trusting it:

```bash
xcrun altool --list-apps --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID"
```

That lists every app the key can reach — which also tells you whether the key has the right
role. A key with **Developer** access can upload builds; **App Manager** or **Admin** is
needed for listing changes.

**`--list-apps` omits apps that have no builds yet**, so a brand-new app record looks absent.
Do not conclude the app must be created; ask the REST API for it directly:

```
GET /v1/apps/<appId>          # → name, bundleId, sku, primaryLocale
```

## Building

```bash
flutter build ipa --release
```

Output lands in `build/ios/ipa/*.ipa`.

This is the step that fails most often, and it fails for reasons the other stores don't
have: iOS artifacts must be **code-signed at build time** with a distribution certificate
and a matching provisioning profile. If the repo has never been archived from this machine,
expect signing errors rather than an artifact. Opening `ios/Runner.xcworkspace` in Xcode and
letting it manage signing once is usually faster than fighting the CLI.

Every upload needs a **unique build number** (`CFBundleVersion`, the `+N` in the Flutter
version). Apple rejects a build number it has already seen for that version string, even if
the earlier build was deleted.

## Upload

```bash
# Dry run — Apple's real checks (signing, entitlements, Info.plist), nothing uploaded
xcrun altool --validate-app -f <ipa> -t ios --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID"

# The actual upload
xcrun altool --upload-app -f <ipa> -t ios --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID"
```

`publish.sh --store asc` validates by default and only uploads with `--submit`, because
`--validate-app` catches nearly every rejection cause in about a minute, while a failed
upload costs the full transfer first.

### A build that uploads successfully and never appears

`UPLOAD SUCCEEDED with no errors` means the bytes transferred. Apple *then* runs static
analysis, and a build that fails it is discarded silently: absent from TestFlight, absent from
`/v1/builds`, absent from `/v1/preReleaseVersions`. The rejection is sent by **email only**, to
the App Store Connect **account-holder** address — under an organisation that is frequently not
the developer's own mailbox, so "no email arrived" is not evidence the build was fine.

The most common cause is **ITMS-90683, a missing purpose string**: the binary links a
privacy-sensitive API with no matching `NS*UsageDescription` in `Info.plist`. It is caused by
*linked* APIs, not used ones, so a plugin pulled in for audio can require a camera string too.

Confirm rather than wait. This is the only authoritative check:

```
GET /v1/builds?filter[app]=<appId>&sort=-uploadedDate   # → version, processingState: VALID
```

A build that vanishes twice in a row is not lag. Diff the Info.plist against a build that did
register — in one real case adding `NSMicrophoneUsageDescription` and `NSCameraUsageDescription`
turned a build that never appeared into one that reached `VALID` in about seven minutes.

**Uploading is not releasing.** The build lands in App Store Connect, spends 5–30 minutes in
"Processing", then becomes available to TestFlight. Attaching it to an App Store version and
submitting for review is a separate action, done in the console or with `fastlane deliver`.

## Listing metadata

`3lahwa/flutter/ios/fastlane/` has working `deliver` lanes for the **listing** — metadata and
screenshots, no binary:

```bash
fastlane listing          # metadata + screenshots
fastlane listing_text     # text only
fastlane screenshots_only
fastlane preview          # shows an HTML preview before uploading
```

`deliver` needs an editable app version to exist in App Store Connect first. For a brand-new
app, create the app record and a version in the console before running it.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `No suitable application records were found` | Bundle id has no app record in App Store Connect, or the key can't see it. `--list-apps` settles which. |
| `Unable to authenticate` / 401 | Wrong Issuer ID, or the `.p8` isn't at `~/.appstoreconnect/private_keys/AuthKey_<KEYID>.p8`. |
| `The bundle version must be higher than the previously uploaded version` | Build number reused. Bump `+N` in pubspec.yaml. |
| `Invalid Signature` / missing entitlements | Built without a distribution profile. Archive once from Xcode to fix signing. |
| Build uploaded but absent from TestFlight | **Usually a processing rejection, not lag.** See below. |
| `flutter build ipa` fails with no signing identity | No distribution certificate on this Mac. Xcode → Settings → Accounts → Manage Certificates. **Do not diagnose this with `security find-identity -v -p codesigning`** — it can list no distribution identity on a machine where `flutter build ipa` signs perfectly well via automatic signing. Try the build before concluding you are blocked. |
