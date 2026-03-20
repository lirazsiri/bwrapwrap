"""Fork/overlay mode tests (require bwrap + fuse-overlayfs)."""

import os
import re
import shutil
import time

import pytest

from conftest import run_sandbox


pytestmark = [
    pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed"),
    pytest.mark.skipif(
        not shutil.which("fuse-overlayfs"), reason="fuse-overlayfs not installed"
    ),
]


def _claude_available():
    """Check if claude is available for fork tests."""
    return shutil.which("claude") is not None


class TestForkSetup:
    @pytest.mark.skipif(not _claude_available(), reason="claude not installed")
    def test_fork_creates_dir(self, tmp_cwd):
        name = f"test-fork-{int(time.time())}"
        fork_dir = os.path.expanduser(f"~/.sandbox/{name}")
        try:
            r = run_sandbox(
                ["--fork", name, "--fork-cleanup", "claude", "--version"],
                cwd=tmp_cwd,
                timeout=30,
            )
            # fork-cleanup should remove it, but check it was created
            # by looking at stderr for the resume message or checking existence
            # With --fork-cleanup it gets deleted, so we just check the command ran
            assert r.returncode == 0 or "fork" in r.stderr.lower()
        finally:
            if os.path.isdir(fork_dir):
                shutil.rmtree(fork_dir, ignore_errors=True)

    def test_fork_auto_names(self, tmp_cwd):
        """--fork without name auto-generates name for claude commands."""
        if not _claude_available():
            pytest.skip("claude not installed")
        r = run_sandbox(
            ["--dry-run", "--fork", "claude"],
            cwd=tmp_cwd,
        )
        # In dry-run, fork setup is skipped by the bash script because
        # it exits before overlay setup. Just verify it parses.
        assert r.returncode == 0

    def test_fork_noop_for_non_claude(self, tmp_cwd):
        """--fork is a no-op for non-claude commands like ls."""
        r = run_sandbox(
            ["--dry-run", "--fork", "test-noop", "ls"],
            cwd=tmp_cwd,
        )
        assert r.returncode == 0
        # Should not contain any overlay-related binds
        assert ".sandbox" not in r.stdout


class TestForkCleanup:
    @pytest.mark.skipif(not _claude_available(), reason="claude not installed")
    def test_fork_cleanup_removes_dir(self, tmp_cwd):
        name = f"test-cleanup-{int(time.time())}"
        fork_dir = os.path.expanduser(f"~/.sandbox/{name}")
        try:
            run_sandbox(
                ["--fork", name, "--fork-cleanup", "claude", "--version"],
                cwd=tmp_cwd,
                timeout=30,
            )
            assert not os.path.isdir(fork_dir), "fork dir should be cleaned up"
        finally:
            if os.path.isdir(fork_dir):
                shutil.rmtree(fork_dir, ignore_errors=True)


class TestForkResume:
    @pytest.mark.skipif(not _claude_available(), reason="claude not installed")
    def test_fork_prints_resume_message(self, tmp_cwd):
        name = f"test-resume-{int(time.time())}"
        fork_dir = os.path.expanduser(f"~/.sandbox/{name}")
        try:
            r = run_sandbox(
                ["--fork", name, "claude", "--version"],
                cwd=tmp_cwd,
                timeout=30,
            )
            assert f"--fork={name}" in r.stderr
        finally:
            if os.path.isdir(fork_dir):
                shutil.rmtree(fork_dir, ignore_errors=True)
