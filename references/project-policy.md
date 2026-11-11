# Project publishing policy

Commit `mobile-publish.config.json` inside the actual Flutter module. It contains only
non-secret project decisions. Example for an app approved for Play and Apple:

```json
{
  "schema_version": 1,
  "runtime": "flutter",
  "stores": ["play", "asc"]
}
```

`runtime` is `flutter` or `shorebird`; stores are the approved nonempty subset of `play`,
`asc`, `agc`. The account used by the developer is not part of this file. Do not copy this
example's stores into a project without checking its existing release setup.

For Shorebird projects, optional `shorebird_warning_users` is a positive integer, default
**400**. Publishing pauses when estimated active devices exceed it. This is a warning
threshold, not a switch to uninstall Shorebird or a quota/billing setting. Only change
the threshold when the user requests it; see [usage decisions](shorebird-usage.md).

- Standard Flutter projects do not install or contact Shorebird, even when it is installed
  on the operator's machine. Domino is a standard Flutter project.
- Shorebird projects keep their configured runtime. Missing local access or a conflicting
  configuration blocks publishing rather than causing a plain-Flutter fallback.
- `shorebird.yaml` must agree with policy. A leftover/missing file is investigated; no
  automatic initialization, deletion, migration or subscription change is allowed.
- Existing standard Flutter projects without policy may use an explicit `--store` after
  inspecting their release setup. A default `all` does not discover stores from credentials.
- A policy change invalidates prepared artifacts. Prepare, inspect and transfer the same
  artifact bytes and project decision.

For flavors, special build defines, a different pinned SDK or custom Fastlane lanes, keep
the existing project workflow. The policy still applies to that workflow: an upload lane
must not replace the project's selected runtime or expand its approved destinations.

## Release context

For coordinated releases, keep `mobile-publish.release.json` beside the policy. It
references the existing build workflow; it does not replace the runtime/store policy.
The resolver rejects multiple app modules, conflicting SDK pins and overrides of the
reviewed environment/flavor/entrypoint. SDK priority: existing FVM/tool-versions pins,
then a reviewed exact profile pin, then unambiguous existing CI flutter-version. Never
resolve `latest`, a channel or `system` as an approved SDK version.

`python3 scripts/release_request.py /path/to/app` is a read-only context report. It
records source/input hashes, identities, version/build and file references, never define
contents or credential values. Store upload is the default operation; OTA, review and
runtime migration remain explicitly separate operations. The coordinator executes store
uploads only; use their dedicated runbooks for the other operations.
