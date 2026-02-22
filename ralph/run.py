"""Claude Code invocation and orchestration loop for Ralph Wiggum."""

from __future__ import annotations

import concurrent.futures
import json
import os
import subprocess
import sys
import time
from typing import Callable

from ralph import dag
from ralph import locks
from ralph.parse import parse_summarise_md, parse_execute_async_md


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

        print("Type your answers below. Press Ctrl+D when you're done, or Ctrl+C to stop:\n")

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
            print("\n[ralph] Ok, stopping the interview.")
            sys.exit(0)
        except EOFError:
            return ""

    except ImportError:
        print("Type your answers below. Press Ctrl+D (macOS/Linux) or Ctrl+Z then Enter (Windows) when done:\n")
        try:
            return sys.stdin.read().strip()
        except EOFError:
            return ""
        except KeyboardInterrupt:
            print("\n[ralph] Ok, stopping the interview.")
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
            print(f"[ralph] Agent error: {result.stderr}", file=sys.stderr)
        return result.stdout

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

    def _run_summarise(self, exit_reason: str) -> None:
        """Spawn a summarise agent to write .ralph/<project-name>/summary.md."""
        print("[ralph] Summarise agent has started working...")
        prompt = parse_summarise_md(
            self.project_name, ralph_dir=self.ralph_dir, exit_reason=exit_reason
        )
        result = run_noninteractive(prompt)
        self._handle_result(result)
        if result.returncode == 0:
            print("[ralph] Execution summary is ready.")
        else:
            print("[ralph] I had some trouble writing the summary.", file=sys.stderr)

    def run_comment(self, prompt: str) -> None:
        """Run the comment agent as a single headless invocation."""
        print(f"[ralph] Comment agent has started working on '{self.project_name}'...")
        result = run_noninteractive(prompt)
        self._handle_result(result)
        if result.returncode != 0:
            print("[ralph] The comment agent ran into some trouble.", file=sys.stderr)

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
                     amends spec.md and creates/refreshes tasks.json.
        """
        total = len(question_prompts)

        for i, q_prompt in enumerate(question_prompts):
            round_num = i + 1
            print(f"\n[ralph] Interview round {round_num}/{total}")

            # Phase 1: generate questions
            print("[ralph] Interview agent has started working — generating questions...\n")
            result = run_noninteractive(q_prompt)
            questions = result.stdout.strip()
            if result.returncode != 0 and result.stderr:
                print(f"[ralph] Agent error: {result.stderr}", file=sys.stderr)

            # Always display questions — user must read and answer them
            print(questions)
            print()

            # Collect user answers
            answers = _collect_user_answers()

            # Phase 2: amend spec with Q&A
            print("\n[ralph] Interview agent has started working — updating spec with your answers...")
            result2 = run_noninteractive(make_amend_prompts[i](questions, answers))
            self._handle_result(result2)
            if result2.returncode == 0:
                print(f"[ralph] Round {round_num} complete.")
            else:
                print(f"[ralph] Round {round_num} ran into some trouble.", file=sys.stderr)

        print("\n[ralph] All interview rounds complete.")

    def run_execute_loop_async(self, prompts: list[str], max_iterations: int) -> None:
        """Run async execute agents in a concurrent polling loop.

        The ``prompts`` parameter is accepted for API compatibility; this method
        generates per-task prompts internally using ``parse_execute_async_md``.
        """
        state_path = os.path.join(self.ralph_dir, "state.json")
        obstacles_path = os.path.join(self.ralph_dir, "obstacles.json")

        # Ensure state and obstacles files exist before agents start writing.
        if not os.path.exists(state_path):
            locks.write_json(state_path, [])
        if not os.path.exists(obstacles_path):
            locks.write_json(obstacles_path, {"obstacles": []})

        futures: dict[str, concurrent.futures.Future] = {}
        executor = concurrent.futures.ThreadPoolExecutor()

        try:
            while True:
                # Step A: Handle completed futures.
                for task_id, future in list(futures.items()):
                    if not future.done():
                        continue
                    del futures[task_id]

                    try:
                        returncode = future.result()
                    except Exception as exc:
                        returncode = 1
                        print(
                            f"[ralph] Agent for task {task_id} raised an exception: {exc}",
                            file=sys.stderr,
                        )

                    if returncode == 0:
                        with locks.locked_json_rw(self._tasks_path) as data:
                            for t in data["tasks"]:
                                if t["id"] == task_id:
                                    t["status"] = "completed"
                                    break
                        with locks.locked_json_rw(state_path) as state:
                            state.append(
                                {
                                    "task_id": task_id,
                                    "status": "completed",
                                    "summary": "",
                                    "files_modified": [],
                                    "obstacles": [],
                                }
                            )
                    else:
                        with locks.locked_json_rw(obstacles_path) as obs_data:
                            obs_list = obs_data.setdefault("obstacles", [])
                            next_id = f"O{len(obs_list) + 1}"
                            obs_list.append(
                                {
                                    "id": next_id,
                                    "task_id": task_id,
                                    "message": (
                                        f"Agent for task {task_id} failed with"
                                        f" returncode {returncode}."
                                    ),
                                    "resolved": False,
                                }
                            )
                        with locks.locked_json_rw(self._tasks_path) as data:
                            for t in data["tasks"]:
                                if t["id"] == task_id:
                                    t["status"] = "pending"
                                    break
                        print(
                            f"[ralph] Agent for task {task_id} failed"
                            f" (returncode {returncode}).",
                            file=sys.stderr,
                        )

                # Step B: Check exit conditions.
                tasks = locks.read_json(self._tasks_path)["tasks"]

                if dag.all_tasks_complete(tasks):
                    self._run_summarise("All tasks completed successfully.")
                    return

                exceeded, task = dag.any_task_exceeded_max_attempts(tasks)
                if exceeded:
                    exit_reason = (
                        f"Task {task['id']} ('{task['title']}') reached"
                        f" max_attempts ({task['max_attempts']})."
                    )
                    print(f"\n[ralph] Stopping early — {exit_reason}")
                    self._run_summarise(exit_reason)
                    return

                # Step C: Spawn agents for newly ready tasks.
                ready_tasks = dag.get_ready_tasks(tasks)
                for task in ready_tasks:
                    task_id = task["id"]
                    if task_id in futures:
                        continue
                    with locks.locked_json_rw(self._tasks_path) as data:
                        for t in data["tasks"]:
                            if t["id"] == task_id:
                                t["status"] = "in_progress"
                                t["attempts"] = t.get("attempts", 0) + 1
                                break
                    prompt = parse_execute_async_md(
                        self.project_name, task_id, 1, max_iterations
                    )
                    print(f'[ralph] Spawned execute agent to attempt task {task['id']} "{task['title']}"')

                    def _worker(p=prompt):
                        return run_noninteractive(p).returncode

                    futures[task_id] = executor.submit(_worker)

                # Step D: Sleep, then repeat.
                time.sleep(2)
        finally:
            executor.shutdown(wait=False)

    def run_execute_loop(self, prompts: list[str], max_iterations: int, asynchronous: bool = False) -> None:
        """Run non-interactive execute agents in a loop."""
        if asynchronous:
            self.run_execute_loop_async(prompts, max_iterations)
            return

        # Pre-check: skip spawning agents if all tasks are already complete.
        if self._all_tasks_complete():
            exit_reason = "All tasks completed successfully."
            print("\n[ralph] All tasks are already done — nothing left to do!")
            self._run_summarise(exit_reason)
            return

        exit_reason = f"Reached maximum iteration limit ({max_iterations})."

        for iteration in range(1, max_iterations + 1):
            prompt = prompts[min(iteration - 1, len(prompts) - 1)]

            print(f'\n[ralph] Spawned execute agent to attempt task {task['id']} "{task['title']}" (iteration {iteration}/{max_iterations})...')
            agent_response = self._handle_result(run_noninteractive(prompt))

            if "You've hit your limit" in agent_response:
                exit_reason = "Claude Code usage limit has been reached."
                print("\n[ralph] Looks like the Claude Code usage limit has been reached.")
                break

            if self._all_tasks_complete():
                exit_reason = "All tasks completed successfully."
                print("\n[ralph] All tasks are done!")
                break

            exceeded, task = self._any_task_exceeded_max_attempts()
            if exceeded:
                exit_reason = f"Task {task['id']} ('{task['title']}') reached max_attempts ({task['max_attempts']})."
                print(f"\n[ralph] Stopping early — {exit_reason}")
                break
        else:
            # for/else fires when all iterations were exhausted without breaking
            print(f"\n[ralph] {exit_reason}")

        self._run_summarise(exit_reason)
