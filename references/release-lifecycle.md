# Reviewed release adapters

The runtime/store policy remains `mobile-publish.config.json`. A separate
`mobile-publish.release.json` references the existing project build, QA and store
tools; it contains no credentials. The agent inspects the existing lanes and CI,
resolves these references once, and commits them within the requested project scope.
Never copy the illustrative commands below blindly into an application.

## Profile contract

Required fields: `schema_version: 1`, `environment`, `identities` (store → exact
package/bundle), `build` (ordered argv arrays), `artifacts` (store → exact relative
file), `qa` (argv), and `stores` (store → `status`, `verify`, `upload` argv arrays
and `certificate_sha256`). Optional `sdk: {version, command}`, `flavor`, `target`,
`defines_files` reference existing inputs. An exact FVM/tool-versions pin is read
first; conflicting pins block. Existing CI literal/env pins are used when there is
no closer reviewed SDK pin. The SDK command must report the same frameworkVersion
through `--version --machine`. No latest/channel/system substitution.

Use project scripts to wrap commands requiring a different working directory. No
shell eval is used. All commands run from the app root, with stdin disabled and
captured output; do not rely on interactive login. Credentials come from the
operator's existing protected files/environment or approved CI secrets. Never put
credential values in argv, the profile or emitted evidence. Review scripts for
side effects, including status/QA, before execution.

Placeholders are `{skill}`, `{request}`, `{artifact}`, `{artifact_sha256}`, `{app_id}`,
`{version}`, `{build}`, `{track}`, `{environment}`. Artifact placeholders are
available only for per-store verify/upload commands. `{request}` is a private JSON
file with the resolved request and `artifacts` hash map plus `artifact_files` paths.
Only structured, allowlisted evidence is journaled; raw tool logs are suppressed.
Unknown placeholders or missing adapters stop before building.

Example shapes (adapt the existing commands; these are not ready-made lanes):

```json
{
  "schema_version": 1,
  "environment": "production",
  "identities": {"play": "com.example.app"},
  "sdk": {"version": "3.47.7", "command": ["flutter"]},
  "build": [["bash", "scripts/existing-signed-build.sh"]],
  "artifacts": {"play": "build/app/outputs/bundle/release/app-release.aab"},
  "qa": ["python3", "scripts/release_qa.py", "{request}"],
  "stores": {
    "play": {
      "certificate_sha256": "REPLACE_WITH_REVIEWED_PUBLIC_CERTIFICATE_SHA256",
      "verify": ["python3", "{skill}/scripts/verify_artifact.py", "{artifact}"],
      "status": ["python3", "scripts/play_status.py", "{request}"],
      "upload": ["bash", "scripts/existing-upload-only.sh", "{artifact}", "{track}"]
    }
  }
}
```

The build adapter owns the existing SDK/flavor/target/defines and clean build/test
sequence. A Shorebird build uses its existing `shorebird release` with the verified
SDK version; it never falls back to Flutter. It may register a baseline remotely,
so inspect partial registration after a failed build before repeating it.

An upload adapter must upload **the passed archived artifact**, without rebuilding,
version mutation, review submission or unexpected metadata edits. A fixed-path
Fastlane lane needs a narrow reviewed artifact-path option/wrapper before use.
Never overwrite a project's curated changelogs or swap its lane for generic supply.

## Native verification and QA

`verify_artifact.py` reads the actual AAB/APK manifest, verifies signatures with
jarsigner/apksigner and reads the signer certificate. IPA checking requires macOS:
codesign deep/strict verification, app/extension profiles, expiry, distribution
type, authorized signer and signed entitlements. Install the existing project SDK
tools on PATH; missing tools fail closed. It does not replace functional tests,
privacy declarations, project entitlements review or device launch verification.

An equivalent reviewed verifier must emit one JSON object:

```json
{"app":"com.example.app","version":"1.2.0","build":"42","platform":"android",
 "sha256":"ARTIFACT_SHA256","signature_valid":true,"distribution":true,
 "certificate_sha256":"APPROVED_SIGNER_SHA256"}
```

QA emits `{"artifacts": {"play": "SHA256", "asc": "SHA256"}, "platforms":
["android", "ios"], "launched": true, "dedicated": true}` only after verifying
installed identity/build and launch behavior on dedicated targets for the exact
artifacts. A store IPA cannot be installed on an arbitrary personal phone. Use a dedicated
approved QA export from the same immutable archive and prove identical compiled
app/native/assets and installed identity/build, with only distribution signing
differences, or another approved capable device/distribution workflow. Bind that
proof to the store artifact hash. If that correspondence cannot be established,
report the unverified path and block publication. Do not fabricate
this JSON or uninstall an app carrying personal data to manufacture a pass.

## Exact store status

Each status adapter emits one object with `app`, `version`, string `build`,
`platform`, `track` (`testflight` for ASC), `state`, `reference`,
`publish_authorized`, `complete`, `version_available`.

States: `absent`, `processing`, `accepted`, `rejected`, `unknown`.
`accepted` requires a safe opaque build/release reference, not a URL. `absent`
requires `complete: true` and `version_available: true`: authoritative evidence
that this exact number is unused, not just absent from one current track/list.
If an API cannot establish that, return `unknown`; resolve using the trusted
central allocation/release record or operator's authorized console evidence.
Do not manufacture completeness to unblock the coordinator.

`publish_authorized` requires verified operator identity and target-scoped release
permission from existing grants/approved CI. Successful GET alone proves neither
write permission nor version availability. Do not test permissions by creating a
release, edit, organization or account.

- Play: use authenticated read-only [release summaries](https://developers.google.com/android-publisher/api-ref/rest/v3/applications.tracks.releases/list),
  paginate and match exact track/build. Track listings alone do not expose every
  previously used code. Existing `google_play_track_version_codes` creates an edit
  internally and is not a pure read-only permissions probe.
- ASC: use installed `asc builds list --help` for exact app, marketing version,
  build number, platform and pagination. `VALID` means processing accepted;
  processing/invalid/failed are distinct. A build absent after transfer is unknown,
  not proof it was never received. Do not repeatedly upload a disappearing IPA.
- AGC: reuse `agc.py`'s client. Verify exact version and package ownership via
  appid-list after asynchronous processing; app-info alone is insufficient.

Adapters may poll processing with a bounded deadline; after it expires preserve
`processing`/`unknown` and resume querying later. Upload exit 75 is reserved for
a confirmed transient transport failure; the coordinator queries before retrying
once. Generic nonzero, authorization, signing, processing and runner errors are
not retry signals. Even exit 0 needs acceptance queried back. Never emit signed
URLs, tokens, headers, full env dumps or raw API errors in evidence.

## Resume, coordination and retention

Private state: `~/.local/state/mobile-publish/<application-environment-hash>/<run-id>/`.
Run JSON contains hashes/source revision, stages/timings and per-store references;
archived artifacts survive Flutter clean. Do not clean this directory to retry.
The same resolved request resumes the same run; changed requests are refused
while another run is pending. Inspect its journal first. An unused preparation
can be closed with `--close-prepared RUN_ID`, then fixed source prepared anew.
Closing is refused after any transport attempt; reconcile exact store state then
resume the original artifacts. It never deletes a cloud baseline or rolls back.
At most 20 completed/closed runs are retained per application/environment;
pending runs and their required artifacts are never pruned automatically.

The local advisory lock spans the whole operation and all selected stores, across
checkouts on that machine. It does **not** lock other computers. Team publishing
must use the existing central release workflow with application/environment
concurrency, independent of source branch, and protected publishing credentials.
Persist private journal/artifacts in approved restricted CI storage when runners
are ephemeral; never upload them publicly or include credentials. Without durable
trusted state do not claim cross-run resume or distributed version allocation.

Keep release dispatch separate from PR tests. Inspect runner labels/capacity,
active concurrency jobs and billing errors before changing YAML; never silently
raise spending or install a persistent self-hosted runner. Record actual stage
durations/retry counts before making performance claims.

OTA, review submission, runtime migration and cloud retirement retain their
dedicated runbooks and explicit authorization boundaries. This coordinator does
not provide a generic command escape hatch for those operations.
