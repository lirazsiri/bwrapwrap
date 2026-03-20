"""Verify generated bwrap arguments via --dry-run."""

import os
import pathlib

from conftest import run_sandbox


def dry_run(args, cwd=None):
    r = run_sandbox(["--dry-run"] + args, cwd=cwd)
    assert r.returncode == 0, f"dry-run failed: {r.stderr}"
    return r.stdout


def encode_claude_path(path):
    return path.replace("/", "-").replace(".", "-")


class TestDefaultBinds:
    def test_includes_static_ro_binds(self, sandbox_bin, tmp_cwd):
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        for d in ["/usr", "/lib", "/lib64", "/bin", "/sbin"]:
            assert f"--ro-bind {d} {d}" in out

    def test_includes_proc_dev_tmp(self, sandbox_bin, tmp_cwd):
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        assert "--proc /proc" in out
        assert "--dev /dev" in out
        assert "--tmpfs /tmp" in out

    def test_includes_hostname(self, sandbox_bin, tmp_cwd):
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        assert "--hostname sandbox" in out

    def test_cwd_bound_rw(self, sandbox_bin, tmp_cwd):
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        assert f"--bind {tmp_cwd} {tmp_cwd}" in out

    def test_home_set(self, sandbox_bin, tmp_cwd):
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        assert f"--setenv HOME {os.environ['HOME']}" in out

    def test_path_set(self, sandbox_bin, tmp_cwd):
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        assert "--setenv PATH " in out


class TestNetworkFlag:
    def test_default_unshare_net(self, sandbox_bin, tmp_cwd):
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        assert "--unshare-net" in out
        assert "--share-net" not in out

    def test_net_flag_shares_net(self, sandbox_bin, tmp_cwd):
        out = dry_run(["--net", "echo", "hi"], cwd=tmp_cwd)
        assert "--share-net" in out


class TestPtraceFlag:
    def test_ptrace_adds_cap(self, sandbox_bin, tmp_cwd):
        out = dry_run(["--ptrace", "echo", "hi"], cwd=tmp_cwd)
        assert "--cap-add CAP_SYS_PTRACE" in out

    def test_no_ptrace_by_default(self, sandbox_bin, tmp_cwd):
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        assert "CAP_SYS_PTRACE" not in out


class TestCargoRustup:
    def test_cargo_bound_if_exists(self, sandbox_bin, tmp_cwd):
        cargo = pathlib.Path.home() / ".cargo"
        if not cargo.is_dir():
            return  # skip silently
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        assert f"--ro-bind {cargo} {cargo}" in out

    def test_rustup_bound_if_exists(self, sandbox_bin, tmp_cwd):
        rustup = pathlib.Path.home() / ".rustup"
        if not rustup.is_dir():
            return
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        assert f"--ro-bind {rustup} {rustup}" in out


class TestClaudeDetection:
    def test_claude_binds_project_session_dir(self, sandbox_bin, tmp_cwd):
        """Claude command binds only the project session dir, not all of ~/.claude."""
        home = os.environ["HOME"]
        claude_dir = os.path.join(home, ".claude")
        if not os.path.isdir(claude_dir):
            return
        encoded = encode_claude_path(tmp_cwd)
        project_dir = os.path.join(claude_dir, "projects", encoded)
        os.makedirs(project_dir, exist_ok=True)
        try:
            out = dry_run(["claude"], cwd=tmp_cwd)
            # Should bind the specific project session dir rw
            assert f"--bind {project_dir} {project_dir}" in out
            # Should NOT bind all of ~/.claude
            assert f"--bind {claude_dir} {claude_dir}" not in out
        finally:
            # Only remove if we created it and it's empty
            try:
                os.rmdir(project_dir)
            except OSError:
                pass

    def test_claude_binds_credentials_ro(self, sandbox_bin, tmp_cwd):
        """Claude command binds .credentials.json read-only."""
        home = os.environ["HOME"]
        creds = os.path.join(home, ".claude", ".credentials.json")
        if not os.path.isfile(creds):
            return
        out = dry_run(["claude"], cwd=tmp_cwd)
        assert f"--ro-bind {creds} {creds}" in out

    def test_claude_binds_settings_ro(self, sandbox_bin, tmp_cwd):
        """Claude command binds settings.json read-only."""
        home = os.environ["HOME"]
        settings = os.path.join(home, ".claude", "settings.json")
        if not os.path.isfile(settings):
            return
        out = dry_run(["claude"], cwd=tmp_cwd)
        assert f"--ro-bind {settings} {settings}" in out

    def test_claude_binds_global_claude_md_ro(self, sandbox_bin, tmp_cwd):
        """Claude command binds CLAUDE.md read-only."""
        home = os.environ["HOME"]
        claude_md = os.path.join(home, ".claude", "CLAUDE.md")
        if not os.path.isfile(claude_md):
            return
        out = dry_run(["claude"], cwd=tmp_cwd)
        assert f"--ro-bind {claude_md} {claude_md}" in out

    def test_claude_code_command_detected(self, sandbox_bin, tmp_cwd):
        """claude-code also triggers claude detection."""
        home = os.environ["HOME"]
        claude_dir = os.path.join(home, ".claude")
        if not os.path.isdir(claude_dir):
            return
        out = dry_run(["claude-code"], cwd=tmp_cwd)
        # Should have claude-related ro binds
        creds = os.path.join(claude_dir, ".credentials.json")
        if os.path.isfile(creds):
            assert f"--ro-bind {creds} {creds}" in out

    def test_ls_no_claude_binds(self, sandbox_bin, tmp_cwd):
        """Non-claude command gets no claude binds at all."""
        home = os.environ["HOME"]
        out = dry_run(["ls"], cwd=tmp_cwd)
        assert f"{home}/.claude" not in out

    def test_claude_no_other_project_sessions(self, sandbox_bin, tmp_cwd):
        """Claude command must not bind other projects' session dirs."""
        home = os.environ["HOME"]
        projects_dir = os.path.join(home, ".claude", "projects")
        if not os.path.isdir(projects_dir):
            return
        encoded = encode_claude_path(tmp_cwd)
        out = dry_run(["claude"], cwd=tmp_cwd)
        # The only project dir bound should be for our cwd
        for entry in os.listdir(projects_dir):
            if entry == encoded:
                continue
            entry_path = os.path.join(projects_dir, entry)
            assert f"--bind {entry_path} {entry_path}" not in out

    def test_claude_basename_detection(self, sandbox_bin, tmp_cwd):
        """Command with path like /usr/bin/claude detected via basename."""
        home = os.environ["HOME"]
        if not os.path.isdir(os.path.join(home, ".claude")):
            return
        out = dry_run(["/usr/bin/claude"], cwd=tmp_cwd)
        creds = os.path.join(home, ".claude", ".credentials.json")
        if os.path.isfile(creds):
            assert f"--ro-bind {creds} {creds}" in out
