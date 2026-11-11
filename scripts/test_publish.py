"""Exercise the release entrypoint without network access or real credentials."""
import os
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name('publish.sh')


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / 'project' / 'flutter'
        (self.app / 'android/app').mkdir(parents=True)
        (self.app / 'ios/Runner.xcodeproj').mkdir(parents=True)
        (self.app / '.tool-versions').write_text('flutter 3.47.7\n')
        (self.app / 'pubspec.yaml').write_text('name: fixture\nversion: 1.2.0+42\n')
        self.set_policy('flutter', ['asc'])
        (self.app / 'android/app/build.gradle').write_text('applicationId "com.test.app"\n')
        (self.app / 'ios/Runner.xcodeproj/project.pbxproj').write_text(
            'PRODUCT_BUNDLE_IDENTIFIER = com.test.ios;\n')
        self.home = self.root / 'home'
        config = self.home / '.config/asc'
        config.mkdir(parents=True)
        config.joinpath('config').write_text('ASC_KEY_ID=TEST\nASC_ISSUER_ID=TEST\n')
        keys = self.home / '.appstoreconnect/private_keys'
        keys.mkdir(parents=True)
        keys.joinpath('AuthKey_TEST.p8').touch()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'calls'
        self.log.touch()
        self.env = dict(os.environ, HOME=str(self.home), PATH=f'{self.bin}:/usr/bin:/bin',
                        CALLS=str(self.log), PLAY_STORE_JSON_KEY='', AGC_KEY_FILE='')
        for key in ['SHOREBIRD_TOKEN', 'ASC_KEY_ID', 'ASC_ISSUER_ID', 'ASC_PRIVATE_KEY_PATH']:
            self.env.pop(key, None)
        self.stub('flutter', '''
if [ "$1" = --version ]; then echo '{"frameworkVersion":"3.47.7"}'; exit 0; fi
echo "flutter $*" >> "$CALLS"
if [ "$1" = clean ]; then rm -rf build; fi
if [ "$1" = build ]; then
  mkdir -p build/ios/ipa
  touch build/ios/ipa/fixture.ipa
fi
''')
        self.stub('xcrun', 'echo "xcrun $*" >> "$CALLS"\n')
        self.stub('asc', '''
echo "asc $*" >> "$CALLS"
case "$*" in
 *"apps list"*) echo '{"data":[{"id":"123"}]}' ;;
esac
exit "${ASC_TEST_EXIT:-0}"
''')

    def stub(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/bash\n' + body)
        path.chmod(0o755)

    def set_policy(self, runtime, stores):
        (self.app / 'mobile-publish.config.json').write_text(json.dumps(
            dict(schema_version=1, runtime=runtime, stores=stores)))

    def run_publish(self, *args):
        return subprocess.run(['bash', str(SCRIPT), *args], cwd=self.app,
                              env=self.env, text=True, capture_output=True, timeout=10)

    def test_legacy_upload_requires_coordinated_profile(self):
        self.assertEqual(self.run_publish('--store', 'asc').returncode, 0)
        result = self.run_publish('--store', 'asc', '--upload-prepared')
        self.assertNotEqual(result.returncode, 0)
        calls = self.log.read_text()
        self.assertNotIn('builds upload', calls)
        self.assertNotIn('--validate-app', calls)

    def test_old_artifact_is_removed_before_build(self):
        old = self.app / 'build/ios/ipa/stale.ipa'
        old.parent.mkdir(parents=True)
        old.touch()
        result = self.run_publish('--store', 'asc')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(old.exists())
        calls = self.log.read_text()
        self.assertLess(calls.index('flutter clean'), calls.index('flutter build'))

    def test_check_does_not_build_or_upload(self):
        result = self.run_publish('--store', 'asc', '--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text(), '')

    def test_missing_explicit_store_fails_before_building_others(self):
        self.set_policy('flutter', ['play'])
        result = self.run_publish('--store', 'play')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.log.read_text(), '')

    def test_failed_apple_processing_is_not_reported_as_success(self):
        self.assertEqual(self.run_publish('--store', 'asc').returncode, 0)
        self.env['ASC_TEST_EXIT'] = '1'
        result = self.run_publish('--store', 'asc', '--upload-prepared')
        self.assertNotEqual(result.returncode, 0)

    def test_bad_store_and_missing_values_fail_without_upload(self):
        for args in [('--store', 'typo'), ('--store',), ('--track',)]:
            with self.subTest(args=args):
                result = self.run_publish(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.log.read_text(), '')

    def test_asc_submit_is_not_silently_ignored(self):
        result = self.run_publish('--store', 'asc', '--submit')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.log.read_text(), '')

    def test_configured_missing_play_key_fails_without_build(self):
        self.set_policy('flutter', ['play'])
        self.env['PLAY_STORE_JSON_KEY'] = str(self.root / 'missing.json')
        self.stub('fastlane', 'echo "fastlane $*" >> "$CALLS"\n')
        result = self.run_publish('--store', 'play')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.log.read_text(), '')

    def test_existing_lanes_require_inspection_before_build(self):
        self.set_policy('flutter', ['play'])
        key = self.root / 'play.json'
        key.write_text('{}')
        self.env['PLAY_STORE_JSON_KEY'] = str(key)
        self.stub('fastlane', 'echo "fastlane $*" >> "$CALLS"\n')
        lane = self.app / 'android/fastlane/Fastfile'
        lane.parent.mkdir()
        lane.write_text('lane :release do\nend\n')
        result = self.run_publish('--store', 'play')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.log.read_text(), '')

    def test_prepare_builds_without_upload(self):
        result = self.run_publish('--store', 'asc', '--prepare')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('flutter build ipa', self.log.read_text())
        self.assertNotIn('builds upload', self.log.read_text())

    def test_upload_prepared_rejects_changed_artifact(self):
        result = self.run_publish('--store', 'asc', '--prepare')
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.app / 'build/ios/ipa/fixture.ipa').write_text('changed after verification')
        self.log.write_text('')
        result = self.run_publish('--store', 'asc', '--upload-prepared')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('builds upload', self.log.read_text())

    def test_upload_prepared_preserves_the_verified_artifact(self):
        result = self.run_publish('--store', 'asc', '--prepare')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.log.write_text('')
        result = self.run_publish('--store', 'asc', '--upload-prepared')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(line.startswith('flutter ') for line in self.log.read_text().splitlines()))
        self.assertNotIn('builds upload', self.log.read_text())

    def enable_shorebird(self):
        self.set_policy('shorebird', ['asc'])
        (self.app / 'shorebird.yaml').write_text('app_id: fixture-app\n')
        self.stub('shorebird', '''
echo "shorebird $*" >> "$CALLS"
if [ "$1" = api ]; then
  [ -z "${SHOREBIRD_AUTH_FAIL:-}" ] || exit 1
  case "$3" in
    /apps/fixture-app) echo '{"app_id":"fixture-app","organization_id":7,"display_name":"Fixture","created_at":"2026-01-01","updated_at":"2026-01-01"}' ;;
    /organizations/7) echo '{"organization":{"id":7},"role":"developer"}' ;;
    /apps/fixture-app/metrics/unique-users) python3 - <<'PY'
import json,os
from datetime import datetime,timedelta,timezone
now=datetime.now(timezone.utc)
print(json.dumps({'as_of':now.isoformat(),'current':{'unique_users':int(os.environ.get('USERS','0')),
    'range':{'start':(now-timedelta(days=28)).isoformat(),'end':now.isoformat()}},'previous':None,'granularity':None}))
PY
    ;;
    /organizations/7/usage) echo '{"apps":[],"reported_overage":null,"position":{"installs":0,"included_installs":5000,"remaining_installs":5000,"at_ceiling":false,"consuming_overage":false}}' ;;
    *) exit 1 ;;
  esac
  exit 0
fi
mkdir -p build/ios/ipa build/app/outputs/bundle/release build/app/outputs/flutter-apk
touch build/ios/ipa/fixture.ipa build/app/outputs/bundle/release/app-release.aab build/app/outputs/flutter-apk/app-release.apk
exit "${SHOREBIRD_TEST_EXIT:-0}"
''')

    def test_shorebird_project_uses_shorebird_for_store_build(self):
        self.enable_shorebird()
        result = self.run_publish('--store', 'asc', '--prepare')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text()
        self.assertIn('shorebird release --platforms ios --flutter-version 3.47.7', calls)
        self.assertNotIn('flutter build', calls)
        self.assertNotIn('builds upload', calls)

    def test_shorebird_build_failure_never_falls_back_to_plain_flutter(self):
        self.enable_shorebird()
        self.env['SHOREBIRD_TEST_EXIT'] = '1'
        result = self.run_publish('--store', 'asc', '--prepare')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('flutter build', self.log.read_text())
        self.assertFalse((self.app / 'build/mobile-publish.json').exists())

    def test_shorebird_config_change_invalidates_prepared_release(self):
        self.enable_shorebird()
        self.assertEqual(self.run_publish('--store', 'asc', '--prepare').returncode, 0)
        (self.app / 'shorebird.yaml').write_text('app_id: another-app\n')
        self.log.write_text('')
        result = self.run_publish('--store', 'asc', '--upload-prepared')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.log.read_text(), '')

    def test_shorebird_builds_both_android_formats_and_ios_together(self):
        self.enable_shorebird()
        self.set_policy('shorebird', ['play', 'asc', 'agc'])
        key = self.root / 'credential.json'
        key.write_text('{}')
        self.env.update(PLAY_STORE_JSON_KEY=str(key), AGC_KEY_FILE=str(key))
        self.stub('fastlane', 'exit 0\n')
        result = self.run_publish('--prepare')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text()
        self.assertIn('shorebird release --platforms android,ios --flutter-version 3.47.7 --artifact apk', calls)
        self.assertNotIn('flutter build', calls)

    def test_missing_declared_shorebird_config_fails_before_build(self):
        with (self.app / 'pubspec.yaml').open('a') as pubspec:
            pubspec.write('flutter:\n  assets:\n    - shorebird.yaml\n')
        result = self.run_publish('--store', 'asc', '--prepare')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.log.read_text(), '')

    def test_standard_developer_needs_no_shorebird_account_or_tool(self):
        self.stub('shorebird', 'echo "UNEXPECTED_SHOREBIRD" >> "$CALLS"; exit 99\n')
        result = self.run_publish('--prepare')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('UNEXPECTED_SHOREBIRD', self.log.read_text())
        self.assertNotEqual(self.run_publish('--upload-prepared').returncode, 0)

    def test_policy_change_invalidates_the_prepared_files(self):
        self.assertEqual(self.run_publish('--prepare').returncode, 0)
        self.set_policy('flutter', ['asc', 'play'])
        self.log.write_text('')
        result = self.run_publish('--store', 'asc', '--upload-prepared')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('builds upload', self.log.read_text())

    def test_policy_prevents_accidental_store_and_runtime_changes(self):
        key = self.root / 'agc.json'
        key.write_text('{}')
        self.env['AGC_KEY_FILE'] = str(key)
        self.stub('shorebird', 'echo UNEXPECTED_SHOREBIRD >> "$CALLS"\n')
        result = self.run_publish('--store', 'agc', '--prepare')
        self.assertNotEqual(result.returncode, 0)
        (self.app / 'shorebird.yaml').write_text('app_id: unexpected\n')
        self.assertNotEqual(self.run_publish('--prepare').returncode, 0)
        self.assertEqual(self.log.read_text(), '')

    def test_play_only_never_loads_apple_configuration(self):
        self.set_policy('flutter', ['play'])
        key = self.root / 'play.json'
        key.write_text('{}')
        self.env['PLAY_STORE_JSON_KEY'] = str(key)
        (self.home / '.config/asc/config').write_text('echo UNEXPECTED_APPLE >> "$CALLS"\n')
        self.stub('fastlane', 'exit 0\n')
        result = self.run_publish('--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text(), '')

    def test_shorebird_auth_failure_stops_before_clean_or_release(self):
        self.enable_shorebird()
        self.env['SHOREBIRD_AUTH_FAIL'] = '1'
        result = self.run_publish('--prepare')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('flutter clean', self.log.read_text())
        self.assertNotIn('shorebird release', self.log.read_text())

    def test_online_check_is_read_only_and_does_not_build(self):
        self.enable_shorebird()
        result = self.run_publish('--check-online')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('shorebird api GET', self.log.read_text())
        self.assertNotIn('flutter', self.log.read_text())
        self.assertNotIn('shorebird release', self.log.read_text())

    def test_large_population_stops_before_clean_and_before_store_upload(self):
        self.enable_shorebird()
        self.env['USERS'] = '401'
        blocked = self.run_publish('--prepare')
        self.assertNotEqual(blocked.returncode, 0)
        self.assertNotIn('flutter clean', self.log.read_text())
        self.assertNotIn('shorebird release', self.log.read_text())
        allowed = self.run_publish('--prepare', '--acknowledge-usage-warning')
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.log.write_text('')
        self.assertNotEqual(self.run_publish('--upload-prepared').returncode, 0)
        self.assertNotIn('builds upload', self.log.read_text())


if __name__ == '__main__':
    unittest.main()
