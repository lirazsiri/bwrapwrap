# bwrapwrap

A [bubblewrap](https://github.com/containers/bubblewrap) wrapper that sandboxes commands with sensible defaults. Network is blocked, the filesystem is read-only (except the current directory), and namespaces are unshared — all with a single command.

## Prerequisites

```
sudo apt install bubblewrap
```

Optional, for `--fork` overlay mode:

```
sudo apt install fuse-overlayfs
```

## Installation

```
pipx install .
```

Or for development:

```
pipx install -e .
```

## Usage

```
bww [OPTIONS] <command> [args...]
```

### Options

| Flag | Description |
|------|-------------|
| `--net` | Allow network access (blocked by default) |
| `--ptrace` | Allow ptrace (for strace/gdb) |
| `--fork [NAME]` | Fork `~/.claude` via fuse-overlayfs into `~/.bww/NAME/` |
| `--fork-cleanup` | Delete the fork directory on exit |
| `--dry-run` | Print the bwrap command without running it |
| `--help`, `-h` | Show help |

### Examples

```bash
# Run a script with no network
bww python3 script.py

# Allow network access
bww --net curl https://example.com

# Run claude with real ~/.claude bound read-write
bww --net claude

# Fork ~/.claude into a copy-on-write overlay
bww --fork --net claude

# Named fork (resumable)
bww --fork=experiment --net claude

# Inspect the generated bwrap command
bww --dry-run echo hello
```

### What gets mounted

| Mount | Mode |
|-------|------|
| `/usr`, `/lib`, `/lib64`, `/bin`, `/sbin` | read-only |
| `/etc/alternatives`, `/etc/fonts`, `/etc/ssl`, `/etc/ca-certificates` | read-only |
| `/proc`, `/dev` | standard |
| `/tmp` | tmpfs |
| Current working directory | **read-write** |
| `~/.cargo`, `~/.rustup` (if they exist) | read-only |
| PATH directories | read-only |
| `~/.claude/projects/<cwd-session>/` (claude only) | read-write |
| `~/.claude/{.credentials.json,settings.json,CLAUDE.md}` (claude only) | read-only |

### Claude detection

When the command name contains "claude", `bww` binds only the project session directory for the current working directory (`~/.claude/projects/<encoded-cwd>/`) read-write. Shared config files (`.credentials.json`, `settings.json`, `CLAUDE.md`) are bound read-only. Other projects' session data is never exposed. Use `--fork` to isolate writes into a copy-on-write overlay instead.

## Testing

```
pip install -e ".[test]"
pytest tests/ -v
```

To test against the original bash script:

```
SANDBOX_BIN=./sandbox.bash pytest tests/ -v
```
