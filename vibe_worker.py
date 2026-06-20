#!/usr/bin/env python3
"""Worker subprocess: loads model, generates one response, prints JSON to stdout."""
import json, os, sys, time
from llama_cpp import Llama

MODEL_PATH = "/root/models/vibethinker-3b/ggml-model-q8_0.gguf"

req = json.loads(sys.stdin.read())

llm = Llama(
    model_path=MODEL_PATH,
    n_ctx=req.get("n_ctx", 4096),
    n_threads=2,
    n_batch=8,
    use_mmap=True,
    mlock=False,
    verbose=False,
)

output = llm.create_chat_completion(
    messages=req["messages"],
    temperature=req.get("temperature", 1.0),
    top_p=req.get("top_p", 0.95),
    max_tokens=req.get("max_tokens", 2048),
)

result = {
    "id": f"chatcmpl-{os.urandom(16).hex()}",
    "object": "chat.completion",
    "created": int(time.time()),
    "model": "VibeThinker",
    "choices": output["choices"],
    "usage": output.get("usage"),
}
print(json.dumps(result))
