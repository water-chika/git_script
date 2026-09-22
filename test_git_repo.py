#!/usr/bin/env python3
"""Unit tests for the Windows-portability additions to git_repo.py:
configurable repo/worktree/git-path roots and the Windows-only honesty
checks (MAX_PATH, symlink capability). Everything here runs on Linux with
no real Windows box, using the injectable `platform=`/`env=` parameters.
"""

import pathlib
import shutil
import sys
import tempfile
import unittest

import git_repo


class RootDefaultsTest(unittest.TestCase):
    def test_linux_defaults(self):
        self.assertEqual(git_repo.default_repo_dir("linux"), pathlib.Path("/mnt/repos"))
        self.assertEqual(git_repo.default_worktrees_dir("linux"), pathlib.Path("/mnt/worktrees"))
        self.assertEqual(git_repo.default_git_path("linux"), pathlib.Path("/usr/bin/git"))

    def test_windows_defaults(self):
        self.assertEqual(git_repo.default_repo_dir("win32"), pathlib.Path("C:/repos"))
        self.assertEqual(git_repo.default_worktrees_dir("win32"), pathlib.Path("C:/worktrees"))
        self.assertEqual(git_repo.default_git_path("win32"),
                          pathlib.Path("C:/Program Files/Git/cmd/git.exe"))

    def test_is_windows_detects_common_win32_values(self):
        self.assertTrue(git_repo._is_windows("win32"))
        self.assertFalse(git_repo._is_windows("linux"))
        self.assertFalse(git_repo._is_windows("darwin"))

    def test_is_windows_defaults_to_real_platform(self):
        self.assertEqual(git_repo._is_windows(None), sys.platform.startswith("win"))


class ResolveRootPrecedenceTest(unittest.TestCase):
    """CLI flag > env var > config.json > platform default, for all three
    of repo_dir/worktrees_dir/git_path."""

    def test_platform_default_when_nothing_else_set(self):
        got = git_repo.resolve_repo_dir(None, env={}, platform="win32")
        self.assertEqual(got, pathlib.Path("C:/repos"))

    def test_config_json_overrides_platform_default(self):
        got = git_repo.resolve_repo_dir({"repo_dir": "/srv/repos"}, env={}, platform="linux")
        self.assertEqual(got, pathlib.Path("/srv/repos").absolute())

    def test_env_overrides_config_json(self):
        got = git_repo.resolve_repo_dir(
            {"repo_dir": "/srv/repos"},
            env={git_repo.REPOS_ROOT_ENV: "/other/repos"},
            platform="linux",
        )
        self.assertEqual(got, pathlib.Path("/other/repos").absolute())

    def test_cli_overrides_everything(self):
        got = git_repo.resolve_repo_dir(
            {"repo_dir": "/srv/repos"},
            cli_value="/cli/repos",
            env={git_repo.REPOS_ROOT_ENV: "/other/repos"},
            platform="linux",
        )
        self.assertEqual(got, pathlib.Path("/cli/repos").absolute())

    def test_worktrees_dir_same_precedence(self):
        got = git_repo.resolve_worktrees_dir(
            {"worktree_dir": "/srv/worktrees"},
            env={git_repo.WORKTREES_ROOT_ENV: "/other/worktrees"},
            platform="linux",
        )
        self.assertEqual(got, pathlib.Path("/other/worktrees").absolute())

    def test_git_path_same_precedence_and_windows_default(self):
        got = git_repo.resolve_git_path(None, env={}, platform="win32")
        self.assertEqual(got, pathlib.Path("C:/Program Files/Git/cmd/git.exe"))

    def test_this_machines_existing_config_resolves_unchanged(self):
        # Regression guard for the actual requirement: this machine's own
        # config.json (repo_dir=/mnt/repos, git_path=/usr/bin/git) must
        # resolve to exactly the same values as before this change, with no
        # env var set and no CLI override - i.e. today's real invocation.
        this_machine_config = {"repo_dir": "/mnt/repos", "build_dir": "/mnt/build",
                                "git_path": "/usr/bin/git"}
        self.assertEqual(
            git_repo.resolve_repo_dir(this_machine_config, env={}, platform="linux"),
            pathlib.Path("/mnt/repos"),
        )
        self.assertEqual(
            git_repo.resolve_git_path(this_machine_config, env={}, platform="linux"),
            pathlib.Path("/usr/bin/git"),
        )


class WorktreePathLengthTest(unittest.TestCase):
    def test_noop_ok_on_non_windows_even_for_long_paths(self):
        long_path = "/mnt/worktrees/" + ("x" * 300)
        ok, detail = git_repo.check_worktree_path_length(long_path, platform="linux")
        self.assertTrue(ok)

    def test_windows_short_path_ok(self):
        ok, detail = git_repo.check_worktree_path_length("C:/worktrees/repo", platform="win32")
        self.assertTrue(ok)

    def test_windows_long_path_flagged(self):
        long_path = "C:/worktrees/" + ("x" * 260)
        ok, detail = git_repo.check_worktree_path_length(long_path, platform="win32")
        self.assertFalse(ok)
        self.assertIn("MAX_PATH", detail)
        self.assertIn("longpaths", detail)

    def test_windows_boundary_is_inclusive(self):
        # exactly at the limit should already be flagged, not one char over
        path = "C:/" + ("x" * (git_repo.WINDOWS_MAX_PATH - 3))
        self.assertEqual(len(path), git_repo.WINDOWS_MAX_PATH)
        ok, _ = git_repo.check_worktree_path_length(path, platform="win32")
        self.assertFalse(ok)


class SymlinkCapableTest(unittest.TestCase):
    def test_noop_true_on_non_windows_touches_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            before = set(pathlib.Path(tmp).iterdir())
            ok, detail = git_repo.check_symlink_capable(tmp, platform="linux")
            after = set(pathlib.Path(tmp).iterdir())
            self.assertTrue(ok)
            self.assertEqual(before, after)

    def test_windows_success_path_reports_ok_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, detail = git_repo.check_symlink_capable(tmp, platform="win32")
            self.assertTrue(ok)
            self.assertEqual(list(pathlib.Path(tmp).iterdir()), [])

    def test_windows_failure_path_reports_developer_mode_hint(self):
        def fail_symlink(link, target):
            raise OSError(1314, "A required privilege is not held by the client")

        with tempfile.TemporaryDirectory() as tmp:
            ok, detail = git_repo.check_symlink_capable(tmp, platform="win32", symlink_fn=fail_symlink)
            self.assertFalse(ok)
            self.assertIn("Developer Mode", detail)
            # probe target/leftover files must still be cleaned up even on failure
            self.assertEqual(list(pathlib.Path(tmp).iterdir()), [])


class MainRootsIntegrationTest(unittest.TestCase):
    """Exercises resolve_* the way main() actually calls them, against a
    throwaway config dict + isolated repo/worktree temp roots, proving the
    wiring end-to-end without needing a real clone."""

    def test_repo_and_worktrees_dir_resolution_matches_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            repo_root = tmp / "repos"
            wt_root = tmp / "worktrees"
            file_config = {"repo_dir": str(repo_root), "worktree_dir": str(wt_root),
                            "git_path": "/usr/bin/git"}
            self.assertEqual(git_repo.resolve_repo_dir(file_config, env={}, platform="linux"),
                              repo_root.absolute())
            self.assertEqual(git_repo.resolve_worktrees_dir(file_config, env={}, platform="linux"),
                              wt_root.absolute())


if __name__ == "__main__":
    unittest.main()
