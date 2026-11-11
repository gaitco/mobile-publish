# Shorebird: small-app development and usage warnings

The owner's intended workflow is Shorebird for small development/ERP audiences and store
updates for larger apps. This is a project decision; growth raises a warning instead of
silently migrating or deleting the app. Domino remains standard Flutter.

## Read-only check and metric

Before a custom Shorebird release/patch workflow, run:

```bash
python3 "$MOBILE_PUBLISH_SKILL_DIR/scripts/publish_readiness.py" "$APP"
```

The shared publisher also enforces this before cleaning/building and before transferring
prepared Shorebird artifacts. It obtains the app's **distinct active devices** using the
Shorebird API's default recent 28-day window, and uses the server's effective range.
This is an HLL estimate of devices, not named users or lifetime store downloads. Never sum
daily users or platform/release breakdowns: one device can appear in several buckets.
Metrics can lag roughly one hour. Missing/invalid metrics, responses older than two hours,
old effective window ends or inconsistent dates pause the operation for a decision.

Default threshold: `shorebird_warning_users = 400`; exactly 400 passes, 401 pauses.
An explicit project override can adjust this positive integer. Do not raise it automatically.
The organization-owner's patch quota is read with GET on the specific organization's
usage endpoint. Show used/included/remaining installs when available, and label unavailable
or incomplete usage, pausing for a decision. This needs no copying of the owner's login. A server-reported quota
ceiling or paid overage also pauses even for a small app. No hardcoded prices or plans.

Shorebird's [billing documentation](https://docs.shorebird.dev/account/billing/) counts
successful **patch installs**, not store downloads. More active devices and frequent
installed patches can consume shared quota faster; an active-device count is not an exact
future bill or a promise every user will install the patch.

## User choice before publishing

When a warning appears, show it and wait. A general upload request is not consent to this
new warning. The user can approve the specific Shorebird operation or ask to prepare a
store-release migration. After explicit approval only, pass `--acknowledge-usage-warning`
to that readiness/publishing command. The flag does not persist and does not waive auth,
signing or Android/iOS OTA compatibility checks. Recheck usage before publication and
show a materially changed warning rather than reusing an unrelated approval.

For OTA, run this check before the two-platform workflow and again before the first
publication, after both platform dry runs/compatibility gates have passed. A missing store
credential is not needed merely to inspect Shorebird usage. No app/organization deletion,
subscription changes, overage enablement or automatic runtime changes occur in this check.

## Moving a growing app off Shorebird

Only when the user separately requests the migration: prepare and verify new **store
releases for Android and iOS** using standard Flutter, update the project's policy and
relevant build configuration deliberately, then distribute through the approved store
workflow. An OTA patch cannot remove the runtime from already installed native binaries.
Old installations remain on their old runtime until users install the store update.

Deleting the cloud app is a separate destructive operation that removes its releases,
patches and artifacts and stops future patch delivery; it is not required to build a new
standard Flutter release. Never delete it just because the count passed 400. Resolve the
exact app and preserve required release records before any separately authorized removal.
See [uninstall](https://docs.shorebird.dev/code-push/uninstall/) and
[cloud deletion](https://docs.shorebird.dev/code-push/delete/).

## Shared-plan early warning

The guard also pauses at **90% of the server-reported included patch installs**,
even when the current app has only a few devices. This is an explicit local early
warning boundary, not a Shorebird billing rule or forecast. Unknown/incomplete
shared quota also needs a decision; it is not proof of free capacity. The existing
400-device threshold remains per project, with 400 passing and 401 warning when
quota is otherwise verified healthy. No subscription, ceiling or billing setting
is modified. Account usage is shared; do not add per-app estimates to invent a bill.
