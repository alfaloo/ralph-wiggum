"""Unit tests for ralph/dag.py — DAG dependency parser."""

import pytest

from ralph.dag import all_tasks_complete, any_task_exceeded_max_attempts, get_ready_tasks


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _task(
    id: str,
    status: str = "pending",
    dependencies: list | None = None,
    attempts: int = 0,
    max_attempts: int = 3,
    blocked: bool = False,
) -> dict:
    """Build a minimal task dict for use in tests."""
    return {
        "id": id,
        "title": f"Task {id}",
        "status": status,
        "dependencies": dependencies if dependencies is not None else [],
        "attempts": attempts,
        "max_attempts": max_attempts,
        "blocked": blocked,
    }


# ===========================================================================
# get_ready_tasks
# ===========================================================================


class TestGetReadyTasks:
    def test_task_with_all_deps_completed_is_returned(self):
        tasks = [
            _task("T1", status="completed"),
            _task("T2", status="completed"),
            _task("T3", status="pending", dependencies=["T1", "T2"]),
        ]
        ready = get_ready_tasks(tasks)
        assert len(ready) == 1
        assert ready[0]["id"] == "T3"

    def test_task_with_pending_dependency_is_excluded(self):
        tasks = [
            _task("T1", status="pending"),
            _task("T2", status="pending", dependencies=["T1"]),
        ]
        ready = get_ready_tasks(tasks)
        # T1 is pending but has no deps → should be ready; T2 depends on T1 (pending) → excluded
        assert any(t["id"] == "T1" for t in ready)
        assert not any(t["id"] == "T2" for t in ready)

    def test_task_with_in_progress_dependency_is_excluded(self):
        tasks = [
            _task("T1", status="in_progress"),
            _task("T2", status="pending", dependencies=["T1"]),
        ]
        ready = get_ready_tasks(tasks)
        assert ready == []

    def test_blocked_task_is_excluded(self):
        tasks = [
            _task("T1", status="pending", blocked=True),
        ]
        ready = get_ready_tasks(tasks)
        assert ready == []

    def test_task_at_max_attempts_is_excluded(self):
        tasks = [
            _task("T1", status="pending", attempts=3, max_attempts=3),
        ]
        ready = get_ready_tasks(tasks)
        assert ready == []

    def test_task_exceeding_max_attempts_is_excluded(self):
        tasks = [
            _task("T1", status="pending", attempts=5, max_attempts=3),
        ]
        ready = get_ready_tasks(tasks)
        assert ready == []

    def test_task_with_empty_dependencies_and_pending_status_is_included(self):
        tasks = [
            _task("T1", status="pending", dependencies=[]),
        ]
        ready = get_ready_tasks(tasks)
        assert len(ready) == 1
        assert ready[0]["id"] == "T1"

    def test_completed_task_is_not_returned(self):
        tasks = [
            _task("T1", status="completed"),
        ]
        ready = get_ready_tasks(tasks)
        assert ready == []

    def test_in_progress_task_is_not_returned(self):
        tasks = [
            _task("T1", status="in_progress"),
        ]
        ready = get_ready_tasks(tasks)
        assert ready == []

    def test_multiple_ready_tasks_all_returned(self):
        tasks = [
            _task("T1", status="pending"),
            _task("T2", status="pending"),
            _task("T3", status="completed"),
        ]
        ready = get_ready_tasks(tasks)
        ids = {t["id"] for t in ready}
        assert ids == {"T1", "T2"}

    def test_partial_deps_not_satisfied(self):
        """Only one of two dependencies is completed — task must not be returned."""
        tasks = [
            _task("T1", status="completed"),
            _task("T2", status="pending"),
            _task("T3", status="pending", dependencies=["T1", "T2"]),
        ]
        ready = get_ready_tasks(tasks)
        ids = {t["id"] for t in ready}
        # T2 is ready (no deps of its own); T3 is NOT ready (T2 not completed)
        assert "T2" in ids
        assert "T3" not in ids

    def test_task_below_max_attempts_is_included(self):
        tasks = [
            _task("T1", status="pending", attempts=2, max_attempts=3),
        ]
        ready = get_ready_tasks(tasks)
        assert len(ready) == 1

    def test_empty_task_list_returns_empty(self):
        assert get_ready_tasks([]) == []


# ===========================================================================
# all_tasks_complete
# ===========================================================================


class TestAllTasksComplete:
    def test_all_completed_returns_true(self):
        tasks = [
            _task("T1", status="completed"),
            _task("T2", status="completed"),
        ]
        assert all_tasks_complete(tasks) is True

    def test_mixed_statuses_returns_false(self):
        tasks = [
            _task("T1", status="completed"),
            _task("T2", status="pending"),
        ]
        assert all_tasks_complete(tasks) is False

    def test_single_pending_returns_false(self):
        tasks = [_task("T1", status="pending")]
        assert all_tasks_complete(tasks) is False

    def test_single_in_progress_returns_false(self):
        tasks = [_task("T1", status="in_progress")]
        assert all_tasks_complete(tasks) is False

    def test_empty_list_returns_true(self):
        assert all_tasks_complete([]) is True

    def test_one_incomplete_in_many_returns_false(self):
        tasks = [
            _task("T1", status="completed"),
            _task("T2", status="completed"),
            _task("T3", status="in_progress"),
            _task("T4", status="completed"),
        ]
        assert all_tasks_complete(tasks) is False


# ===========================================================================
# any_task_exceeded_max_attempts
# ===========================================================================


class TestAnyTaskExceededMaxAttempts:
    def test_task_at_max_attempts_not_completed_returns_true_and_task(self):
        t = _task("T1", status="pending", attempts=3, max_attempts=3)
        found, task = any_task_exceeded_max_attempts([t])
        assert found is True
        assert task is t

    def test_task_exceeding_max_attempts_returns_true_and_task(self):
        t = _task("T1", status="in_progress", attempts=5, max_attempts=3)
        found, task = any_task_exceeded_max_attempts([t])
        assert found is True
        assert task["id"] == "T1"

    def test_all_tasks_below_max_attempts_returns_false_none(self):
        tasks = [
            _task("T1", status="pending", attempts=1, max_attempts=3),
            _task("T2", status="pending", attempts=2, max_attempts=3),
        ]
        found, task = any_task_exceeded_max_attempts(tasks)
        assert found is False
        assert task is None

    def test_task_at_max_attempts_but_completed_is_not_flagged(self):
        tasks = [
            _task("T1", status="completed", attempts=3, max_attempts=3),
        ]
        found, task = any_task_exceeded_max_attempts(tasks)
        assert found is False
        assert task is None

    def test_mixed_returns_first_exceeded_task(self):
        t1 = _task("T1", status="pending", attempts=1, max_attempts=3)
        t2 = _task("T2", status="pending", attempts=3, max_attempts=3)
        t3 = _task("T3", status="pending", attempts=3, max_attempts=3)
        tasks = [t1, t2, t3]
        found, task = any_task_exceeded_max_attempts(tasks)
        assert found is True
        assert task["id"] == "T2"

    def test_empty_list_returns_false_none(self):
        found, task = any_task_exceeded_max_attempts([])
        assert found is False
        assert task is None

    def test_completed_task_exceeding_attempts_ignored_others_ok(self):
        """All non-completed tasks are below max_attempts — should return (False, None)."""
        tasks = [
            _task("T1", status="completed", attempts=5, max_attempts=3),
            _task("T2", status="pending", attempts=1, max_attempts=3),
        ]
        found, task = any_task_exceeded_max_attempts(tasks)
        assert found is False
        assert task is None
