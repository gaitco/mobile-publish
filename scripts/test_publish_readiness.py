import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('publish_readiness.py')


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'pubspec.yaml').write_text('name: fixture\n')
        self.policy('shorebird')
        (self.root / 'shorebird.yaml').write_text('app_id: fixture-app\n')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.calls = self.root / 'calls'
        self.calls.touch()
        self.env = dict(os.environ, PATH=f'{self.bin}:/usr/bin:/bin', CALLS=str(self.calls),
                        ROLE='developer', APP_ROLE='', AUTH_FAIL='', WRONG_APP='', USERS='0')
        self.env.pop('SHOREBIRD_TOKEN', None)
        tool = self.bin / 'shorebird'
        tool.write_text('''#!/usr/bin/env python3
import json,os,sys
from datetime import datetime,timedelta,timezone
with open(os.environ['CALLS'],'a') as log: log.write(' '.join(sys.argv[1:])+'\\n')
if os.environ.get('AUTH_FAIL'):
    sys.stderr.write('fixture-secret-must-not-appear')
    sys.exit(1)
route=sys.argv[3]
if route=='/apps/fixture-app':
    data={'app_id':'wrong-app' if os.environ.get('WRONG_APP') else 'fixture-app', 'organization_id':7,
          'display_name':'Fixture','created_at':'2026-01-01','updated_at':'2026-01-01'}
elif route=='/organizations':
    data={'organizations':[{'organization':{'id':7,'name':'Fixture','organization_type':'team',
          'created_at':'2026-01-01','updated_at':'2026-01-01'},'role':os.environ['ROLE']}]}
elif route=='/organizations/7':
    if os.environ['ROLE']=='none': sys.exit(1)
    data={'organization':{'id':7,'name':'Fixture','organization_type':'team',
          'created_at':'2026-01-01','updated_at':'2026-01-01'},'role':os.environ['ROLE']}
elif route=='/users/me': data={'id':123,'email':'operator@example.invalid','display_name':'Operator'}
elif route=='/apps/fixture-app/collaborators':
    data=[{'user_id':123,'email':'operator@example.invalid','role':os.environ['APP_ROLE']}]
elif route=='/apps/fixture-app/metrics/unique-users':
    if os.environ.get('METRICS_UNAVAILABLE'): sys.exit(1)
    now=datetime.now(timezone.utc)
    data={'as_of':now.isoformat(),'granularity':None,'previous':None,'current':{
        'unique_users':int(os.environ['USERS']), 'range':{'start':(now-timedelta(days=28)).isoformat(),'end':now.isoformat()}}}
elif route=='/organizations/7/usage':
    if os.environ['ROLE']=='none': sys.exit(1)
    data={'apps':[], 'reported_overage':None, 'position':{'included_installs':5000,'installs':0,
          'remaining_installs':5000,'at_ceiling':False,'consuming_overage':False}}
else: sys.exit(2)
print(json.dumps(data))
''')
        tool.chmod(0o755)

    def policy(self, runtime):
        (self.root / 'mobile-publish.config.json').write_text(json.dumps(
            dict(schema_version=1, runtime=runtime, stores=['play'])))

    def run_check(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), str(self.root), *args],
                              env=self.env, capture_output=True, text=True)

    def test_standard_developer_without_shorebird_does_not_contact_it(self):
        self.policy('flutter')
        (self.root / 'shorebird.yaml').unlink()
        self.env['AUTH_FAIL'] = '1'
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text(), '')

    def test_checks_exact_app_and_effective_writer_role_using_only_get(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('api GET /apps/fixture-app', self.calls.read_text())
        for line in self.calls.read_text().splitlines():
            self.assertTrue(line.startswith('api GET '), line)

    def test_read_only_role_is_not_enough(self):
        self.env['ROLE'] = 'viewer'
        self.assertNotEqual(self.run_check().returncode, 0)

    def test_personal_app_collaborator_needs_their_own_matching_role(self):
        self.env.update(ROLE='none', APP_ROLE='developer')
        result = self.run_check('--acknowledge-usage-warning')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_wrong_app_cannot_pass_preflight(self):
        self.env['WRONG_APP'] = '1'
        self.assertNotEqual(self.run_check().returncode, 0)

    def test_unauthenticated_operator_does_not_leak_output_or_switch_account(self):
        self.env['AUTH_FAIL'] = '1'
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('fixture-secret-must-not-appear', result.stdout + result.stderr)
        self.assertNotIn('login', self.calls.read_text())
        self.assertNotIn('release', self.calls.read_text())

    def test_missing_cli_is_actionable_and_does_not_modify_configuration(self):
        (self.bin / 'shorebird').unlink()
        original = (self.root / 'shorebird.yaml').read_bytes()
        self.assertNotEqual(self.run_check().returncode, 0)
        self.assertEqual((self.root / 'shorebird.yaml').read_bytes(), original)

    def test_never_calls_cli_organization_listing_which_can_create_an_account_org(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls.read_text().splitlines()
        self.assertFalse(any(line.split()[:3] == ['api', 'GET', '/organizations'] for line in calls))
        self.assertIn('api GET /organizations/7', calls)

    def test_warning_blocks_until_approval_and_approval_is_not_persisted(self):
        self.env['USERS'] = '401'
        blocked = self.run_check()
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn('401', blocked.stderr)
        allowed = self.run_check('--acknowledge-usage-warning')
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertIn('401', allowed.stderr)
        self.assertNotEqual(self.run_check().returncode, 0)

    def test_400_is_allowed_and_project_can_raise_the_warning_threshold(self):
        self.env['USERS'] = '400'
        self.assertEqual(self.run_check().returncode, 0)
        self.env['USERS'] = '450'
        path = self.root / 'mobile-publish.config.json'
        data = json.loads(path.read_text())
        data['shorebird_warning_users'] = 500
        path.write_text(json.dumps(data))
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_metrics_pause_publishing_instead_of_assuming_a_small_app(self):
        self.env['METRICS_UNAVAILABLE'] = '1'
        self.assertNotEqual(self.run_check().returncode, 0)


if __name__ == '__main__':
    unittest.main()
