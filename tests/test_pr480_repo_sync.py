"""Real local Git remotes: refreshed reads and review-branch-only writes."""
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher.service import LauncherService


class RepoSyncTests(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.run(['git', *args], cwd=root, check=True,
                              capture_output=True, text=True, encoding='utf8').stdout.strip()

    def identity(self, root):
        self.git(root, 'config', 'user.name', 'Review Fixture')
        self.git(root, 'config', 'user.email', 'fixture@example.invalid')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='els-repo-sync-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root/'remote.git'
        self.remote.mkdir()
        self.git(self.remote, 'init', '--bare', '--initial-branch=main')
        self.a, self.b = self.root/'a', self.root/'b'
        self.git(self.root, 'clone', str(self.remote), str(self.a))
        self.identity(self.a)
        (self.a/'sample.txt').write_text('first', encoding='utf8')
        self.git(self.a, 'add', 'sample.txt')
        self.git(self.a, 'commit', '-m', 'first')
        self.git(self.a, 'push', 'origin', 'main')
        self.first = self.git(self.a, 'rev-parse', 'HEAD')
        self.git(self.root, 'clone', str(self.remote), str(self.b))
        self.identity(self.b)
        # Avoid constructing a game service or opening any player database.
        self.service = LauncherService.__new__(LauncherService)
        self.service.root = self.a
        self.service.home = self.root/'launcher'
        self.service.lock = threading.RLock()
        self.service.repo_lock = threading.RLock()
        self.service._game_busy = lambda: False

    def advance_remote(self):
        (self.b/'sample.txt').write_text('remote second', encoding='utf8')
        self.git(self.b, 'commit', '-am', 'remote second')
        self.git(self.b, 'push', 'origin', 'main')

    def assert_main_unchanged(self):
        self.assertEqual(self.git(self.remote, 'rev-parse', 'main'), self.first)
        self.assertEqual(self.git(self.a, 'rev-parse', 'main'), self.first)

    def test_refresh_discovers_remote_commit_and_pull_fast_forwards(self):
        self.advance_remote()
        self.assertEqual(self.service.repo_state()['behind'], 0)
        state = self.service.repo_state(refresh=True)
        self.assertEqual(state['behind'], 1)
        self.assertTrue(state['remote_checked'])
        self.assertTrue(state['can_pull'])
        self.service.repo_pull()
        self.assertEqual(self.git(self.a, 'rev-parse', 'HEAD'),
                         self.git(self.remote, 'rev-parse', 'main'))
        self.assertEqual((self.a/'sample.txt').read_text(), 'remote second')

    def test_refresh_failure_does_not_report_synchronized(self):
        original = self.service._git
        def fail_fetch(*args, **kwargs):
            if args[0] == 'fetch':
                return subprocess.CompletedProcess(args, 1, '', 'offline fixture')
            return original(*args, **kwargs)
        with patch.object(self.service, '_git', side_effect=fail_fetch):
            with self.assertRaisesRegex(ValueError, 'offline fixture'):
                self.service.repo_state(refresh=True)

    def test_main_changes_are_pushed_only_to_new_review_branch(self):
        (self.a/'new.txt').write_text('review me', encoding='utf8')
        result = self.service.repo_commit({'message': 'review fixture'})
        branch = result['branch']
        self.assertTrue(branch.startswith('fix/local-'))
        self.assertEqual(self.git(self.a, 'branch', '--show-current'), branch)
        self.assertEqual(self.git(self.remote, 'rev-parse', branch),
                         self.git(self.a, 'rev-parse', 'HEAD'))
        self.assert_main_unchanged()

    def test_failed_push_retry_reuses_commit_and_branch_without_message(self):
        (self.a/'new.txt').write_text('review me', encoding='utf8')
        original = self.service._git
        def fail_push(*args, **kwargs):
            if args[0] == 'push':
                return subprocess.CompletedProcess(args, 1, '', 'push fixture failed')
            return original(*args, **kwargs)
        with patch.object(self.service, '_git', side_effect=fail_push):
            with self.assertRaisesRegex(ValueError, 'push fixture failed'):
                self.service.repo_commit({'message': 'one commit only'})
        branch = self.git(self.a, 'branch', '--show-current')
        head = self.git(self.a, 'rev-parse', 'HEAD')
        result = self.service.repo_commit({})
        self.assertEqual(result['branch'], branch)
        self.assertEqual(self.git(self.a, 'rev-parse', 'HEAD'), head)
        self.assertEqual(self.git(self.remote, 'rev-parse', branch), head)
        self.assert_main_unchanged()

    def test_concurrent_branch_push_is_rejected_without_rebase_or_force(self):
        self.git(self.a, 'switch', '-c', 'fix/existing')
        (self.a/'new.txt').write_text('first branch commit', encoding='utf8')
        self.service.repo_commit({'message': 'publish branch'})
        self.git(self.b, 'fetch', 'origin')
        self.git(self.b, 'switch', '--track', 'origin/fix/existing')
        (self.b/'other.txt').write_text('other author', encoding='utf8')
        self.git(self.b, 'add', 'other.txt')
        self.git(self.b, 'commit', '-m', 'concurrent change')
        self.git(self.b, 'push')
        other_head = self.git(self.remote, 'rev-parse', 'fix/existing')
        (self.a/'local.txt').write_text('local change', encoding='utf8')
        with self.assertRaisesRegex(ValueError, '推送失败'):
            self.service.repo_commit({'message': 'keep both histories'})
        self.assertEqual(self.git(self.remote, 'rev-parse', 'fix/existing'), other_head)
        self.assertEqual(self.git(self.a, 'rev-list', '--count', self.first+'..HEAD'), '2')
        self.assertEqual(self.git(self.a, 'branch', '--show-current'), 'fix/existing')
        self.assert_main_unchanged()

    def test_diverged_main_pull_preserves_both_histories(self):
        (self.a/'local.txt').write_text('local', encoding='utf8')
        self.git(self.a, 'add', 'local.txt')
        self.git(self.a, 'commit', '-m', 'local main change')
        local_head = self.git(self.a, 'rev-parse', 'HEAD')
        self.advance_remote()
        self.assertFalse(self.service.repo_state(refresh=True)['can_pull'])
        with self.assertRaisesRegex(ValueError, '不能自动改写'):
            self.service.repo_pull()
        self.assertEqual(self.git(self.a, 'rev-parse', 'HEAD'), local_head)
        self.assertEqual((self.a/'local.txt').read_text(), 'local')

    def test_busy_and_snapshot_branch_reject_writes(self):
        (self.a/'new.txt').write_text('local', encoding='utf8')
        with patch.object(self.service, '_game_busy', return_value=True):
            with self.assertRaisesRegex(ValueError, '退出游戏'):
                self.service.repo_commit({'message': 'blocked'})
        self.git(self.a, 'switch', '-c', 'snapshot/accepted')
        with self.assertRaisesRegex(ValueError, '不能推送快照'):
            self.service.repo_commit({'message': 'blocked'})
        self.assert_main_unchanged()

    def test_empty_commit_does_not_create_branch(self):
        with self.assertRaisesRegex(ValueError, '没有可提交'):
            self.service.repo_commit({})
        self.assertEqual(self.git(self.a, 'branch', '--show-current'), 'main')

    def test_review_link_uses_review_branch_and_never_credentials(self):
        url = self.service._review_url('https://github.com/example/project.git', 'fix/fixture')
        self.assertEqual(url, 'https://github.com/example/project/compare/main...fix%2Ffixture?expand=1')
        self.assertIsNone(self.service._review_url('https://github.com/example/project.git', 'main'))
        self.assertIsNone(self.service._review_url('https://name:private@example.invalid/project', 'fix/fixture'))


if __name__ == '__main__':
    unittest.main()
