"""Unit tests for run_execute_loop() single-agent dispatch and run_execute_single()."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

from ralph.run import Runner


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _task(
    task_id: str,
    status: str = "pending",
    dependencies: list | None = None,
    attempts: int = 0,
    max_attempts: int = 3,
) -> dict:
    return {
        "id": task_id,
        "title": f"Task {task_id}",
        "status": status,
        "dependencies": dependencies if dependencies is not None else [],
        "attempts": attempts,
        "max_attempts": max_attempts,
        "blocked": False,
    }


def _setup(tmp_path, tasks: list[dict]):
    """Write tasks.json under .ralph/test-project/ inside tmp_path and return a Runner.

    run_execute_single() reads from the hardcoded relative path
    ``.ralph/{project_name}/tasks.json``, so the directory structure must match
    when the working directory is set to ``tmp_path``.
    """
    ralph_dir = tmp_path / ".ralph" / "test-project"
    ralph_dir.mkdir(parents=True)
    tasks_file = ralph_dir / "tasks.json"
    tasks_file.write_text(json.dumps({"tasks": tasks}, indent=2))

    runner = Runner("test-project")
    runner.ralph_dir = str(ralph_dir)
    runner._tasks_path = str(tasks_file)

    return runner, tasks_file


def _ok_json(result_text: str = "") -> MagicMock:
    """Return a mock subprocess result with returncode=0 and JSON stdout."""
    m = MagicMock()
    m.returncode = 0
    m.stdout = json.dumps({"result": result_text, "usage": {"input_tokens": 10, "output_tokens": 5}})
    return m


# ===========================================================================
# Test 1 — run_execute_loop dispatches to run_execute_single when single=True
# ===========================================================================


def test_run_execute_loop_dispatches_to_single_when_single_true(tmp_path):
    """When single=True, run_execute_loop calls run_execute_single and skips the async/sync loops."""
    tasks = [_task("T1")]
    runner, _ = _setup(tmp_path, tasks)

    with patch.object(runner, "run_execute_single") as mock_single, \
         patch.object(runner, "run_execute_loop_async") as mock_async, \
         patch("ralph.run.Runner._run_noninteractive_json") as mock_json:
        runner.run_execute_loop(10, single=True)

    mock_single.assert_called_once()
    mock_async.assert_not_called()
    mock_json.assert_not_called()


# ===========================================================================
# Test 2 — run_execute_single invokes the agent and calls _run_summarise
# ===========================================================================


def test_run_execute_single_invokes_agent(tmp_path):
    """run_execute_single renders the prompt, calls run_noninteractive_json, and calls _run_summarise."""
    tasks = [_task("T1")]
    runner, tasks_file = _setup(tmp_path, tasks)

    captured_prompts: list[str] = []

    def mock_run_json(prompt: str):
        captured_prompts.append(prompt)
        # Simulate agent completing all tasks by updating tasks.json
        data = json.loads(tasks_file.read_text())
        for t in data["tasks"]:
            t["status"] = "completed"
        tasks_file.write_text(json.dumps(data, indent=2))
        return _ok_json()

    orig_dir = os.getcwd()
    try:
        os.chdir(tmp_path)
        with patch("ralph.run.Runner._run_noninteractive_json", side_effect=mock_run_json), \
             patch.object(runner, "_run_summarise") as mock_summarise:
            runner.run_execute_single()
    finally:
        os.chdir(orig_dir)

    # Agent was invoked with a non-empty prompt
    assert len(captured_prompts) == 1
    assert len(captured_prompts[0]) > 0

    # _run_summarise was called with an exit_reason string indicating success
    mock_summarise.assert_called_once()
    exit_reason = mock_summarise.call_args[0][0]
    assert isinstance(exit_reason, str)
    assert "completed" in exit_reason.lower()
