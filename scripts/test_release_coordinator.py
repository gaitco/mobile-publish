"""End-to-end tests using isolated project tools, never a live store or SDK."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('release_coordinator.py')


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / 'app'
        self.app.mkdir()
        self.home = self.root / 'home'
        self.home.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), TEST_STATE=str(self.root / 'remote.json'),
                        TEST_LOG=str(self.root / 'calls'))
        (self.app / 'pubspec.yaml').write_text('name: test\nversion: 1.2.0+42\n')
        (self.app / '.gitignore').write_text('build/\n')
        (self.app / 'mobile-publish.config.json').write_text(json.dumps(
            dict(schema_version=1, runtime='flutter', stores=['play', 'asc'])))
        subprocess.run(['git', 'init', '-q', str(self.app)], check=True)
        adapter = self.app / 'adapter.py'
        adapter.write_text('''import hashlib,json,os,pathlib,sys
action=sys.argv[1]
log=pathlib.Path(os.environ['TEST_LOG'])
with log.open('a') as f:f.write(action+'\\n')
if action=='sdk':
 print(json.dumps({'frameworkVersion':'3.47.7'}));sys.exit()
if action=='build':
 p=pathlib.Path('build');p.mkdir(exist_ok=True)
 (p/'app.aab').write_bytes(b'android signed')
 (p/'app.ipa').write_bytes(b'ios signed')
 sys.exit()
request=json.loads(pathlib.Path(sys.argv[2]).read_text())
remote=pathlib.Path(os.environ['TEST_STATE'])
states=json.loads(remote.read_text()) if remote.exists() else {}
if action=='qa':
 print(json.dumps({'artifacts':request['artifacts'],'launched':True,
                   'platforms':['android','ios'],'dedicated':True}));sys.exit()
store=sys.argv[3]
if action=='verify':
 artifact=pathlib.Path(sys.argv[4])
 print(json.dumps({'app':request['identities'][store],'version':request['version'],
 'build':request['build'],'platform':'ios' if store=='asc' else 'android',
 'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),
 'signature_valid':os.environ.get('BAD_SIGNING')!='1',
 'distribution':True,'certificate_sha256':'A'*64}));sys.exit()
if action=='status':
 state=states.get(store,'absent')
 print(json.dumps({'app':request['identities'][store],'version':request['version'],
 'build':request['build'],'platform':'ios' if store=='asc' else 'android',
 'track':'testflight' if store=='asc' else request['track'], 'state':state,
 'reference':'build-42' if state!='absent' else None,
 'complete':True,'version_available':True,
 'publish_authorized':os.environ.get('READ_ONLY')!='1'}));sys.exit()
if action=='upload':
 if store==os.environ.get('FAIL_STORE'):
  print('https://signed.invalid?token=SECRET',file=sys.stderr);sys.exit(1)
 states[store]='processing' if os.environ.get('PROCESSING') else 'accepted'
 remote.write_text(json.dumps(states))
''')
        command = [sys.executable, 'adapter.py']
        self.profile = dict(schema_version=1, environment='production',
                            identities=dict(play='com.test.app', asc='com.test.ios'),
                            sdk=dict(version='3.47.7', command=command + ['sdk']),
                            build=[command + ['build']],
                            artifacts=dict(play='build/app.aab', asc='build/app.ipa'),
                            qa=command + ['qa', '{request}'], stores={})
        for store in ['play', 'asc']:
            self.profile['stores'][store] = dict(
                status=command + ['status', '{request}', store],
                upload=command + ['upload', '{request}', store, '{artifact}'],
                verify=command + ['verify', '{request}', store, '{artifact}'],
                certificate_sha256='A' * 64)
        self.write_profile()

    def write_profile(self):
        (self.app / 'mobile-publish.release.json').write_text(json.dumps(self.profile))

    def run_release(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.app,
                              env=self.env, capture_output=True, text=True, timeout=20)

    def calls(self):
        log = self.root / 'calls'
        return log.read_text().splitlines() if log.exists() else []

    def test_check_is_offline_and_does_not_execute_project_commands(self):
        result = self.run_release('--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [])

    def test_online_check_does_not_create_a_pending_release(self):
        result = self.run_release('--check-online')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.home.glob('.local/state/mobile-publish/*/*/run.json')), [])

    def test_actual_sdk_mismatch_prevents_build_and_upload(self):
        self.profile['sdk']['version'] = '3.44.0'
        self.write_profile()
        result = self.run_release('--prepare')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('build', self.calls())
        self.assertNotIn('upload', self.calls())

    def test_prepare_then_resume_after_clean_and_skip_accepted_store(self):
        self.assertEqual(self.run_release('--prepare').returncode, 0)
        (self.app / 'build/app.aab').unlink()
        (self.app / 'build/app.ipa').unlink()
        self.env['FAIL_STORE'] = 'asc'
        first = self.run_release('--upload-prepared')
        self.assertNotEqual(first.returncode, 0)
        self.assertNotIn('SECRET', first.stdout + first.stderr)
        self.env.pop('FAIL_STORE')
        final = self.run_release('--upload-prepared')
        self.assertEqual(final.returncode, 0, final.stderr)
        self.assertEqual(self.calls().count('build'), 1)
        self.assertEqual(self.calls().count('upload'), 3)
        journals = list(self.home.glob('.local/state/mobile-publish/*/*/run.json'))
        self.assertEqual(len(journals), 1)
        state = json.loads(journals[0].read_text())
        self.assertEqual({s['state'] for s in state['stores'].values()}, {'accepted'})

    def test_bad_signing_or_missing_publish_role_stops_all_uploads(self):
        self.env['READ_ONLY'] = '1'
        self.assertNotEqual(self.run_release('--prepare').returncode, 0)
        self.assertNotIn('build', self.calls())
        self.env.pop('READ_ONLY')
        self.env['BAD_SIGNING'] = '1'
        self.assertNotEqual(self.run_release('--prepare').returncode, 0)
        self.assertNotIn('upload', self.calls())

    def test_processing_does_not_reupload_or_report_acceptance(self):
        self.assertEqual(self.run_release('--prepare').returncode, 0)
        self.env['PROCESSING'] = '1'
        self.assertNotEqual(self.run_release('--upload-prepared').returncode, 0)
        count = self.calls().count('upload')
        self.assertNotEqual(self.run_release('--upload-prepared').returncode, 0)
        self.assertEqual(self.calls().count('upload'), count)

    def test_source_change_sdk_mismatch_and_non_upload_operation_block(self):
        self.assertEqual(self.run_release('--prepare').returncode, 0)
        (self.app / 'pubspec.yaml').write_text('name: changed\nversion: 1.2.0+42\n')
        self.assertNotEqual(self.run_release('--upload-prepared').returncode, 0)
        self.assertNotIn('upload', self.calls())
        self.assertNotEqual(self.run_release('--operation', 'ota_patch').returncode, 0)

    def test_duplicate_remote_version_blocks_before_build(self):
        Path(self.env['TEST_STATE']).write_text('{"play":"accepted"}')
        self.assertNotEqual(self.run_release('--prepare').returncode, 0)
        self.assertNotIn('build', self.calls())


if __name__ == '__main__':
    unittest.main()
