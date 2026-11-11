import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('publish_policy.py')


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = Path(self.temp.name)
        (self.app / 'pubspec.yaml').write_text('name: fixture\n')

    def policy(self, runtime='flutter', stores=None, **extra):
        value = dict(schema_version=1, runtime=runtime, stores=stores or ['play'], **extra)
        (self.app / 'mobile-publish.config.json').write_text(json.dumps(value))

    def resolve(self, store='all'):
        return subprocess.run([sys.executable, str(SCRIPT), str(self.app), '--store', store],
                              text=True, capture_output=True)

    def test_standard_project_without_policy_requires_explicit_store(self):
        self.assertNotEqual(self.resolve().returncode, 0)
        result = self.resolve('play')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ['flutter', 'play'])

    def test_project_policy_selects_only_approved_stores(self):
        self.policy(stores=['play', 'asc'])
        result = self.resolve()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ['flutter', 'play asc'])
        self.assertNotEqual(self.resolve('agc').returncode, 0)

    def test_shorebird_requires_explicit_policy_and_existing_config(self):
        (self.app / 'shorebird.yaml').write_text('app_id: fixture\n')
        self.assertNotEqual(self.resolve('play').returncode, 0)
        self.policy(runtime='shorebird')
        result = self.resolve()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[0], 'shorebird')
        (self.app / 'shorebird.yaml').unlink()
        self.assertNotEqual(self.resolve().returncode, 0)

    def test_standard_policy_never_disables_shorebird_silently(self):
        self.policy()
        (self.app / 'shorebird.yaml').write_text('app_id: fixture\n')
        self.assertNotEqual(self.resolve().returncode, 0)

    def test_missing_declared_config_blocks_a_standard_build(self):
        self.policy()
        (self.app / 'pubspec.yaml').write_text('flutter:\n  assets:\n    - shorebird.yaml\n')
        self.assertNotEqual(self.resolve().returncode, 0)

    def test_rejects_unknown_duplicate_and_invalid_settings(self):
        target = self.app / 'mobile-publish.config.json'
        samples = [
            '{', '[]', '{"schema_version":1,"runtime":"flutter","runtime":"shorebird","stores":["play"]}',
            json.dumps(dict(schema_version=True, runtime='flutter', stores=['play'])),
            json.dumps(dict(schema_version=1, runtime='automatic', stores=['play'])),
            json.dumps(dict(schema_version=1, runtime='flutter', stores=[])),
            json.dumps(dict(schema_version=1, runtime='flutter', stores=['play', 'play'])),
            json.dumps(dict(schema_version=1, runtime='flutter', stores=['anything'])),
            json.dumps(dict(schema_version=1, runtime='flutter', stores=['play'], token='not-allowed')),
            json.dumps(dict(schema_version=1, runtime='flutter', stores=['play'], shorebird_warning_users=0)),
            json.dumps(dict(schema_version=1, runtime='flutter', stores=['play'], shorebird_warning_users=True)),
            json.dumps(dict(schema_version=1, runtime='flutter', stores=['play'], shorebird_warning_users='400')),
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                target.write_text(sample)
                self.assertNotEqual(self.resolve().returncode, 0)


if __name__ == '__main__':
    unittest.main()
