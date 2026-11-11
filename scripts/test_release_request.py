"""Resolve project inputs without credentials or account-dependent decisions."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from release_request import discover, resolve


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = Path(self.temp.name)
        (self.app / 'pubspec.yaml').write_text('name: fixture\nversion: 1.2.3+42\n')
        (self.app / 'mobile-publish.config.json').write_text(json.dumps(
            dict(schema_version=1, runtime='flutter', stores=['play', 'asc'])))
        (self.app / '.fvmrc').write_text('{"flutter":"3.47.7"}')
        subprocess.run(['git', 'init', '-q', str(self.app)], check=True)

    def profile(self, **kwargs):
        data = dict(schema_version=1, environment='production',
                    identities={'play': 'com.test.app', 'asc': 'com.test.ios'}, **kwargs)
        (self.app / 'mobile-publish.release.json').write_text(json.dumps(data))

    def test_ambiguous_monorepo_requires_exact_app(self):
        for name in ['flutter', 'mobile']:
            (self.app / name).mkdir()
            (self.app / name / 'pubspec.yaml').touch()
        (self.app / 'pubspec.yaml').unlink()
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            discover(self.app)

    def test_default_is_store_upload_and_destinations_follow_policy(self):
        self.profile()
        request = resolve(self.app)
        self.assertEqual(request['operation'], 'store_upload')
        self.assertEqual(request['runtime'], 'flutter')
        self.assertEqual(request['sdk']['version'], '3.47.7')
        self.assertEqual(set(request['stores']), {'play', 'asc'})
        with self.assertRaises(ValueError):
            resolve(self.app, store='agc')
        with self.assertRaises(ValueError):
            resolve(self.app, operation='ota_patch')

    def test_wrong_flavor_target_environment_and_sdk_are_blocked(self):
        self.profile(flavor='prod', target='lib/main_prod.dart')
        for overrides in [dict(flavor='dev'), dict(target='lib/main.dart'),
                          dict(environment='staging'), dict(sdk_version='3.44.0')]:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                resolve(self.app, **overrides)

    def test_source_and_define_file_changes_change_fingerprint(self):
        self.profile(defines_files=['defines.json'])
        (self.app / 'defines.json').write_text('{"mode":"one"}')
        first = resolve(self.app)
        (self.app / 'defines.json').write_text('{"mode":"two"}')
        second = resolve(self.app)
        self.assertNotEqual(first['source'], second['source'])
        self.assertNotIn('"mode"', json.dumps(second))

    def test_missing_and_conflicting_sdk_pins_fail_closed(self):
        self.profile(sdk={'version': '3.44.0', 'command': ['flutter']})
        with self.assertRaisesRegex(ValueError, 'SDK'):
            resolve(self.app)
        (self.app / 'mobile-publish.release.json').unlink()
        (self.app / '.fvmrc').unlink()
        with self.assertRaisesRegex(ValueError, 'SDK'):
            resolve(self.app)

    def test_nested_directory_resolves_nearest_app(self):
        nested = self.app / 'lib/features'
        nested.mkdir(parents=True)
        self.assertEqual(discover(nested), self.app.resolve())

    def test_ignored_entrypoint_is_still_an_authoritative_build_input(self):
        (self.app / '.gitignore').write_text('generated/\n')
        (self.app / 'generated').mkdir()
        entry = self.app / 'generated/main.dart'
        entry.write_text('before')
        self.profile(target='generated/main.dart')
        before = resolve(self.app)
        entry.write_text('after')
        self.assertNotEqual(before, resolve(self.app))

    def test_selected_store_does_not_allow_a_partial_application_lock_identity(self):
        self.profile()
        path = self.app / 'mobile-publish.release.json'
        data = json.loads(path.read_text())
        del data['identities']['asc']
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            resolve(self.app, store='play')


if __name__ == '__main__':
    unittest.main()
