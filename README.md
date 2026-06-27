# VibeThinker — Local AI for Dev Tasks

Self-hosted 3B reasoning model (Qwen2.5-3B Instruct Q8_0 GGUF) served via FastAPI with an OpenAI-compatible API and CLI.

## Quick Start

```bash
# Prerequisites: Python 3.10+, llama-cpp-python
pip install llama-cpp-python fastapi uvicorn requests

# Download model (3.1GB)
mkdir -p /root/models/vibethinker-3b
# Get Qwen2.5-3B-Instruct-Q8_0.gguf and place it there

# Start server
python3 serve_vibethinker.py
```

## CLI Usage

```bash
# Set API endpoint (optional, defaults to localhost:8003)
export VIBE_API=http://localhost:8003

# Commands
python3 vibecli.py prompt "what is 2+2?"
python3 vibecli.py chat "write a rust fibonacci function" -s
python3 vibecli.py code "parse CSV and sum second column" -o sum.py
python3 vibecli.py think "why is the sky blue"
python3 vibecli.py explain app.py
python3 vibecli.py sh "find all pdf files in /home/user"
python3 vibecli.py review buggy.py
python3 vibecli.py eval core -n 3 -v --report
```

## Architecture

- `serve_vibethinker.py` — FastAPI server on port 8003, in-process model with thread-safe inference
- `vibecli.py` — CLI with 8 commands (prompt, chat, code, think, explain, sh, review, eval)
- `watchdog.sh` — Health-poll loop, auto-restarts server on 3 consecutive failures
- `start_vibe.sh` — Orchestrator: kills stale processes, starts watchdog, waits for healthy
- LRUCache cache (128 entries, 5min TTL) avoids model reload on repeated queries

## API Endpoints

```
POST /v1/chat/completions  # OpenAI-compatible chat completions
GET  /v1/models            # List models
GET  /stats                # Request metrics (requests, errors, cache_hits, cache_size)
POST /feedback             # Feedback endpoint for self-improvement
```

## Eval Suites

- `core` — Regression (hello, capital, 1+1)
- `math` — Arithmetic, algebra, primes
- `logic` — Word puzzles, river crossing
- `code` — FizzBuzz, factorial, palindrome
- `reasoning` — Sally's marbles, train speed, water jug
- `shell` — Find, sed, wc, git, pkill
- `regex` — Email, URL, IPv4 patterns
- `codegen` — CSV parsing, awk, API GET
- `dev` — shell + regex + codegen (fastest)

## Performance

- ~70s per request (model load + inference on first call)
- Cache hits return instantly (~2ms)
- Model loads once at startup (in-process mode)
- ~3.4GB RAM usage

## Documentation

🌐 https://vibethinker.pages.dev