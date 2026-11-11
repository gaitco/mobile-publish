# Shorebird: store release or OTA patch

Use the installed CLI's `--help` and existing project release workflow. Official references:
[release](https://docs.shorebird.dev/code-push/release/),
[patch](https://docs.shorebird.dev/code-push/patch/), and
[CI scripting](https://docs.shorebird.dev/code-push/ci/scripting/).
Do not upgrade the CLI, change the app's SDK, initialize Shorebird, or migrate an app's
runtime as an incidental part of publishing.

## Establish the target

Read `shorebird.yaml` from the actual Flutter module; resolve the flavor-specific app ID.
Check the intended account, exact release versions, target platforms and latest patches
against Shorebird and the stores. Android and iOS release versions can differ. Record
which installed/store release each patch will affect; do not infer this from `pubspec.yaml`
or use an unverified `latest` target.

```bash
# From the app module, substitute the exact resolved version and project flavor flags.
shorebird releases info --release-version "$ANDROID_RELEASE" --json
shorebird releases info --release-version "$IOS_RELEASE" --json
shorebird patches list --release-version "$ANDROID_RELEASE" --json
shorebird patches list --release-version "$IOS_RELEASE" --json
```

Match the original release's flavor, entrypoint, Dart defines, target architectures,
obfuscation/symbol settings, export options, signing and SDK. Restore any required
dependencies/configuration before building. Keep central credentials out of logs and Git.
CI uses its protected Shorebird authentication (normally `SHOREBIRD_TOKEN`), not a token
checked into the project or passed as a literal argument.

## New store version with Shorebird

A new market release needs a new store build number. Use `shorebird release`, which
builds the update-capable runtime and registers its baseline with Shorebird. Then inspect
and upload **those exact artifacts** using the usual store transports. Registration with
Shorebird does not upload the app to Google/Apple/Huawei and does not send users a patch.

The shared `publish.sh --prepare` selects this path for `shorebird.yaml`, builds all selected
platforms with `shorebird release --platforms ... --flutter-version system`, and records
artifact hashes plus the Shorebird configuration. With AppGallery selected it requests
`--artifact apk`, producing APK/AAB from the Shorebird release rather than a separate plain
Flutter build. It refuses missing outputs or a failed Shorebird command without fallback.
The helper covers the simple unflavored app; inspect/use the existing project workflow
for custom SDK, flavor, entrypoint, defines or signing/export flags.

After artifact inspection, `publish.sh --upload-prepared` verifies the same runtime,
configuration and artifact hashes and transfers them without rebuilding. Keep the
preparation and upload store/track selections identical. For a custom project workflow,
pin the artifacts' SHA256 before inspection and verify it again before transfer.

For CI-only build verification, the installed CLI supports `shorebird release ... --dry-run`;
this does not register a distributable baseline. Do not upload that validation artifact as
if it were an actual registered Shorebird release. If Android registration succeeds but
iOS fails, inspect the partial release with `releases info` and finish/recover the intended
baseline; do not blindly recreate Android or claim both platforms are ready.

## OTA patch: both platforms before either upload

An OTA patch changes an existing Shorebird release, not its store version/build number.
Do not use `publish.sh`, `shorebird release` or any store upload command for this path.

1. Identify the intended Android and iOS baseline versions and original build inputs.
   Verify the changed source is the intended revision and keep it fixed through checks
   and publishing. Run relevant format, analysis, regression tests and runtime checks.
2. Complete a real patch build/dry run against **each** exact baseline with its original
   build flags. Inspect the full native/plugin/dependency and asset comparison output;
   source diff or Dart analysis alone is insufficient. Preserve logs/results per platform.

   ```bash
   shorebird patch android --release-version "$ANDROID_RELEASE" --dry-run
   shorebird patch ios --release-version "$IOS_RELEASE" --dry-run
   ```

3. Both dry runs, native/asset comparisons and relevant runtime checks must pass before
   publishing to either platform. If either platform fails, is incompatible, has a known
   runtime issue, or remains unchecked, publish **neither** patch. State the exact blocker,
   affected functionality and whether the failure is confirmed or the path is unverified.
   Do not bypass warnings with `--allow-native-diffs` or `--allow-asset-diffs`. Do not ignore
   mismatched build flags. Explain when a new store release or a separately scoped compatible
   patch is required; a patch request does not authorize that replacement.
4. After a fix, repeat the affected checks and establish that **both** remain ready.
   Publish only the checked revision, exact versions, original flags and intended track.
   The track defaults to stable only when that matches the user's requested rollout.
   A multi-platform `patch` command is not an atomic compatibility gate: it can publish
   Android before iOS fails. Finish both dry runs first even if publishing with one command.
5. Query `shorebird patches list`/`releases info` for both exact versions and verify the
   patch IDs, active target platforms and tracks. If one upload fails, report the partial
   publication accurately, inspect remote state before retrying, and do not blindly rerun
   an already accepted patch. No automatic rollback or track promotion without scope.

CI must put both dry-run results behind a dependency gate before any publish job, using
the same source revision and original build inputs. A green Android job cannot release
while iOS is failing or pending. Hosted-runner billing problems do not waive either gate;
run the required builds locally or report that publication is blocked.
