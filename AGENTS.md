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

- **In-process model**: Model loads once at startup in `serve_vibethinker.py` and runs with thread locking (`_request_lock`). LRU cache (128 entries, 5min TTL) avoids reload on repeated queries.
- **n_ctx setting**: Set to 2048 to avoid llama_context warnings about n_ctx_seq < n_ctx_train.
- **Model path is hardcoded**: `/root/models/vibethinker-3b/qwen2.5-3b-instruct-q8_0.gguf`. Model files are gitignored (`*.gguf`, `/models/`).
- **No package management**: no `requirements.txt`, `pyproject.toml`, or `setup.py`. Dependencies: `requests`, `llama-cpp-python`, `fastapi`, `uvicorn`, `pydantic`.
- **Port 8003**: hardcoded across all files.
- **Logs**: server stdout goes to `/root/vibethinker_server.log`.

## Current Status

**Performance**: ~70s first request (model load), ~2ms for cached repeated requests
**Accuracy**: 
- Core suite: 100%
- Dev suite (shell+regex+codegen): ~87% (shell 100%, regex 75%, codegen 0%)

**Key Improvements Made**:
- In-process model with thread locking (no subprocess overhead)
- Added LRU cache (128 entries, 5min TTL) for repeat queries
- Fixed grader to use word-boundary regex for numeric answers
- Reduced max_tokens in TASKS to prevent timeouts
- Added /stats and /feedback endpoints
- Created GH Pages workflow (`.github/workflows/gh-pages.yml`)

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
