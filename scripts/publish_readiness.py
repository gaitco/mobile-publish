"""Read-only Shorebird app/role verification; never logs in or publishes a probe."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from publish_policy import load_policy
from shorebird_usage import quota_description, usage_warning

WRITERS = {'owner', 'admin', 'appmanager', 'developer'}


def can_publish(role):
    return isinstance(role, str) and role.lower().replace('_', '') in WRITERS


def query(app, endpoint, paginate=False, allow_denied=False):
    command = ['shorebird', 'api', 'GET', endpoint]
    if paginate:
        command.append('--paginate')
    try:
        result = subprocess.run(command, cwd=app, capture_output=True, text=True,
                                timeout=45, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError('Shorebird access could not be verified; check your own CLI/access or the approved project CI') from None
    if result.returncode:
        if allow_denied:
            return None
        # CLI output may contain account details or credentials. Never echo it.
        raise ValueError('Shorebird read-only access check failed; verify your own account/app permissions or the approved CI')
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise ValueError('unsupported Shorebird API response; no release was attempted') from None


def app_id_from_config(app):
    raw = (Path(app) / 'shorebird.yaml').read_text()
    matches = re.findall(r'^app_id:[ \t]*(?:"([^"\n]+)"|\'([^\'\n]+)\'|([A-Za-z0-9_-]+))[ \t]*(?:#.*)?$', raw, re.M)
    if len(matches) != 1:
        raise ValueError('cannot resolve one root Shorebird app_id; use the reviewed flavor-specific project workflow')
    app_id = next(part for part in matches[0] if part)
    if not re.fullmatch(r'[A-Za-z0-9_-]+', app_id):
        raise ValueError('invalid Shorebird app_id')
    return app_id


def check_shorebird_access(app):
    if not shutil.which('shorebird'):
        raise ValueError('Shorebird is required by this project but not installed; no plain-Flutter fallback')
    app_id = app_id_from_config(app)
    metadata = query(app, f'/apps/{app_id}')
    if (not isinstance(metadata, dict) or metadata.get('app_id') != app_id
            or type(metadata.get('organization_id')) is not int or metadata['organization_id'] <= 0):
        raise ValueError('the intended Shorebird app/organization could not be verified')
    # Do NOT call GET /organizations: with x-cli-version it can create an org.
    # The single-organization endpoint reads only, and may deny app-only collaborators.
    membership = query(app, f'/organizations/{metadata["organization_id"]}', allow_denied=True)
    if isinstance(membership, dict) and isinstance(membership.get('organization'), dict):
        if (membership['organization'].get('id') == metadata['organization_id']
                and can_publish(membership.get('role'))):
            return metadata
    # Personal app collaborators can have write access without an organization role.
    user = query(app, '/users/me')
    collaborators = query(app, f'/apps/{app_id}/collaborators', paginate=True)
    if isinstance(user, dict) and user.get('id') and isinstance(collaborators, list):
        if any(isinstance(item, dict) and item.get('user_id') == user['id']
               and can_publish(item.get('role')) for item in collaborators):
            return metadata
    raise ValueError('Shorebird release permission is missing or unverified; use your own authorized access or an approved CI workflow')


def check_usage(app, policy, metadata, acknowledge=False):
    try:
        metrics = query(app, f'/apps/{metadata["app_id"]}/metrics/unique-users', allow_denied=True)
    except ValueError:
        metrics = None
    try:
        quota = query(app, f'/organizations/{metadata["organization_id"]}/usage', allow_denied=True)
    except ValueError:
        quota = None
    warning = usage_warning(metrics, quota, policy.shorebird_warning_users)
    if warning:
        print(warning, file=sys.stderr)
        if not acknowledge:
            raise ValueError('Shorebird publishing paused for a user decision; use --acknowledge-usage-warning only after explicit approval of this operation')
        print('تم الإقرار بالتنبيه لهذه العملية فقط؛ لم تُحفظ موافقة دائمة.', file=sys.stderr)
    else:
        print(f'الأجهزة النشطة في نافذة Shorebird: نحو {metrics["current"]["unique_users"]}؛ حد التنبيه: {policy.shorebird_warning_users}.')
        print(quota_description(quota)[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=Path)
    parser.add_argument('--store', default='all')
    parser.add_argument('--acknowledge-usage-warning', action='store_true')
    args = parser.parse_args()
    policy = load_policy(args.app, args.store)
    if policy.runtime == 'shorebird':
        metadata = check_shorebird_access(args.app)
        check_usage(args.app, policy, metadata, args.acknowledge_usage_warning)
        print('Shorebird app and release role verified; store access/signing/version checks remain required')
    else:
        print('Standard Flutter project: no Shorebird account or tool required')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        sys.exit(f'error: {error}')
