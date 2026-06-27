# VibeThinker — Agent Instructions

## What This Is

Self-hosted 3B reasoning model (Qwen2.5-3B Instruct Q8_0 GGUF) served via FastAPI with an OpenAI-compatible API and a CLI (`vibe`). No package manager, no build system — standalone Python scripts + shell.

## Running the Server

```bash
bash start_vibe.sh          # kills port 8003, starts watchdog, waits up to 120s for healthy
bash watchdog.sh            # background loop: polls /v1/models every 10s, kills+restarts server after 3 failures
python3 serve_vibethinker.py # FastAPI server directly (port 8003)
```

The server must be running before the CLI works. `start_vibe.sh` is the canonical entry — it handles stale processes and watchdog lifecycle.

## CLI Usage

```bash
python3 vibecli.py <command> [args]
# Commands: prompt, chat, code, think, explain, sh, review, eval
```

Set `VIBE_API` to override the default server URL (`http://localhost:8003`).

## Eval Suite

```bash
python3 vibecli.py eval [suite] -n 3 -v --report
# Suites: all, math, logic, code, reasoning, shell, regex, codegen, core, dev
# dev = shell + regex + codegen (fastest)
# --report writes HTML to /root/vibe_eval_report_<suite>.html
```

Eval tasks and graders are defined inline in `vibecli.py` (no external test framework).

## Architecture Gotchas

- **Worker subprocess pattern**: `serve_vibethinker.py` spawns `vibe_worker.py` as a subprocess per request. The worker loads the GGUF model, generates, prints JSON to stdout, and exits. This is intentional — llama-cpp-python segfaults after ~12-15 requests in-process, so the subprocess pattern provides crash isolation.
- **n_ctx setting**: Set to 2048 in `vibe_worker.py` to avoid llama_context warnings about n_ctx_seq < n_ctx_train.
- **Model path is hardcoded**: `/root/models/vibethinker-3b/qwen2.5-3b-instruct-q8_0.gguf` in `vibe_worker.py`. Model files are gitignored (`*.gguf`, `/models/`).
- **No package management**: no `requirements.txt`, `pyproject.toml`, or `setup.py`. Dependencies are installed system-wide by `install.sh` (requires `requests`, `llama-cpp-python`, `fastapi`, `uvicorn`, `pydantic`).
- **Port 8003**: hardcoded across `start_vibe.sh`, `watchdog.sh`, `serve_vibethinker.py`, `vibethinker.service`.
- **Logs**: watchdog writes to `/root/watchdog.log`; server stdout goes to `/root/vibethinker_server.log`.
- **`install.sh`** references files (`server.py`, `worker.py`) that differ from repo filenames (`serve_vibethinker.py`, `vibe_worker.py`). The install script downloads from GitHub `RAW_BASE`, so repo filenames are the source of truth — the script may need updating if used.

## Current Status

**Performance**: ~60s per request (model load + inference via subprocess)
**Accuracy**: 
- Core suite: 100%
- Dev suite (shell+regex+codegen): ~55%
- Math suite: ~50-75% (model gives inconsistent answers on some questions)

**Key Improvements Made**:
- Fixed grader to use word-boundary regex for numeric answers
- Reduced max_tokens in TASKS to prevent timeouts
- Added /stats endpoint for request monitoring
- Simplified chat() function (removed retry loop)
- Fixed API_BASE to default to localhost:8003

| File | Role |
|---|---|
| `serve_vibethinker.py` | FastAPI server, OpenAI-compatible endpoints on :8003 |
| `vibe_worker.py` | Subprocess: loads model, generates, exits |
| `vibecli.py` | CLI with 8 commands + eval framework |
| `watchdog.sh` | Health-poll loop, auto-restarts server on 3 failures |
| `start_vibe.sh` | Orchestrator: kills stale processes, starts watchdog, waits for healthy |
| `install.sh` | System-wide installer (Linux, root, Python 3.10+, systemd) |
| `vibethinker.service` | Systemd unit (Restart=on-failure) |
| `docs/` | Static HTML site deployed to GitHub Pages |

## Dependencies

- Python 3.10+
- `llama-cpp-python` (CPU inference)
- `requests` (CLI HTTP)
- `fastapi` + `uvicorn` + `pydantic` (server)
