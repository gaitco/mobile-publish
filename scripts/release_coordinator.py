"""Run reviewed project tools with immutable artifacts and exact store evidence.

This is a store-upload coordinator. OTA/review/migration use their dedicated
runbooks; no operation is silently converted into another.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from publish_policy import load_policy
from publish_readiness import check_shorebird_access, check_usage
from release_request import discover, project_file, read_profile, resolve
from release_run import Journal, application_lock
from store_status import normalize, transfer


def command(argv, values):
    if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or not x for x in argv):
        raise ValueError('reviewed project commands must be nonempty argv arrays')
    try:
        return [arg.format_map(values) for arg in argv]
    except (KeyError, ValueError):
        raise ValueError('unsupported command placeholder') from None


def execute(argv, app, values, timeout=120):
    try:
        return subprocess.run(command(argv, values), cwd=app, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ValueError('project tool timed out; inspect status before retrying') from None
    except OSError:
        raise ValueError('required project tool is unavailable; use the approved local or CI environment') from None


def evidence(argv, app, values):
    result = execute(argv, app, values)
    if result.returncode:
        raise ValueError('evidence command failed; raw logs suppressed to protect credentials and signed URLs')
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise ValueError('evidence command did not return one JSON object') from None


def validate_profile(profile, request):
    values = dict(skill=str(Path(__file__).resolve().parent.parent), request='request.json', artifact='artifact', app_id='app',
                  version=request['version'], build=request['build'], track=request['track'],
                  artifact_sha256='0' * 64, environment=request['environment'])
    builds = profile.get('build')
    if not isinstance(builds, list) or not builds:
        raise ValueError('record the existing reviewed build commands in release profile')
    for argv in [*builds, profile.get('qa')]:
        command(argv, values)
    for store in request['stores']:
        target = profile.get('stores', {}).get(store, {})
        for field in ('status', 'verify', 'upload'):
            command(target.get(field), values)
        if not re.fullmatch(r'[A-Fa-f0-9]{64}', target.get('certificate_sha256', '')):
            raise ValueError('record the approved signing certificate SHA256 for each store')
        project_file(Path(request['app']), profile.get('artifacts', {}).get(store))


def verify_signature(data, request, store, sha256, certificate):
    expected = dict(app=request['identities'][store], version=request['version'],
                    build=request['build'], platform='ios' if store == 'asc' else 'android', sha256=sha256)
    if not isinstance(data, dict) or any(data.get(k) != v for k, v in expected.items()):
        raise ValueError('artifact identity/version/hash differs from the resolved release')
    if (data.get('signature_valid') is not True or data.get('distribution') is not True
            or data.get('certificate_sha256', '').lower() != certificate.lower()):
        raise ValueError('artifact signature/distribution/certificate verification failed')


def readiness(app, request, acknowledge):
    policy = load_policy(app, request['stores'][0] if len(request['stores']) == 1 else 'all')
    if policy.runtime == 'shorebird':
        metadata = check_shorebird_access(app)
        check_usage(app, policy, metadata, acknowledge=acknowledge)


def summary(journal):
    print(json.dumps(dict(run=journal.data['id'], stage=journal.data['stage'],
                          stores=journal.data['stores']), indent=2))


def run(args):
    request = resolve(args.app, args.store, args.operation, track=args.track)
    if request['operation'] != 'store_upload':
        raise ValueError('coordinator supports store_upload only; use the explicit operation runbook')
    app = Path(request['app'])
    profile = read_profile(app)
    validate_profile(profile, request)
    if args.check:
        print(json.dumps(request, indent=2))
        return 0
    if args.check_online:
        readiness(app, request, args.acknowledge_usage_warning)
        with tempfile.TemporaryDirectory(prefix='mobile-publish-check-') as directory:
            path = Path(directory) / 'request.json'
            path.write_text(json.dumps(dict(request, artifacts={})))
            path.chmod(0o600)
            values = dict(skill=str(Path(__file__).resolve().parent.parent), request=str(path), version=request['version'], build=request['build'],
                          track=request['track'], environment=request['environment'])
            states = {}
            for store in request['stores']:
                data = evidence(profile['stores'][store]['status'], app,
                                dict(values, app_id=request['identities'][store]))
                states[store] = normalize(data, request, store)
            print(json.dumps(states, indent=2))
        return 0
    with application_lock(request):
        if args.close_prepared:
            summary(Journal.close_prepared(request, args.close_prepared))
            return 0
        journal = Journal.open(request)
        # All JSON contains only the normalized allowlisted request and hashes.
        request_path = journal.path / 'request.json'
        values = dict(skill=str(Path(__file__).resolve().parent.parent), request=str(request_path), version=request['version'],
                      build=request['build'], track=request['track'],
                      environment=request['environment'])

        def update_request():
            data = dict(request, artifacts={s: item['sha256'] for s, item in journal.data['artifacts'].items()},
                        artifact_files={s: str(journal.artifact(s)) for s in journal.data['artifacts']})
            request_path.write_text(json.dumps(data))
            request_path.chmod(0o600)

        def query(store):
            target = profile['stores'][store]
            scoped = dict(values, app_id=request['identities'][store])
            data = evidence(target['status'], app, scoped)
            state = normalize(data, request, store)
            journal.transition(store, state, data.get('reference'))
            return state

        try:
            update_request()
            readiness(app, request, args.acknowledge_usage_warning)
            sdk = evidence(request['sdk']['command'] + ['--version', '--machine'], app, values)
            if sdk.get('frameworkVersion') != request['sdk']['version']:
                raise ValueError('installed SDK differs from the exact project pin')
            if not journal.data['artifacts']:
                if args.upload_prepared:
                    raise ValueError('no durable prepared artifacts; prepare this request first')
                # Never build for an already-used or unverified number.
                for store in request['stores']:
                    if query(store) != 'absent':
                        raise ValueError('build number already exists or is unverified; inspect the exact release')
                journal.stage('building')
                started = time.monotonic()
                for argv in profile['build']:
                    if execute(argv, app, values, timeout=1800).returncode:
                        journal.stage('build_failed', time.monotonic() - started)
                        raise ValueError('reviewed project build failed; preserve runtime and inspect its environment')
                # Catch source changes during pub get/generation/build before evidence is pinned.
                if resolve(app, args.store, args.operation, track=args.track) != request:
                    raise ValueError('source/build inputs changed during build; inspect changes before preparing again')
                journal.stage('built', time.monotonic() - started)
                journal.archive({s: project_file(app, profile['artifacts'][s]) for s in request['stores']})
            if set(journal.data['artifacts']) != set(request['stores']):
                raise ValueError('prepared artifact set differs from requested destinations')
            journal.verify_artifacts()
            update_request()
            journal.stage('verifying')
            started = time.monotonic()
            for store in request['stores']:
                target = profile['stores'][store]
                scoped = dict(values, app_id=request['identities'][store],
                              artifact=str(journal.artifact(store)),
                              artifact_sha256=journal.data['artifacts'][store]['sha256'])
                data = evidence(target['verify'], app, scoped)
                verify_signature(data, request, store, scoped['artifact_sha256'], target['certificate_sha256'])
            qa = evidence(profile['qa'], app, values)
            platforms = {'ios' if s == 'asc' else 'android' for s in request['stores']}
            if (qa.get('artifacts') != {s: a['sha256'] for s, a in journal.data['artifacts'].items()}
                    or qa.get('launched') is not True or qa.get('dedicated') is not True
                    or set(qa.get('platforms', [])) != platforms):
                raise ValueError('exact artifacts need launch evidence on dedicated QA targets for all selected platforms')
            journal.verify_artifacts()
            journal.stage('verified', time.monotonic() - started)
            if not args.upload_prepared:
                summary(journal)
                return 0
            # Both/all targets have passed verification before the first upload.
            readiness(app, request, args.acknowledge_usage_warning)
            for store in request['stores']:
                target = profile['stores'][store]
                scoped = dict(values, app_id=request['identities'][store],
                              artifact=str(journal.artifact(store)),
                              artifact_sha256=journal.data['artifacts'][store]['sha256'])

                def upload():
                    journal.verify_artifacts()
                    if resolve(app, args.store, args.operation, track=args.track) != request:
                        raise ValueError('source/build inputs changed before upload')
                    journal.transition(store, 'transport')
                    started = time.monotonic()
                    try:
                        result = execute(target['upload'], app, scoped, timeout=1800)
                    except ValueError:
                        # A timeout may have happened after acceptance. Query before any retry.
                        return 'unknown'
                    journal.transition(store, 'processing', elapsed=time.monotonic() - started)
                    return 'transient' if result.returncode == 75 else 'ok' if result.returncode == 0 else 'failed'

                state = transfer(lambda: query(store), upload)
                if state == 'unknown':
                    journal.transition(store, 'unknown')
            journal.stage('accepted' if Journal.complete(journal.data) else 'needs_attention')
            journal.prune()
            summary(journal)
            return 0 if Journal.complete(journal.data) else 1
        except (ValueError, OSError, subprocess.SubprocessError):
            summary(journal)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', default='.')
    parser.add_argument('--store', default='all')
    parser.add_argument('--track', default='internal')
    parser.add_argument('--operation', default='store_upload')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--prepare', '--build', action='store_true')
    mode.add_argument('--upload-prepared', action='store_true')
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--check-online', action='store_true')
    mode.add_argument('--close-prepared', metavar='RUN_ID')
    parser.add_argument('--acknowledge-usage-warning', action='store_true')
    return run(parser.parse_args())


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        # Only our fixed messages are emitted. Never relay raw subprocess exceptions.
        message = str(error) if isinstance(error, ValueError) else 'project release evidence is unavailable'
        sys.exit('error: ' + message)
