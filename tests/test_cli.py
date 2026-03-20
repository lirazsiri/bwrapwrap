"""CLI argument parsing and help/usage output."""

from conftest import run_sandbox


class TestUsage:
    def test_no_args_shows_usage(self, sandbox_bin):
        r = run_sandbox([])
        assert r.returncode == 1
        assert "Usage" in r.stdout or "Usage" in r.stderr

    def test_help_flag(self, sandbox_bin):
        r = run_sandbox(["--help"])
        assert r.returncode == 0
        assert "Options" in r.stdout
        assert "Examples" in r.stdout

    def test_help_short_flag(self, sandbox_bin):
        r = run_sandbox(["-h"])
        assert r.returncode == 0
        assert "Options" in r.stdout

    def test_unknown_flag(self, sandbox_bin):
        r = run_sandbox(["--bogus"])
        assert r.returncode == 1
        assert "Unknown option" in r.stdout or "Unknown option" in r.stderr
