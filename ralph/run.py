"""Claude Code invocation and orchestration loop for Ralph Wiggum."""

import json
import os
import subprocess
import sys
from typing import Callable

from ralph.parse import parse_results_summary


def _artifacts_dir(project_name: str) -> str:
    return os.path.join("artifacts", project_name)


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


def _run_results_summary(project_name: str, exit_reason: str, verbose: bool = False) -> None:
    """Spawn a results summary agent to write artifacts/<project-name>/results.md."""
    artifacts = _artifacts_dir(project_name)
    print(f"[ralph] Generating results summary...")
    prompt = parse_results_summary(project_name, artifacts_dir=artifacts, exit_reason=exit_reason)
    proc = run_noninteractive(prompt)
    if verbose and proc.stdout:
        print(proc.stdout)
    if proc.returncode != 0 and proc.stderr:
        print(f"[ralph] Agent stderr: {proc.stderr}", file=sys.stderr)
    print(f"[ralph] Results summary complete.")


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
    total = len(question_prompts)

    for i, q_prompt in enumerate(question_prompts):
        round_num = i + 1
        print(f"\n[ralph] Interview round {round_num}/{total}")

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

        print(f"[ralph] Round {round_num} complete.")

    print("\n[ralph] All interview rounds complete.")


def run_execute_loop(project_name: str, prompts: list[str], max_iterations: int, verbose: bool = False) -> None:
    """Run non-interactive execute agents in a loop."""
    # Pre-check: skip spawning agents if all tasks are already complete.
    if _all_tasks_complete(project_name):
        exit_reason = "All tasks completed successfully."
        print("\n[ralph] All tasks already completed!")
        _run_results_summary(project_name, exit_reason, verbose=verbose)
        return

    exit_reason = f"Reached maximum iteration limit ({max_iterations})."

    for iteration in range(1, max_iterations + 1):
        prompt = prompts[min(iteration - 1, len(prompts) - 1)]

        print(f"\n[ralph] Spawning execute agent (iteration {iteration}/{max_iterations})...")
        proc = run_noninteractive(prompt)
        if verbose and proc.stdout:
            print(proc.stdout)
        if proc.returncode != 0 and proc.stderr:
            print(f"[ralph] Agent stderr: {proc.stderr}", file=sys.stderr)

        if _all_tasks_complete(project_name):
            exit_reason = "All tasks completed successfully."
            print("\n[ralph] All tasks completed!")
            break

        exceeded, task = _any_task_exceeded_max_attempts(project_name)
        if exceeded:
            exit_reason = f"Task {task['id']} ('{task['title']}') reached max_attempts ({task['max_attempts']})."
            print(f"\n[ralph] Halting: {exit_reason}")
            break
    else:
        # for/else fires when all iterations were exhausted without breaking
        print(f"\n[ralph] {exit_reason}")

    _run_results_summary(project_name, exit_reason, verbose=verbose)
