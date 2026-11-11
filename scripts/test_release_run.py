"""Durable release state, immutable artifacts and application-scoped locking."""
import json
from pathlib import Path
import tempfile
import unittest

from release_run import Journal, application_lock


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.request = dict(application='com.test.app', environment='production',
                            app=str(self.root), source='abc', stores=['play', 'asc'],
                            operation='store_upload', build='42')
        self.state = self.root / 'state'

    def test_restart_resumes_same_run_and_immutable_bytes_outside_build(self):
        journal = Journal.open(self.request, self.state)
        artifact = self.root / 'build/app.aab'
        artifact.parent.mkdir()
        artifact.write_bytes(b'signed bytes')
        journal.archive({'play': artifact})
        artifact.unlink()
        resumed = Journal.open(self.request, self.state)
        self.assertEqual(journal.data['id'], resumed.data['id'])
        self.assertEqual(resumed.artifact('play').read_bytes(), b'signed bytes')

    def test_changed_source_and_tampered_artifact_cannot_resume(self):
        journal = Journal.open(self.request, self.state)
        artifact = self.root / 'app.aab'
        artifact.write_bytes(b'original')
        journal.archive({'play': artifact})
        changed = dict(self.request, source='def')
        with self.assertRaisesRegex(ValueError, 'pending'):
            Journal.open(changed, self.state)
        journal.artifact('play').chmod(0o600)
        journal.artifact('play').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'artifact'):
            journal.verify_artifacts()

    def test_lock_is_shared_across_checkouts_and_stores(self):
        with application_lock(self.request, self.state):
            other = dict(self.request, app='/other/checkout', stores=['asc'])
            with self.assertRaisesRegex(ValueError, 'locked'):
                with application_lock(other, self.state):
                    self.fail('concurrent entry')

    def test_partial_acceptance_survives_restart_and_has_timings(self):
        journal = Journal.open(self.request, self.state)
        journal.transition('play', 'accepted', reference='build-42')
        journal.transition('asc', 'processing')
        resumed = Journal.open(self.request, self.state)
        self.assertEqual(resumed.data['stores']['play']['state'], 'accepted')
        self.assertEqual(resumed.data['stores']['asc']['state'], 'processing')
        self.assertIn('at', resumed.data['events'][0])
        self.assertNotIn('succeeded', resumed.data)

    def test_retention_never_deletes_pending_releases(self):
        journal = Journal.open(self.request, self.state)
        for n in range(4):
            path = journal.path.parent / ('old-' + str(n))
            path.mkdir()
            (path / 'run.json').write_text(json.dumps(dict(journal.data, id=path.name)))
        journal.prune(keep=1)
        self.assertEqual(len(list(journal.path.parent.glob('*/run.json'))), 5)


if __name__ == '__main__':
    unittest.main()
