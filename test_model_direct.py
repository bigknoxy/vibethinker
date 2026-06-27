#!/usr/bin/env python3
"""Test VibeThinker directly on math tasks."""

import os
import sys

os.environ["VIBE_API"] = "http://localhost:8003"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vibecli import chat, strip_think, TASKS, grade_exact

# Test the first math task
task = TASKS["math"][0]
print(f"Task: {task['id']}")
print(f"Prompt: {task['prompt']}")
print(f"Expected: {task['answer']}")

messages = [{"role": "system", "content": "You are a helpful assistant."}]
messages.append({"role": "user", "content": task["prompt"]})

response = "".join(chat(messages, temperature=0.5, top_p=0.95, max_tokens=512, stream=False))
print(f"\nRaw response: {response}")
print(f"\nStripped response: {strip_think(response)}")

passed = grade_exact(response, task["answer"])
print(f"\nPassed: {passed}")