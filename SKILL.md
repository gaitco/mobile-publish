---
name: mobile-publish
description: Build and upload mobile apps to Google Play, Huawei AppGallery, or the Apple App Store. Use for store uploads, internal testing, TestFlight, release submission, signing or provisioning failures, missing uploaded builds, and store review rejections. Includes pre-submission listing and game-services setup.
---

# Publishing a mobile app to a store

Every store release is the same four moves — produce a signed artifact, prove it is the
*right* signed artifact, push it to a holding area, and hand back the list of things only
a human in the console can do. What changes per store is the transport and the traps.

## Start here: just publish it

This skill works in Codex and Claude Code. Resolve `MOBILE_PUBLISH_SKILL_DIR` to the
absolute directory containing **this loaded SKILL.md**, not the app project. All
`references/`, `scripts/`, and `SETUP.md` paths in this skill and its references are
relative to that directory. Read references there and invoke bundled shell/Python
scripts through `bash`/`python3` using quoted absolute paths.

Keep the command's working directory inside the target app project so discovery finds
the correct app. For example, for the standard Codex installation:

```bash
MOBILE_PUBLISH_SKILL_DIR="$HOME/.agents/skills/mobile-publish"
bash "$MOBILE_PUBLISH_SKILL_DIR/scripts/publish.sh" --store play # one store (play | agc | asc)
# Add --build to rebuild, or --submit only when review submission is requested.
```

Use the actual loaded path for Claude Code or a custom installation. Do not change into
the skill directory to run the publisher. Check the project's existing publishing setup
and complete the verification steps below before invoking an upload. The convenience
script discovers Flutter modules; for native Android/iOS, use the project's build/release
tooling and the relevant store reference instead.

It discovers the Flutter module, the `applicationId`, the version, the artifact paths, and
the credentials on its own. **Do not ask the user for a package name, an app ID, a
credential path, or a store configuration before running it** — those questions are the
thing this skill exists to eliminate. If a credential really is missing, the script says
which store it skipped and why; only then is there something to ask about.

Read a store reference when something fails, when the user wants a step this doesn't cover
(promotion, changelogs, first-time listing), or when you need to explain what happened.

## Credentials live centrally, and are almost certainly already there

| Store | Looked up in order |
|---|---|
| AppGallery | `$AGC_KEY_FILE` → `<app>/android/agc-service-account.json` → `~/.config/agc/service-account.json` |
| Google Play | `$PLAY_STORE_JSON_KEY` → `<app>/android/play-store-key.json` → `~/.config/play/service-account.json` |
| App Store | `~/.config/asc/config` (`ASC_KEY_ID`, `ASC_ISSUER_ID`) + `~/.appstoreconnect/private_keys/AuthKey_<KEYID>.p8` |

Account-level credentials can serve multiple apps when granted access to them. Check
the central paths above and the project's existing configuration before requesting new
credentials. Verify access to the intended app; a credential file's presence does not
prove permissions. Keep secrets out of source control and do not overwrite shared
credentials while setting up a new project.

## The underlying workflow

Read the reference for the target store **after** the shared steps below:

| Store | Reference | Transport |
|---|---|---|
| Huawei AppGallery | `references/appgallery.md` | `scripts/agc.py` (bundled) |
| Google Play | `references/play.md` | the repo's fastlane lanes, else `fastlane supply` |
| Apple App Store | `references/appstore.md` | `xcrun altool` (needs macOS + Xcode) |

Cross-store console configuration that publishing tooling does **not** create:
`references/game-services.md` — achievements and leaderboards on Play Games Services / Game Center.
Read it if the app has achievements, leaderboards, or ranked progression, before submitting: the
IDs must be minted in both consoles first, and two of the setup mistakes crash at launch or fail
only on a real device.

**Check the repo for existing publishing setup before reaching for these.** An
`android/fastlane/Appfile`, a `Fastfile`, an `agc-service-account.json`, or a runbook under
`docs/` means someone already made per-app decisions — package names, artifact paths,
changelog handling, which track is safe. Use what is there and treat this skill as the
fallback and the explanation. Publishing configuration that already works is worth more
than consistency with a generic script.

When the user names no store, publishing to every store the app has credentials for is the
right reading of "upload it" — that is what `publish.sh` does by default. Only ask when
they seem to want one specific store and it is genuinely ambiguous which.

## Step 1 — Establish what the release is

Check the version before touching anything, because a duplicate version code is rejected
after the upload finishes, which is the slowest possible way to discover it.

```bash
grep '^version:' pubspec.yaml        # Flutter: version: 1.0.8+8  → name 1.0.8, code 8
```

Every store requires the version code to *increase* relative to what that store already
has. The stores count independently — Play at 42 and AppGallery at 3 is normal — so
check against the target store, not against a number in the repo.

## Step 2 — Build

```bash
flutter build appbundle --release    # Google Play
flutter build apk --release          # AppGallery
flutter build ipa --release          # App Store (macOS + Xcode + signing required)
```

Release builds with minification take minutes. Start the build, then use the wait to read
the store reference and check credentials rather than sitting idle.

**Never ship an incremental build.** Run `flutter clean` first for anything going to a store.
Gradle's manifest merger caches its output, and if a source file changed since the last build
it can emit a merged manifest holding **both** the old and new values. A real case: an
`AndroidManifest.xml` edited between two builds produced an APK whose merged manifest carried
the new deep-link host *and* a stale one that existed in no source file — only in
`build/app/intermediates/merged_manifest/`. Android verifies **every** `autoVerify` host, so
the dead entry would have broken App Links verification for the whole filter set. It was
invisible in the source tree and only showed up in `aapt2 dump xmltree` on the artifact.

**Check for product flavors before building.** A bare `flutter build apk --release` builds
*every* flavor, so one misconfigured flavor fails the whole run even when the flavor you
actually ship is fine:

```
Execution failed for task ':app:processDevReleaseGoogleServices'.
> No matching client found for package name 'com.example.app.dev' in google-services.json
```

`google-services.json` usually registers only the production package, so `dev`/`staging`
die at the Google Services task. Grep `android/app/build.gradle` for `productFlavors` and
pass `--flavor <prod>`. Cost of missing this is a full wasted build.

One Android failure is worth recognizing on sight, because it only ever appears in a release
build and reads like a code error rather than a toolchain one:

```
GeneratedPluginRegistrant.java: error: cannot find symbol
  class FlutterFirebaseAnalyticsPlugin
```

The registrant is generated and correct — a **Kotlin-only plugin** simply produced no classes.
Under AGP 9 a plugin either applies `kotlin-android` itself or relies on AGP's built-in Kotlin,
and `android/gradle.properties` decides which via `android.builtInKotlin`. When the flag is
`false` but the plugin skipped applying the Kotlin plugin (many guard on `agpMajor >= 9`), its
sources never compile. Flipping the flag to `true` usually fails the other way, since plugins
that *do* apply `kotlin-android` are then rejected — check which of your plugins apply it
before flipping. The narrow fix is to apply the plugin to that one module from the app's root
`build.gradle.kts`, with a `jvmTarget` matching the app's Java level.

## Step 3 — Verify the artifact before uploading

### Privacy declarations, if the app records audio or video

Check this **before** uploading, because the iOS failure mode is silent (see Step 5). A plugin
that links microphone or camera APIs — `flutter_webrtc`, recorders, scanners — obliges the
*host app* to declare them. Plugins frequently declare nothing on their own behalf:
`flutter_webrtc` ships an Android manifest containing literally no `uses-permission` at all.

```bash
# iOS: linking mic/camera APIs with no purpose string ⇒ ITMS-90683, rejected at processing
plutil -p ios/Runner/Info.plist | grep UsageDescription

# Android: without RECORD_AUDIO in the manifest, Permission.microphone.request()
# resolves denied WITHOUT EVER SHOWING A DIALOG, and getUserMedia fails
aapt2 dump permissions <artifact> | grep RECORD_AUDIO
```

Both defects break the feature on a real device only — a simulator will not reveal either.
Declare what the app actually uses and nothing more: an audio-only call needs `RECORD_AUDIO`
and `MODIFY_AUDIO_SETTINGS`, not `CAMERA`, and an unused permission is one more thing the
listing has to justify. On iOS the purpose string is required by *linked* APIs rather than
used ones, so a camera string may be needed even for an audio-only feature.

### A device launch test, and the adb trap that fakes a pass

For a first release or any build whose manifest/plugins changed, install the release artifact on
a device or an existing emulator and launch it — static checks cannot catch a startup crash. But
know this failure mode first, because it produces a **passing test against the wrong build**:

```
adb: failed to install …: INSTALL_FAILED_UPDATE_INCOMPATIBLE:
     Existing package com.example signatures do not match newer version; ignoring!
```

After that failed install, `adb shell am start` happily launches the **stale package already on
the device** — healthy process, clean logcat, all green, none of it about your build. Uninstall
first, and only trust the launch test after `dumpsys package <pkg> | grep versionCode` reports
the versionCode you just built:

```bash
adb uninstall <pkg>; adb install <artifact>
adb shell dumpsys package <pkg> | grep versionCode     # MUST match the new build
adb shell am start -n <pkg>/.MainActivity && sleep 12
adb shell pidof <pkg>                                   # alive?
adb logcat -d | grep -c "FATAL EXCEPTION"               # 0?
```

### Signature

A debug-signed artifact is rejected by every store, and the failure message is rarely
clear about why. One command settles it:

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@17   # keytool/apksigner are often not on PATH
$ANDROID_HOME/build-tools/*/apksigner verify --print-certs <artifact>
```

The certificate DN should name the organization, not `CN=Android Debug`.

Worth telling the user once, if it applies: when Play App Signing is enabled, Play
re-signs with Google's key, so an AppGallery build carries a *different* signature and
users cannot update across the two stores. That is expected, not a defect.

## Step 4 — Upload, but do not submit

Both transports default to uploading into a holding state — a draft version on AppGallery,
an internal track on Play — and require an explicit flag to send anything for review.

Keep that discipline. Uploading is reversible and cheap; submitting enters a queue that a
human then has to manage, and on some stores a rejection carries a cooldown. Only pass the
submit flag when the user asks for that specific release, not because it seems like the
natural end of the task.

See the store reference for the exact command.

## Step 5 — Verify it actually landed

**AppGallery has a second trap here: the package check is asynchronous and its verdict never
reaches the API.** `app-info` reporting the right `versionCode` does not mean the package was
accepted — poll `appid-list?packageName=<pkg>` until it returns your appId, and read
`references/appgallery.md` if it returns a different one (that is error 9005, a duplicate app
record owning the name).


**Exit code 0 means the tool finished, not that the store accepted the build.** Always query
the store back and confirm the version matches what you just built. This is not a formality —
it is the only way to catch a store that reports success and then silently discards the build.

```bash
# Play — what the track actually holds
fastlane run google_play_track_version_codes \
  package_name:<pkg> track:internal json_key:<key>           # → Result: [7]

# App Store Connect — the ONLY proof an iOS upload survived
#   (needs an ASC API JWT; altool cannot answer this)
GET /v1/builds?filter[app]=<appId>&sort=-uploadedDate        # → version + processingState

# AppGallery
python3 "$MOBILE_PUBLISH_SKILL_DIR/scripts/agc.py" info                                  # → versionNumber
```

**iOS is the dangerous one.** `altool` reporting `UPLOAD SUCCEEDED with no errors` means the
bytes arrived, nothing more. Apple then runs static analysis, and a build it rejects there
**never appears anywhere** — not TestFlight, not `/v1/builds` — while the only notification
goes by **email, to the account-holder address**, which is often not the developer's own
mailbox. A build that uploads twice and vanishes twice is this, not lag. Confirm
`processingState: VALID` before believing an iOS upload landed.

## Step 6 — Report what no API can do

Publishing tooling moves binaries. It does not create the store listing, and every store
rejects releases that are missing listing work:

- **A test account**, whenever the app is login-gated. Reviewers who cannot get past the
  login screen reject the build. This is the most common rejection across every store.
- **Screenshots** — minimum 3, portrait, 1080×1920 for phones.
- **Written justification for sensitive permissions** — location, camera, and advertising
  ID. If an ID permission arrives transitively via an analytics SDK and no ads are served,
  say exactly that.
- **Privacy policy URL**, reachable and describing what the app actually collects.
- **Achievements and leaderboards**, if the app has them — minted per store, icons uploaded by
  hand on Android. See `references/game-services.md`.

**Reuse the listing copy that already exists.** Before writing any marketing text, look for
`android/fastlane/metadata/android/<locale>/` and `ios/fastlane/metadata/<locale>/` — title,
short/full description, changelogs, and `images/phoneScreenshots/` are usually already there
in every locale the app ships. Reusing them keeps the stores consistent and avoids inventing
copy for an app you are describing blind. Count characters against store limits with a
**Unicode-aware** tool: `awk`'s `length()` counts bytes, so an Arabic tagline reads as ~2×
its real length and looks like it breaks an 80-character limit when it does not.

**The privacy policy must be at least as broad as the privacy declarations.** Stores ask you
to declare advertising, third-party sharing, and cross-border transfer, then link the policy
next to it — and reviewers compare them. A policy narrower than the declaration is a
documented rejection reason, so read the actual policy before ticking the boxes. Check the
policy renders in the **listing's language** too: a localized store listing pointing at a
policy URL that falls back to English is a bad look on an otherwise complete submission.

Surface these as a checklist rather than assuming the user has them. Finishing an upload
and staying silent about a missing test account just moves the failure a week later.

## Credentials

Each store uses its own mechanism, described in its reference. Two rules hold everywhere:

**Never print a secret into the conversation.** Load it from a file directly into its
destination. A transcript is a place secrets persist, so if the user pastes one anyway,
use it, then tell them to rotate it.

**One credential covers all their apps.** Both stores support an account-level credential
granted access to every app. If you find yourself setting up a key per app, that is a sign
the credential was scoped too narrowly at creation.

## Working style

Prefer measuring over guessing. Store APIs are cheap to probe read-only, and a single
targeted call usually distinguishes "who am I?" from "what may I touch?" — a distinction
that plausible reasoning gets wrong. The AppGallery reference documents a real case where
a wrong ID produced a 403 that looked exactly like a permissions problem and cost an hour
of investigating the wrong thing.
