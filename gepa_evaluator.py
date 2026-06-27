#!/usr/bin/env python3
"""Comprehensive GEPA evaluator for VibeThinker using multiple task types."""

import os
import sys

# Override API_BASE to use localhost
os.environ["VIBE_API"] = "http://localhost:8003"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vibecli import chat, strip_think, TASKS, GRADERS

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


def comprehensive_evaluate(candidate: str) -> float:
    """Comprehensive evaluator using multiple task categories."""
    system_prompt = candidate.strip()
    
    # Use tasks from multiple categories for comprehensive evaluation
    test_tasks = []
    for category in ["math", "logic", "code", "reasoning", "shell", "regex"]:
        if category in TASKS:
            test_tasks.extend(TASKS[category][:2])  # Take first 2 tasks per category
    
    total_score = 0.0
    category_scores = {}
    
    for task in test_tasks:
        try:
            category = task["id"].split("_")[0]
            
            messages = [{"role": "system", "content": system_prompt}]
            messages.append({"role": "user", "content": task["prompt"]})
            
            max_tokens = task.get("max_tokens", 512)
            response = "".join(chat(messages, temperature=0.5, top_p=0.95, max_tokens=max_tokens, stream=False))
            
            oa.log(f"Task: {task['id']} ({category})")
            oa.log(f"Response: {response[:200]}...")
            
            # Grade the response using the appropriate grader
            grader_type = task.get("grader", "exact")
            grader_func = GRADERS.get(grader_type)
            
            if grader_func:
                if grader_type == "code":
                    passed, detail = grader_func(response)
                elif grader_type == "rubric":
                    passed, detail = grader_func(response, task)
                else:
                    passed, detail = grader_func(response, task)
            else:
                passed = False
                detail = "unknown grader"
            
            oa.log(f"Passed: {passed} ({detail})")
            
            # Track category scores
            if category not in category_scores:
                category_scores[category] = {"total": 0, "passed": 0}
            category_scores[category]["total"] += 1
            if passed:
                category_scores[category]["passed"] += 1
                total_score += 1.0
                
        except Exception as e:
            oa.log(f"Error evaluating task {task['id']}: {e}")
            import traceback
            oa.log(traceback.format_exc())
            continue
    
    avg_score = total_score / len(test_tasks) if test_tasks else 0.0
    
    # Log category breakdown
    oa.log("=== Category Breakdown ===")
    for cat, scores in category_scores.items():
        cat_score = scores["passed"] / scores["total"] if scores["total"] > 0 else 0.0
        oa.log(f"{cat}: {cat_score:.2f} ({scores['passed']}/{scores['total']})")
    
    oa.log(f"Overall score: {avg_score:.2f} ({total_score}/{len(test_tasks)})")
    return avg_score


def run_gepa_optimization(max_metric_calls: int = 20):
    """Run GEPA optimization on VibeThinker prompts."""
    
    # Seed candidate - basic system prompt
    seed_prompt = """You are a helpful AI assistant. Answer questions accurately and concisely. When solving problems, show your reasoning step by step."""
    
    print("Starting GEPA optimization for VibeThinker...")
    print(f"Seed prompt: {seed_prompt}")
    print(f"Evaluating against {sum(len(TASKS[c][:2]) for c in ['math', 'logic', 'code', 'reasoning', 'shell', 'regex'] if c in TASKS)} tasks across multiple categories.")
    print(f"Budget: {max_metric_calls} metric calls")
    print("Optimization may take several minutes.\n")
    
    # Configure GEPA
    config = GEPAConfig(
        engine=EngineConfig(
            max_metric_calls=max_metric_calls,
            display_progress_bar=True,
        ),
        reflection=ReflectionConfig(
            reflection_lm=vibethinker_reflection_lm,  # Use VibeThinker as reflection LM
        ),
    )
    
    # Run optimization
    result = optimize_anything(
        seed_candidate=seed_prompt,
        evaluator=comprehensive_evaluate,
        objective="Optimize the system prompt to maximize accuracy across math, logic, code, reasoning, shell, and regex tasks. The prompt should encourage clear step-by-step reasoning, accurate answers, and proper code generation.",
        config=config,
    )
    
    print("\n" + "="*60)
    print("OPTIMIZATION COMPLETE")
    print("="*60)
    print(f"Total metric calls: {result.total_metric_calls}")
    print(f"Number of candidates: {result.num_candidates}")
    print(f"Best candidate: {result.best_candidate}")
    print(f"Best score: {result.val_aggregate_scores[result.best_idx]:.3f}")
    print("\n" + "="*60)
    
    # Save result
    output_file = "/root/code/vibethinker/gepa_optimized_prompt.txt"
    with open(output_file, "w") as f:
        f.write(f"# GEPA Optimized Prompt for VibeThinker\n")
        f.write(f"# Best score: {result.val_aggregate_scores[result.best_idx]:.3f}\n")
        f.write(f"# Metric calls: {result.total_metric_calls}\n")
        f.write(f"# Candidates evaluated: {result.num_candidates}\n\n")
        f.write(result.best_candidate)
    
    print(f"\nOptimized prompt saved to: {output_file}")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GEPA optimization for VibeThinker")
    parser.add_argument("--budget", type=int, default=20, help="Max metric calls budget")
    args = parser.parse_args()
    
    run_gepa_optimization(max_metric_calls=args.budget)