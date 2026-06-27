#!/usr/bin/env python3
"""Quick test of GEPA optimizer with minimal budget."""

import os
import sys

# Override API_BASE to use localhost
os.environ["VIBE_API"] = "http://localhost:8003"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vibecli import chat, strip_think, TASKS, grade_exact

import gepa.optimize_anything as oa
from gepa.optimize_anything import optimize_anything, GEPAConfig, EngineConfig, ReflectionConfig


def vibethinker_reflection_lm(prompt: str, **kwargs) -> str:
    """Reflection LLM function that uses VibeThinker."""
    messages = [{"role": "user", "content": prompt}]
    try:
        response = "".join(chat(messages, temperature=0.7, top_p=0.95, max_tokens=1024, stream=False))
        return response
    except Exception as e:
        return f"Error: {e}"


def simple_evaluate(candidate: str) -> float:
    """Simple evaluator using just math tasks."""
    system_prompt = candidate.strip()
    
    # Use only 2 math tasks for quick testing
    test_tasks = TASKS["math"][:2]
    
    total_score = 0.0
    for task in test_tasks:
        try:
            messages = [{"role": "system", "content": system_prompt}]
            messages.append({"role": "user", "content": task["prompt"]})
            
            response = "".join(chat(messages, temperature=0.5, top_p=0.95, max_tokens=512, stream=False))
            
            oa.log(f"Task: {task['id']}")
            oa.log(f"Prompt: {task['prompt']}")
            oa.log(f"Response: {response[:200]}")
            oa.log(f"Expected: {task['answer']}")
            
            # Use the grade_exact function directly
            clean = strip_think(response).strip().lower()
            answer = task["answer"]
            if isinstance(answer, str):
                answer = [answer]
            passed = any(a.strip().lower() in clean for a in answer)
            
            oa.log(f"Passed: {passed}")
            
            if passed:
                total_score += 1.0
        except Exception as e:
            oa.log(f"Error: {e}")
            import traceback
            oa.log(traceback.format_exc())
    
    avg_score = total_score / len(test_tasks)
    oa.log(f"Score: {avg_score:.2f}")
    return avg_score


if __name__ == "__main__":
    print("Testing GEPA with minimal budget (5 metric calls)...")
    
    config = GEPAConfig(
        engine=EngineConfig(
            max_metric_calls=5,  # Very small budget for testing
            display_progress_bar=True,
        ),
        reflection=ReflectionConfig(
            reflection_lm=vibethinker_reflection_lm,  # Use VibeThinker as reflection LM
        ),
    )
    
    seed = "You are a helpful assistant."
    
    result = optimize_anything(
        seed_candidate=seed,
        evaluator=simple_evaluate,
        objective="Improve the system prompt for math accuracy.",
        config=config,
    )
    
    print(f"\nResult: {result}")
    print(f"Result attributes: {dir(result)}")
    if hasattr(result, 'best_candidate'):
        print(f"Best candidate: {result.best_candidate}")
    if hasattr(result, 'final_valset_score'):
        print(f"Final valset score: {result.final_valset_score}")