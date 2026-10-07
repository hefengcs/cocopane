# CocoPane

[中文说明](README.zh-CN.md)

A terminal dashboard for AI coding agents. Run Codex or Claude Code on a Linux server.
Keep the agent, Codex account quota, GPU utilization and a task log in one tmux window.
No Python packages, web server or background service installation required.

![CocoPane dashboard: agent on the left; quota, GPU and task log on the right](docs/images/dashboard.png)

Rendered capture of a real tmux session, using a demo agent and synthetic quota,
GPU and log data. The left pane is an illustrative conversation, not the Codex UI.
The dashboard uses a 60/40 split.

Claude sessions omit the Codex quota pane. CPU-only hosts show a useful GPU
placeholder; use `--no-gpu` to hide it entirely.

## Requirements

- Linux or WSL2, Bash 4+, Python 3.9+, tmux 3.0+, GNU coreutils.
- A working, authenticated [Codex CLI](https://learn.chatgpt.com/docs/developer-commands?surface=cli)
  or [Claude Code](https://code.claude.com/docs/en/setup), installed separately.
- UTF-8 terminal, at least 80×24; 120×40 or larger is more comfortable.
- `nvidia-smi` is optional. No GPU, root access, Docker or pip packages are required by coco.

On Ubuntu/Debian/WSL, install missing system tools with:

```bash
sudo apt update
sudo apt install tmux python3 bash coreutils
```

The first release is validated on Linux. WSL2 uses the same Linux tools but has
not been tested here on a Windows host. Native Windows and macOS are not supported
by this release. Codex 0.160.1 and Claude Code 2.1.207 were used for CLI compatibility checks;
earlier versions may lack required interfaces.

## Install and start

Clone the source and install:

```bash
git clone https://github.com/hefengcs/cocopane.git
cd cocopane
./install.sh
export PATH="$HOME/.local/bin:$PATH"
coco doctor
cd /path/to/your/project
coco open
```

For the release archive, extract with `tar -xzf cocopane-0.1.0.tar.gz`
and enter `cocopane-0.1.0` instead of `cocopane`.

Installation copies only program files to `~/.local/share/cocopane` and creates
`~/.local/bin/coco`. It does not edit your shell startup files, agent configuration,
credentials or project documentation. Add the displayed PATH setting to your shell
configuration if you want it in future terminals.

If a `coco` command already exists at the destination, installation refuses to
overwrite it. Use a separate prefix:

```bash
./install.sh --prefix "$HOME/.local/coco-preview"
"$HOME/.local/coco-preview/bin/coco" doctor
```

No installation is needed to try the checkout:

```bash
./monitor/coco doctor
./monitor/coco open claude
```

## Everyday commands

```bash
coco open                         # Codex in the current directory
coco claude                       # Claude Code
coco open --resume                # Interactive resume picker
coco open --continue              # Continue the latest session
coco open --no-gpu --no-usage      # Agent + log only
coco open --detach                # Print an attach command; useful over SSH
coco status
coco kill                         # List coco sessions; does not stop any
coco kill SESSION_NAME            # Stop an exact coco session, including its panes
```

Default CLI authentication, approvals and sandbox settings are preserved.
The monitor log directory is passed as `--add-dir` so the agent can maintain its log link.
`--unsafe` is an explicit opt-in to the agent's permission-bypass flags.
Claude is launched with its normal configuration loading, not `--bare` mode.

Only `coco-*` sessions on coco's dedicated `coco-public` tmux socket are managed.
`coco kill --all` stops those sessions. Detaching with **Ctrl+b, d** keeps them running.
Use **Ctrl+b, o** to switch panes; **Ctrl+b, [** for keyboard scrollback, **q** to leave it.

### Mouse scrolling and paste

Mouse-wheel scrolling is enabled. After viewing history, press **q** to return to input.
In Xshell use **Shift+right-click** (with right-click configured as paste) or **Shift+Insert**.
Enable Xshell's “Restrict Application Mouse Mode When the SHIFT Key is Pressed” setting
under session properties → Terminal → Advanced. See the [Xshell manual](https://www.netsarang.com/docs/Xshell8_manual.pdf).
Other terminals have their own local-paste shortcut. **Ctrl+b, m** remains a fallback mouse toggle.

### Connect a task log

The agent receives the current slot, log directory and maintenance rules on startup
and resume. Rules ask it to create a task-specific log, bind it, and record real progress
and the final exit result. This is an instruction to the model, not an automatic task runner.

From a shell inside the agent's environment:

```bash
mkdir -p logs
job_log="$PWD/logs/my-run.log"
touch "$job_log"
coco set-log "$job_log"
python -u your_script.py >>"$job_log" 2>&1
```

Outside that session, provide `--slot N` explicitly; otherwise the default is slot 1.
`set-log` never replaces an existing regular log file. GPU and quota panes refresh themselves.
Customize the injected rules in `monitor/AGENT_PANEL_INSTRUCTIONS.md` before installation.
Newly started/resumed sessions pick up the rules; already-running sessions do not reload them.

### Account quota

The quota pane uses Codex's own `account/rateLimits/read` interface and displays actual
server-provided windows, percentages and reset times. It refreshes every 60 seconds,
marks stale data when reads fail, and does not start inference turns. This is account-wide
quota, not per-session token counts. API-key accounts or some providers may not return
ChatGPT plan quota: use `--no-usage` in that case.

Codex instruction injection uses `config/read` to preserve existing developer instructions.
If an older CLI lacks this interface, update it or use `--no-instructions`.

## Configuration

| Variable | Default / purpose |
|---|---|
| `COCO_DATA_DIR` | `$XDG_STATE_HOME/cocopane`, or `~/.local/state/cocopane` |
| `COCO_LOG_DIR` | `$COCO_DATA_DIR/logs` |
| `COCO_TMUX_SOCKET` | `coco-public`; use a different name for an independent dashboard group |
| `COCO_CWD` | Current directory |
| `CODEX_BIN`, `CLAUDE_BIN` | Agent executable found on PATH; override with an absolute path |
| `COCO_SLOT` | Set by the launcher; used by log/task commands |
| `COCO_LOG_PATH` | Set by the launcher; the log link, not the new job's output file |

All state lives outside the installation directory. Concurrent launches reserve slots
under a lock; an explicitly requested occupied slot is rejected. Environment variables are
inherited by the selected CLI, including normal provider/authentication settings. They are
not embedded in pane command strings or stored in coco configuration files.

## Uninstall

Stop your coco sessions first if you want to end their tasks, then:

```bash
python3 "$HOME/.local/share/cocopane/install.py" --uninstall
```

For a custom prefix, pass the same `--prefix` used for installation. Uninstall only removes
files marked as owned by this installer. It preserves logs, agent accounts and sessions.
For an update, uninstall the old copy and install the new source archive.

## Development and distribution

```bash
python3 -m unittest discover -s monitor -p 'test_*.py'
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tools/package.py           # writes dist/cocopane-0.1.0.tar.gz
```

To regenerate the screenshot, run `python3 tools/screenshot.py` with Chrome/Chromium
installed. It uses an isolated tmux server and temporary HOME with demo executables;
it does not access your agent account or send model requests. Chrome is only needed
for this optional documentation tool.

Integration tests use temporary HOME/state/install directories, fake agent executables and
private tmux sockets. They do not send model requests or use your agent account.
A complete task with a real authenticated model has not yet been verified in this
standalone distribution. A GitHub Actions template is provided at
`ci/github-actions.yml` for Ubuntu with Python 3.9 and 3.12. To enable it, copy
it to `.github/workflows/tests.yml` and push using credentials with permission
to write workflows. Automated GitHub CI is not enabled in this initial upload.

This project wraps third-party CLIs; no Codex/Claude binaries, credentials, user conversations
or experiment logs are included. MIT licensed. This is an independent community tool.
