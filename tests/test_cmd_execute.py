"""Unit tests for ralph/cli.py — cmd_execute / ralph execute subcommand."""

import argparse
import json
from unittest.mock import MagicMock, mock_open, patch

import pytest

from ralph.cli import cmd_execute
from ralph.run import Runner

# Minimal valid tasks.json content used to satisfy the tasks-exist guard in cmd_execute.
_TASKS_JSON = '{"tasks": [{"id": "T1"}]}'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _args(
    project_name: str = "my-project",
    verbose: str | None = None,
    asynchronous: str | None = None,
    single: str | None = None,
    limit: int | None = None,
    base: str | None = None,
    resume: bool = False,
    id: str | None = None,
) -> argparse.Namespace:
    """Build a minimal argparse.Namespace for cmd_execute."""
    return argparse.Namespace(
        project_name=project_name,
        verbose=verbose,
        asynchronous=asynchronous,
        single=single,
        limit=limit,
        base=base,
        resume=resume,
        id=id,
    )


def _ok(stdout: str = "") -> MagicMock:
    """Return a mock subprocess.CompletedProcess with returncode=0."""
    m = MagicMock()
    m.returncode = 0
    m.stdout = stdout
    m.stderr = ""
    return m


def _fail(stderr: str = "error") -> MagicMock:
    """Return a mock subprocess.CompletedProcess with returncode=1."""
    m = MagicMock()
    m.returncode = 1
    m.stdout = ""
    m.stderr = stderr
    return m


# ===========================================================================
# Core functionality
# ===========================================================================


class TestCmdExecuteCore:
    """Happy-path: project exists, project branch absent, base branch present."""

    @pytest.fixture(autouse=True)
    def _mock_tasks_json(self):
        """Satisfy the tasks.json existence/non-empty guard without touching the filesystem."""
        with patch("ralph.commands.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_TASKS_JSON)):
            yield

    def test_assert_project_exists_is_called(self):
        """cmd_execute calls _assert_project_exists with the correct project name."""
        mock_runner = MagicMock()
        with patch("ralph.commands.assert_project_exists") as mock_assert, \
             patch("ralph.commands.subprocess.run", side_effect=[
                 _ok(),   # git branch --list my-project (empty → branch absent)
                 _ok(),   # git checkout main
                 _ok(),   # git checkout -b my-project
             ]), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False):
            cmd_execute(_args())

        mock_assert.assert_called_once_with("my-project")

    def test_run_execute_loop_is_called(self):
        """cmd_execute calls Runner.run_execute_loop after setting up the branch."""
        mock_runner = MagicMock()
        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False):
            cmd_execute(_args())

        mock_runner.run_execute_loop.assert_called_once()

    def test_run_execute_loop_receives_limit_from_settings(self):
        """cmd_execute passes the settings limit to run_execute_loop when --limit is absent."""
        mock_runner = MagicMock()
        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=7), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False):
            cmd_execute(_args(limit=None))

        pos_args, _ = mock_runner.run_execute_loop.call_args
        assert pos_args[0] == 7

    def test_limit_from_args_overrides_settings(self):
        """When --limit N is passed, it takes precedence over the persisted setting."""
        mock_runner = MagicMock()
        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=999), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False):
            cmd_execute(_args(limit=4))

        pos_args, _ = mock_runner.run_execute_loop.call_args
        assert pos_args[0] == 4

    def test_project_branch_created_via_git_checkout_b(self):
        """cmd_execute creates the project branch via 'git checkout -b <project>'."""
        mock_runner = MagicMock()
        subprocess_calls = []

        def capture_subprocess(cmd, **kwargs):
            subprocess_calls.append(cmd)
            return _ok()

        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=capture_subprocess), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False):
            cmd_execute(_args(project_name="my-project"))

        assert ["git", "checkout", "-b", "my-project"] in subprocess_calls

    def test_base_branch_checked_out_before_project_branch_created(self):
        """cmd_execute checks out the base branch before creating the project branch."""
        mock_runner = MagicMock()
        checkout_calls = []

        def capture_subprocess(cmd, **kwargs):
            if cmd[:2] == ["git", "checkout"]:
                checkout_calls.append(cmd)
            return _ok()

        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=capture_subprocess), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False):
            cmd_execute(_args(project_name="my-project"))

        assert len(checkout_calls) == 2
        assert checkout_calls[0] == ["git", "checkout", "main"]
        assert checkout_calls[1] == ["git", "checkout", "-b", "my-project"]

    def test_runner_constructed_with_project_name(self):
        """Runner is instantiated with the correct project name."""
        mock_runner = MagicMock()
        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.commands.Runner", return_value=mock_runner) as mock_runner_cls, \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False):
            cmd_execute(_args(project_name="proj-123"))

        assert mock_runner_cls.call_args[0][0] == "proj-123"

    def test_run_execute_loop_receives_limit_as_first_positional_arg(self):
        """run_execute_loop receives the limit as its first positional argument."""
        mock_runner = MagicMock()
        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=3), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False):
            cmd_execute(_args())

        pos_args, _ = mock_runner.run_execute_loop.call_args
        assert pos_args[0] == 3


# ===========================================================================
# Failcase — project does not exist
# ===========================================================================


class TestCmdExecuteProjectNotExist:
    def test_aborts_with_exit_code_1_when_project_missing(self):
        """cmd_execute exits with code 1 when _assert_project_exists raises SystemExit(1)."""
        with patch("ralph.commands.assert_project_exists", side_effect=SystemExit(1)):
            with pytest.raises(SystemExit) as exc_info:
                cmd_execute(_args())
        assert exc_info.value.code == 1

    def test_no_git_calls_when_project_missing(self):
        """No subprocess calls are made when the project does not exist."""
        with patch("ralph.commands.assert_project_exists", side_effect=SystemExit(1)), \
             patch("ralph.commands.subprocess.run") as mock_sub:
            with pytest.raises(SystemExit):
                cmd_execute(_args())
        mock_sub.assert_not_called()

    def test_run_execute_loop_not_called_when_project_missing(self):
        """Runner.run_execute_loop is not called when the project is missing."""
        mock_runner = MagicMock()
        with patch("ralph.commands.assert_project_exists", side_effect=SystemExit(1)), \
             patch("ralph.commands.Runner", return_value=mock_runner):
            with pytest.raises(SystemExit):
                cmd_execute(_args())
        mock_runner.run_execute_loop.assert_not_called()


# ===========================================================================
# Failcase — project branch already exists (without --resume)
# ===========================================================================


class TestCmdExecuteBranchAlreadyExists:
    def test_aborts_when_project_branch_already_exists(self):
        """cmd_execute exits when the project branch exists and --resume is not passed."""
        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", return_value=_ok(stdout="my-project\n")), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False), \
             patch("ralph.commands.get_limit", return_value=1):
            with pytest.raises(SystemExit) as exc_info:
                cmd_execute(_args(project_name="my-project", resume=False))
        assert exc_info.value.code == 1

    def test_run_execute_loop_not_called_when_branch_exists(self):
        """run_execute_loop is not called when the project branch already exists."""
        mock_runner = MagicMock()
        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", return_value=_ok(stdout="my-project\n")), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False), \
             patch("ralph.commands.get_limit", return_value=1):
            with pytest.raises(SystemExit):
                cmd_execute(_args(project_name="my-project", resume=False))
        mock_runner.run_execute_loop.assert_not_called()


# ===========================================================================
# Failcase — base branch does not exist
# ===========================================================================


class TestCmdExecuteBaseBranchNotExist:
    @pytest.fixture(autouse=True)
    def _mock_tasks_json(self):
        """Satisfy the tasks.json guard for tests that reach that code path."""
        with patch("ralph.commands.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_TASKS_JSON)):
            yield

    def test_aborts_when_specified_base_branch_not_found(self):
        """cmd_execute exits when --base specifies a branch that does not exist in the repo."""
        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", return_value=_ok(stdout="")), \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False):
            with pytest.raises(SystemExit) as exc_info:
                cmd_execute(_args(base="no-such-branch"))
        assert exc_info.value.code == 1

    def test_run_execute_loop_not_called_when_base_missing(self):
        """run_execute_loop is not called when the specified base branch does not exist."""
        mock_runner = MagicMock()
        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", return_value=_ok(stdout="")), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False):
            with pytest.raises(SystemExit):
                cmd_execute(_args(base="no-such-branch"))
        mock_runner.run_execute_loop.assert_not_called()

    def test_base_from_args_is_validated_not_settings(self):
        """_validate_branch_exists is called with the --base value, not the settings value."""
        validated = []

        def capture_subprocess(cmd, **kwargs):
            if cmd[:3] == ["git", "branch", "--list"]:
                validated.append(cmd[3])
                # Return non-empty so _validate_branch_exists passes, empty so project branch absent
                return _ok(stdout=cmd[3] + "\n") if cmd[3] == "feature-branch" else _ok(stdout="")
            return _ok()

        mock_runner = MagicMock()
        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=capture_subprocess), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False):
            cmd_execute(_args(base="feature-branch"))

        # The first branch --list check should be for "feature-branch" (from _validate_branch_exists)
        assert validated[0] == "feature-branch"


# ===========================================================================
# Flag: --resume
# ===========================================================================


class TestCmdExecuteResumeFlag:
    @pytest.fixture(autouse=True)
    def _mock_tasks_json(self):
        """Satisfy the tasks.json guard for tests that reach that code path."""
        with patch("ralph.commands.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_TASKS_JSON)):
            yield

    def test_resume_checks_out_existing_branch(self):
        """With --resume, cmd_execute checks out the existing project branch directly."""
        mock_runner = MagicMock()
        checkout_calls = []

        def track_subproc(cmd, **kwargs):
            if cmd[:2] == ["git", "checkout"]:
                checkout_calls.append(cmd)
            if cmd[:3] == ["git", "branch", "--list"]:
                return _ok(stdout="my-project\n")
            return _ok()

        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=track_subproc), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False):
            cmd_execute(_args(project_name="my-project", resume=True))

        assert checkout_calls == [["git", "checkout", "my-project"]]

    def test_resume_does_not_create_new_branch(self):
        """With --resume, cmd_execute never calls 'git checkout -b'."""
        mock_runner = MagicMock()
        subprocess_calls = []

        def track_subproc(cmd, **kwargs):
            subprocess_calls.append(cmd)
            if cmd[:3] == ["git", "branch", "--list"]:
                return _ok(stdout="my-project\n")
            return _ok()

        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=track_subproc), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False):
            cmd_execute(_args(project_name="my-project", resume=True))

        create_branch_calls = [c for c in subprocess_calls if c[:3] == ["git", "checkout", "-b"]]
        assert create_branch_calls == []

    def test_resume_aborts_when_project_branch_not_found(self):
        """With --resume, cmd_execute exits when the project branch does not exist."""
        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", return_value=_ok(stdout="")), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False), \
             patch("ralph.commands.get_limit", return_value=1):
            with pytest.raises(SystemExit) as exc_info:
                cmd_execute(_args(project_name="my-project", resume=True))
        assert exc_info.value.code == 1

    def test_resume_still_calls_run_execute_loop(self):
        """With --resume, Runner.run_execute_loop is still invoked after checkout."""
        mock_runner = MagicMock()

        def track_subproc(cmd, **kwargs):
            if cmd[:3] == ["git", "branch", "--list"]:
                return _ok(stdout="my-project\n")
            return _ok()

        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=track_subproc), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False):
            cmd_execute(_args(project_name="my-project", resume=True))

        mock_runner.run_execute_loop.assert_called_once()

    def test_resume_does_not_checkout_base_branch(self):
        """With --resume, cmd_execute does not check out the base branch first."""
        mock_runner = MagicMock()
        checkout_calls = []

        def track_subproc(cmd, **kwargs):
            if cmd[:2] == ["git", "checkout"]:
                checkout_calls.append(cmd)
            if cmd[:3] == ["git", "branch", "--list"]:
                return _ok(stdout="my-project\n")
            return _ok()

        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=track_subproc), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False):
            cmd_execute(_args(project_name="my-project", resume=True))

        base_checkouts = [c for c in checkout_calls if c == ["git", "checkout", "main"]]
        assert base_checkouts == []


# ===========================================================================
# Flag: --asynchronous true
# ===========================================================================


class TestCmdExecuteAsynchronousFlag:
    @pytest.fixture(autouse=True)
    def _mock_tasks_json(self):
        """Satisfy the tasks.json guard for tests that reach that code path."""
        with patch("ralph.commands.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_TASKS_JSON)):
            yield

    def test_asynchronous_true_forwarded_to_run_execute_loop(self):
        """When --asynchronous true is passed, run_execute_loop receives asynchronous=True."""
        mock_runner = MagicMock()
        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False):
            cmd_execute(_args(asynchronous="true"))

        _, kw = mock_runner.run_execute_loop.call_args
        assert kw["asynchronous"] is True

    def test_asynchronous_false_forwarded_to_run_execute_loop(self):
        """When --asynchronous false is passed, run_execute_loop receives asynchronous=False."""
        mock_runner = MagicMock()
        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=True):
            cmd_execute(_args(asynchronous="false"))

        _, kw = mock_runner.run_execute_loop.call_args
        assert kw["asynchronous"] is False

    def test_asynchronous_defaults_to_settings_when_not_passed(self):
        """When --asynchronous is absent, the value from settings.json is forwarded."""
        mock_runner = MagicMock()
        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=True):
            cmd_execute(_args(asynchronous=None))

        _, kw = mock_runner.run_execute_loop.call_args
        assert kw["asynchronous"] is True


# ===========================================================================
# Runner._reset_incomplete_tasks — resume reset behaviour
# ===========================================================================


class TestResetIncompleteTasks:
    """Tests for Runner._reset_incomplete_tasks() and its integration with --resume."""

    def _make_runner(self, tmp_path, tasks: list[dict]):
        """Create a Runner whose _tasks_path points at a temp tasks.json."""
        tasks_path = tmp_path / "tasks.json"
        tasks_path.write_text(json.dumps({"tasks": tasks}))
        runner = Runner("test-project")
        runner._tasks_path = str(tasks_path)
        return runner, tasks_path

    def test_in_progress_task_reset_to_pending(self, tmp_path):
        """in_progress task is reset to status=pending, attempts=0, blocked=False."""
        tasks = [{"id": "T1", "status": "in_progress", "attempts": 2, "blocked": True}]
        runner, tasks_path = self._make_runner(tmp_path, tasks)
        runner._reset_incomplete_tasks()
        result = json.loads(tasks_path.read_text())
        task = result["tasks"][0]
        assert task["status"] == "pending"
        assert task["attempts"] == 0
        assert task["blocked"] is False

    def test_pending_task_attempts_and_blocked_reset(self, tmp_path):
        """pending task gets attempts=0 and blocked=False even if already pending."""
        tasks = [{"id": "T1", "status": "pending", "attempts": 1, "blocked": False}]
        runner, tasks_path = self._make_runner(tmp_path, tasks)
        runner._reset_incomplete_tasks()
        result = json.loads(tasks_path.read_text())
        task = result["tasks"][0]
        assert task["status"] == "pending"
        assert task["attempts"] == 0
        assert task["blocked"] is False

    def test_blocked_task_reset_to_pending(self, tmp_path):
        """blocked task is reset to status=pending, attempts=0, blocked=False."""
        tasks = [{"id": "T1", "status": "blocked", "attempts": 3, "blocked": True}]
        runner, tasks_path = self._make_runner(tmp_path, tasks)
        runner._reset_incomplete_tasks()
        result = json.loads(tasks_path.read_text())
        task = result["tasks"][0]
        assert task["status"] == "pending"
        assert task["attempts"] == 0
        assert task["blocked"] is False

    def test_completed_task_is_unchanged(self, tmp_path):
        """completed task is not modified at all."""
        tasks = [
            {"id": "T1", "status": "completed", "attempts": 2, "blocked": False},
            {"id": "T2", "status": "in_progress", "attempts": 1, "blocked": True},
        ]
        runner, tasks_path = self._make_runner(tmp_path, tasks)
        runner._reset_incomplete_tasks()
        result = json.loads(tasks_path.read_text())
        completed = next(t for t in result["tasks"] if t["id"] == "T1")
        assert completed["status"] == "completed"
        assert completed["attempts"] == 2

    def test_multiple_non_completed_all_reset(self, tmp_path):
        """All non-completed tasks across different statuses are reset."""
        tasks = [
            {"id": "T1", "status": "in_progress", "attempts": 3, "blocked": True},
            {"id": "T2", "status": "blocked", "attempts": 2, "blocked": True},
            {"id": "T3", "status": "pending", "attempts": 1, "blocked": False},
        ]
        runner, tasks_path = self._make_runner(tmp_path, tasks)
        runner._reset_incomplete_tasks()
        result = json.loads(tasks_path.read_text())
        for task in result["tasks"]:
            assert task["status"] == "pending"
            assert task["attempts"] == 0
            assert task["blocked"] is False

    def test_no_console_output_during_reset(self, tmp_path, capsys):
        """_reset_incomplete_tasks prints nothing to stdout or stderr."""
        tasks = [{"id": "T1", "status": "in_progress", "attempts": 2, "blocked": True}]
        runner, _ = self._make_runner(tmp_path, tasks)
        runner._reset_incomplete_tasks()
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_missing_tasks_file_does_not_crash(self, tmp_path):
        """_reset_incomplete_tasks returns silently when tasks.json does not exist."""
        runner = Runner("test-project")
        runner._tasks_path = str(tmp_path / "nonexistent_tasks.json")
        runner._reset_incomplete_tasks()  # must not raise

    def test_run_execute_loop_calls_reset_when_resume_true(self, tmp_path):
        """run_execute_loop triggers _reset_incomplete_tasks when resume=True."""
        runner = Runner("test-project")
        runner._tasks_path = str(tmp_path / "tasks.json")
        runner.ralph_dir = str(tmp_path)

        with patch.object(runner, "_reset_incomplete_tasks") as mock_reset, \
             patch.object(runner, "_all_tasks_complete", return_value=True), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop(1, resume=True)

        mock_reset.assert_called_once()

    def test_run_execute_loop_no_reset_when_resume_false(self, tmp_path):
        """run_execute_loop does NOT trigger _reset_incomplete_tasks when resume=False."""
        runner = Runner("test-project")
        runner._tasks_path = str(tmp_path / "tasks.json")
        runner.ralph_dir = str(tmp_path)
        (tmp_path / "tasks.json").write_text(
            json.dumps({"tasks": [{"id": "T1", "status": "completed"}]})
        )

        with patch.object(runner, "_reset_incomplete_tasks") as mock_reset, \
             patch.object(runner, "_all_tasks_complete", return_value=True), \
             patch.object(runner, "_run_summarise"):
            runner.run_execute_loop(1, resume=False)

        mock_reset.assert_not_called()


# ===========================================================================
# Flag: --single true
# ===========================================================================


class TestCmdExecuteSingleFlag:
    @pytest.fixture(autouse=True)
    def _mock_tasks_json(self):
        """Satisfy the tasks.json guard for tests that reach that code path."""
        with patch("ralph.commands.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_TASKS_JSON)):
            yield

    def test_single_true_forwarded_to_run_execute_loop(self):
        """When --single true is passed, run_execute_loop receives single=True."""
        mock_runner = MagicMock()
        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False), \
             patch("ralph.commands.get_single", return_value=False):
            cmd_execute(_args(single="true"))

        _, kw = mock_runner.run_execute_loop.call_args
        assert kw["single"] is True

    def test_single_false_forwarded_to_run_execute_loop(self):
        """When --single false is passed, run_execute_loop receives single=False."""
        mock_runner = MagicMock()
        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False), \
             patch("ralph.commands.get_single", return_value=True):
            cmd_execute(_args(single="false"))

        _, kw = mock_runner.run_execute_loop.call_args
        assert kw["single"] is False

    def test_single_defaults_from_settings(self):
        """When --single is omitted, the value from get_single() is forwarded."""
        mock_runner = MagicMock()
        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False), \
             patch("ralph.commands.get_single", return_value=True):
            cmd_execute(_args(single=None))

        _, kw = mock_runner.run_execute_loop.call_args
        assert kw["single"] is True

    def test_single_and_async_mutual_exclusivity(self):
        """Passing both --single true and --asynchronous true causes sys.exit(1)."""
        mock_runner = MagicMock()
        with patch("ralph.commands.assert_project_exists"), \
             patch("ralph.commands.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_limit", return_value=1), \
             patch("ralph.commands.get_base", return_value="main"), \
             patch("ralph.commands.get_verbose", return_value=False), \
             patch("ralph.commands.get_asynchronous", return_value=False), \
             patch("ralph.commands.get_single", return_value=False):
            with pytest.raises(SystemExit) as exc_info:
                cmd_execute(_args(single="true", asynchronous="true"))

        assert exc_info.value.code == 1
