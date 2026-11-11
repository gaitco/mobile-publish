"""Installation uses only Git, and preserves local work and account files."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('install_skill.py')


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='publish install ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.git('init', '-q', str(self.source))
        self.git('-C', str(self.source), 'config', 'user.email', 'fixture@example.invalid')
        self.git('-C', str(self.source), 'config', 'user.name', 'Fixture')
        (self.source / 'SKILL.md').write_text('first\n')
        self.commit()
        self.home = self.root / 'home'
        self.home.mkdir()
        self.env = dict(os.environ, HOME=str(self.home))

    def git(self, *args):
        return subprocess.check_output(['git', *args], text=True).strip()

    def commit(self):
        self.git('-C', str(self.source), 'add', 'SKILL.md')
        self.git('-C', str(self.source), 'commit', '-qm', 'fixture')
        self.revision = self.git('-C', str(self.source), 'rev-parse', 'HEAD')

    def run_installer(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), '--source', str(self.source),
                               '--revision', self.revision, '--target', 'all', *args],
                              env=self.env, text=True, capture_output=True, timeout=20)

    def test_installs_both_runtimes_and_registers_rules_idempotently(self):
        for _ in range(2):
            result = self.run_installer('--register')
            self.assertEqual(result.returncode, 0, result.stderr)
        for folder in ['.agents/skills/mobile-publish', '.claude/skills/mobile-publish']:
            self.assertEqual((self.home / folder / 'SKILL.md').read_text(), 'first\n')
            self.assertEqual(self.git('-C', str(self.home / folder), 'rev-parse', 'HEAD'), self.revision)
        for file in ['.codex/AGENTS.md', '.claude/CLAUDE.md']:
            self.assertEqual((self.home / file).read_text().count('<!-- mobile-publish:start -->'), 1)

    def test_check_never_creates_files_or_changes_registration(self):
        result = self.run_installer('--check', '--register')
        self.assertNotEqual(result.returncode, 0)
        for folder in ['.agents', '.claude', '.codex']:
            self.assertFalse((self.home / folder).exists())

    def test_updates_clean_clone_but_preserves_unrelated_rules(self):
        rules = self.home / '.codex/AGENTS.md'
        rules.parent.mkdir()
        rules.write_text('Keep my project conventions.\n')
        self.assertEqual(self.run_installer('--register').returncode, 0)
        (self.source / 'SKILL.md').write_text('second\n')
        self.commit()
        result = self.run_installer('--register')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(rules.read_text().startswith('Keep my project conventions.\n'))
        self.assertEqual((self.home / '.agents/skills/mobile-publish/SKILL.md').read_text(), 'second\n')

    def test_dirty_clone_is_preserved(self):
        self.assertEqual(self.run_installer().returncode, 0)
        local = self.home / '.agents/skills/mobile-publish/SKILL.md'
        local.write_text('my changes\n')
        result = self.run_installer('--register')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(local.read_text(), 'my changes\n')
        self.assertFalse((self.home / '.codex/AGENTS.md').exists())

    def test_wrong_origin_and_non_git_directory_are_never_overwritten(self):
        self.assertEqual(self.run_installer().returncode, 0)
        target = self.home / '.agents/skills/mobile-publish'
        self.git('-C', str(target), 'remote', 'set-url', 'origin', 'https://example.invalid/other.git')
        self.assertNotEqual(self.run_installer().returncode, 0)
        self.assertEqual((target / 'SKILL.md').read_text(), 'first\n')

    def test_never_copies_credentials_from_home(self):
        secret = self.home / '.config/asc/config'
        secret.parent.mkdir(parents=True)
        secret.write_text('fixture-secret-do-not-copy')
        result = self.run_installer('--register')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(secret.read_text(), 'fixture-secret-do-not-copy')
        for target in ['.agents/skills/mobile-publish', '.claude/skills/mobile-publish']:
            self.assertFalse((self.home / target / '.config').exists())

    def test_committed_local_work_is_not_mistaken_for_the_approved_revision(self):
        self.assertEqual(self.run_installer().returncode, 0)
        target = self.home / '.claude/skills/mobile-publish'
        self.git('-C', str(target), 'config', 'user.email', 'fixture@example.invalid')
        self.git('-C', str(target), 'config', 'user.name', 'Fixture')
        (target / 'SKILL.md').write_text('my committed local work\n')
        self.git('-C', str(target), 'add', 'SKILL.md')
        self.git('-C', str(target), 'commit', '-qm', 'local work')
        original = self.git('-C', str(target), 'rev-parse', 'HEAD')
        result = self.run_installer('--register')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git('-C', str(target), 'rev-parse', 'HEAD'), original)
        self.assertFalse((self.home / '.codex/AGENTS.md').exists())
        self.assertFalse((self.home / '.claude/CLAUDE.md').exists())


if __name__ == '__main__':
    unittest.main()
