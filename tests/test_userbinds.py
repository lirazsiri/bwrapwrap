"""Tests for user-specified binds via CLI flags and .bwrapwrap config."""

import os

from conftest import run_sandbox


def dry_run(args, cwd=None):
    r = run_sandbox(["--dry-run"] + args, cwd=cwd)
    assert r.returncode == 0, f"dry-run failed: {r.stderr}"
    return r.stdout


class TestCliBindFlags:
    def test_bind_flag(self, tmp_cwd):
        target = os.path.join(tmp_cwd, "rw-dir")
        os.makedirs(target)
        out = dry_run(["--bind", target, "echo", "hi"], cwd=tmp_cwd)
        assert f"--bind {target} {target}" in out

    def test_ro_bind_flag(self, tmp_cwd):
        target = os.path.join(tmp_cwd, "ro-dir")
        os.makedirs(target)
        out = dry_run(["--ro-bind", target, "echo", "hi"], cwd=tmp_cwd)
        assert f"--ro-bind {target} {target}" in out

    def test_bind_equals_syntax(self, tmp_cwd):
        target = os.path.join(tmp_cwd, "eq-dir")
        os.makedirs(target)
        out = dry_run([f"--bind={target}", "echo", "hi"], cwd=tmp_cwd)
        assert f"--bind {target} {target}" in out

    def test_ro_bind_equals_syntax(self, tmp_cwd):
        target = os.path.join(tmp_cwd, "eq-ro-dir")
        os.makedirs(target)
        out = dry_run([f"--ro-bind={target}", "echo", "hi"], cwd=tmp_cwd)
        assert f"--ro-bind {target} {target}" in out

    def test_multiple_binds(self, tmp_cwd):
        d1 = os.path.join(tmp_cwd, "d1")
        d2 = os.path.join(tmp_cwd, "d2")
        os.makedirs(d1)
        os.makedirs(d2)
        out = dry_run(["--bind", d1, "--ro-bind", d2, "echo", "hi"], cwd=tmp_cwd)
        assert f"--bind {d1} {d1}" in out
        assert f"--ro-bind {d2} {d2}" in out

    def test_bind_missing_arg(self, tmp_cwd):
        r = run_sandbox(["--dry-run", "--bind"], cwd=tmp_cwd)
        assert r.returncode != 0

    def test_bind_nonexistent_path_skipped(self, tmp_cwd):
        """Binds to nonexistent paths are silently skipped."""
        out = dry_run(["--bind", "/nonexistent/path/xyz", "echo", "hi"], cwd=tmp_cwd)
        assert "/nonexistent/path/xyz" not in out


class TestConfigFile:
    def test_config_bind(self, tmp_cwd):
        target = os.path.join(tmp_cwd, "cfg-rw")
        os.makedirs(target)
        with open(os.path.join(tmp_cwd, ".bwrapwrap"), "w") as f:
            f.write(f"bind {target}\n")
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        assert f"--bind {target} {target}" in out

    def test_config_ro_bind(self, tmp_cwd):
        target = os.path.join(tmp_cwd, "cfg-ro")
        os.makedirs(target)
        with open(os.path.join(tmp_cwd, ".bwrapwrap"), "w") as f:
            f.write(f"ro-bind {target}\n")
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        assert f"--ro-bind {target} {target}" in out

    def test_config_comments_and_blanks(self, tmp_cwd):
        target = os.path.join(tmp_cwd, "cfg-dir")
        os.makedirs(target)
        with open(os.path.join(tmp_cwd, ".bwrapwrap"), "w") as f:
            f.write(f"# this is a comment\n\nbind {target}\n")
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        assert f"--bind {target} {target}" in out

    def test_config_bad_directive(self, tmp_cwd):
        with open(os.path.join(tmp_cwd, ".bwrapwrap"), "w") as f:
            f.write("bogus /tmp\n")
        r = run_sandbox(["--dry-run", "echo", "hi"], cwd=tmp_cwd)
        assert r.returncode != 0

    def test_config_relative_path(self, tmp_cwd):
        target = os.path.join(tmp_cwd, "reldir")
        os.makedirs(target)
        with open(os.path.join(tmp_cwd, ".bwrapwrap"), "w") as f:
            f.write("bind reldir\n")
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        assert f"--bind {target} {target}" in out

    def test_config_tilde_expansion(self, tmp_cwd):
        home = os.environ["HOME"]
        with open(os.path.join(tmp_cwd, ".bwrapwrap"), "w") as f:
            f.write("ro-bind ~/.config\n")
        if os.path.isdir(os.path.join(home, ".config")):
            out = dry_run(["echo", "hi"], cwd=tmp_cwd)
            config_real = os.path.realpath(os.path.join(home, ".config"))
            assert f"--ro-bind {config_real} {config_real}" in out


class TestConfigBooleans:
    def test_config_net(self, tmp_cwd):
        with open(os.path.join(tmp_cwd, ".bwrapwrap"), "w") as f:
            f.write("net\n")
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        assert "--share-net" in out

    def test_config_ptrace(self, tmp_cwd):
        with open(os.path.join(tmp_cwd, ".bwrapwrap"), "w") as f:
            f.write("ptrace\n")
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        assert "--cap-add CAP_SYS_PTRACE" in out

    def test_cli_no_net_overrides_config(self, tmp_cwd):
        """--no-net on CLI overrides net in config."""
        with open(os.path.join(tmp_cwd, ".bwrapwrap"), "w") as f:
            f.write("net\n")
        out = dry_run(["--no-net", "echo", "hi"], cwd=tmp_cwd)
        assert "--unshare-net" in out
        assert "--share-net" not in out

    def test_cli_no_ptrace_overrides_config(self, tmp_cwd):
        """--no-ptrace on CLI overrides ptrace in config."""
        with open(os.path.join(tmp_cwd, ".bwrapwrap"), "w") as f:
            f.write("ptrace\n")
        out = dry_run(["--no-ptrace", "echo", "hi"], cwd=tmp_cwd)
        assert "CAP_SYS_PTRACE" not in out

    def test_cli_net_without_config(self, tmp_cwd):
        """--net works without a config file."""
        out = dry_run(["--net", "echo", "hi"], cwd=tmp_cwd)
        assert "--share-net" in out

    def test_cli_net_overrides_absent_config(self, tmp_cwd):
        """--net on CLI works even with empty config."""
        with open(os.path.join(tmp_cwd, ".bwrapwrap"), "w") as f:
            f.write("# no net here\n")
        out = dry_run(["--net", "echo", "hi"], cwd=tmp_cwd)
        assert "--share-net" in out

    def test_default_no_net_no_ptrace(self, tmp_cwd):
        """Without config or CLI flags, net is blocked and ptrace denied."""
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        assert "--unshare-net" in out
        assert "CAP_SYS_PTRACE" not in out


class TestInit:
    def test_init_net(self, tmp_cwd):
        r = run_sandbox(["--net", "--init"], cwd=tmp_cwd)
        assert r.returncode == 0
        config = os.path.join(tmp_cwd, ".bwrapwrap")
        assert os.path.isfile(config)
        content = open(config).read()
        assert "net\n" in content

    def test_init_ptrace(self, tmp_cwd):
        r = run_sandbox(["--ptrace", "--init"], cwd=tmp_cwd)
        assert r.returncode == 0
        content = open(os.path.join(tmp_cwd, ".bwrapwrap")).read()
        assert "ptrace\n" in content

    def test_init_binds(self, tmp_cwd):
        d1 = os.path.join(tmp_cwd, "d1")
        d2 = os.path.join(tmp_cwd, "d2")
        os.makedirs(d1)
        os.makedirs(d2)
        r = run_sandbox(["--bind", d1, "--ro-bind", d2, "--init"], cwd=tmp_cwd)
        assert r.returncode == 0
        content = open(os.path.join(tmp_cwd, ".bwrapwrap")).read()
        assert f"bind {d1}\n" in content
        assert f"ro-bind {d2}\n" in content

    def test_init_combined(self, tmp_cwd):
        d = os.path.join(tmp_cwd, "data")
        os.makedirs(d)
        r = run_sandbox(["--net", "--ptrace", "--bind", d, "--init"], cwd=tmp_cwd)
        assert r.returncode == 0
        content = open(os.path.join(tmp_cwd, ".bwrapwrap")).read()
        assert "net\n" in content
        assert "ptrace\n" in content
        assert f"bind {d}\n" in content

    def test_init_empty(self, tmp_cwd):
        """--init with no flags creates an empty file."""
        r = run_sandbox(["--init"], cwd=tmp_cwd)
        assert r.returncode == 0
        content = open(os.path.join(tmp_cwd, ".bwrapwrap")).read()
        assert content == ""

    def test_init_no_command_needed(self, tmp_cwd):
        """--init should not require a command argument."""
        r = run_sandbox(["--net", "--init"], cwd=tmp_cwd)
        assert r.returncode == 0

    def test_init_overwrites_existing(self, tmp_cwd):
        config = os.path.join(tmp_cwd, ".bwrapwrap")
        with open(config, "w") as f:
            f.write("ptrace\n")
        r = run_sandbox(["--net", "--init"], cwd=tmp_cwd)
        assert r.returncode == 0
        content = open(config).read()
        assert "net\n" in content
        assert "ptrace" not in content


class TestConfigFileDenylist:
    def test_config_file_hidden(self, tmp_cwd):
        """The .bwrapwrap file must be mapped to /dev/null inside the sandbox."""
        config = os.path.join(tmp_cwd, ".bwrapwrap")
        with open(config, "w") as f:
            f.write("# empty config\n")
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        assert f"--ro-bind /dev/null {config}" in out

    def test_config_file_hidden_even_without_directives(self, tmp_cwd):
        config = os.path.join(tmp_cwd, ".bwrapwrap")
        with open(config, "w") as f:
            f.write("")
        out = dry_run(["echo", "hi"], cwd=tmp_cwd)
        assert f"--ro-bind /dev/null {config}" in out
