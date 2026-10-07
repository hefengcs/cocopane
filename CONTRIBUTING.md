# Contributing

Keep dependencies limited to Python's standard library and common Linux tools.
Do not add account credentials, model conversation history or experiment logs to the repository.
Preserve the CLI's normal permission settings and pass all shell arguments with proper quoting.

Run before proposing a change:

```bash
bash -n install.sh monitor/coco monitor/set_latest_log.sh monitor/set_task.sh monitor/_resize_layout.sh
python3 -m unittest discover -s monitor -p 'test_*.py'
python3 -m unittest discover -s tests -p 'test_*.py'
```

Integration tests must use temporary HOME/install/state directories and an isolated tmux socket.
Use fake agent CLIs for inference paths. Do not require contributors' API keys or call a real model.
Describe what changed, why it changed, and the relevant verification in pull requests.

Update both README files for user-facing changes. Bump VERSION for a release, then run
`python3 tools/package.py` and test installation from the generated archive.
