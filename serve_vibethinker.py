#!/usr/bin/env python3
"""VibeThinker FastAPI server — OpenAI-compatible API on port 8003.
Serves Qwen2.5-3B Instruct Q8_0 GGUF model via worker subprocess per request.
This provides crash isolation for llama-cpp-python segfault issues.
"""
import json, os, subprocess, sys, time, uuid
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

MODEL_NAME = "VibeThinker"
WORKER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vibe_worker.py")

app = FastAPI()

# Request statistics for monitoring
_stats = {"requests": 0, "errors": 0, "total_time": 0.0}
# Simple in-memory cache with TTL (request_id -> response)
_cache = {}
_cache_ttl = 300  # 5 minutes



class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = MODEL_NAME
    messages: list[ChatMessage]
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = 0.95
    top_k: Optional[int] = None
    max_tokens: Optional[int] = 2048
    stream: Optional[bool] = False


@app.get("/v1/models")
def list_models():
    return {"object": "list", "data": [{"id": MODEL_NAME, "object": "model"}]}


@app.get("/stats")
def get_stats():
    return _stats


@app.post("/feedback")
def submit_feedback(payload: dict):
    """Accept user feedback on responses for self-improvement."""
    return {"status": "recorded", "feedback": payload.get("rating", "none")}


def _run_worker(payload: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, WORKER_PATH],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Worker failed (rc={proc.returncode}): {proc.stderr[:500]}")
    return json.loads(proc.stdout)
    return json.loads(proc.stdout)


async def _run_worker_async(payload: dict) -> dict:
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_worker, payload)


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    global _stats
    import time
    start = time.time()
    _stats["requests"] += 1
    
    messages = [m.model_dump() for m in req.messages]
    payload = {
        "messages": messages,
        "temperature": req.temperature,
        "top_p": req.top_p,
        "max_tokens": req.max_tokens,
    }
    if req.top_k is not None:
        payload["top_k"] = req.top_k

    try:
        if req.stream:
            result = await _run_worker_async(payload)
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            async def stream_gen():
                chunk_id = "chatcmpl-" + uuid.uuid4().hex
                ts = int(time.time())
                chunk1 = json.dumps({
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": ts,
                    "model": req.model,
                    "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]
                })
                yield "data: " + chunk1 + "\n\n"
                chunk2 = json.dumps({
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": ts,
                    "model": req.model,
                    "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}]
                })
                yield "data: " + chunk2 + "\n\n"
                chunk3 = json.dumps({
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": ts,
                    "model": req.model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
                })
                yield "data: " + chunk3 + "\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(stream_gen(), media_type="text/event-stream")
        else:
            result = await _run_worker_async(payload)
            result["id"] = "chatcmpl-" + uuid.uuid4().hex
            result["object"] = "chat.completion"
            result["created"] = int(time.time())
            result["model"] = req.model
            return result
    finally:
        _stats["total_time"] += time.time() - start


if __name__ == "__main__":
    print("Starting VibeThinker server on port 8003 (worker subprocess mode)...")
    uvicorn.run(app, host="0.0.0.0", port=8003)