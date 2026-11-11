import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from onboard import inspect_project


class OnboardTests(unittest.TestCase):
    def test_plain_colleague_inventory_never_needs_owner_or_shorebird(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            (app / 'pubspec.yaml').write_text('version: 1.0.0+1')
            (app / 'mobile-publish.config.json').write_text(json.dumps(
                dict(schema_version=1, runtime='flutter', stores=['play'])))
            (app / '.tool-versions').write_text('flutter 3.47.7\n')
            with patch('onboard.shutil.which', side_effect=lambda name: '/bin/' + name):
                data = inspect_project(app)
            self.assertNotIn('shorebird', data['tools'])
            self.assertEqual(data['store_access'], 'unverified: use your own grants or approved CI')
            self.assertFalse(data['coordinated_profile'])
            self.assertEqual(data['runtime'], 'flutter')


if __name__ == '__main__':
    unittest.main()
