#!/usr/bin/env python3
"""GEPA optimizer for VibeThinker - optimize prompts using reflective evolution."""

import json
import os
import sys
from typing import Any

# Import VibeThinker CLI functions
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Override API_BASE to use localhost
os.environ["VIBE_API"] = "http://localhost:8003"

from vibecli import chat, strip_think, TASKS, GRADERS, grade_exact, grade_code, grade_rubric, grade_reg_hello, grade_exact_raw

import gepa.optimize_anything as oa
from gepa.optimize_anything import optimize_anything, GEPAConfig, EngineConfig


def evaluate_prompt(candidate: str) -> float:
    """Evaluate a prompt candidate against the eval suite."""
    
    # Parse the candidate as a system prompt
    system_prompt = candidate.strip()
    
    # Use a subset of tasks for faster evaluation
    test_tasks = []
    for category in ["math", "logic", "code", "reasoning"]:
        if category in TASKS:
            test_tasks.extend(TASKS[category][:2])  # Take first 2 tasks per category
    
    total_score = 0.0
    total_tasks = len(test_tasks)
    
    for task in test_tasks:
        try:
            # Build messages with the candidate system prompt
            messages = [{"role": "system", "content": system_prompt}]
            messages.append({"role": "user", "content": task["prompt"]})
            
            # Get response from VibeThinker
            max_tokens = task.get("max_tokens", 512)
            response = "".join(chat(messages, temperature=0.5, top_p=0.95, max_tokens=max_tokens, stream=False))
            
            # Grade the response
            grader_type = task.get("grader", "exact")
            if grader_type == "exact":
                passed, _ = grade_exact(response, task["answer"])
            elif grader_type == "exact_raw":
                passed, _ = grade_exact_raw(response, task["answer"])
            elif grader_type == "code":
                passed, _ = grade_code(response)
            elif grader_type == "rubric":
                passed, _ = grade_rubric(response, task)
            elif grader_type == "reg_hello":
                passed, _ = grade_reg_hello(response)
            else:
                passed = False
            
            # Log feedback for GEPA
            oa.log(f"Task: {task['id']}")
            oa.log(f"Prompt: {task['prompt'][:100]}...")
            oa.log(f"Response: {response[:200]}...")
            oa.log(f"Expected: {task.get('answer', 'N/A')}")
            oa.log(f"Passed: {passed}")
            oa.log("---")
            
            if passed:
                total_score += 1.0
                
        except Exception as e:
            oa.log(f"Error evaluating task {task['id']}: {e}")
            continue
    
    # Return average score (0-1)
    avg_score = total_score / total_tasks if total_tasks > 0 else 0.0
    oa.log(f"Average score: {avg_score:.2f} ({total_score}/{total_tasks})")
    return avg_score


def run_gepa_optimization():
    """Run GEPA optimization on VibeThinker prompts."""
    
    # Seed candidate - basic system prompt
    seed_prompt = """You are a helpful AI assistant. Answer questions accurately and concisely. When solving problems, show your reasoning step by step."""
    
    print("Starting GEPA optimization for VibeThinker...")
    print(f"Seed prompt: {seed_prompt}")
    print("This will evaluate prompts against a subset of the eval suite.")
    print("Optimization may take several minutes depending on budget.\n")
    
    # Configure GEPA
    config = GEPAConfig(
        engine=EngineConfig(
            max_metric_calls=20,  # Start with conservative budget
            display_progress_bar=True,
        ),
    )
    
    # Run optimization
    result = optimize_anything(
        seed_candidate=seed_prompt,
        evaluator=evaluate_prompt,
        objective="Optimize the system prompt to maximize accuracy on math, logic, code, and reasoning tasks. The prompt should encourage clear step-by-step reasoning and accurate answers.",
        config=config,
    )
    
    print("\n" + "="*60)
    print("OPTIMIZATION COMPLETE")
    print("="*60)
    print(f"\nBest score: {result.best_score:.3f}")
    print(f"\nOptimized prompt:\n{result.best_candidate}")
    print("\n" + "="*60)
    
    # Save result
    output_file = "/root/code/vibethinker/gepa_optimized_prompt.txt"
    with open(output_file, "w") as f:
        f.write(f"# GEPA Optimized Prompt for VibeThinker\n")
        f.write(f"# Best score: {result.best_score:.3f}\n")
        f.write(f"# Metric calls: {result.metric_calls}\n\n")
        f.write(result.best_candidate)
    
    print(f"\nOptimized prompt saved to: {output_file}")
    return result


if __name__ == "__main__":
    run_gepa_optimization()