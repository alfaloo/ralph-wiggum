"""Claude Code invocation and orchestration loop for Ralph Wiggum."""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import subprocess
import sys
import time
from typing import Callable

from ralph import dag
from ralph import locks
from ralph.parse import parse_summarise_md, parse_execute_async_md, parse_execute_md

_RALPH_ROOT = ".ralph"



def _open_multiline_editor(preamble: str) -> str:
    """Open the multiline editor with the given preamble text.

    Internally determines whether stdin is a TTY and routes accordingly:
    - TTY mode: opens the full prompt_toolkit multiline editor supporting
      arrow key navigation, mouse-click cursor positioning, Enter for new
      lines, Ctrl+D to submit, and Ctrl+C to abort.
    - Non-TTY mode: reads multi-line input without exhausting stdin, so that
      subsequent questions can still receive input (including further
      "Describe yourself..." selections). Reads lines until a sentinel line
      containing only "." is received.
    """
    if sys.stdin.isatty():
        try:
            from prompt_toolkit import prompt as pt_prompt
            from prompt_toolkit.key_binding import KeyBindings

            print(f"{preamble}\n")

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
                print("\n[ralph] Okay, I'm stopping the interview now! Bye bye!")
                sys.exit(0)
            except EOFError:
                return ""

        except ImportError:
            pass

    print(preamble)
    print('(Type your answer and put a "." all by itself on a new line when you\'re done!)\n')
    lines = []
    try:
        while True:
            line = sys.stdin.readline()
            if not line or line.rstrip("\n") == ".":
                break
            lines.append(line.rstrip("\n"))
    except KeyboardInterrupt:
        print("\n[ralph] Okay, I'm stopping the interview now! Bye bye!")
        sys.exit(0)
    return "\n".join(lines).strip()


def _collect_user_answers() -> str:
    """Read multi-line user input until Ctrl+D (submit) or Ctrl+C (abort).

    Attempts to use prompt_toolkit for a richer editing experience (arrow keys,
    mouse-click cursor positioning, revisit previous lines). Falls back to
    sentinel-based line reading if stdin is not a TTY (e.g. when stdin is a
    pipe from the VSCode extension).
    """
    return _open_multiline_editor("Type your answers down here! Press Ctrl+D when you're all done, or Ctrl+C to stop:")


def _parse_questions_json(raw: str) -> list[dict] | None:
    """Parse Claude's JSON output into a list of question dicts.

    Returns None on parse failure so the caller can fall back gracefully.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data.get("questions", [])
    except (json.JSONDecodeError, AttributeError):
        return None


_DESCRIBE_YOURSELF = "Describe yourself..."
_VSCODE_SENTINEL = "[ralph-vscode] interview_questions_ready"


def _collect_guided_answers_vscode(questions: list[dict], ralph_dir: str) -> str:
    """VS Code extension mode: write questions to a temp file, wait for answers.

    Only called when the RALPH_VSCODE env var is set (set by the extension).
    Terminal runs skip this entirely and use the normal TTY/non-TTY paths.
    """
    questions_path = os.path.join(ralph_dir, "interview_questions.json")
    answers_path = os.path.join(ralph_dir, "interview_answers.json")

    # Remove any stale answers file from a previous interrupted run
    if os.path.exists(answers_path):
        os.unlink(answers_path)

    # Write questions including the "Describe yourself..." freeform option
    with open(questions_path, "w") as f:
        json.dump(
            [
                {
                    "question": q.get("question", ""),
                    "options": list(q.get("options", [])) + [_DESCRIBE_YOURSELF],
                }
                for q in questions
            ],
            f,
        )

    # Signal the extension to read the file and display the form
    print(_VSCODE_SENTINEL, flush=True)

    # Poll for the answers file written back by the extension (10-min timeout)
    deadline = time.time() + 600
    while time.time() < deadline:
        if os.path.exists(answers_path):
            with open(answers_path) as f:
                content = f.read()
            try:
                os.unlink(answers_path)
            except OSError:
                pass
            try:
                os.unlink(questions_path)
            except OSError:
                pass
            return content
        time.sleep(0.2)

    raise TimeoutError("[ralph] VS Code interview timed out waiting for answers.")


def _collect_guided_answers(questions: list[dict], ralph_dir: str = "") -> str:
    """Present questions one at a time with arrow-key or numbered selection.

    Returns a JSON string of question–answer pairs suitable for passing to the
    generate_tasks template.

    When the RALPH_VSCODE environment variable is set (VS Code extension mode),
    delegates to _collect_guided_answers_vscode which uses a file protocol
    instead of terminal I/O. Terminal runs are completely unaffected.
    """
    if os.environ.get("RALPH_VSCODE") and ralph_dir:
        return _collect_guided_answers_vscode(questions, ralph_dir)

    DESCRIBE_YOURSELF = _DESCRIBE_YOURSELF
    SEPARATOR = "\u2500" * 61
    total = len(questions)
    qa_pairs: list[dict] = []

    def _tty_select(all_options: list[str]) -> str:
        """Arrow-key selection via prompt_toolkit Application."""
        from prompt_toolkit.application import Application
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.layout import Layout
        from prompt_toolkit.layout.containers import Window
        from prompt_toolkit.layout.controls import FormattedTextControl

        cursor = [0]
        result: list[str | None] = [None]

        def get_text():
            lines = []
            for idx, opt in enumerate(all_options):
                if idx == cursor[0]:
                    lines.append(("class:cursor", f"  > {opt}\n"))
                else:
                    lines.append(("", f"    {opt}\n"))
            lines.append(("", "\n\u2191\u2193 to move  Enter to select"))
            return lines

        kb = KeyBindings()

        @kb.add("up")
        def _up(event):
            cursor[0] = (cursor[0] - 1) % len(all_options)

        @kb.add("down")
        def _down(event):
            cursor[0] = (cursor[0] + 1) % len(all_options)

        @kb.add("enter")
        def _enter(event):
            result[0] = all_options[cursor[0]]
            event.app.exit()

        @kb.add("c-c")
        def _ctrl_c(event):
            event.app.exit(exception=KeyboardInterrupt())

        control = FormattedTextControl(get_text)
        window = Window(content=control)
        layout = Layout(window)
        app = Application(layout=layout, key_bindings=kb, full_screen=False)
        app.run()
        return result[0] or ""

    def _nontty_select(all_options: list[str]) -> str:
        """Numbered-list selection via sys.stdin.readline()."""
        k_plus_1 = len(all_options)
        for idx, opt in enumerate(all_options, start=1):
            print(f"  {idx}. {opt}")
        print()
        while True:
            print(f"Pick one! (1\u2013{k_plus_1}): ", end="", flush=True)
            line = sys.stdin.readline()
            if not line:
                return ""
            line = line.strip()
            try:
                choice = int(line)
                if 1 <= choice <= k_plus_1:
                    return all_options[choice - 1]
            except ValueError:
                pass
            print(f"Oopsie! That's not right. Pick a number from 1 to {k_plus_1}.")

    try:
        for i, q in enumerate(questions, start=1):
            question_text = q.get("question", "")
            options = list(q.get("options", []))
            all_options = options + [DESCRIBE_YOURSELF]

            print(f"Q{i}: {question_text}\n")

            if not options:
                # Empty options — fall back to multiline editor directly
                answer = _open_multiline_editor(
                    "Type your answer. Press Ctrl+D when done, or Ctrl+C to stop:"
                )
            elif sys.stdin.isatty():
                selected = _tty_select(all_options)
                if selected == DESCRIBE_YOURSELF:
                    answer = _open_multiline_editor(
                        "Type your answer. Press Ctrl+D when done, or Ctrl+C to stop:"
                    )
                else:
                    answer = selected
            else:
                selected = _nontty_select(all_options)
                if selected == DESCRIBE_YOURSELF:
                    answer = _open_multiline_editor(
                        "Type your answer. Press Ctrl+D when done, or Ctrl+C to stop:"
                    )
                else:
                    answer = selected

            qa_pairs.append({"question": question_text, "answer": answer})

            if i < total:
                print(f"\n{SEPARATOR}\n")

    except KeyboardInterrupt:
        print("\n[ralph] Okay! I'm gonna stop the interview now. Bye!")
        sys.exit(0)

    return json.dumps(qa_pairs)


class Runner:
    """Orchestrator that manages agent invocations for a single project."""

    def __init__(self, project_name: str, verbose: bool = False) -> None:
        self.project_name = project_name
        self.verbose = verbose
        self.ralph_dir = os.path.join(_RALPH_ROOT, project_name)
        self._tasks_path = os.path.join(self.ralph_dir, "tasks.json")

    @staticmethod
    def _run_noninteractive(prompt: str) -> subprocess.CompletedProcess:
        """Run Claude Code in non-interactive (headless) mode.

        Invokes `claude` with --print so output is piped back.
        """
        cmd = ["claude", "--dangerously-skip-permissions", "--print", prompt]
        return subprocess.run(cmd, capture_output=True, text=True)

    @staticmethod
    def _run_noninteractive_json(prompt: str) -> subprocess.CompletedProcess:
        """Run Claude Code in non-interactive mode with JSON output format.

        Like _run_noninteractive() but adds --output-format json so that stdout is
        a JSON object containing the result text and token usage information.
        """
        cmd = ["claude", "--dangerously-skip-permissions", "--print", "--output-format", "json", prompt]
        return subprocess.run(cmd, capture_output=True, text=True)

    def _handle_result(self, result: subprocess.CompletedProcess) -> None:
        """Print stdout if verbose; always print stderr on non-zero exit."""
        if self.verbose and result.stdout:
            print(result.stdout)
        if result.returncode != 0 and result.stderr:
            print(f"[ralph] Uh oh, the agent did a bad thing: {result.stderr}", file=sys.stderr)

    def _all_tasks_complete(self) -> bool:
        if not os.path.exists(self._tasks_path):
            return False
        tasks = locks.read_json(self._tasks_path).get("tasks", [])
        return bool(tasks) and dag.all_tasks_complete(tasks)

    def _any_task_exceeded_max_attempts(self) -> tuple[bool, dict | None]:
        if not os.path.exists(self._tasks_path):
            return False, None
        tasks = locks.read_json(self._tasks_path).get("tasks", [])
        return dag.any_task_exceeded_max_attempts(tasks)

    def _run_summarise(self, exit_reason: str) -> None:
        """Spawn a summarise agent to write .ralph/<project-name>/summary.md."""
        print("[ralph] Ooh ooh, I'm writing the summary now!")
        prompt = parse_summarise_md(
            self.project_name, ralph_dir=self.ralph_dir, exit_reason=exit_reason
        )
        result = self._run_noninteractive(prompt)
        self._handle_result(result)
        if result.returncode == 0:
            print("[ralph] The summary is all done! You can read it now!")
        else:
            print("[ralph] Uh oh, I couldn't write the summary. Something went wrong.", file=sys.stderr)

    def run_prompt(self, prompt: str, command_name: str, json_output: bool = False) -> str | None:
        """Run a single headless agent invocation for the given command.

        If json_output is True, invokes Claude with --output-format json and
        returns the agent's result text string. Otherwise returns None.
        """
        print(f"[ralph] I'm doing the {command_name} thing for '{self.project_name}'! Here we go!")
        if json_output:
            result = self._run_noninteractive_json(prompt)
        else:
            result = self._run_noninteractive(prompt)
        self._handle_result(result)
        if result.returncode == 0:
            print(f"[ralph] Yay! The {command_name} thing is all done for '{self.project_name}'!")
        else:
            print(f"[ralph] Uh oh, the {command_name} thing had a problem. Something went wrong.", file=sys.stderr)

        if json_output:
            try:
                data = json.loads(result.stdout)
                return data.get("result", result.stdout)
            except (json.JSONDecodeError, AttributeError):
                return result.stdout
        return None

    def run_interview_loop(
        self,
        question_prompts: list[str],
        make_amend_prompts: list[Callable[..., str]],
    ) -> None:
        """Run sequential two-phase interview agents, one per round.

        Each round:
          Phase 1 — non-interactive agent outputs clarifying questions (JSON).
          (user answers questions via guided or free-form path)
          Phase 2 — non-interactive agent receives Q&A JSON and amends
                     spec.md and creates/refreshes tasks.json.
        """
        total = len(question_prompts)
        print(f"[ralph] I'm doing the interview thing for '{self.project_name}'! There are {total} round(s)!")

        for i, q_prompt in enumerate(question_prompts):
            round_num = i + 1
            print(f"\n[ralph] Interview round {round_num} of {total}! Here we go!")

            # Phase 1: generate questions (JSON output mode so result text is cleanly extracted)
            print("[ralph] I'm thinking up some questions for you...\n")
            result = self._run_noninteractive_json(q_prompt)
            if result.returncode != 0 and result.stderr:
                print(f"[ralph] Uh oh, the agent did a bad thing: {result.stderr}", file=sys.stderr)
            raw_output = result.stdout.strip()
            try:
                json_data = json.loads(raw_output)
                raw_output = json_data.get("result", raw_output)
            except (json.JSONDecodeError, AttributeError):
                pass

            # Try structured (guided) path first
            questions_data = _parse_questions_json(raw_output)
            if questions_data:
                qa_json = _collect_guided_answers(questions_data, ralph_dir=self.ralph_dir)
            else:
                # Fallback: legacy free-form path
                print("[ralph] I couldn't make the questions come out right, so I'll just ask you normally.")
                print(raw_output)
                print()
                answers = _collect_user_answers()
                qa_json = json.dumps([{"question": raw_output, "answer": answers}])

            # Phase 2: amend spec with Q&A
            print("\n[ralph] Ooh, now I'm updating the spec with all your answers!")
            result2 = self._run_noninteractive(make_amend_prompts[i](qa_json=qa_json))
            self._handle_result(result2)
            if result2.returncode == 0:
                print(f"[ralph] Yay! Round {round_num} is all done!")
            else:
                print(f"[ralph] Uh oh, round {round_num} had a problem. Something went wrong.", file=sys.stderr)

        print("\n[ralph] Yay! All the interview rounds are done! Great job answering!")

    def run_execute_loop_async(self, max_iterations: int) -> None:
        """Run async execute agents in a concurrent polling loop."""
        state_path = os.path.join(self.ralph_dir, "state.json")
        obstacles_path = os.path.join(self.ralph_dir, "obstacles.json")

        # Ensure state and obstacles files exist before agents start writing.
        if not os.path.exists(state_path):
            locks.write_json(state_path, [])
        if not os.path.exists(obstacles_path):
            locks.write_json(obstacles_path, {"obstacles": []})

        futures: dict[str, concurrent.futures.Future] = {}
        executor = concurrent.futures.ThreadPoolExecutor()
        iteration = 0
        exit_reason = f"Reached maximum iteration limit ({max_iterations})."

        try:
            while True:
                iteration += 1

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
                            f"[ralph] Uh oh, the agent for task {task_id} did something really bad: {exc}",
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
                                    "iteration": iteration,
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
                            f"[ralph] Uh oh, the agent for task {task_id} didn't work"
                            f" (returncode {returncode}). I'll try again later!",
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
                    print(f"\n[ralph] I have to stop now — {exit_reason}")
                    self._run_summarise(exit_reason)
                    return

                if iteration >= max_iterations:
                    print(f"\n[ralph] I used up all {max_iterations} rounds and I'm all tired out now.")
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
                        self.project_name,
                        task_id,
                        iteration,
                        max_iterations,
                        task_title=task.get("title", ""),
                        task_description=task.get("description", ""),
                    )
                    print(f"[ralph] I'm starting an agent for task {task['id']} \"{task['title']}\"! Yay!")

                    def _worker(p=prompt):
                        return Runner._run_noninteractive(p).returncode

                    futures[task_id] = executor.submit(_worker)

                # Step D: Sleep, then repeat.
                time.sleep(2)
        finally:
            executor.shutdown(wait=False)

    def _reset_incomplete_tasks(self) -> None:
        """Reset all non-completed tasks to pending state silently."""
        if not os.path.exists(self._tasks_path):
            return
        data = locks.read_json(self._tasks_path)
        for task in data.get("tasks", []):
            if task.get("status") != "completed":
                task["status"] = "pending"
                task["attempts"] = 0
                task["blocked"] = False
        locks.write_json(self._tasks_path, data)

    def run_execute_single(self) -> None:
        """Spawn one agent to implement all pending tasks in sequence."""
        from ralph.parse import parse_execute_single_md

        # Pre-check: skip spawning if all tasks are already completed
        try:
            with open(self._tasks_path) as f:
                tasks_data = json.load(f)
            if tasks_data.get("tasks") and all(
                t.get("status") == "completed" for t in tasks_data["tasks"]
            ):
                print("[ralph] All tasks already completed. Skipping agent spawn.")
                self._run_summarise("All tasks completed")
                return
        except Exception:
            pass

        print("[ralph] Single-agent mode: spawning one agent for all tasks.")
        prompt = parse_execute_single_md(self.project_name)
        result = self._run_noninteractive_json(prompt)

        if self.verbose:
            print(result.stdout)

        try:
            data = json.loads(result.stdout)
            usage = data.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            print(f"[ralph] Agent complete. Tokens used — input: {input_tokens}, output: {output_tokens}")
        except (json.JSONDecodeError, KeyError):
            pass

        # Determine exit reason from tasks.json after agent completes
        try:
            with open(self._tasks_path) as f:
                tasks_data = json.load(f)
            all_completed = all(
                t.get("status") == "completed" for t in tasks_data.get("tasks", [])
            )
            exit_reason = "All tasks completed" if all_completed else "Some tasks did not complete successfully"
        except Exception:
            exit_reason = "Some tasks did not complete successfully"

        self._run_summarise(exit_reason)

    def run_execute_loop(self, max_iterations: int, asynchronous: bool = False, single: bool = False, resume: bool = False) -> None:
        """Run non-interactive execute agents in a loop."""
        if resume:
            self._reset_incomplete_tasks()

        if single:
            self.run_execute_single()
            return

        if asynchronous:
            self.run_execute_loop_async(max_iterations)
            return

        # Pre-check: skip spawning agents if all tasks are already complete.
        if self._all_tasks_complete():
            exit_reason = "All tasks completed successfully."
            print("\n[ralph] All the tasks are already done — I didn't have to do anything! Neat!")
            self._run_summarise(exit_reason)
            return

        exit_reason = f"Reached maximum iteration limit ({max_iterations})."

        for iteration in range(1, max_iterations + 1):
            # Load tasks.json and select the next ready task via dag.get_ready_tasks().
            with open(self._tasks_path) as f:
                tasks_data = json.load(f)
            tasks = tasks_data.get("tasks", [])

            ready_tasks = dag.get_ready_tasks(tasks)
            if not ready_tasks:
                exit_reason = (
                    "No tasks are ready to execute — all remaining tasks are blocked or have unmet dependencies."
                )
                print(f"\n[ralph] I can't do anything right now — all the tasks are stuck or waiting for other tasks!")
                break

            task = ready_tasks[0]
            task_id = task["id"]
            task_title = task.get("title", "")
            task_description = task.get("description", "")

            # Pre-update tasks.json: mark selected task as in_progress and increment attempts.
            for t in tasks_data["tasks"]:
                if t["id"] == task_id:
                    t["status"] = "in_progress"
                    t["attempts"] = t.get("attempts", 0) + 1
                    break
            locks.write_json(self._tasks_path, tasks_data)

            # Build the prompt with the pre-assigned task injected.
            prompt = parse_execute_md(
                self.project_name,
                iteration_num=iteration,
                max_iterations=max_iterations,
                task_id=task_id,
                task_title=task_title,
                task_description=task_description,
            )

            print(
                f"\n[ralph] I'm working on task {task_id} \"{task_title}\""
                f" (round {iteration} of {max_iterations})! Here we go!"
            )
            result = self._run_noninteractive_json(prompt)

            # Handle errors from the subprocess.
            if result.returncode != 0 and result.stderr:
                print(f"[ralph] Uh oh, the agent did a bad thing: {result.stderr}", file=sys.stderr)

            # Parse JSON output for the agent's text response and context window usage.
            agent_text = result.stdout
            try:
                data = json.loads(result.stdout)
                agent_text = data.get("result", result.stdout)

                if self.verbose and agent_text:
                    print(agent_text)

                # Log context window usage from the completed agent.
                usage = data.get("usage", {})
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                total_tokens = input_tokens + output_tokens
                model_usage = data.get("modelUsage", {})
                context_window = model_usage.get("contextWindow", 200000)
                pct = (total_tokens / context_window * 100) if context_window > 0 else 0
                print(
                    f"[ralph] The agent used {total_tokens:,} out of {context_window:,} brain tokens"
                    f" ({pct:.1f}% of the thinky space)."
                )
            except (json.JSONDecodeError, ValueError):
                if self.verbose and result.stdout:
                    print(result.stdout)

            if "You've hit your limit" in agent_text:
                exit_reason = "Claude Code usage limit has been reached."
                print("\n[ralph] Uh oh! We ran out of Claude Code tokens. That's too bad.")
                break

            if self._all_tasks_complete():
                exit_reason = "All tasks completed successfully."
                print("\n[ralph] Yay yay yay! All the tasks are done! We did it!")
                break

            exceeded, task = self._any_task_exceeded_max_attempts()
            if exceeded:
                exit_reason = f"Task {task['id']} ('{task['title']}') reached max_attempts ({task['max_attempts']})."
                print(f"\n[ralph] I have to stop now — {exit_reason}")
                break
        else:
            # for/else fires when all iterations were exhausted without breaking
            print(f"\n[ralph] I used up all {max_iterations} rounds and I'm all tired out now.")

        self._run_summarise(exit_reason)
