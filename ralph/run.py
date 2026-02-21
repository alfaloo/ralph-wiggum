"""Claude Code invocation and orchestration loop for Ralph Wiggum."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Callable

from ralph.parse import parse_results_summary


def run_noninteractive(prompt: str) -> subprocess.CompletedProcess:
    """Run Claude Code in non-interactive (headless) mode.

    Invokes `claude` with --print so output is piped back.
    """
    cmd = ["claude", "--dangerously-skip-permissions", "--print", prompt]
    return subprocess.run(cmd, capture_output=True, text=True)


def _collect_user_answers() -> str:
    """Read multi-line user input until Ctrl+D (submit) or Ctrl+C (abort).

    Attempts to use prompt_toolkit for a richer editing experience (arrow keys,
    mouse-click cursor positioning, revisit previous lines). Falls back to
    sys.stdin.read() if prompt_toolkit is not installed.
    """
    try:
        from prompt_toolkit import prompt as pt_prompt
        from prompt_toolkit.key_binding import KeyBindings

        print("Enter your answers below. Press Ctrl+D when done, or Ctrl+C to abort:\n")

        kb = KeyBindings()

        @kb.add("c-d")
        def _submit(event):
            event.app.exit(result=event.app.current_buffer.text)

        @kb.add("c-c")
        def _abort(event):
            event.app.exit(exception=KeyboardInterrupt())

        try:
            return pt_prompt("", multiline=True, key_bindings=kb, mouse_support=True).strip()
        except KeyboardInterrupt:
            print("\nInterview aborted.")
            sys.exit(0)
        except EOFError:
            return ""

    except ImportError:
        print("Enter your answers below. Press Ctrl+D (macOS/Linux) or Ctrl+Z then Enter (Windows) when done:\n")
        try:
            return sys.stdin.read().strip()
        except EOFError:
            return ""
        except KeyboardInterrupt:
            print("\nInterview aborted.")
            sys.exit(0)


class Runner:
    """Orchestrator that manages agent invocations for a single project."""

    def __init__(self, project_name: str, verbose: bool = False) -> None:
        self.project_name = project_name
        self.verbose = verbose
        self.ralph_dir = os.path.join(".ralph", project_name)
        self._tasks_path = os.path.join(self.ralph_dir, "tasks.json")

    def _handle_result(self, result: subprocess.CompletedProcess) -> None:
        """Print stdout if verbose; always print stderr on non-zero exit."""
        if self.verbose and result.stdout:
            print(result.stdout)
        if result.returncode != 0 and result.stderr:
            print(f"[ralph] Agent stderr: {result.stderr}", file=sys.stderr)

    def _all_tasks_complete(self) -> bool:
        if not os.path.exists(self._tasks_path):
            return False
        with open(self._tasks_path) as f:
            data = json.load(f)
        tasks = data.get("tasks", [])
        return bool(tasks) and all(t.get("status") == "completed" for t in tasks)

    def _any_task_exceeded_max_attempts(self) -> tuple[bool, dict | None]:
        if not os.path.exists(self._tasks_path):
            return False, None
        with open(self._tasks_path) as f:
            data = json.load(f)
        for task in data.get("tasks", []):
            if task.get("attempts", 0) >= task.get("max_attempts", 3):
                return True, task
        return False, None

    def _run_results_summary(self, exit_reason: str) -> None:
        """Spawn a results summary agent to write .ralph/<project-name>/results.md."""
        print("[ralph] Generating results summary...")
        prompt = parse_results_summary(
            self.project_name, ralph_dir=self.ralph_dir, exit_reason=exit_reason
        )
        self._handle_result(run_noninteractive(prompt))
        print("[ralph] Results summary complete.")

    def run_comment(self, prompt: str) -> None:
        """Run the comment agent as a single headless invocation."""
        print(f"[ralph] Running comment agent for '{self.project_name}'...")
        self._handle_result(run_noninteractive(prompt))

    def run_interview_loop(
        self,
        question_prompts: list[str],
        make_amend_prompts: list[Callable[[str, str], str]],
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
            self._handle_result(run_noninteractive(make_amend_prompts[i](questions, answers)))
            print(f"[ralph] Round {round_num} complete.")

        print("\n[ralph] All interview rounds complete.")

    def run_execute_loop(self, prompts: list[str], max_iterations: int) -> None:
        """Run non-interactive execute agents in a loop."""
        # Pre-check: skip spawning agents if all tasks are already complete.
        if self._all_tasks_complete():
            exit_reason = "All tasks completed successfully."
            print("\n[ralph] All tasks already completed!")
            self._run_results_summary(exit_reason)
            return

        exit_reason = f"Reached maximum iteration limit ({max_iterations})."

        for iteration in range(1, max_iterations + 1):
            prompt = prompts[min(iteration - 1, len(prompts) - 1)]

            print(f"\n[ralph] Spawning execute agent (iteration {iteration}/{max_iterations})...")
            self._handle_result(run_noninteractive(prompt))

            if self._all_tasks_complete():
                exit_reason = "All tasks completed successfully."
                print("\n[ralph] All tasks completed!")
                break

            exceeded, task = self._any_task_exceeded_max_attempts()
            if exceeded:
                exit_reason = f"Task {task['id']} ('{task['title']}') reached max_attempts ({task['max_attempts']})."
                print(f"\n[ralph] Halting: {exit_reason}")
                break
        else:
            # for/else fires when all iterations were exhausted without breaking
            print(f"\n[ralph] {exit_reason}")

        self._run_results_summary(exit_reason)
