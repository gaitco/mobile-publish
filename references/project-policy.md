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
