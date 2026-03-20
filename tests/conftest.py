import os
import shutil
import subprocess
import sys

import pytest


def _sandbox_bin():
    env = os.environ.get("SANDBOX_BIN")
    if env:
        return env
    # Default: use the installed entry point
    found = shutil.which("bww")
    if found:
        return found
    # Fallback: run as python module
    return None


def _run(args, cwd=None, env=None, timeout=30):
    bin_path = _sandbox_bin()
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    if bin_path:
        cmd = [bin_path] + args
    else:
        cmd = [sys.executable, "-m", "bwrapwrap.cli"] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=merged_env,
        timeout=timeout,
    )


# Public alias used by test files
run_sandbox = _run


@pytest.fixture
def sandbox_bin():
    path = _sandbox_bin()
    if path:
        assert os.path.isfile(path), f"sandbox binary not found: {path}"
    return path


@pytest.fixture
def tmp_cwd(tmp_path):
    """Provide a temporary directory to use as cwd for sandbox commands."""
    return str(tmp_path)


@pytest.fixture
def skip_no_bwrap():
    if not shutil.which("bwrap"):
        pytest.skip("bwrap not installed")


@pytest.fixture
def skip_no_fuse_overlayfs():
    if not shutil.which("fuse-overlayfs"):
        pytest.skip("fuse-overlayfs not installed")
