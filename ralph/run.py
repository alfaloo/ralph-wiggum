"""Claude Code invocation and orchestration loop for Ralph Wiggum."""

import json
import os
import subprocess
import sys
import time
from typing import Callable

POLL_INTERVAL = 5  # seconds between done.md checks


def _artifacts_dir(project_name: str) -> str:
    return os.path.join("artifacts", project_name)


def _done_path(project_name: str) -> str:
    return os.path.join(_artifacts_dir(project_name), "done.md")


def _tasks_path(project_name: str) -> str:
    return os.path.join(_artifacts_dir(project_name), "tasks.json")


def run_noninteractive(prompt: str) -> subprocess.CompletedProcess:
    """Run Claude Code in non-interactive (headless) mode (for execute).

    Invokes `claude` with --print so output is piped back.
    """
    cmd = ["claude", "--dangerously-skip-permissions", "--print", prompt]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result


def _all_tasks_complete(project_name: str) -> bool:
    tasks_path = _tasks_path(project_name)
    if not os.path.exists(tasks_path):
        return False
    with open(tasks_path) as f:
        data = json.load(f)
    tasks = data.get("tasks", [])
    return bool(tasks) and all(t.get("status") == "completed" for t in tasks)


def _any_task_exceeded_max_attempts(project_name: str) -> tuple[bool, dict | None]:
    tasks_path = _tasks_path(project_name)
    if not os.path.exists(tasks_path):
        return False, None
    with open(tasks_path) as f:
        data = json.load(f)
    for task in data.get("tasks", []):
        if task.get("attempts", 0) >= task.get("max_attempts", 3):
            return True, task
    return False, None


def _write_results(project_name: str, reason: str) -> None:
    artifacts = _artifacts_dir(project_name)
    tasks_path = _tasks_path(project_name)
    state_path = os.path.join(artifacts, "state.json")

    tasks = []
    if os.path.exists(tasks_path):
        with open(tasks_path) as f:
            tasks = json.load(f).get("tasks", [])

    state = []
    if os.path.exists(state_path):
        with open(state_path) as f:
            state = json.load(f)

    completed = [t for t in tasks if t.get("status") == "completed"]
    pending = [t for t in tasks if t.get("status") in ("pending", "in_progress")]
    blocked = [t for t in tasks if t.get("status") == "blocked" or t.get("blocked")]

    lines = [
        f"# {project_name} — Execution Results\n",
        f"## Reason for stopping\n\n{reason}\n",
        f"## Tasks Completed ({len(completed)}/{len(tasks)})\n",
    ]
    for t in completed:
        lines.append(f"- **{t['id']}**: {t['title']}\n")
    if pending:
        lines.append(f"\n## Tasks Remaining\n")
        for t in pending:
            lines.append(f"- **{t['id']}**: {t['title']} (attempts: {t.get('attempts', 0)})\n")
    if blocked:
        lines.append(f"\n## Blocked Tasks\n")
        for t in blocked:
            lines.append(f"- **{t['id']}**: {t['title']}\n")
    if state:
        lines.append(f"\n## Agent Run History\n")
        for entry in state:
            status = entry.get("status", "unknown")
            task_id = entry.get("task_id", "?")
            summary = entry.get("summary", "")
            lines.append(f"- Iteration {entry.get('iteration', '?')}: [{task_id}] {status} — {summary}\n")

    results_path = os.path.join(artifacts, "results.md")
    with open(results_path, "w") as f:
        f.writelines(lines)
    print(f"Results written to {results_path}")


def run_comment(project_name: str, prompt: str, verbose: bool = False) -> None:
    """Run the comment agent as a single headless invocation (no polling)."""
    print(f"[ralph] Running comment agent for '{project_name}'...")
    result = run_noninteractive(prompt)
    if verbose and result.stdout:
        print(result.stdout)
    if result.returncode != 0 and result.stderr:
        print(f"[ralph] Agent stderr: {result.stderr}", file=sys.stderr)


def run_init(project_name: str, prompt: str, verbose: bool = False) -> None:
    """Run the init agent as a single blocking subprocess invocation."""
    print(f"[ralph] Running init agent for '{project_name}'...")
    result = run_noninteractive(prompt)
    if verbose and result.stdout:
        print(result.stdout)
    if result.returncode != 0 and result.stderr:
        print(f"[ralph] Agent stderr: {result.stderr}", file=sys.stderr)
    print(f"[ralph] Init complete.")


def _collect_user_answers() -> str:
    """Read multi-line user input until EOF (Ctrl+D / Ctrl+Z+Enter)."""
    print("Enter your answers below. Press Ctrl+D (macOS/Linux) or Ctrl+Z then Enter (Windows) when done:\n")
    try:
        return sys.stdin.read().strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def run_interview_loop(
    project_name: str,
    question_prompts: list[str],
    make_amend_prompts: list[Callable[[str, str], str]],
    verbose: bool = False,
) -> None:
    """Run sequential two-phase interview agents, one per round.

    Each round:
      Phase 1 — non-interactive agent outputs clarifying questions.
      (user types answers via stdin)
      Phase 2 — non-interactive agent receives questions + answers and
                 amends spec.md (and on the final round generates tasks.json).
    """
    done_path = _done_path(project_name)
    total = len(question_prompts)

    for i, q_prompt in enumerate(question_prompts):
        round_num = i + 1
        print(f"\n[ralph] Interview round {round_num}/{total}")
        if verbose:
            print("-" * 60)

        # Remove stale done.md
        if os.path.exists(done_path):
            os.remove(done_path)

        # Phase 1: generate questions
        print("[ralph] Generating clarifying questions...\n")
        result = run_noninteractive(q_prompt)
        questions = result.stdout.strip()
        if result.returncode != 0 and result.stderr:
            print(f"[ralph] Agent stderr: {result.stderr}", file=sys.stderr)

        # Always display questions — user must read and answer them
        print(questions)
        print()

        # Collect user answers
        answers = _collect_user_answers()

        # Phase 2: amend spec with Q&A
        print("\n[ralph] Updating spec with your answers...")
        amend_prompt = make_amend_prompts[i](questions, answers)
        proc = run_noninteractive(amend_prompt)
        if verbose and proc.stdout:
            print(proc.stdout)
        if proc.returncode != 0 and proc.stderr:
            print(f"[ralph] Agent stderr: {proc.stderr}", file=sys.stderr)

        # Poll for done.md
        if verbose:
            print(f"[ralph] Waiting for agent to finish round {round_num}...")
        while not os.path.exists(done_path):
            time.sleep(POLL_INTERVAL)

        os.remove(done_path)
        print(f"[ralph] Round {round_num} complete.")

    print("\n[ralph] All interview rounds complete.")


def run_execute_loop(project_name: str, prompts: list[str], max_iterations: int, verbose: bool = False) -> None:
    """Run non-interactive execute agents in a loop."""
    done_path = _done_path(project_name)
    iteration = 0

    while iteration < max_iterations:
        # Check done.md from previous agent
        if os.path.exists(done_path):
            os.remove(done_path)

            if _all_tasks_complete(project_name):
                print("\n[ralph] All tasks completed!")
                _write_results(project_name, "All tasks completed successfully.")
                return

            exceeded, task = _any_task_exceeded_max_attempts(project_name)
            if exceeded:
                reason = f"Task {task['id']} ('{task['title']}') reached max_attempts ({task['max_attempts']})."
                print(f"\n[ralph] Halting: {reason}")
                _write_results(project_name, reason)
                return

        # Get the prompt for this iteration (use the last prompt if we've exhausted the list)
        prompt_index = min(iteration, len(prompts) - 1)
        prompt = prompts[prompt_index]

        iteration += 1
        print(f"\n[ralph] Spawning execute agent (iteration {iteration}/{max_iterations})...")

        proc = run_noninteractive(prompt)
        if verbose and proc.stdout:
            print(proc.stdout)
        if proc.returncode != 0 and proc.stderr:
            print(f"[ralph] Agent stderr: {proc.stderr}", file=sys.stderr)

        # Poll for done.md
        if verbose:
            print(f"[ralph] Waiting for execute agent to signal completion...")
        timeout = 600  # 10 minutes max per iteration
        elapsed = 0
        while not os.path.exists(done_path) and elapsed < timeout:
            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

        if not os.path.exists(done_path):
            print(f"[ralph] Warning: agent did not create done.md within timeout.", file=sys.stderr)
            continue

    # Max iterations reached
    reason = f"Reached maximum iteration limit ({max_iterations})."
    print(f"\n[ralph] {reason}")
    _write_results(project_name, reason)
