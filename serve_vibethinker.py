import asyncio, json, time, uuid
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from llama_cpp import Llama
from pydantic import BaseModel

MODEL_PATH = "/root/models/vibethinker-3b/ggml-model-q8_0.gguf"
MODEL_NAME = "VibeThinker"

app = FastAPI()

print(f"Loading {MODEL_NAME} from {MODEL_PATH}...")
llm = Llama(
    model_path=MODEL_PATH,
    n_ctx=4096,
    n_threads=2,
    n_batch=8,
    use_mmap=True,
    mlock=False,
    verbose=False,
)
print("Model loaded. Server ready.")


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


@app.post("/v1/chat/completions")
def chat_completions(req: ChatRequest):
    messages = [m.model_dump() for m in req.messages]

    if req.stream:
        gen = llm.create_chat_completion(
            messages=messages,
            temperature=req.temperature,
            top_p=req.top_p,
            max_tokens=req.max_tokens,
            stream=True,
        )

        async def stream_gen():
            chunk_id = f"chatcmpl-{uuid.uuid4().hex}"
            ts = int(time.time())

            yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'created': ts, 'model': req.model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"

            for chunk in gen:
                delta = chunk["choices"][0]["delta"]
                if "content" in delta:
                    yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'created': ts, 'model': req.model, 'choices': [{'index': 0, 'delta': {'content': delta['content']}, 'finish_reason': None}]})}\n\n"
                await asyncio.sleep(0)

            yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'created': ts, 'model': req.model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(stream_gen(), media_type="text/event-stream")
    else:
        output = llm.create_chat_completion(
            messages=messages,
            temperature=req.temperature,
            top_p=req.top_p,
            max_tokens=req.max_tokens,
        )
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.model,
            "choices": output["choices"],
            "usage": output.get("usage"),
        }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
