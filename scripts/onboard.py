"""Read-only local publishing inventory; never logs in or executes project scripts."""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys

from publish_policy import load_policy
from release_request import discover, read_profile, sdk_context


def inspect_project(start):
    app = discover(start)
    policy = load_policy(app)
    profile = read_profile(app)
    try:
        sdk = sdk_context(app, profile)
    except ValueError:
        sdk = {'unverified': 'resolve existing SDK pin before building'}
    names = ['flutter', 'python3']
    if policy.runtime == 'shorebird':
        names.append('shorebird')
    for store, tool in [('play', 'fastlane'), ('asc', 'asc')]:
        if store in policy.stores:
            names.append(tool)
    lanes = {}
    for path in [app / 'android/fastlane/Fastfile', app / 'ios/fastlane/Fastfile']:
        if path.is_file():
            lanes[str(path.relative_to(app))] = re.findall(r'^\s*lane\s+:(\w+)', path.read_text(), re.M)
    return dict(app=str(app), runtime=policy.runtime, stores=list(policy.stores), sdk=sdk,
                coordinated_profile=bool(profile), existing_lanes=lanes,
                tools={name: bool(shutil.which(name)) for name in names},
                store_access='unverified: use your own grants or approved CI',
                signing='unverified: inspect final artifacts before publication',
                delivery=dict(local='existing Flutter debug/hot reload',
                              team='existing APK/Play Internal/TestFlight workflow only',
                              users='approved store destinations; preserve runtime'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', nargs='?', default='.')
    args = parser.parse_args()
    print(json.dumps(inspect_project(Path(args.app)), indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError):
        sys.exit('error: project policy or local inventory is incomplete; no account was changed')
