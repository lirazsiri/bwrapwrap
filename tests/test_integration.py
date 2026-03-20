"""Integration tests that actually run sandboxed commands (require bwrap)."""

import os
import shutil

import pytest

from conftest import run_sandbox


pytestmark = pytest.mark.skipif(
    not shutil.which("bwrap"), reason="bwrap not installed"
)


class TestBasicExecution:
    def test_echo(self, tmp_cwd):
        r = run_sandbox(["echo", "hello"], cwd=tmp_cwd)
        assert r.returncode == 0
        assert r.stdout.strip() == "hello"

    def test_false_exits_nonzero(self, tmp_cwd):
        r = run_sandbox(["false"], cwd=tmp_cwd)
        assert r.returncode != 0

    def test_hostname(self, tmp_cwd):
        r = run_sandbox(["hostname"], cwd=tmp_cwd)
        assert r.stdout.strip() == "sandbox"

    def test_command_not_found(self, tmp_cwd):
        r = run_sandbox(["nonexistent_command_xyz"], cwd=tmp_cwd)
        assert r.returncode != 0


class TestFilesystem:
    def test_usr_readonly(self, tmp_cwd):
        r = run_sandbox(["touch", "/usr/testfile"], cwd=tmp_cwd)
        assert r.returncode != 0

    def test_cwd_writable(self, tmp_cwd):
        r = run_sandbox(["touch", "testfile"], cwd=tmp_cwd)
        assert r.returncode == 0
        assert os.path.exists(os.path.join(tmp_cwd, "testfile"))

    def test_path_dirs_accessible(self, tmp_cwd):
        """Can run binaries from PATH locations."""
        r = run_sandbox(["which", "ls"], cwd=tmp_cwd)
        assert r.returncode == 0


class TestNetwork:
    def test_network_blocked_by_default(self, tmp_cwd):
        if not shutil.which("curl"):
            pytest.skip("curl not installed")
        r = run_sandbox(
            ["sh", "-c", "curl -s --max-time 5 http://example.com"],
            cwd=tmp_cwd,
            timeout=30,
        )
        assert r.returncode != 0

    def test_network_allowed_with_flag(self, tmp_cwd):
        if not shutil.which("curl"):
            pytest.skip("curl not installed")
        r = run_sandbox(
            ["--net", "sh", "-c", "curl -s --max-time 10 http://example.com"],
            cwd=tmp_cwd,
            timeout=30,
        )
        assert r.returncode == 0
        assert len(r.stdout) > 0


class TestPtrace:
    def test_ptrace_with_strace(self, tmp_cwd):
        if not shutil.which("strace"):
            pytest.skip("strace not installed")
        r = run_sandbox(
            ["--ptrace", "strace", "-e", "trace=write", "echo", "hi"],
            cwd=tmp_cwd,
        )
        assert r.returncode == 0
