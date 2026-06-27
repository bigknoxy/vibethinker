#!/usr/bin/env python3
"""VibeThinker FastAPI server — OpenAI-compatible API on port 8003.
Serves Qwen2.5-3B Instruct Q8_0 GGUF model in-process with thread-safe inference.
"""
import hashlib
import json
import os
import sys
import time
import uuid
import threading
from collections import OrderedDict
from typing import Optional, Generator

import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from llama_cpp import Llama

MODEL_NAME = "VibeThinker"
MODEL_PATH = "/root/models/vibethinker-3b/qwen2.5-3b-instruct-q8_0.gguf"

app = FastAPI()

llm = None
_request_lock = threading.Lock()
_stats_lock = threading.Lock()
_stats = {"requests": 0, "errors": 0, "total_time": 0.0, "cache_hits": 0, "cache_misses": 0}


class LRUCache:
    """Thread-safe LRU cache with per-entry TTL."""

    def __init__(self, capacity: int = 128, default_ttl: int = 300):
        self.capacity = capacity
        self.default_ttl = default_ttl
        self.cache = OrderedDict()
        self.lock = threading.Lock()

    def _is_expired(self, entry: dict) -> bool:
        return time.time() - entry["time"] > entry["ttl"]

    def get(self, key: str) -> dict | None:
        with self.lock:
            entry = self.cache.get(key)
            if entry is None:
                return None
            if self._is_expired(entry):
                del self.cache[key]
                return None
            self.cache.move_to_end(key)
            return entry["response"]

    def put(self, key: str, response: dict, ttl: int | None = None) -> None:
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = {
                "response": response,
                "time": time.time(),
                "ttl": ttl if ttl is not None else self.default_ttl,
            }
            while len(self.cache) > self.capacity:
                self.cache.popitem(last=False)

    def cleanup(self) -> int:
        """Remove all expired entries. Returns the number removed."""
        removed = 0
        with self.lock:
            now = time.time()
            expired = [k for k, v in self.cache.items() if now - v["time"] > v["ttl"]]
            for k in expired:
                del self.cache[k]
                removed += 1
        return removed

    @property
    def size(self) -> int:
        with self.lock:
            return len(self.cache)


_response_cache = LRUCache(capacity=128, default_ttl=300)

def _stats_inc(key: str, delta: float = 1.0) -> None:
    with _stats_lock:
        _stats[key] += delta

def _stats_add_time(seconds: float) -> None:
    with _stats_lock:
        _stats["total_time"] += seconds

_make_cache_key = lambda req: hashlib.sha256(
    json.dumps(
        {
            "messages": [m.model_dump() for m in req.messages],
            "temperature": req.temperature,
            "top_p": req.top_p,
            "top_k": req.top_k,
            "max_tokens": req.max_tokens,
        },
        sort_keys=True,
    ).encode()
).hexdigest()


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


@app.on_event("startup")
async def _load_model():
    global llm
    print("Loading model from " + MODEL_PATH + "...", flush=True)
    llm = Llama(
        model_path=MODEL_PATH,
        n_ctx=2048,
        n_threads=2,
        n_batch=8,
        use_mmap=True,
        mlock=False,
    )
    print("Model loaded successfully.", flush=True)


@app.get("/v1/models")
def list_models():
    return {"object": "list", "data": [{"id": MODEL_NAME, "object": "model"}]}


@app.get("/stats")
def get_stats():
    return {**_stats, "cache_size": _response_cache.size}


@app.post("/feedback")
def submit_feedback(payload: dict):
    return {"status": "recorded", "feedback": payload.get("rating", "none")}


def _stream_with_lock(kwargs: dict, req: ChatRequest) -> Generator[str, None, None]:
    chunk_id = "chatcmpl-" + uuid.uuid4().hex
    ts = int(time.time())
    chunk = {"id": chunk_id, "object": "chat.completion.chunk", "created": ts, "model": req.model, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
    yield "data: " + json.dumps(chunk) + "\n\n"
    with _request_lock:
        stream = llm.create_chat_completion(**kwargs, stream=True)
        for chunk_data in stream:
            choice = chunk_data.get("choices", [{}])[0]
            delta = choice.get("delta", {})
            finish = choice.get("finish_reason")
            if delta.get("content"):
                chunk = {"id": chunk_id, "object": "chat.completion.chunk", "created": ts, "model": req.model, "choices": [{"index": 0, "delta": {"content": delta["content"]}, "finish_reason": None}]}
                yield "data: " + json.dumps(chunk) + "\n\n"
            if finish:
                chunk = {"id": chunk_id, "object": "chat.completion.chunk", "created": ts, "model": req.model, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]}
                yield "data: " + json.dumps(chunk) + "\n\n"
                break
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    global llm, _stats
    if llm is None:
        return {"error": "Model not loading"}, 503

    start = time.time()
    _stats_inc("requests")
    _response_cache.cleanup()

    # Build kwargs (shared by streaming, cache lookup, and model call)
    messages = [m.model_dump() for m in req.messages]
    kwargs = {
        "messages": messages,
        "temperature": req.temperature,
        "top_p": req.top_p,
        "max_tokens": req.max_tokens,
    }
    if req.top_k is not None:
        kwargs["top_k"] = req.top_k

    # Streaming requests bypass the cache
    if req.stream:
        try:
            return StreamingResponse(
                _stream_with_lock(kwargs, req), media_type="text/event-stream"
            )
        finally:
            _stats_add_time(time.time() - start)

    # Non-streaming: check cache first
    cache_key = _make_cache_key(req)
    cached = _response_cache.get(cache_key)
    if cached is not None:
        _stats_inc("cache_hits")
        _stats_add_time(time.time() - start)
        return cached

    _stats_inc("cache_misses")

    try:
        with _request_lock:
            output = llm.create_chat_completion(**kwargs)
        response = {
            "id": "chatcmpl-" + uuid.uuid4().hex,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.model,
            "choices": output.get("choices", []),
            "usage": output.get("usage"),
        }
        _response_cache.put(cache_key, response)
        return response
    finally:
        _stats_add_time(time.time() - start)


if __name__ == "__main__":
    print("Starting VibeThinker server on port 8003 (in-process model)...")
    uvicorn.run(app, host="0.0.0.0", port=8003)