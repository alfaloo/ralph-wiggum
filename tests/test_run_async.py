"""Unit tests for run_execute_loop_async() in ralph/run.py.

All tests mock ``ralph.run.run_noninteractive`` — no real Claude Code agents
are spawned. Concurrency scenarios use Python threading with ``threading.Event``
and ``threading.Semaphore`` to gate workers and verify parallel execution.
"""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from ralph.run import Runner

# Capture the real time.sleep before any test patches it.
# patch("ralph.run.time.sleep", ...) replaces the attribute on the shared `time`
# module object, which would cause infinite recursion if the side_effect itself
# called `time.sleep`.  Binding to the function object directly avoids this.
_real_sleep = time.sleep


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _task(
    task_id: str,
    status: str = "pending",
    dependencies: list | None = None,
    attempts: int = 0,
    max_attempts: int = 3,
    blocked: bool = False,
    title: str | None = None,
) -> dict:
    """Build a minimal task dict for use in tests."""
    return {
        "id": task_id,
        "title": title if title is not None else f"Task {task_id}",
        "status": status,
        "dependencies": dependencies if dependencies is not None else [],
        "attempts": attempts,
        "max_attempts": max_attempts,
        "blocked": blocked,
    }


def _setup(tmp_path, tasks: list[dict]):
    """Write artifact JSON files and return a Runner pointed at tmp_path.

    Returns (runner, tasks_file, state_file, obstacles_file).
    """
    tasks_file = tmp_path / "tasks.json"
    state_file = tmp_path / "state.json"
    obstacles_file = tmp_path / "obstacles.json"

    tasks_file.write_text(json.dumps({"tasks": tasks}, indent=2))
    state_file.write_text(json.dumps([], indent=2))
    obstacles_file.write_text(json.dumps({"obstacles": []}, indent=2))

    runner = Runner("test-project")
    runner.ralph_dir = str(tmp_path)
    runner._tasks_path = str(tasks_file)

    return runner, tasks_file, state_file, obstacles_file


def _ok() -> MagicMock:
    """Return a mock subprocess result with returncode=0."""
    m = MagicMock()
    m.returncode = 0
    return m


def _fail() -> MagicMock:
    """Return a mock subprocess result with returncode=1."""
    m = MagicMock()
    m.returncode = 1
    return m


# ===========================================================================
# Test 1 — All tasks completed; state.json has one entry per task
# ===========================================================================


class TestAllTasksCompleted:
    def test_single_task_marked_completed(self, tmp_path):
        """A single task is marked completed after the agent returns 0."""
        tasks = [_task("T1")]
        runner, tasks_file, _, _ = _setup(tmp_path, tasks)

        with patch("ralph.run.run_noninteractive", return_value=_ok()), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop_async([], 10)

        final = json.loads(tasks_file.read_text())["tasks"]
        assert final[0]["status"] == "completed"

    def test_two_independent_tasks_both_completed(self, tmp_path):
        """Two independent tasks are both eventually marked completed."""
        tasks = [_task("T1"), _task("T2")]
        runner, tasks_file, _, _ = _setup(tmp_path, tasks)

        with patch("ralph.run.run_noninteractive", return_value=_ok()), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop_async([], 10)

        final = json.loads(tasks_file.read_text())["tasks"]
        assert all(t["status"] == "completed" for t in final)

    def test_state_json_has_one_entry_per_completed_task(self, tmp_path):
        """state.json receives exactly one entry per completed task."""
        tasks = [_task("T1"), _task("T2"), _task("T3")]
        runner, _, state_file, _ = _setup(tmp_path, tasks)

        with patch("ralph.run.run_noninteractive", return_value=_ok()), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop_async([], 10)

        state = json.loads(state_file.read_text())
        assert len(state) == 3
        ids_in_state = {e["task_id"] for e in state}
        assert ids_in_state == {"T1", "T2", "T3"}

    def test_state_json_entries_have_completed_status(self, tmp_path):
        """Each state.json entry has status='completed'."""
        tasks = [_task("T1"), _task("T2")]
        runner, _, state_file, _ = _setup(tmp_path, tasks)

        with patch("ralph.run.run_noninteractive", return_value=_ok()), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop_async([], 10)

        state = json.loads(state_file.read_text())
        for entry in state:
            assert entry["status"] == "completed"

    def test_state_json_entries_have_correct_structure(self, tmp_path):
        """Each state.json entry contains the expected keys."""
        tasks = [_task("T1")]
        runner, _, state_file, _ = _setup(tmp_path, tasks)

        with patch("ralph.run.run_noninteractive", return_value=_ok()), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop_async([], 10)

        state = json.loads(state_file.read_text())
        assert len(state) == 1
        entry = state[0]
        assert entry["task_id"] == "T1"
        assert entry["status"] == "completed"
        assert "summary" in entry
        assert "files_modified" in entry
        assert "obstacles" in entry

    def test_run_summarise_called_with_all_completed_reason(self, tmp_path):
        """_run_summarise is called with 'All tasks completed successfully.' on success."""
        tasks = [_task("T1")]
        runner, _, _, _ = _setup(tmp_path, tasks)

        with patch("ralph.run.run_noninteractive", return_value=_ok()), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise") as mock_summarise:
            runner.run_execute_loop_async([], 10)

        mock_summarise.assert_called_once_with("All tasks completed successfully.")


# ===========================================================================
# Test 2 — Independent tasks dispatched in parallel
# ===========================================================================


class TestParallelDispatch:
    def test_two_independent_tasks_run_concurrently(self, tmp_path):
        """Two independent tasks are in-flight simultaneously (verified via threading gates).

        Uses ``threading.Event`` to block both workers until we can confirm they
        are both active at the same moment — no real agents are spawned.
        """
        tasks = [_task("T1"), _task("T2")]
        runner, _, _, _ = _setup(tmp_path, tasks)

        worker_gate = threading.Event()      # blocks workers until released
        workers_started = threading.Semaphore(0)  # counts workers that have entered the mock
        concurrent = [0]
        max_concurrent = [0]
        count_lock = threading.Lock()

        def mock_agent(prompt):
            with count_lock:
                concurrent[0] += 1
                if concurrent[0] > max_concurrent[0]:
                    max_concurrent[0] = concurrent[0]
            workers_started.release()
            worker_gate.wait(timeout=15)
            with count_lock:
                concurrent[0] -= 1
            return _ok()

        run_done = threading.Event()

        def run_loop():
            with patch("ralph.run.run_noninteractive", side_effect=mock_agent), \
                 patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.005)), \
                 patch.object(runner, "_run_summarise"):
                runner.run_execute_loop_async([], 10)
            run_done.set()

        t = threading.Thread(target=run_loop, daemon=True)
        t.start()

        # Wait for both workers to be inside the mock at the same time
        assert workers_started.acquire(timeout=10), "Worker 1 did not start in time"
        assert workers_started.acquire(timeout=10), "Worker 2 did not start in time"

        with count_lock:
            assert concurrent[0] == 2, (
                f"Expected 2 concurrent workers, got {concurrent[0]}"
            )

        worker_gate.set()  # release all workers
        assert run_done.wait(timeout=15), "run_execute_loop_async did not complete"
        assert max_concurrent[0] == 2, "Tasks were not dispatched in parallel"

    def test_three_independent_tasks_all_dispatched_before_first_returns(self, tmp_path):
        """Three independent tasks are all submitted before any one of them finishes.

        Uses ``threading.Barrier`` so all three workers AND the main test thread
        must arrive before any worker is allowed to return — confirming all three
        are simultaneously in-flight.
        """
        tasks = [_task("T1"), _task("T2"), _task("T3")]
        runner, _, _, _ = _setup(tmp_path, tasks)

        # 4 parties: 3 workers + 1 test thread
        barrier = threading.Barrier(4, timeout=15)
        gate = threading.Event()

        def mock_agent(prompt):
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass
            gate.wait(timeout=15)
            return _ok()

        run_done = threading.Event()

        def run_loop():
            with patch("ralph.run.run_noninteractive", side_effect=mock_agent), \
                 patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.005)), \
                 patch.object(runner, "_run_summarise"):
                runner.run_execute_loop_async([], 10)
            run_done.set()

        t = threading.Thread(target=run_loop, daemon=True)
        t.start()

        try:
            barrier.wait()  # join the barrier as the 4th party
        except threading.BrokenBarrierError:
            pytest.fail(
                "Not all 3 workers reached the barrier — tasks were not dispatched in parallel"
            )

        gate.set()
        assert run_done.wait(timeout=15), "run_execute_loop_async did not complete"


# ===========================================================================
# Test 3 — Dependent tasks not started until dependency is completed
# ===========================================================================


class TestDependencyOrdering:
    def test_dependent_task_not_dispatched_while_dep_is_in_progress(self, tmp_path):
        """T2 (depends on T1) is NOT dispatched while T1's agent is still running."""
        tasks = [
            _task("T1", dependencies=[]),
            _task("T2", dependencies=["T1"]),
        ]
        runner, tasks_file, _, _ = _setup(tmp_path, tasks)

        t1_gate = threading.Event()   # blocks T1's worker until released
        call_log: list[str] = []
        log_lock = threading.Lock()

        def mock_agent(prompt):
            with log_lock:
                call_log.append(prompt)
            if "T1" in prompt:
                t1_gate.wait(timeout=15)
            return _ok()

        run_done = threading.Event()

        def run_loop():
            with patch("ralph.run.run_noninteractive", side_effect=mock_agent), \
                 patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.005)), \
                 patch.object(runner, "_run_summarise"):
                runner.run_execute_loop_async([], 10)
            run_done.set()

        t = threading.Thread(target=run_loop, daemon=True)
        t.start()

        # Let the loop run several iterations while T1 is blocked
        time.sleep(0.2)

        # T2 must not have been dispatched yet
        with log_lock:
            t2_early_calls = [p for p in call_log if "T2" in p]
        assert t2_early_calls == [], "T2 was dispatched before T1 completed"

        # Confirm via tasks.json that T2 is still pending
        current_tasks = json.loads(tasks_file.read_text())["tasks"]
        t2 = next(tk for tk in current_tasks if tk["id"] == "T2")
        assert t2["status"] == "pending", (
            f"T2 status should be 'pending' while T1 is in-flight, got '{t2['status']}'"
        )

        t1_gate.set()  # release T1
        assert run_done.wait(timeout=15), "run_execute_loop_async did not complete"

        final = json.loads(tasks_file.read_text())["tasks"]
        assert all(tk["status"] == "completed" for tk in final)

    def test_dependent_task_dispatched_after_dependency_completes(self, tmp_path):
        """T1 is dispatched before T2 when T2 depends on T1."""
        tasks = [
            _task("T1", dependencies=[]),
            _task("T2", dependencies=["T1"]),
        ]
        runner, _, _, _ = _setup(tmp_path, tasks)

        call_order: list[str] = []
        order_lock = threading.Lock()

        def mock_agent(prompt):
            # Identify which task from the prompt ({{TASK_ID}} renders to T1/T2)
            with order_lock:
                for tid in ("T1", "T2"):
                    if tid in prompt:
                        call_order.append(tid)
                        break
            return _ok()

        with patch("ralph.run.run_noninteractive", side_effect=mock_agent), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop_async([], 10)

        assert "T1" in call_order
        assert "T2" in call_order
        assert call_order.index("T1") < call_order.index("T2"), (
            f"T2 was dispatched before T1; observed order: {call_order}"
        )

    def test_chain_of_dependencies_respected(self, tmp_path):
        """T1 → T2 → T3 chain: each task is dispatched only after its predecessor completes."""
        tasks = [
            _task("T1", dependencies=[]),
            _task("T2", dependencies=["T1"]),
            _task("T3", dependencies=["T2"]),
        ]
        runner, _, _, _ = _setup(tmp_path, tasks)

        call_order: list[str] = []
        order_lock = threading.Lock()

        def mock_agent(prompt):
            with order_lock:
                for tid in ("T1", "T2", "T3"):
                    if tid in prompt:
                        call_order.append(tid)
                        break
            return _ok()

        with patch("ralph.run.run_noninteractive", side_effect=mock_agent), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop_async([], 10)

        assert call_order == ["T1", "T2", "T3"], (
            f"Expected T1→T2→T3 dispatch order, got: {call_order}"
        )


# ===========================================================================
# Test 4 — Agent failure handling
# ===========================================================================


class TestFailureHandling:
    def test_failed_agent_resets_task_to_pending(self, tmp_path):
        """A non-zero returncode resets the task status to 'pending' in tasks.json."""
        tasks = [_task("T1", max_attempts=3)]
        runner, tasks_file, _, _ = _setup(tmp_path, tasks)

        call_count = [0]
        call_lock = threading.Lock()

        def mock_agent(prompt):
            with call_lock:
                call_count[0] += 1
                count = call_count[0]
            return _ok() if count > 1 else _fail()

        with patch("ralph.run.run_noninteractive", side_effect=mock_agent), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop_async([], 10)

        assert call_count[0] == 2, (
            f"Expected 2 agent calls (1 fail + 1 success), got {call_count[0]}"
        )
        final = json.loads(tasks_file.read_text())["tasks"]
        assert final[0]["status"] == "completed"
        assert final[0]["attempts"] == 2

    def test_failed_agent_appends_obstacle_to_obstacles_json(self, tmp_path):
        """A non-zero returncode appends an obstacle entry to obstacles.json."""
        tasks = [_task("T1", max_attempts=3)]
        runner, _, _, obstacles_file = _setup(tmp_path, tasks)

        call_count = [0]
        call_lock = threading.Lock()

        def mock_agent(prompt):
            with call_lock:
                call_count[0] += 1
                count = call_count[0]
            return _ok() if count > 1 else _fail()

        with patch("ralph.run.run_noninteractive", side_effect=mock_agent), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop_async([], 10)

        obstacles = json.loads(obstacles_file.read_text())["obstacles"]
        assert len(obstacles) == 1
        assert obstacles[0]["task_id"] == "T1"
        assert obstacles[0]["resolved"] is False

    def test_retry_agent_spawned_after_failure(self, tmp_path):
        """After a failure the task is eventually retried and completes."""
        tasks = [_task("T1", max_attempts=3)]
        runner, tasks_file, state_file, _ = _setup(tmp_path, tasks)

        call_count = [0]
        call_lock = threading.Lock()

        def mock_agent(prompt):
            with call_lock:
                call_count[0] += 1
                count = call_count[0]
            return _ok() if count >= 2 else _fail()

        with patch("ralph.run.run_noninteractive", side_effect=mock_agent), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop_async([], 10)

        final = json.loads(tasks_file.read_text())["tasks"]
        assert final[0]["status"] == "completed"

        # state.json must have exactly one completed entry (from the successful attempt)
        state = json.loads(state_file.read_text())
        completed = [e for e in state if e["status"] == "completed"]
        assert len(completed) == 1
        assert completed[0]["task_id"] == "T1"

    def test_task_attempts_incremented_on_retry(self, tmp_path):
        """Each time a task is dispatched its attempts counter is incremented."""
        tasks = [_task("T1", max_attempts=3)]
        runner, tasks_file, _, _ = _setup(tmp_path, tasks)

        call_count = [0]
        call_lock = threading.Lock()

        def mock_agent(prompt):
            with call_lock:
                call_count[0] += 1
                count = call_count[0]
            return _ok() if count >= 2 else _fail()

        with patch("ralph.run.run_noninteractive", side_effect=mock_agent), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop_async([], 10)

        final = json.loads(tasks_file.read_text())["tasks"]
        assert final[0]["attempts"] == 2


# ===========================================================================
# Test 5 — Max-attempts enforcement
# ===========================================================================


class TestMaxAttemptsEnforcement:
    def test_loop_exits_when_task_reaches_max_attempts(self, tmp_path):
        """The loop exits and calls _run_summarise when max_attempts is exhausted."""
        tasks = [_task("T1", max_attempts=2)]
        runner, _, _, _ = _setup(tmp_path, tasks)

        with patch("ralph.run.run_noninteractive", return_value=_fail()), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise") as mock_summarise:
            runner.run_execute_loop_async([], 10)

        expected = "Task T1 ('Task T1') reached max_attempts (2)."
        mock_summarise.assert_called_once_with(expected)

    def test_task_attempts_equals_max_attempts_when_exhausted(self, tmp_path):
        """A task that reaches max_attempts has attempts == max_attempts in tasks.json."""
        tasks = [_task("T1", max_attempts=2)]
        runner, tasks_file, _, _ = _setup(tmp_path, tasks)

        with patch("ralph.run.run_noninteractive", return_value=_fail()), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop_async([], 10)

        final = json.loads(tasks_file.read_text())["tasks"]
        assert final[0]["attempts"] == 2

    def test_max_attempts_obstacle_entries_created(self, tmp_path):
        """One obstacle is created per failed attempt when max_attempts is exhausted."""
        tasks = [_task("T1", max_attempts=2)]
        runner, _, _, obstacles_file = _setup(tmp_path, tasks)

        with patch("ralph.run.run_noninteractive", return_value=_fail()), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop_async([], 10)

        obstacles = json.loads(obstacles_file.read_text())["obstacles"]
        assert len(obstacles) == 2  # one per failed attempt
        for obs in obstacles:
            assert obs["task_id"] == "T1"

    def test_exit_reason_references_correct_task_title(self, tmp_path):
        """The _run_summarise exit reason contains the correct task title."""
        tasks = [_task("T1", max_attempts=1, title="My Custom Task")]
        runner, _, _, _ = _setup(tmp_path, tasks)

        with patch("ralph.run.run_noninteractive", return_value=_fail()), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise") as mock_summarise:
            runner.run_execute_loop_async([], 10)

        call_arg = mock_summarise.call_args[0][0]
        assert "My Custom Task" in call_arg
        assert "max_attempts" in call_arg
        assert "T1" in call_arg

    def test_max_attempts_with_mixed_tasks_exits_on_failing_task(self, tmp_path):
        """Loop exits for max_attempts violation even when other tasks are pending."""
        tasks = [
            _task("T1", max_attempts=2),  # always fails
            _task("T2"),                   # would succeed but T1 may trigger exit first
        ]
        runner, _, _, _ = _setup(tmp_path, tasks)

        def mock_agent(prompt):
            if "T1" in prompt:
                return _fail()
            return _ok()

        with patch("ralph.run.run_noninteractive", side_effect=mock_agent), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise") as mock_summarise:
            runner.run_execute_loop_async([], 10)

        mock_summarise.assert_called_once()
        call_arg = mock_summarise.call_args[0][0]
        assert "T1" in call_arg
        assert "max_attempts" in call_arg


# ===========================================================================
# Test 6 — state.json correctness and file-locking
# ===========================================================================


class TestStateJsonCorrectness:
    def test_no_lost_updates_with_concurrent_task_completions(self, tmp_path):
        """Concurrent completions produce no lost state.json entries (locking verified)."""
        N = 5
        tasks = [_task(f"T{i}") for i in range(1, N + 1)]
        runner, _, state_file, _ = _setup(tmp_path, tasks)

        with patch("ralph.run.run_noninteractive", return_value=_ok()), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop_async([], 10)

        state = json.loads(state_file.read_text())
        assert len(state) == N, f"Expected {N} state entries, got {len(state)}"
        ids = {e["task_id"] for e in state}
        assert ids == {f"T{i}" for i in range(1, N + 1)}

    def test_state_json_written_via_locked_json_rw(self, tmp_path):
        """state.json updates go through ``locked_json_rw`` (not bare file writes)."""
        import ralph.locks as locks_mod

        tasks = [_task("T1")]
        runner, _, state_file, _ = _setup(tmp_path, tasks)

        original_rw = locks_mod.locked_json_rw
        rw_paths: list[str] = []

        @contextmanager
        def spy_rw(path: str):
            rw_paths.append(path)
            with original_rw(path) as data:
                yield data

        with patch("ralph.run.run_noninteractive", return_value=_ok()), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(locks_mod, "locked_json_rw", spy_rw), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop_async([], 10)

        state_path = str(state_file)
        state_rw_calls = [p for p in rw_paths if p == state_path]
        assert len(state_rw_calls) >= 1, (
            "locked_json_rw was not called for state.json — writes may not be atomic"
        )

    def test_state_json_initialised_if_absent(self, tmp_path):
        """If state.json does not exist at startup, the loop creates it automatically."""
        tasks = [_task("T1")]
        runner, _, state_file, _ = _setup(tmp_path, tasks)
        state_file.unlink()  # simulate missing state.json

        with patch("ralph.run.run_noninteractive", return_value=_ok()), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop_async([], 10)

        assert state_file.exists(), "state.json was not created by run_execute_loop_async"
        state = json.loads(state_file.read_text())
        assert len(state) == 1
        assert state[0]["task_id"] == "T1"
        assert state[0]["status"] == "completed"

    def test_obstacles_json_initialised_if_absent(self, tmp_path):
        """If obstacles.json does not exist at startup, the loop creates it."""
        tasks = [_task("T1")]
        runner, _, _, obstacles_file = _setup(tmp_path, tasks)
        obstacles_file.unlink()  # simulate missing obstacles.json

        with patch("ralph.run.run_noninteractive", return_value=_ok()), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop_async([], 10)

        assert obstacles_file.exists(), "obstacles.json was not created by run_execute_loop_async"

    def test_state_json_remains_valid_json_after_concurrent_writes(self, tmp_path):
        """state.json is valid JSON after all concurrent task completions."""
        tasks = [_task(f"T{i}") for i in range(1, 4)]
        runner, _, state_file, _ = _setup(tmp_path, tasks)

        with patch("ralph.run.run_noninteractive", return_value=_ok()), \
             patch("ralph.run.time.sleep", side_effect=lambda *a: _real_sleep(0.001)), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop_async([], 10)

        content = state_file.read_text()
        parsed = json.loads(content)  # must not raise
        assert isinstance(parsed, list)
