#!/usr/bin/env python3
"""vibe - CLI for VibeThinker 3B reasoning model"""

import argparse, json, os, re, sys, time, uuid
from typing import Optional

import requests

API_BASE = os.environ.get("VIBE_API", "http://192.168.8.136:8002")
MODEL = "VibeThinker"


def strip_think(text: str) -> str:
    text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>", "", text)
    return text.strip()


def chat(messages: list, temperature=1.0, top_p=0.95, max_tokens=2048, stream=False, timeout_s=300):
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "stream": stream,
    }

    last_exc = None
    backoff = [5, 10, 20]

    for attempt in range(4):
        try:
            resp = requests.post(f"{API_BASE}/v1/chat/completions", json=payload, stream=stream, timeout=timeout_s)
            resp.raise_for_status()
        except (ConnectionError, ConnectionRefusedError, requests.exceptions.Timeout) as e:
            last_exc = e
            if attempt == 3:
                raise

            last_dot = time.monotonic()
            for _ in range(12):
                try:
                    hr = requests.get(f"{API_BASE}/v1/models", timeout=5)
                    if hr.ok:
                        break
                except requests.RequestException:
                    pass
                if time.monotonic() - last_dot >= 15:
                    print(".", file=sys.stderr, end="", flush=True)
                    last_dot = time.monotonic()
                time.sleep(10)

            time.sleep(backoff[attempt])
        else:
            if stream:
                for line in resp.iter_lines():
                    if not line or line.startswith(b":") or line == b"data: [DONE]":
                        continue
                    if line.startswith(b"data: "):
                        chunk = json.loads(line[6:])
                        delta = chunk["choices"][0]["delta"]
                        if "content" in delta:
                            yield delta["content"]
            else:
                data = resp.json()
                yield data["choices"][0]["message"]["content"]
            return

    raise last_exc


def write_output(text: str, output: Optional[str]):
    if output:
        with open(output, "w") as f:
            f.write(text)
    else:
        print(text)


def cmd_prompt(args):
    messages = []
    if getattr(args, "no_think", False):
        messages.append({"role": "system", "content": "Answer directly without step-by-step reasoning. Do not use think tags."})
    messages.append({"role": "user", "content": args.text or sys.stdin.read().strip()})
    result = "".join(chat(messages, args.temperature, args.top_p, args.max_tokens, args.stream))
    if getattr(args, "no_think", False):
        result = strip_think(result)
    write_output(result, args.output)


def cmd_chat(args):
    messages = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    if getattr(args, "no_think", False):
        messages.append({"role": "system", "content": "Answer directly without step-by-step reasoning. Do not use think tags."})
    messages.append({"role": "user", "content": args.text or sys.stdin.read().strip()})
    result = "".join(chat(messages, args.temperature, args.top_p, args.max_tokens, args.stream))
    if getattr(args, "no_think", False):
        result = strip_think(result)
    write_output(result, args.output)


def cmd_code(args):
    prompt = f"Write code for the following task. Output only the code in a single block.\n\n{args.text or sys.stdin.read().strip()}"
    messages = [{"role": "user", "content": prompt}]
    result = "".join(chat(messages, args.temperature, args.top_p, args.max_tokens, args.stream))
    write_output(result, args.output)


def cmd_think(args):
    messages = [{"role": "user", "content": args.text or sys.stdin.read().strip()}]
    result = "".join(chat(messages, args.temperature, args.top_p, args.max_tokens, stream=False))

    think = re.search(r"<think>(.*?)</think>", result, re.DOTALL)
    answer = strip_think(result)

    if args.json:
        print(json.dumps({"reasoning": think.group(1).strip() if think else "", "answer": answer}))
    else:
        if think:
            print(f"🤔 {think.group(1).strip()}\n")
        print(f"💡 {answer}")


def cmd_explain(args):
    path = args.file
    if not os.path.exists(path):
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        content = f.read()
    prompt = f"Explain the following code. Describe what it does, its inputs/outputs, and any notable patterns or issues.\n\n```\n{content}\n```"
    messages = [{"role": "user", "content": prompt}]
    result = "".join(chat(messages, args.temperature, args.top_p, args.max_tokens, args.stream))
    write_output(result, args.output)


def cmd_sh(args):
    prompt = f"Generate a shell command for the following task. Output ONLY the command, no explanation.\n\n{args.text or sys.stdin.read().strip()}"
    messages = [{"role": "user", "content": prompt}]
    result = "".join(chat(messages, args.temperature, args.top_p, args.max_tokens, stream=False))
    cmd = strip_think(result).strip().split("\n")[0]
    print(cmd)


def cmd_review(args):
    path = args.file
    if not os.path.exists(path):
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        content = f.read()
    prompt = f"Review the following code. List issues, bugs, security concerns, and suggestions for improvement.\n\n```\n{content}\n```"
    messages = [{"role": "user", "content": prompt}]
    for chunk in chat(messages, args.temperature, args.top_p, args.max_tokens, stream=True):
        print(chunk, end="", flush=True)

def main():
    p = argparse.ArgumentParser(description="vibe - VibeThinker 3B CLI")
    sub = p.add_subparsers(dest="command")

    pp = sub.add_parser("prompt", help="Simple prompt-response")
    pp.add_argument("text", nargs="?", help="Prompt text (omit for stdin)")
    pp.add_argument("-t", "--temperature", type=float, default=1.0)
    pp.add_argument("--top-p", type=float, default=0.95)
    pp.add_argument("-m", "--max-tokens", type=int, default=2048)
    pp.add_argument("-o", "--output", help="Output file")
    pp.add_argument("-s", "--stream", action="store_true")
    pp.add_argument("--no-think", action="store_true", help="Suppress reasoning tags, answer directly")

    cp = sub.add_parser("chat", help="Chat with optional system prompt")
    cp.add_argument("text", nargs="?", help="Prompt text (omit for stdin)")
    cp.add_argument("-S", "--system", help="System prompt")
    cp.add_argument("-t", "--temperature", type=float, default=1.0)
    cp.add_argument("--top-p", type=float, default=0.95)
    cp.add_argument("-m", "--max-tokens", type=int, default=2048)
    cp.add_argument("-o", "--output", help="Output file")
    cp.add_argument("-s", "--stream", action="store_true")
    cp.add_argument("--no-think", action="store_true", help="Suppress reasoning tags, answer directly")

    cp2 = sub.add_parser("code", help="Generate code")
    cp2.add_argument("text", nargs="?", help="Task description")
    cp2.add_argument("-t", "--temperature", type=float, default=0.2)
    cp2.add_argument("--top-p", type=float, default=0.95)
    cp2.add_argument("-m", "--max-tokens", type=int, default=4096)
    cp2.add_argument("-o", "--output", help="Output file")
    cp2.add_argument("-s", "--stream", action="store_true")

    tp = sub.add_parser("think", help="Show reasoning + answer separately")
    tp.add_argument("text", nargs="?", help="Prompt text")
    tp.add_argument("-t", "--temperature", type=float, default=1.0)
    tp.add_argument("--top-p", type=float, default=0.95)
    tp.add_argument("-m", "--max-tokens", type=int, default=2048)
    tp.add_argument("--json", action="store_true", help="Output as JSON")

    exp = sub.add_parser("explain", help="Explain code from a file")
    exp.add_argument("file", help="Path to source file")
    exp.add_argument("-t", "--temperature", type=float, default=0.3)
    exp.add_argument("--top-p", type=float, default=0.95)
    exp.add_argument("-m", "--max-tokens", type=int, default=2048)
    exp.add_argument("-o", "--output", help="Output file")
    exp.add_argument("-s", "--stream", action="store_true")

    shp = sub.add_parser("sh", help="Generate a shell command")
    shp.add_argument("text", nargs="?", help="Task description (omit for stdin)")
    shp.add_argument("-t", "--temperature", type=float, default=0.2)
    shp.add_argument("--top-p", type=float, default=0.95)
    shp.add_argument("-m", "--max-tokens", type=int, default=1024)

    rvp = sub.add_parser("review", help="Review code from a file")
    rvp.add_argument("file", help="Path to source file")
    rvp.add_argument("-t", "--temperature", type=float, default=0.3)
    rvp.add_argument("--top-p", type=float, default=0.95)
    rvp.add_argument("-m", "--max-tokens", type=int, default=2048)

    ep = sub.add_parser("eval", help="Run eval suite (Anthropic evals framework)")
    ep.add_argument("suite", nargs="?", default="all", help="Eval suite name")
    ep.add_argument("-n", "--trials", type=int, default=3, help="Trials per task")
    ep.add_argument("-v", "--verbose", action="store_true")
    ep.add_argument("--report", action="store_true", help="Generate HTML report")

    args = p.parse_args()
    if not args.command:
        p.print_help()
        return

    if args.command == "eval":
        run_eval(args)
    elif args.command == "prompt":
        cmd_prompt(args)
    elif args.command == "chat":
        cmd_chat(args)
    elif args.command == "code":
        cmd_code(args)
    elif args.command == "think":
        cmd_think(args)
    elif args.command == "explain":
        cmd_explain(args)
    elif args.command == "sh":
        cmd_sh(args)
    elif args.command == "review":
        cmd_review(args)


# ─── EVAL SUITE (Anthropic evals framework) ─────────────────────────────────

EVAL_SYSTEM_PROMPT = None

TASKS = {
    "math": [
        {"id": "math_add", "desc": "2+2", "prompt": "What is 2+2?", "answer": "4", "grader": "exact", "max_tokens": 512},
        {"id": "math_mul", "desc": "7*8", "prompt": "What is 7 times 8?", "answer": "56", "grader": "exact", "max_tokens": 512},
        {"id": "math_quad", "desc": "x^2-9=0", "prompt": "Solve x^2 - 9 = 0 for x.", "answer": ["3", "-3", "x=3", "x=-3"], "grader": "exact", "max_tokens": 512},
        {"id": "math_prime", "desc": "Is 17 prime?", "prompt": "Is 17 a prime number?", "answer": ["yes", "prime"], "grader": "exact", "max_tokens": 512},
    ],
    "logic": [
        {"id": "logic_reverse", "desc": "Reverse a word", "prompt": "Write 'stressed' backwards.", "answer": "desserts", "grader": "exact_raw", "max_tokens": 768},
        {"id": "logic_anagram", "desc": "Anagram: listen", "prompt": "What word can you make by rearranging the letters of 'listen'?", "answer": ["silent", "inlets"], "grader": "exact", "max_tokens": 512},
        {"id": "logic_river", "desc": "River crossing puzzle", "prompt": "A farmer needs to cross a river with a wolf, goat, and cabbage. The boat can only carry the farmer and one item. The wolf eats the goat if left alone. The goat eats the cabbage if left alone. Can he get all across? Explain briefly.", "answer": ["yes"], "grader": "exact", "max_tokens": 768},
    ],
    "code": [
        {"id": "code_fizzbuzz", "desc": "FizzBuzz in Python", "prompt": "Write a Python function that prints numbers 1 to 100, replacing multiples of 3 with 'Fizz', multiples of 5 with 'Buzz', and multiples of both with 'FizzBuzz'.", "grader": "code", "max_tokens": 1024},
        {"id": "code_factorial", "desc": "Factorial function", "prompt": "Write a recursive Python function to compute factorial of n.", "grader": "code", "max_tokens": 1024},
        {"id": "code_palindrome", "desc": "Palindrome check", "prompt": "Write a Python function to check if a string is a palindrome.", "grader": "code", "max_tokens": 1024},
    ],
    "reasoning": [
        {"id": "reason_sally", "desc": "Sally's marbles", "prompt": "Sally has 3 red marbles and 5 blue marbles. She gives half of her red marbles to John. How many marbles does Sally have now?", "answer": ["8", "eight"], "grader": "exact", "max_tokens": 512},
        {"id": "reason_train", "desc": "Train speed", "prompt": "A train travels 300 km in 2.5 hours. What is its average speed in km/h?", "answer": ["120", "120 km/h"], "grader": "exact", "max_tokens": 512},
        {"id": "reason_water", "desc": "Water jug", "prompt": "You have a 5-liter jug and a 3-liter jug. How can you measure exactly 4 liters?", "grader": "rubric", "rubric_keywords": ["fill", "pour", "3", "5", "liter"], "max_tokens": 1024},
    ],
    "shell": [
        {"id": "shell_find", "desc": "Find Python files", "prompt": "Write a find command to locate all Python files in /home/user/project", "answer": ["find", ".py", "/home/user/project"], "grader": "exact_raw", "max_tokens": 384},
        {"id": "shell_replace", "desc": "Sed replace", "prompt": "Write a sed command to replace all occurrences of 'foo' with 'bar' in file.txt", "answer": ["sed", "s/foo/bar/g", "file.txt"], "grader": "exact_raw", "max_tokens": 384},
        {"id": "shell_count", "desc": "Count log lines", "prompt": "Write a command to count lines in all .log files in /var/log", "answer": ["wc -l", ".log", "/var/log"], "grader": "exact_raw", "max_tokens": 384},
        {"id": "shell_git", "desc": "Git log oneline", "prompt": "What git command shows a formatted log with one commit per line?", "answer": ["git log --oneline", "log --oneline"], "grader": "exact_raw", "max_tokens": 384},
        {"id": "shell_kill", "desc": "Kill node processes", "prompt": "Write a command to kill all processes named 'node'", "answer": ["pkill node", "killall node", "pgrep", "kill -9", "kill `pgrep"], "grader": "exact_raw", "max_tokens": 384},
    ],
    "regex": [
        {"id": "regex_email", "desc": "Email regex", "prompt": "Write a regex pattern to match email addresses", "answer": ["@", "\\w+"], "grader": "exact_raw", "max_tokens": 384},
        {"id": "regex_url", "desc": "URL regex", "prompt": "Write a regex pattern to match URLs starting with https://", "answer": ["https", "\\."], "grader": "exact_raw", "max_tokens": 384},
        {"id": "regex_ip", "desc": "IPv4 regex", "prompt": "Write a regex to match IPv4 addresses", "answer": ["\\d"], "grader": "exact_raw", "max_tokens": 384},
    ],
    "codegen": [
        {"id": "codegen_csv", "desc": "Parse CSV", "prompt": "Write a Python script to parse a CSV file and print the sum of the second column", "grader": "code", "max_tokens": 512},
        {"id": "codegen_lines", "desc": "Awk one-liner", "prompt": "Write a bash one-liner using awk to print the first field of each line in a file", "answer": ["awk", "print $1"], "grader": "exact_raw", "max_tokens": 384},
        {"id": "codegen_api", "desc": "API GET function", "prompt": "Write a Python function using requests to GET data from an API endpoint and return the JSON", "grader": "code", "max_tokens": 512},
    ],
}

REGRESSION_TASKS = {
    "core": [
        {"id": "reg_hello", "desc": "Greeting", "prompt": "Say hello.", "grader": "reg_hello", "max_tokens": 256},
        {"id": "reg_capital_france", "desc": "Capital of France", "prompt": "What is the capital of France?", "answer": ["Paris"], "grader": "exact", "max_tokens": 256},
        {"id": "reg_1plus1", "desc": "1+1", "prompt": "What is 1+1?", "answer": ["2", "two"], "grader": "exact", "max_tokens": 256},
    ]
}


def grade_exact(response: str, answer) -> bool:
    clean = strip_think(response).strip().lower()
    if isinstance(answer, str):
        answer = [answer]
    return any(a.strip().lower() in clean for a in answer)


def grade_exact_raw(response: str, answer) -> bool:
    clean = response.strip().lower()
    if isinstance(answer, str):
        answer = [answer]
    return any(a.strip().lower() in clean for a in answer)


def _try_compile(code: str) -> tuple:
    code = code.strip()
    if not code or code.count("\n") < 2:
        return False, None
    try:
        compile(code, "<eval>", "exec")
        return True, "compiles"
    except SyntaxError:
        pass
    lines = code.split("\n")
    for j in range(len(lines) - 1, 2, -1):
        partial = "\n".join(lines[:j])
        try:
            compile(partial, "<eval>", "exec")
            return True, f"trimmed {len(lines)-j} lines"
        except SyntaxError:
            continue
    return False, None


def grade_code(response: str) -> tuple:
    candidates = []
    text = re.sub(r"</?think>", "", response).strip()
    for src in [response, text]:
        closed = re.findall(r"```(?:python)?\n(.+?)```", src, re.DOTALL)
        candidates.extend(closed)
        if "```" in src:
            unclosed = re.findall(r"```(?:python)?\n(.+)$", src, re.DOTALL)
            candidates.extend(unclosed)
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if re.match(r"(?:def |class |import |from )", line):
            start = i
            break
    if start is not None:
        candidates.append("\n".join(lines[start:]))
    candidates.append(text)
    seen = set()
    for code in candidates:
        if code in seen:
            continue
        seen.add(code)
        ok, detail = _try_compile(code)
        if ok:
            return True, detail
    try:
        compile(text, "<eval>", "exec")
        return True, "compiles"
    except SyntaxError as e:
        return False, f"syntax error: {e}"


def grade_rubric(response: str, task: dict) -> tuple:
    clean = strip_think(response).strip().lower()
    answer_keywords = task.get("rubric_keywords", ["fill", "pour", "jug", "liter"])
    found = sum(1 for kw in answer_keywords if kw.lower() in clean)
    ok = found >= len(answer_keywords) * 0.5
    return ok, f"rubric_keywords({found}/{len(answer_keywords)})"


def grade_reg_hello(response: str) -> bool:
    clean = strip_think(response).strip().lower()
    return any(g in clean for g in ["hello", "hi", "greetings", "hey"])


GRADERS = {
    "exact": lambda r, t: (grade_exact(r, t["answer"]), "exact"),
    "exact_raw": lambda r, t: (grade_exact_raw(r, t["answer"]), "exact_raw"),
    "code": lambda r, t: grade_code(r),
    "rubric": lambda r, t: grade_rubric(r, t),
    "reg_hello": lambda r, t: (grade_reg_hello(r), "reg_hello"),
}


def run_suite(suite_name: str, trials: int, verbose: bool) -> dict:
    tasks = []
    if suite_name == "all":
        for s in TASKS:
            tasks.extend(TASKS[s])
        for s in REGRESSION_TASKS:
            tasks.extend(REGRESSION_TASKS[s])
    elif suite_name == "dev":
        for s in ["shell", "regex", "codegen"]:
            if s in TASKS:
                tasks.extend(TASKS[s])
    elif suite_name in TASKS:
        tasks = TASKS[suite_name]
    elif suite_name in REGRESSION_TASKS:
        tasks = REGRESSION_TASKS[suite_name]
    else:
        print(f"Unknown suite: {suite_name}")
        print(f"  Capability: {', '.join(TASKS.keys())}")
        print(f"  Regression: {', '.join(REGRESSION_TASKS.keys())}")
        sys.exit(1)

    results = {}
    for task in tasks:
        tid = task["id"]
        passes = []
        transcripts = []
        for t in range(trials):
            try:
                mt = task.get("max_tokens", 384)
                et = task.get("temperature", 0.5)
                msgs = []
                if EVAL_SYSTEM_PROMPT:
                    msgs.append({"role": "system", "content": EVAL_SYSTEM_PROMPT})
                msgs.append({"role": "user", "content": task["prompt"]})
                response = "".join(chat(msgs, temperature=et, top_p=0.95, max_tokens=mt))
            except Exception as e:
                response = f"<error: {e}>"

            grader_fn = GRADERS.get(task["grader"])
            if grader_fn:
                ok, detail = grader_fn(response, task)
            else:
                ok, detail = False, "no_grader"

            passes.append(ok)
            transcripts.append({"trial": t + 1, "response": response[:200], "pass": ok, "detail": detail})

            if verbose:
                status = "PASS" if ok else "FAIL"
                print(f"  [{status}] {tid} trial {t+1}: {detail}")

        n_pass = sum(passes)
        pass_at_1 = n_pass / trials
        pass_at_k = 1.0 if n_pass > 0 else 0.0
        pass_k = 1.0 if n_pass == trials else 0.0

        results[tid] = {
            "task": task,
            "pass@1": pass_at_1,
            "pass@k": pass_at_k,
            "pass^k": pass_k,
            "n_pass": n_pass,
            "n_trials": trials,
            "transcripts": transcripts,
        }

    return results


def print_results(results: dict):
    print(f"\n{'='*60}")
    print(f"EVAL RESULTS")
    print(f"{'='*60}")
    totals = {"pass@1": [], "pass^k": []}
    for tid, r in sorted(results.items()):
        p1 = r["pass@1"]
        pk = r["pass^k"]
        icon = "PASS" if pk == 1.0 else ("PART" if r["pass@k"] > 0 else "FAIL")
        print(f"  [{icon:4s}] {tid:25s} pass@1={p1:.0%}  pass^k={pk:.0%}  ({r['n_pass']}/{r['n_trials']})")
        totals["pass@1"].append(p1)
        totals["pass^k"].append(pk)

    print(f"  {'─'*55}")
    avg_p1 = sum(totals['pass@1']) / len(totals['pass@1'])
    avg_pk = sum(totals['pass^k']) / len(totals['pass^k'])
    print(f"  {'AVERAGE':25s} pass@1={avg_p1:.0%}  pass^k={avg_pk:.0%}")
    print()


def generate_report(results: dict, suite: str):
    html = "<html><head><title>VibeThinker Eval Report</title>"
    html += "<style>body{font-family:monospace;margin:40px;background:#1e1e2e;color:#cdd6f4}"
    html += "h1,h2{color:#cba6f7}.pass{color:#a6e3a1}.fail{color:#f38ba8}.partial{color:#f9e2af}"
    html += "table{border-collapse:collapse;width:100%;margin:20px 0}"
    html += "th,td{padding:8px 12px;text-align:left;border-bottom:1px solid #313244}"
    html += "th{background:#313244;color:#cdd6f4}.detail{font-size:0.9em;color:#a6adc8}"
    html += "</style></head><body>"
    html += f"<h1>VibeThinker Eval Report</h1><p>Suite: {suite} | {len(results)} tasks</p>"
    html += "<table><tr><th>Task</th><th>pass@1</th><th>pass^k</th><th>Trials</th></tr>"

    for tid, r in sorted(results.items()):
        cls = "pass" if r["pass^k"] == 1.0 else ("partial" if r["pass@k"] > 0 else "fail")
        html += f"<tr class='{cls}'><td>{tid}</td>"
        html += f"<td>{r['pass@1']:.0%}</td><td>{r['pass^k']:.0%}</td>"
        html += f"<td>{r['n_pass']}/{r['n_trials']}</td></tr>"
        for t in r["transcripts"]:
            status = "PASS" if t["pass"] else "FAIL"
            html += f"<tr class='detail'><td></td><td colspan='3'>{status} Trial {t['trial']}: {t['detail']} - {t['response'][:100]}...</td></tr>"

    html += "</table></body></html>"
    path = f"/root/vibe_eval_report_{suite}.html"
    with open(path, "w") as f:
        f.write(html)
    print(f"  Report saved: {path}")


def run_eval(args):
    print(f"Running eval suite '{args.suite}' ({args.trials} trials/task)...")
    print()
    results = run_suite(args.suite, args.trials, args.verbose)
    print_results(results)
    if args.report:
        generate_report(results, args.suite)


if __name__ == "__main__":
    main()
