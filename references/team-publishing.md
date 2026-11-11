# Team publishing

Each operator installs the same approved skill revision and uses their own authorized
store credentials, signing material and, only for projects that use it, Shorebird access.
The skill is not an account or a mobile SDK distribution.

From a trusted clone of `gaitco/mobile-publish`, inspect and install an approved **full
commit SHA** (set `APPROVED_COMMIT` to the company-reviewed revision):

```bash
python3 scripts/install_skill.py --revision "$APPROVED_COMMIT" --target all --check
python3 scripts/install_skill.py --revision "$APPROVED_COMMIT" --target all --register
```

Use `--target codex` or `--target claude` when only one agent is used. The installer checks
all selected clones before changing them, rejects foreign origins or local edits, and
only fast-forwards existing checkouts. It never force-resets, stashes, logs out, copies
credentials, installs Shorebird, modifies the shell, or silently changes a subscription.
It adds one managed mobile-publishing rule to the selected operator's global instructions,
preserving other rules. Re-running the command does not duplicate the rule.

The rule routes mobile store/OTA requests, including «ارفع» in a mobile-app context,
through this skill. Backend, website and file uploads retain their own workflows.
Repository instructions should also say to use `mobile-publish` for mobile releases so
operators who have not installed it discover the prerequisite before publishing.

If the installer refuses an old checkout, inspect its changes/origin before updating it.
Do not resolve the refusal by deleting the checkout or resetting someone else's work.
An update to the company Git repository alone does not update colleagues' computers.

## Independent access

A standard Flutter project needs Flutter and its target store/signing tools; it must not
call Shorebird or require a Shorebird login, token or subscription. A developer without
the owner's Shorebird account can publish such a project using their own authorized
store access. Missing Flutter/Xcode/store access is reported before building.

For a Shorebird project, use the developer's invited account or a scoped service credential
where the existing organization plan permits it. Never share the owner's login or copy
their private keys. Access to Git and access to the app in Shorebird/stores are separate.
See [Shorebird organization access](https://docs.shorebird.dev/account/orgs/).

If local access is missing, use an existing, authorized project CI release workflow only
after checking its repository, environment, exact source revision, protected secrets and
the actions it will perform. Do not trigger a guessed workflow, add a billing plan, create
a service account or install a persistent runner as a fallback. If no verified workflow
exists, report exactly what needs a one-time setup. A lack of access never changes the
project's runtime or turns a store request into an OTA patch.

## Onboard and delivery context

Run `python3 scripts/onboard.py /exact/app` from the installed skill to inventory
policy, SDK pins, tools and existing lanes without running project code or reading
credentials. Then use the [release lifecycle](release-lifecycle.md) adapters. Tool
presence is not proof of account access or signing. For a colleague without the
owner account, standard Flutter remains usable with their own store/signing access;
a Shorebird application requires their own granted Shorebird access or approved CI.
The regression suite simulates this; it does not configure Abdullah's real machine.

Use hot reload for a developer's local edits. Use the project's existing APK,
Play Internal or TestFlight distribution for team/client testing. A store-upload
request creates a holding-area build; promoting a Play draft to testers or enabling
TestFlight distribution must follow the requested existing distribution workflow.
Do not create new flavors/apps/distribution services or add Shorebird automatically.

Central publishing jobs must serialize by the exact application and environment,
independent of branch. Example job fragment in the application's already trusted
workflow (substitute the reviewed identity, not a user-controlled PR value):

```yaml
concurrency:
  group: mobile-com-example-app-production
  cancel-in-progress: false
environment: mobile-production
```

Require protected manual/trusted dispatch, restrict permissions, and keep credentials
out of PR tests. Ephemeral runners need approved private persistence for journals
and archived artifacts; local state alone cannot resume across different runners.
Check the selected run SHA and actual Linux/macOS results; a queued runner is not
success. Measure journal phase durations and retry counts before claiming a speedup.

## Read-only pilot — 2026-11-11

No application was built, signed, uploaded, patched, installed or modified for this pilot.

| Project | Existing evidence | Next integration before a real release |
|---|---|---|
| Domino | Flutter policy; Play+ASC; CI Flutter `3.44.0-0.2.pre`; existing Android build/upload/internal/production/verify lanes | Preserve that SDK and curated changelogs. The upload lane currently uses a fixed build path, so give its adapter the archived artifact explicitly. Configure exact store-status and QA evidence. Do not introduce Shorebird. |
| 3M | Shorebird policy; Play+ASC; CI Flutter `3.47.7`; no existing Fastlane lanes discovered | Preserve Shorebird release builder and current baseline identities. Add reviewed store-status/upload/QA adapters using the operator's existing access. |

Neither app currently contains the new coordinated profile. This task changes the
shared skill repository only; these are integration requirements, not claims that
application releases or Abdullah's device have been tested. Read-only onboard
reports retain those access/signing states as unverified. On the next authorized
release, the agent resolves the project integration from existing scripts and
access, records it, and completes the requested release without asking routine
technical questions. Missing real access or an unresolved product/cost decision
is reported specifically.
