#!/usr/bin/env python3
"""Run a command inside a bubblewrap (bwrap) sandbox."""

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HELP_TEXT = """\
Usage: bww [OPTIONS] <command> [args...]

Run a command inside a bubblewrap (bwrap) sandbox.

The sandbox isolates the process: network is blocked by default,
the filesystem is read-only except for the current directory, and
namespaces are unshared. PATH directories and common toolchains
(cargo/rustup) are auto-detected and bound read-only.

When the command name contains "claude", the project session directory
(~/.claude/projects/<encoded-cwd>/) is bound read-write. Shared config
(.credentials.json, settings.json, CLAUDE.md) is bound read-only.
Other projects' sessions are never exposed. Use --fork to branch
into an isolated copy-on-write overlay instead.

Options:
  --net, --no-net    Allow/block network access (default: blocked)
  --ptrace, --no-ptrace
                     Allow/deny ptrace (default: denied)
  --bind PATH        Bind-mount PATH read-write inside the sandbox
  --ro-bind PATH     Bind-mount PATH read-only inside the sandbox
  --fork [NAME]      Fork ~/.claude via fuse-overlayfs so writes go
                     to ~/.bww/NAME/ without touching the real
                     data. Auto-names if NAME is omitted. Prints a
                     resume command on exit.
  --fork-cleanup     Delete the fork directory on exit (ephemeral).
  --dry-run          Print the bwrap command instead of running it.
  --help, -h         Show this help

Config file:
  If a .bwrapwrap file exists in the current directory, it is read for
  sandbox defaults. Supported directives (one per line):
    net              Allow network access
    ptrace           Allow ptrace
    bind PATH        Bind-mount PATH read-write
    ro-bind PATH     Bind-mount PATH read-only
  Blank lines and lines starting with # are ignored. CLI flags
  (including --no-* variants) always override the config file.
  The .bwrapwrap file itself is never writable inside the sandbox.

Examples:
  bww python3 script.py          # isolated, no network
  bww --net claude               # claude with real ~/.claude
  bww --fork --net claude        # forked ~/.claude (auto-named)
  bww --fork=experiment claude   # forked, named "experiment"
  bww --bind /data python3 app.py  # with /data read-write
"""

BOUND_DIRS = ["/usr", "/lib", "/lib64", "/bin", "/sbin"]

# Files/dirs under ~/.claude to bind read-only for claude commands
CLAUDE_RO_FILES = [".credentials.json", "settings.json", "CLAUDE.md", "statsig"]
# Dirs under ~/.claude to bind read-write for claude commands
CLAUDE_RW_DIRS = ["projects"]


def encode_claude_path(path):
    """Encode a path the way Claude Code does: replace / and . with -"""
    return path.replace("/", "-").replace(".", "-")


def parse_args(argv):
    """Parse sandbox flags, return (opts, command_args)."""
    opts = {
        "net": None,
        "ptrace": None,
        "fork": None,
        "fork_cleanup": False,
        "dry_run": False,
        "binds": [],
        "ro_binds": [],
    }
    rest = list(argv)

    while rest and (rest[0].startswith("--") or rest[0] == "-h"):
        arg = rest.pop(0)
        if arg in ("--help", "-h"):
            print(HELP_TEXT, end="")
            sys.exit(0)
        elif arg == "--net":
            opts["net"] = True
        elif arg == "--no-net":
            opts["net"] = False
        elif arg == "--ptrace":
            opts["ptrace"] = True
        elif arg == "--no-ptrace":
            opts["ptrace"] = False
        elif arg.startswith("--bind="):
            opts["binds"].append(arg.split("=", 1)[1])
        elif arg == "--bind":
            if not rest:
                print("--bind requires a PATH argument", file=sys.stderr)
                sys.exit(1)
            opts["binds"].append(rest.pop(0))
        elif arg.startswith("--ro-bind="):
            opts["ro_binds"].append(arg.split("=", 1)[1])
        elif arg == "--ro-bind":
            if not rest:
                print("--ro-bind requires a PATH argument", file=sys.stderr)
                sys.exit(1)
            opts["ro_binds"].append(rest.pop(0))
        elif arg.startswith("--fork="):
            opts["fork"] = arg.split("=", 1)[1]
        elif arg == "--fork":
            if rest and not rest[0].startswith("--") and not shutil.which(rest[0]):
                opts["fork"] = rest.pop(0)
            else:
                opts["fork"] = "__auto__"
        elif arg == "--fork-cleanup":
            opts["fork_cleanup"] = True
        elif arg == "--dry-run":
            opts["dry_run"] = True
        else:
            print(f"Unknown option: {arg} (try --help)")
            sys.exit(1)

    return opts, rest


def is_claude(cmd):
    """Check if command basename contains 'claude'."""
    return "claude" in Path(cmd).name


def is_within_bound_dirs(path, cwd, home):
    """Check if path is already covered by static binds."""
    for d in BOUND_DIRS:
        if path == d or path.startswith(d + "/"):
            return True
    if path.startswith(cwd + "/") or path == cwd:
        return True
    cargo = os.path.join(home, ".cargo")
    if os.path.isdir(cargo) and (path == cargo or path.startswith(cargo + "/")):
        return True
    rustup = os.path.join(home, ".rustup")
    if os.path.isdir(rustup) and (path == rustup or path.startswith(rustup + "/")):
        return True
    claude = os.path.join(home, ".claude")
    if path == claude or path.startswith(claude + "/"):
        return True
    return False


CONFIG_FILE = ".bwrapwrap"


BOOLEAN_DIRECTIVES = {"net", "ptrace"}
PATH_DIRECTIVES = {"bind", "ro-bind"}


def load_config(cwd):
    """Load directives from .bwrapwrap in the given directory."""
    config = {"binds": [], "ro_binds": []}
    config_path = os.path.join(cwd, CONFIG_FILE)
    if not os.path.isfile(config_path):
        return config
    with open(config_path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            directive = parts[0]
            if directive in BOOLEAN_DIRECTIVES:
                config[directive] = True
                continue
            if directive not in PATH_DIRECTIVES:
                print(f"{config_path}:{lineno}: unknown directive '{directive}'",
                      file=sys.stderr)
                sys.exit(1)
            if len(parts) != 2:
                print(f"{config_path}:{lineno}: '{directive}' requires a PATH argument",
                      file=sys.stderr)
                sys.exit(1)
            path = os.path.expanduser(parts[1])
            if not os.path.isabs(path):
                path = os.path.join(cwd, path)
            path = os.path.realpath(path)
            if directive == "bind":
                config["binds"].append(path)
            elif directive == "ro-bind":
                config["ro_binds"].append(path)
    return config


def resolve_command(cmd):
    """Resolve command to absolute path."""
    found = shutil.which(cmd)
    if found:
        return os.path.realpath(found)
    if os.path.isfile(cmd) and os.access(cmd, os.X_OK):
        return os.path.realpath(cmd)
    return None


def main():
    if not shutil.which("bwrap"):
        print("Error: bubblewrap is not installed. Run: sudo apt install bubblewrap")
        sys.exit(1)

    opts, cmd_args = parse_args(sys.argv[1:])

    if not cmd_args:
        print("Usage: bww [--help] [--net] [--ptrace] [--fork [NAME]] <command> [args]")
        sys.exit(1)

    home = os.environ.get("HOME", str(Path.home()))
    cwd = os.getcwd()
    cmd_name = cmd_args[0]
    cmd_is_claude = is_claude(cmd_name)

    # Fork setup
    fork_dir = None
    fork_name = None
    if opts["fork"] and cmd_is_claude:
        if opts["fork"] == "__auto__":
            fork_name = f"{Path(cmd_name).name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        else:
            fork_name = opts["fork"]
        fork_dir = os.path.join(home, ".bww", fork_name)

    extra_args = []
    overlay_mounts = []

    # Claude setup — bind only what this session needs, not all of ~/.claude
    claude_dir = os.path.join(home, ".claude")
    claude_json = os.path.join(home, ".claude.json")
    if cmd_is_claude and os.path.isdir(claude_dir):
        # Project session dir for the current working directory
        encoded_cwd = encode_claude_path(cwd)
        project_session_dir = os.path.join(claude_dir, "projects", encoded_cwd)

        if fork_dir:
            os.makedirs(fork_dir, exist_ok=True)
            # Overlay the project session dir
            if os.path.isdir(project_session_dir):
                upper = os.path.join(fork_dir, "upper", "session")
                work = os.path.join(fork_dir, "work", "session")
                merged = os.path.join(fork_dir, "merged", "session")
                os.makedirs(upper, exist_ok=True)
                os.makedirs(work, exist_ok=True)
                os.makedirs(merged, exist_ok=True)
                result = subprocess.run(
                    ["fuse-overlayfs", "-o",
                     f"lowerdir={project_session_dir},upperdir={upper},workdir={work}",
                     merged],
                    capture_output=True,
                )
                if result.returncode == 0:
                    overlay_mounts.append(merged)
                    extra_args += ["--bind", merged, project_session_dir]
                else:
                    print(f"Warning: failed to mount overlay for {project_session_dir}", file=sys.stderr)

            # Copy and bind ~/.claude.json
            claude_json_fork = os.path.join(fork_dir, "claude.json")
            if os.path.isfile(claude_json) and not os.path.isfile(claude_json_fork):
                shutil.copy2(claude_json, claude_json_fork)
            if os.path.isfile(claude_json_fork):
                extra_args += ["--bind", claude_json_fork, claude_json]
        else:
            # Direct mode: bind project session dir read-write
            if os.path.isdir(project_session_dir):
                extra_args += ["--bind", project_session_dir, project_session_dir]
            if os.path.isfile(claude_json):
                extra_args += ["--bind", claude_json, claude_json]

        # Read-only binds for shared claude config
        for name in CLAUDE_RO_FILES:
            path = os.path.join(claude_dir, name)
            if os.path.exists(path):
                extra_args += ["--ro-bind", path, path]


    # Cargo / Rustup
    cargo_dir = os.path.join(home, ".cargo")
    rustup_dir = os.path.join(home, ".rustup")
    if os.path.isdir(cargo_dir):
        extra_args += ["--ro-bind", cargo_dir, cargo_dir]
    if os.path.isdir(rustup_dir):
        extra_args += ["--ro-bind", rustup_dir, rustup_dir]

    extra_args += ["--setenv", "HOME", home]
    sandbox_path = f"{cwd}/bin:{home}/.cargo/bin:/usr/local/bin:/usr/bin:/bin"

    # Command resolution
    staging_dir = None
    if not opts["dry_run"]:
        cmd_path = resolve_command(cmd_name)
        if cmd_path is None:
            print(f"Error: '{cmd_name}' is not an executable command or file.")
            sys.exit(1)

        if not is_within_bound_dirs(cmd_path, cwd, home):
            staging_dir = tempfile.mkdtemp(prefix="sandbox-staging.")
            staged = os.path.join(staging_dir, os.path.basename(cmd_path))
            shutil.copy2(cmd_path, staged)
            os.chmod(staged, 0o755)
            cmd_args = [staged] + cmd_args[1:]
    else:
        cmd_path = resolve_command(cmd_name)
        if cmd_path and not is_within_bound_dirs(cmd_path, cwd, home):
            staging_dir = tempfile.mkdtemp(prefix="sandbox-staging.")
            staged = os.path.join(staging_dir, os.path.basename(cmd_path))
            shutil.copy2(cmd_path, staged)
            os.chmod(staged, 0o755)
            cmd_args = [staged] + cmd_args[1:]

    # PATH directories
    seen = set()
    for d in os.environ.get("PATH", "").split(":"):
        try:
            d = os.path.realpath(d)
        except (OSError, ValueError):
            continue
        if not d or not os.path.isdir(d) or d in seen:
            continue
        seen.add(d)
        if is_within_bound_dirs(d, cwd, home):
            continue
        extra_args += ["--ro-bind-try", d, d]
        sandbox_path += f":{d}"

    # Bind staging dir
    if staging_dir:
        extra_args += ["--ro-bind", staging_dir, staging_dir]

    extra_args += ["--setenv", "PATH", sandbox_path]

    # Load config file and merge (CLI takes precedence)
    config = load_config(cwd)
    for key in BOOLEAN_DIRECTIVES:
        if opts[key] is None:
            opts[key] = config.get(key, False)
        # else CLI explicitly set it, keep that value
    all_binds = opts["binds"] + config["binds"]
    all_ro_binds = opts["ro_binds"] + config["ro_binds"]
    for path in all_binds:
        path = os.path.realpath(os.path.expanduser(path))
        if os.path.exists(path):
            extra_args += ["--bind", path, path]
    for path in all_ro_binds:
        path = os.path.realpath(os.path.expanduser(path))
        if os.path.exists(path):
            extra_args += ["--ro-bind", path, path]

    # Hide .bwrapwrap config file inside the sandbox
    config_file = os.path.join(cwd, CONFIG_FILE)
    if os.path.isfile(config_file):
        extra_args += ["--ro-bind", "/dev/null", config_file]

    # Net flag
    net_flag = "--share-net" if opts["net"] else "--unshare-net"

    # Ptrace flag
    ptrace_args = ["--cap-add", "CAP_SYS_PTRACE"] if opts["ptrace"] else []

    # Build bwrap command
    bwrap_cmd = [
        "bwrap",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/lib", "/lib",
        "--ro-bind", "/lib64", "/lib64",
        "--ro-bind", "/bin", "/bin",
        "--ro-bind", "/sbin", "/sbin",
        "--ro-bind", "/etc/alternatives", "/etc/alternatives",
        "--ro-bind", "/etc/fonts", "/etc/fonts",
        "--ro-bind", "/etc/ssl", "/etc/ssl",
        "--ro-bind", "/etc/ca-certificates", "/etc/ca-certificates",
        "--ro-bind-try", "/etc/resolv.conf", "/etc/resolv.conf",
        "--ro-bind-try", "/run/systemd/resolve", "/run/systemd/resolve",
        "--ro-bind-try", "/var/run/NetworkManager", "/var/run/NetworkManager",
        "--ro-bind-try", "/etc/hosts", "/etc/hosts",
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        *ptrace_args,
        "--unshare-all", net_flag,
        "--hostname", "sandbox",
        "--bind", cwd, cwd,
        "--chdir", cwd,
        *extra_args,
        *cmd_args,
    ]

    if opts["dry_run"]:
        print(" ".join(bwrap_cmd))
        # Cleanup staging
        if staging_dir and os.path.isdir(staging_dir):
            shutil.rmtree(staging_dir)
        sys.exit(0)

    try:
        result = subprocess.run(bwrap_cmd)
        bwrap_exit = result.returncode
    finally:
        # Cleanup overlays
        for mnt in overlay_mounts:
            subprocess.run(["fusermount", "-u", mnt], capture_output=True)
            subprocess.run(["fusermount3", "-u", mnt], capture_output=True)
        # Cleanup staging
        if staging_dir and os.path.isdir(staging_dir):
            shutil.rmtree(staging_dir)
        # Cleanup fork dir if requested
        if opts["fork_cleanup"] and fork_dir and os.path.isdir(fork_dir):
            shutil.rmtree(fork_dir, ignore_errors=True)

    if fork_name and not opts["fork_cleanup"]:
        print(f"bww: resume with: bww --fork={fork_name}", file=sys.stderr)

    sys.exit(bwrap_exit)


if __name__ == "__main__":
    main()
