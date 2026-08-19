# Achievements & leaderboards — Play Games Services and Game Center

Console configuration that must exist **before** submission, in the same category as IAP
products: no API in the publishing path creates it, and a build referencing IDs that were
never minted fails at runtime rather than at upload.

Everything below is drawn from a shipped client integration (domono: `com.gaitco.domono`) rather
than from the vendor docs. Be precise about what that verifies: domono's **Android** side is
demonstrably configured — `games-ids.xml` holds 12 real console-minted achievement IDs and a
leaderboard ID. Its **iOS** side has the entitlement and plugin wired, but the App Store Connect
Game Center state could not be confirmed either way.

**Game Center cannot be configured through the App Store Connect API.** A key returns
**403 FORBIDDEN** on every Game Center collection — `/v1/gameCenterDetails`,
`/v1/gameCenterAchievements`, `/v1/gameCenterLeaderboards` — so this is console-only work, like
the AppGallery icon. And do not read a `null` from `/v1/apps/{id}/gameCenterDetail` as proof
Game Center is unconfigured: the same key returns `null` there *and* 403 on the collections, so
it cannot tell "not set up" apart from "not allowed to look".

## First decide whether to integrate at all

This is a real decision, not a checkbox. Skip it when the app already has its own progression:

> Duplicates shipped systems. [The app] already has 30 server-derived achievements, a seasonal
> ranked ladder, and unified identity. PGS would mirror all three, Android-only, with manual
> console upkeep. […] Setup competes with the go-live critical path — PGS needs a Cloud
> project, OAuth client, Play App Signing SHA-256, testers, and a games-project publish.

— a real deferral decision, and the right one for an app whose progression is server-authoritative
and cross-platform. The cheap slice, if you do want it, is **achievement mirroring**: one plugin
call reaches both stores, and unlocks that already happen server-side need no second source of
truth. Leaderboards and Play Game Stats can wait.

## One plugin, both stores

`games_services` routes to **Play Games Services** on Android and **Game Center** on iOS, so a
single integration covers both. Treat it as a **mirror, never a source of truth**:

> PGS is a mirror of the server-authoritative progression system: the backend is the source of
> truth, and the client only reflects that state into Google/Apple's native UI. Nothing here
> grants rewards.

Keep a local "already mirrored" set so a sync only issues unlock calls for newly-unlocked codes,
and only cache a code once the platform actually accepted it — otherwise one failed unlock is
cached as done and never retried. And **cap every plugin call with a timeout** (a few seconds):
on a device without Play Games, a channel can simply never answer, and once real IDs are wired
in, a fire-and-forget future that never completes is a leak your unit tests will hit as a hang.

## The ID asymmetry — the thing that shapes your code

| | Android (PGS) | iOS (Game Center) |
|---|---|---|
| Who mints the ID | Play Console, **auto-generated** | **You choose it** |
| Shape | opaque token, `CgkIxsS4qqcWEAIQEw` | any string |
| Consequence | needs a lookup table | can equal the backend `code` verbatim |

So Android forces a mapping from your backend's achievement `code` to an opaque ID, while iOS
needs no mapping at all. Key that table by the **live** backend codes — the ones your service
actually unlocks — and say so in a comment, because the failure mode is silent: a superseded
seeder in domono left **nine orphaned achievements** configured in the console against codes
nothing emitted any more.

## Android setup

IDs come out of Play Console as a generated `games-ids.xml` you drop into
`android/app/src/main/res/values/`. It carries `app_id`, `package_name`, and one string per
achievement and leaderboard. The `app_id` is just the games project's numeric ID — the cloud
project *number* shown on the PGS Configuration page — so you can hand-write a minimal
`games-ids.xml` with only `app_id` before the console ever offers the generated one.

**Reference the app id as a string resource, never inline:**

```xml
<!-- @string/app_id comes from games-ids.xml. The Games SDK reads this at
     launch and a non-string/invalid value CRASHES STARTUP. -->
<meta-data
    android:name="com.google.android.gms.games.APP_ID"
    android:value="@string/app_id" />
```

Inlining the number is the classic mistake: it is parsed as an integer, and the app dies on
launch rather than failing gracefully at the point of first use.

**A missing APP_ID is safe — verified on device.** A release build with `games_services` linked
(its `playgamesinitprovider` runs at startup) and **no** `APP_ID` meta-data at all launches
cleanly on Android 14: process up, zero FATAL EXCEPTION. So the crash trap is an *invalid or
inline* value, not absence — you can ship the mirror code before the Play Console games project
exists, and add the meta-data only once a real `app_id` is minted.

PGS lives on a **Google Cloud project** (typically the app's existing Firebase project) and needs
an OAuth client bound to the **Play App Signing** SHA-256 — the one from Play Console → App
integrity, not the local keystore. Same fingerprint the App Links `assetlinks.json` needs, so do
both in one visit. The games project must also be **published**, and testers added, before it
works for anyone but you.

**Bulk-creating achievements — two paths, and which works depends on the project.** The
Configuration API (`gamesconfiguration.googleapis.com`) created domono's configs in bulk, but on
a games project created fresh in 2026 (karak, next-gen-IDs era) **every write returned a bare
500 "Internal error"** — achievements and leaderboards alike, for every principal *including a
service account with no grant at all*. That last part is the diagnostic: an ungranted caller
should get 403, so a 500 for it means the project fails before authorization is even evaluated,
and no permission work will fix it. Reads kept working throughout; enabling the API on the cloud
project and re-toggling next-gen IDs changed nothing. Do not burn an hour on retries — fall back
to the console's **ZIP import** (Play Console → Play Games Services → Achievements → Import).
On projects where the API does write, its image endpoint 503s, so icons are manual either way
unless the ZIP path carries them.

**The ZIP import format** (achievements only — leaderboards stay a by-hand console form when the
API 500s). Three CSVs plus 512×512 PNG icons, zipped flat:

- `AchievementsMetadata.csv` — `Name,Description,Incremental,Steps,State,Points,Order`,
  **no header row**; names must be unique and comma-free, because they are your only join key
  afterwards.
- `AchievementsLocalizations.csv` — `Name,LocName,LocDesc,locale`. **Rows in the game's default
  locale are rejected as "Wrong locale"** — the metadata CSV *is* the default locale, so this
  file may only carry the other languages (ar rows for an en-US-default game).
- `AchievementsIconsMappings.csv` — name → icon filename; pointing several achievements at one
  shared fallback icon is accepted.

The import creates drafts and returns nothing. **Verify every console save by listing back via
the API** — reads work even when writes 500 — because one "Save as draft" click can silently
persist nothing, and only the empty API list reveals it. Root cause when automating: the
console's Save button stays **disabled** until the form model goes dirty, and setting an
input's value programmatically (even with a native setter + dispatched input/change events)
updates the character counter but not the dirty flag — the click then lands on a disabled
button, firing no RPC and no error. Only real keystrokes (a trusted keyboard event stream)
enable Save; check `button.disabled` before clicking and you turn a silent failure into a
loud one.

Two more rules discovered the hard way:

- **Import is create-only.** The validator rejects any row whose name (or localized name)
  matches an *existing* achievement — "Duplicate names - Remove or rename". So a ZIP can never
  update what's already imported; fixes to existing achievements go through each one's
  edit page (`games/edit-achievement?id=CgkI…`), which is at least directly URL-addressable.
- **Every achievement must have a unique icon**, or publishing blocks with "Multiple
  achievements have the same icon" — one action per achievement, 36 of them if you shared
  family art across tiers. Plan one distinct icon per achievement from the start; a cheap
  compliant scheme is family art + a bronze/silver/gold tier badge composited on
  programmatically (PIL), which is unique in both pixels and meaning.

**Joining minted IDs back to your codes.** After import, the `CgkI…` IDs exist only in the
console/API, keyed by display name. Keep a `display name → backend code` map from the moment you
generate the CSVs, then list achievements via the API and produce the `code → CgkI…` table
mechanically. Never hand-transcribe 36 opaque tokens.

## iOS setup

Two places, and forgetting the second is the trap:

```xml
<key>com.apple.developer.game-center</key>
<true/>
```

…in `Runner.entitlements`, **and** the Game Center capability enabled on the App ID in the Apple
Developer portal, so device and release provisioning profiles carry it.

**The simulator does not enforce the capability.** Game Center therefore works in the simulator
and fails on device and in the release build — the same shape as the microphone purpose-string
failure in the main workflow, and it will not show up in simulator testing.

Achievements and leaderboards are then defined in **App Store Connect → your app → Game Center**.
Because you choose the IDs, use the backend code verbatim and skip the mapping table.

## Checklist

- [ ] Decided it is worth the console upkeep, given what the app's own backend already does
- [ ] Android: PGS configured on the Cloud project; OAuth client bound to the Play App Signing SHA-256
- [ ] Android: `games-ids.xml` in `res/values/`; `APP_ID` meta-data references `@string/app_id`
- [ ] Android: achievements created (ZIP import when the Config API 500s; import is create-only), one **unique** icon per achievement
- [ ] Android: every console save verified by an API read-back (saves can silently not persist)
- [ ] Android: games project published, testers added
- [ ] iOS: `com.apple.developer.game-center` entitlement **and** the App ID capability in the portal
- [ ] iOS: verified on a **real device** — the simulator does not enforce the capability
- [ ] IDs keyed to the live backend codes, with no orphans from a superseded catalogue
- [ ] Mirror only: no platform call grants a reward the backend did not already grant
