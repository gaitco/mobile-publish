# Google Play

Artifact: `.aab` (Play requires App Bundles for new apps). Transport: `fastlane supply`,
already installed — do not hand-roll the API. Play's publishing flow is a *transaction*
(`edits.insert` → `bundles.upload` → `tracks.update` → `edits.commit`), and a half-finished
edit leaves a dangling transaction. `supply` handles that plus resumable uploads.

`supply` runs standalone — no `Fastfile`, `Gemfile`, or `fastlane/` directory in the repo.

## Credentials

A **Google Cloud service account JSON**, one per Play Console account, covering every app.

Setup, if the user doesn't have one. Start from **Play Console**, not Google Cloud — it
links the cloud project and the Play account for you, which is the step people get wrong
when they start from the GCP side and end up with a key Play has never heard of:

1. Play Console → **Developer account** → **API access** (in the left sidebar, below
   Download reports; it is not under Settings). Direct URL, if you know the account id
   from any console URL: `play.google.com/console/u/0/developers/<accountId>/api-access`
2. Link a Google Cloud project if prompted, then **Create new service account** — it hands
   you off to GCP to create the account, and back
3. In GCP, create a **JSON key** for that service account and download it
4. Back in Play Console → **Users and permissions**, grant the service account
   **Release** permissions (Releases: production and testing tracks) for the apps it
   should publish
5. Grants take a few minutes to propagate; a 401 immediately after granting is usually
   just propagation, not a misconfiguration

**Do not reuse a Firebase Admin SDK key.** Those are `type: service_account` and look
right, but they belong to a Firebase project, carry far broader privileges than publishing
needs, and have not been invited into Play Console. Create a dedicated one.

Unlike AppGallery, this credential lives as a **file**, because `supply` takes a path.
Keep it out of any repo:

```bash
mkdir -p ~/.config/play && chmod 700 ~/.config/play
cp <downloaded>.json ~/.config/play/service-account.json
chmod 600 ~/.config/play/service-account.json
```

Verify it before building anything — a bad credential is the most common failure and costs
nothing to check:

```bash
fastlane run validate_play_store_json_key json_key:~/.config/play/service-account.json
```

## The first release must be manual

Google does not allow the API to upload the **first** version of a new app. The initial
build has to go through the Play Console by hand, along with the store listing, content
rating, and data safety form. Every release after that can be automated.

If `supply` fails on a brand-new app with a message about the app not being found, this is
almost always why — not a credential problem.

## Upload — check for existing lanes first

**Look for `android/fastlane/Appfile` before doing anything else.** Several repos here
(`domono`, `arraf`, `3lahwa`) already have configured lanes, and they encode per-app
decisions — the AAB path, the package name, whether changelogs are published from
`metadata/android/<lang>/changelogs/<versionCode>.txt`. Bypassing them with a standalone
invocation loses the changelog and risks contradicting the repo's own setup.

When lanes exist, read the `Fastfile` and use them:

```bash
cd <repo>/android            # wherever fastlane/ lives
fastlane verify              # confirm the key reaches the Play API
fastlane upload track:internal   # upload an already-built AAB, no rebuild
fastlane internal            # build + upload to internal testing
fastlane production          # build + upload to production as a DRAFT
```

Lane names vary by repo — read the `desc` lines in the `Fastfile` rather than assuming.
Note that build-and-upload lanes compile the **current working tree**, so uncommitted
changes end up in the artifact. Publish from a clean checkout, or build separately and use
the upload-only lane.

### No lanes in the repo — standalone `supply`

Default to the **internal** track. It is visible only to testers you list, needs no review,
and is the correct holding area equivalent to an AppGallery draft.

```bash
fastlane supply \
  --json_key ~/.config/play/service-account.json \
  --package_name <com.x.y> \
  --aab <path-to-.aab> \
  --track internal \
  --skip_upload_metadata true \
  --skip_upload_images true \
  --skip_upload_screenshots true \
  --skip_upload_changelogs true
```

**The four `skip_upload_*` flags are not optional in practice.** By default `supply` syncs
the store listing from a local `fastlane/metadata/android/` directory. When that directory
doesn't exist — which it won't, since we run standalone — you are one flag away from
pushing empty metadata over a live listing. Skip them unless the user explicitly wants to
manage listing text from the repo.

Useful additions:

- `--validate_only true` — dry run against Play, uploads nothing. Good first invocation on
  an app you haven't published to before.
- `--release_status draft` — upload to a track without activating the release.
- `--changes_not_sent_for_review true` — commit the edit but leave review to a human in the
  console. This is the Play analogue of withholding `--submit` on AppGallery.

Promote to production only on explicit request:

```bash
fastlane supply --json_key ... --package_name ... --track internal \
  --track_promote_to production --skip_upload_metadata true --skip_upload_images true \
  --skip_upload_screenshots true --skip_upload_changelogs true
```

## Verify it landed

`supply` exiting 0 means the edit committed, not that the build is where you think. Ask
Play what version codes the track actually holds:

```bash
fastlane run google_play_track_version_codes \
  package_name:<com.x.y> track:internal \
  json_key:~/.config/play/service-account.json
```

The version code you just built should appear in that list.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `Google Api Error: applicationNotFound` | First release not yet made manually, or wrong `package_name`. |
| 401 / `The current user has insufficient permissions` | Service account not invited in Play Console, missing Release permission, or grant hasn't propagated yet. |
| `APK specifies a version code that has already been used` | Version codes are global across all tracks and archived releases, not per-track. Bump it. |
| `Only releases with status draft may be created on draft app` | The app itself is still a draft in Play Console; add `--release_status draft`. |
| Listing text or screenshots disappeared | A `supply` run without the `skip_upload_*` flags overwrote them from a non-existent local metadata dir. |
| Upload succeeds, testers see nothing | Internal track needs a tester list configured in the console, and testers must accept the opt-in link. |
