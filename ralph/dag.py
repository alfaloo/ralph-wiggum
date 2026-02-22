"""DAG dependency parser for ralph task orchestration."""


def get_ready_tasks(tasks: list[dict]) -> list[dict]:
    """Return all tasks that are ready to be executed.

    A task is ready if:
    - status == "pending"
    - blocked == False
    - attempts < max_attempts
    - every task ID in dependencies has status == "completed"
    """
    completed_ids = {t["id"] for t in tasks if t["status"] == "completed"}
    ready = []
    for task in tasks:
        if task["status"] != "pending":
            continue
        if task.get("blocked", False):
            continue
        if task.get("attempts", 0) >= task.get("max_attempts", 3):
            continue
        if all(dep in completed_ids for dep in task.get("dependencies", [])):
            ready.append(task)
    return ready


def all_tasks_complete(tasks: list[dict]) -> bool:
    """Return True if every task has status == "completed"."""
    return all(t["status"] == "completed" for t in tasks)


def any_task_exceeded_max_attempts(tasks: list[dict]) -> tuple[bool, dict | None]:
    """Return (True, task) for the first task that exceeded max_attempts and is not completed.

    Returns (False, None) if no such task exists.
    """
    for task in tasks:
        if task["status"] != "completed" and task.get("attempts", 0) >= task.get("max_attempts", 3):
            return (True, task)
    return (False, None)
