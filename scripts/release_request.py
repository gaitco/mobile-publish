"""One credential-free identity for a reviewed mobile release request."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from prepared_release import digest
from publish_policy import load_policy, unique_keys

PROFILE = 'mobile-publish.release.json'
OPERATIONS = ('store_upload', 'ota_patch', 'store_review', 'runtime_migration')


def discover(start):
    start = Path(start).resolve()
    for directory in (start, *start.parents):
        if (directory / 'pubspec.yaml').is_file():
            return directory
        candidates = [directory / sub for sub in ('flutter', 'mobile', 'app')
                      if (directory / sub / 'pubspec.yaml').is_file()]
        if len(candidates) > 1:
            raise ValueError('ambiguous app modules; run from the exact application directory')
        if candidates:
            return candidates[0]
    raise ValueError('no Flutter application found')


def read_profile(app):
    path = app / PROFILE
    if not path.exists():
        return {}
    data = json.loads(path.read_text(), object_pairs_hook=unique_keys)
    allowed = {'schema_version', 'environment', 'identities', 'sdk', 'flavor', 'target',
               'defines_files', 'build', 'artifacts', 'stores', 'qa'}
    if not isinstance(data, dict) or data.get('schema_version') != 1 or set(data) - allowed:
        raise ValueError('invalid release profile schema; no credentials or shell expressions')
    return data


def project_file(app, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError('project references must be relative paths')
    path = (app / name).resolve()
    if app not in path.parents:
        raise ValueError('project reference escapes application')
    return path


def sdk_context(app, profile):
    pins = []
    fvm = app / '.fvmrc'
    if fvm.exists():
        pins.append(json.loads(fvm.read_text()).get('flutter'))
    legacy = app / '.fvm/fvm_config.json'
    if legacy.exists():
        pins.append(json.loads(legacy.read_text()).get('flutterSdkVersion'))
    versions = app / '.tool-versions'
    if versions.exists():
        pins.extend(re.findall(r'^flutter\s+(\S+)', versions.read_text(), re.M))
    configured = profile.get('sdk', {})
    if configured.get('version'):
        pins.append(configured['version'])
    # CI pins are authoritative when no closer SDK manager/profile pin exists.
    if not pins:
        for root in (app, *app.parents):
            workflows = root / '.github/workflows'
            if workflows.is_dir():
                for path in sorted(workflows.glob('*.y*ml')):
                    pins.extend(re.findall(r'flutter-version:\s*[\'"]?([^\s\'"#]+)', path.read_text()))
                break
            if (root / '.git').exists():
                break
    if not pins or any(not isinstance(pin, str) for pin in pins) or len(set(pins)) != 1:
        raise ValueError('missing or conflicting SDK pins; resolve the existing project SDK source')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?', pins[0]):
        raise ValueError('SDK must be an exact Flutter version, never latest/system/channel')
    command = configured.get('command', ['fvm', 'flutter'] if fvm.exists() or legacy.exists() else ['flutter'])
    if not isinstance(command, list) or not command or any(not isinstance(x, str) or not x for x in command):
        raise ValueError('SDK command must be an argv array')
    return {'version': pins[0], 'command': command}


def source_snapshot(app, extra):
    result = subprocess.run(['git', '-C', str(app), 'ls-files', '-z', '--cached',
                             '--others', '--exclude-standard', '--', '.'],
                            capture_output=True, check=True)
    files = set(result.stdout.decode().split('\0')) - {''}
    files.update(extra)
    hashes = []
    for name in sorted(files):
        path = project_file(app, name)
        hashes.append((name, digest(path) if path.is_file() else 'missing'))
    return hashlib.sha256(json.dumps(hashes).encode()).hexdigest()


def resolve(start, store='all', operation='store_upload', environment=None,
            flavor=None, target=None, sdk_version=None, track='internal'):
    app = discover(start)
    policy = load_policy(app, store)
    profile = read_profile(app)
    if operation not in OPERATIONS or (operation == 'ota_patch' and policy.runtime != 'shorebird'):
        raise ValueError('operation is not authorized by this runtime')
    if track not in ('internal', 'alpha', 'beta', 'production'):
        raise ValueError('unsupported track')
    sdk = sdk_context(app, profile)
    for key, actual in [('environment', environment), ('flavor', flavor), ('target', target)]:
        if actual is not None and actual != profile.get(key):
            raise ValueError('requested build context differs from reviewed project ' + key)
    if sdk_version is not None and sdk_version != sdk['version']:
        raise ValueError('requested SDK differs from project pin')
    version = re.search(r'^version:\s*[\'"]?([0-9.]+)\+(\d+)',
                        (app / 'pubspec.yaml').read_text(), re.M)
    if not version:
        raise ValueError('project needs an explicit marketing version and build number')
    identities = profile.get('identities', {})
    if any(not re.fullmatch(r'[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+', identities.get(s, '')) for s in policy.stores):
        raise ValueError('record reviewed application identities for selected stores in release profile')
    env = profile.get('environment')
    if not isinstance(env, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', env):
        raise ValueError('record the reviewed release environment')
    defines = profile.get('defines_files', [])
    if not isinstance(defines, list):
        raise ValueError('defines_files must contain project file references')
    for name in defines + ([profile['target']] if profile.get('target') else []):
        if not project_file(app, name).is_file():
            raise ValueError('referenced build input is missing')
    inputs = [PROFILE, 'pubspec.yaml', 'mobile-publish.config.json', *defines]
    if policy.runtime == 'shorebird':
        inputs.append('shorebird.yaml')
    return dict(app=str(app), operation=operation, runtime=policy.runtime,
                stores=list(policy.stores), identities={s: identities[s] for s in policy.stores},
                environment=env, track=track, version=version[1], build=version[2], sdk=sdk,
                flavor=profile.get('flavor'), target=profile.get('target'),
                defines_files=defines, source=source_snapshot(app, inputs))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', nargs='?', default='.')
    parser.add_argument('--store', default='all')
    parser.add_argument('--track', default='internal')
    parser.add_argument('--operation', default='store_upload', choices=OPERATIONS)
    args = parser.parse_args()
    print(json.dumps(resolve(args.app, args.store, args.operation, track=args.track), indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError):
        sys.exit('error: release context is incomplete or conflicting; inspect the project profile and SDK pins')
