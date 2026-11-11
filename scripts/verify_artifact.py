"""Verify native identity and distribution signature using installed platform tools.

JSON output is the release coordinator's verification contract. No key is loaded.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from prepared_release import digest


def tool(argv):
    result = subprocess.run(argv, capture_output=True, stdin=subprocess.DEVNULL,
                            env=dict(os.environ, LC_ALL='C'), timeout=120)
    if result.returncode:
        raise ValueError('native artifact tool failed; check installed tooling and distribution signing')
    return result.stdout


def android(path):
    if path.suffix == '.aab':
        verified = tool(['jarsigner', '-verify', '-verbose', str(path)]).decode()
        if 'jar verified.' not in verified or re.search(r'unsigned entr', verified, re.I):
            raise ValueError('bundle is unsigned or contains unsigned entries')
        certificate = tool(['keytool', '-J-Duser.language=en', '-printcert', '-jarfile', str(path)]).decode()
        fingerprints = re.findall(r'SHA256:\s*([0-9A-Fa-f:]{64,95})', certificate)
        manifest = tool(['bundletool', 'dump', 'manifest', '--bundle', str(path), '--module', 'base'])
    elif path.suffix == '.apk':
        certificate = tool(['apksigner', 'verify', '--verbose', '--print-certs', str(path)]).decode()
        fingerprints = re.findall(r'certificate SHA-256 digest:\s*([0-9A-Fa-f]+)', certificate)
        manifest = tool(['apkanalyzer', 'manifest', 'print', str(path)])
    else:
        raise ValueError('Android artifact must be AAB or APK')
    fingerprints = {value.replace(':', '').lower() for value in fingerprints}
    if len(fingerprints) != 1:
        raise ValueError('expected one verified Android signing certificate')
    root = ET.fromstring(manifest)
    namespace = '{http://schemas.android.com/apk/res/android}'
    application = root.find('application')
    if application is None or application.get(namespace + 'debuggable', 'false').lower() in ('true', '1', '0xffffffff'):
        raise ValueError('debuggable or invalid Android artifact')
    return dict(app=root.get('package'), version=root.get(namespace + 'versionName'),
                build=root.get(namespace + 'versionCode'), certificate_sha256=fingerprints.pop(),
                platform='android', distribution=True, signature_valid=True)


def ios(path):
    if sys.platform != 'darwin':
        raise ValueError('IPA signature verification requires macOS')
    with tempfile.TemporaryDirectory(prefix='mobile-publish-ipa-') as directory:
        output = Path(directory)
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                name = Path(entry.filename)
                if (name.is_absolute() or '..' in name.parts
                        or stat.S_ISLNK(entry.external_attr >> 16)):
                    raise ValueError('unsafe IPA archive entry; inspect the archive')
            archive.extractall(output)
        apps = list((output / 'Payload').glob('*.app'))
        if len(apps) != 1:
            raise ValueError('expected exactly one root iOS application')
        app = apps[0]
        tool(['codesign', '--verify', '--deep', '--strict', str(app)])
        root_info = None
        root_certificate = None
        bundles = [app, *app.rglob('*.app'), *app.rglob('*.appex')]
        for index, bundle in enumerate(bundles):
            info = plistlib.loads((bundle / 'Info.plist').read_bytes())
            profile = plistlib.loads(tool(['security', 'cms', '-D', '-i', str(bundle / 'embedded.mobileprovision')]))
            entitlements = profile.get('Entitlements', {})
            if (profile.get('ProvisionedDevices') is not None or profile.get('ProvisionsAllDevices')
                    or entitlements.get('get-task-allow') is not False):
                raise ValueError('IPA needs App Store distribution profiles for app and extensions')
            from datetime import datetime
            if profile.get('ExpirationDate', datetime.min) <= datetime.utcnow():
                raise ValueError('distribution profile has expired')
            expected_ids = [value + '.' + info['CFBundleIdentifier']
                            for value in profile.get('ApplicationIdentifierPrefix', [])]
            if entitlements.get('application-identifier') not in expected_ids:
                raise ValueError('profile does not match application identity')
            actual = plistlib.loads(tool(['codesign', '-d', '--entitlements', ':-', str(bundle)]))
            if (actual.get('application-identifier') not in expected_ids
                    or not entitlement_allowed(actual, entitlements)):
                raise ValueError('signed entitlements exceed the distribution profile')
            cert_prefix = output / ('signer-' + str(index))
            tool(['codesign', '-d', '--extract-certificates', str(cert_prefix), str(bundle)])
            certificate = Path(str(cert_prefix) + '0').read_bytes()
            if certificate not in profile.get('DeveloperCertificates', []):
                raise ValueError('IPA signer is not authorized by its provisioning profile')
            if index == 0:
                root_info, root_certificate = info, certificate
        return dict(app=root_info['CFBundleIdentifier'], version=str(root_info['CFBundleShortVersionString']),
                    build=str(root_info['CFBundleVersion']),
                    certificate_sha256=hashlib.sha256(root_certificate).hexdigest(),
                    platform='ios', distribution=True, signature_valid=True)


def entitlement_allowed(actual, allowed):
    from fnmatch import fnmatchcase
    if isinstance(actual, dict):
        return isinstance(allowed, dict) and all(k in allowed and entitlement_allowed(v, allowed[k])
                                                 for k, v in actual.items())
    if isinstance(actual, list):
        return isinstance(allowed, list) and all(any(entitlement_allowed(v, grant) for grant in allowed)
                                                for v in actual)
    if isinstance(actual, str) and isinstance(allowed, str):
        return fnmatchcase(actual, allowed)
    return type(actual) is type(allowed) and actual == allowed



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    before = digest(args.artifact)
    data = ios(args.artifact) if args.artifact.suffix == '.ipa' else android(args.artifact)
    if digest(args.artifact) != before:
        raise ValueError('artifact changed during native verification')
    print(json.dumps(dict(data, sha256=before)))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, ET.ParseError, zipfile.BadZipFile, subprocess.SubprocessError):
        sys.exit('error: native signature/identity verification failed; inspect platform tools and signing configuration')
