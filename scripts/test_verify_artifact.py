"""Exercise native verification failures without real signing material."""
from pathlib import Path
import tempfile
import plistlib
import unittest
import zipfile
from datetime import datetime, timedelta
from unittest.mock import patch

from verify_artifact import android, ios


MANIFEST = b'''<manifest xmlns:android="http://schemas.android.com/apk/res/android"
 package="com.test.app" android:versionName="1.2.0" android:versionCode="42">
 <application android:debuggable="false"/></manifest>'''


class ArtifactTests(unittest.TestCase):
    def test_native_identity_and_certificate_come_from_the_signed_bundle(self):
        with patch('verify_artifact.tool', side_effect=[b'jar verified.', b'SHA256: ' + b'AA:' * 31 + b'AA', MANIFEST]):
            data = android(Path('artifact.aab'))
        self.assertEqual(data['app'], 'com.test.app')
        self.assertEqual(data['build'], '42')
        self.assertEqual(data['certificate_sha256'], 'aa' * 32)

    def test_unsigned_entries_debuggable_or_multiple_signers_are_rejected(self):
        for results in [[b'jar is unsigned.'], [b'jar verified. unsigned entries'],
                        [b'jar verified.', b'SHA256: ' + b'AA' * 32,
                         MANIFEST.replace(b'false', b'true')]]:
            with self.subTest(results=results), patch('verify_artifact.tool', side_effect=results):
                with self.assertRaises(ValueError):
                    android(Path('artifact.aab'))

    def test_debuggable_numeric_true_is_also_rejected(self):
        with patch('verify_artifact.tool', side_effect=[b'jar verified.', b'SHA256: ' + b'AA' * 32,
                                                     MANIFEST.replace(b'false', b'1')]):
            with self.assertRaises(ValueError):
                android(Path('artifact.aab'))

    def test_signed_ios_entitlements_cannot_exceed_distribution_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'app.ipa'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('Payload/Test.app/Info.plist', plistlib.dumps(dict(
                    CFBundleIdentifier='com.test.app', CFBundleShortVersionString='1.2.0', CFBundleVersion='42')))
                archive.writestr('Payload/Test.app/embedded.mobileprovision', b'profile')
            profile = dict(Entitlements={'get-task-allow': False, 'application-identifier': 'TEAM.com.test.app'},
                           ApplicationIdentifierPrefix=['TEAM'], DeveloperCertificates=[b'certificate'],
                           ExpirationDate=datetime.utcnow() + timedelta(days=30))

            def native_tool(argv):
                if argv[0] == 'security':
                    return plistlib.dumps(profile)
                if '--extract-certificates' in argv:
                    Path(argv[argv.index('--extract-certificates') + 1] + '0').write_bytes(b'certificate')
                if '--entitlements' in argv:
                    return plistlib.dumps({'get-task-allow': True, 'application-identifier': 'TEAM.com.test.app'})
                return b''

            with patch('verify_artifact.sys.platform', 'darwin'), patch('verify_artifact.tool', side_effect=native_tool):
                with self.assertRaises(ValueError):
                    ios(path)


if __name__ == '__main__':
    unittest.main()
