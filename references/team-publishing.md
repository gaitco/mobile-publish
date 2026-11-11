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
