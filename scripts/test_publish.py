"""Exercise the release entrypoint without network access or real credentials."""
import os
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
        (self.app / 'pubspec.yaml').write_text('name: fixture\nversion: 1.2.0+42\n')
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
        self.stub('flutter', '''
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

    def run_publish(self, *args):
        return subprocess.run(['bash', str(SCRIPT), *args], cwd=self.app,
                              env=self.env, text=True, capture_output=True, timeout=10)

    def test_upload_is_real_and_waits_for_apple_processing(self):
        self.assertEqual(self.run_publish('--store', 'asc').returncode, 0)
        result = self.run_publish('--store', 'asc', '--upload-prepared')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text()
        self.assertIn('builds upload', calls)
        self.assertIn('--wait', calls)
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
        self.env['PLAY_STORE_JSON_KEY'] = str(self.root / 'missing.json')
        self.stub('fastlane', 'echo "fastlane $*" >> "$CALLS"\n')
        result = self.run_publish('--store', 'play')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.log.read_text(), '')

    def test_existing_lanes_require_inspection_before_build(self):
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
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(line.startswith('flutter ') for line in self.log.read_text().splitlines()))
        self.assertIn('builds upload', self.log.read_text())

    def enable_shorebird(self):
        (self.app / 'shorebird.yaml').write_text('app_id: fixture-app\n')
        self.stub('shorebird', '''
echo "shorebird $*" >> "$CALLS"
mkdir -p build/ios/ipa build/app/outputs/bundle/release build/app/outputs/flutter-apk
touch build/ios/ipa/fixture.ipa build/app/outputs/bundle/release/app-release.aab build/app/outputs/flutter-apk/app-release.apk
exit "${SHOREBIRD_TEST_EXIT:-0}"
''')

    def test_shorebird_project_uses_shorebird_for_store_build(self):
        self.enable_shorebird()
        result = self.run_publish('--store', 'asc', '--prepare')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text()
        self.assertIn('shorebird release --platforms ios --flutter-version system', calls)
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
        key = self.root / 'credential.json'
        key.write_text('{}')
        self.env.update(PLAY_STORE_JSON_KEY=str(key), AGC_KEY_FILE=str(key))
        self.stub('fastlane', 'exit 0\n')
        result = self.run_publish('--prepare')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text()
        self.assertIn('shorebird release --platforms android,ios --flutter-version system --artifact apk', calls)
        self.assertNotIn('flutter build', calls)

    def test_missing_declared_shorebird_config_fails_before_build(self):
        with (self.app / 'pubspec.yaml').open('a') as pubspec:
            pubspec.write('flutter:\n  assets:\n    - shorebird.yaml\n')
        result = self.run_publish('--store', 'asc', '--prepare')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.log.read_text(), '')


if __name__ == '__main__':
    unittest.main()
