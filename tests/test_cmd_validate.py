"""Unit tests for ralph/cli.py — cmd_validate / ralph validate subcommand."""

import argparse
import json
from unittest.mock import MagicMock, mock_open, patch

import pytest

from ralph.cli import cmd_validate


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ALL_COMPLETED_TASKS = json.dumps({
    "tasks": [
        {"id": "T1", "title": "Task 1", "status": "completed"},
        {"id": "T2", "title": "Task 2", "status": "completed"},
    ]
})

_SOME_INCOMPLETE_TASKS = json.dumps({
    "tasks": [
        {"id": "T1", "title": "Task 1", "status": "completed"},
        {"id": "T2", "title": "Task 2", "status": "pending"},
    ]
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(project_name: str = "my-project", verbose: str | None = None) -> argparse.Namespace:
    """Build a minimal Namespace for cmd_validate."""
    return argparse.Namespace(project_name=project_name, verbose=verbose)


def _ok(stdout: str = "", stderr: str = "") -> MagicMock:
    """Return a mock subprocess.CompletedProcess with returncode=0."""
    m = MagicMock()
    m.returncode = 0
    m.stdout = stdout
    m.stderr = stderr
    return m


def _fail(stdout: str = "", stderr: str = "error") -> MagicMock:
    """Return a mock subprocess.CompletedProcess with returncode=1."""
    m = MagicMock()
    m.returncode = 1
    m.stdout = stdout
    m.stderr = stderr
    return m


def _make_subprocess_run(
    project_name: str = "my-project",
    branch_exists: bool = True,
    checkout_ok: bool = True,
):
    """Return a side_effect for subprocess.run covering the validate path."""

    def _run(cmd, **kwargs):
        if cmd[:3] == ["git", "branch", "--list"]:
            return _ok(stdout=project_name + "\n") if branch_exists else _ok(stdout="")
        if cmd[:2] == ["git", "checkout"]:
            return _ok() if checkout_ok else _fail(stderr="checkout failed")
        return _ok()

    return _run


# ===========================================================================
# Failcase — project does not exist
# ===========================================================================


class TestCmdValidateProjectNotExist:
    def test_aborts_with_exit_code_1_when_project_missing(self):
        """cmd_validate exits with code 1 when the project does not exist."""
        with patch("ralph.commands._assert_project_exists", side_effect=SystemExit(1)):
            with pytest.raises(SystemExit) as exc_info:
                cmd_validate(_make_args())

        assert exc_info.value.code == 1

    def test_no_further_checks_when_project_missing(self):
        """No subprocess or os.path.exists calls are made when the project does not exist."""
        with patch("ralph.commands._assert_project_exists", side_effect=SystemExit(1)), \
             patch("ralph.commands.subprocess.run") as mock_sub, \
             patch("ralph.commands.os.path.exists") as mock_exists:
            with pytest.raises(SystemExit):
                cmd_validate(_make_args())

        mock_sub.assert_not_called()
        mock_exists.assert_not_called()

    def test_runner_not_called_when_project_missing(self):
        """Runner is not invoked when the project does not exist."""
        mock_runner = MagicMock()
        with patch("ralph.commands._assert_project_exists", side_effect=SystemExit(1)), \
             patch("ralph.commands.Runner", return_value=mock_runner):
            with pytest.raises(SystemExit):
                cmd_validate(_make_args())

        mock_runner.run_prompt.assert_not_called()


# ===========================================================================
# Failcase — pr-description.md missing
# ===========================================================================


class TestCmdValidatePrDescriptionMissing:
    def test_aborts_when_pr_description_missing(self, capsys):
        """cmd_validate exits with code 1 when pr-description.md does not exist."""
        args = _make_args()

        def mock_exists(path):
            return "pr-description.md" not in path

        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.os.path.exists", side_effect=mock_exists), \
             pytest.raises(SystemExit) as exc_info:
            cmd_validate(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "pr-description.md" in captured.err

    def test_runner_not_called_when_pr_description_missing(self):
        """Runner is not invoked when pr-description.md is missing."""
        mock_runner = MagicMock()

        def mock_exists(path):
            return "pr-description.md" not in path

        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.os.path.exists", side_effect=mock_exists), \
             patch("ralph.commands.Runner", return_value=mock_runner):
            with pytest.raises(SystemExit):
                cmd_validate(_make_args())

        mock_runner.run_prompt.assert_not_called()


# ===========================================================================
# Failcase — tasks not all completed
# ===========================================================================


class TestCmdValidateIncompleteTask:
    def test_aborts_when_tasks_not_all_completed(self, capsys):
        """cmd_validate exits with code 1 when any task is not completed."""
        args = _make_args()

        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_SOME_INCOMPLETE_TASKS)), \
             pytest.raises(SystemExit) as exc_info:
            cmd_validate(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "tasks" in captured.err.lower()

    def test_runner_not_called_when_tasks_incomplete(self):
        """Runner is not invoked when tasks are not all completed."""
        mock_runner = MagicMock()

        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_SOME_INCOMPLETE_TASKS)), \
             patch("ralph.commands.Runner", return_value=mock_runner):
            with pytest.raises(SystemExit):
                cmd_validate(_make_args())

        mock_runner.run_prompt.assert_not_called()

    def test_no_subprocess_call_when_tasks_incomplete(self):
        """No subprocess calls are made when tasks are not all completed."""
        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_SOME_INCOMPLETE_TASKS)), \
             patch("ralph.commands.subprocess.run") as mock_sub:
            with pytest.raises(SystemExit):
                cmd_validate(_make_args())

        mock_sub.assert_not_called()


# ===========================================================================
# Failcase — project git branch does not exist
# ===========================================================================


class TestCmdValidateBranchNotExist:
    def test_aborts_when_project_branch_not_found(self, capsys):
        """cmd_validate exits with code 1 when the project branch does not exist."""
        args = _make_args()

        def mock_exists(path):
            return "validation.md" not in path

        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.os.path.exists", side_effect=mock_exists), \
             patch("builtins.open", mock_open(read_data=_ALL_COMPLETED_TASKS)), \
             patch("ralph.commands.subprocess.run", side_effect=_make_subprocess_run(branch_exists=False)), \
             pytest.raises(SystemExit) as exc_info:
            cmd_validate(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "my-project" in captured.err

    def test_runner_not_called_when_branch_missing(self):
        """Runner is not invoked when the project branch is missing."""
        mock_runner = MagicMock()

        def mock_exists(path):
            return "validation.md" not in path

        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.os.path.exists", side_effect=mock_exists), \
             patch("builtins.open", mock_open(read_data=_ALL_COMPLETED_TASKS)), \
             patch("ralph.commands.subprocess.run", side_effect=_make_subprocess_run(branch_exists=False)), \
             patch("ralph.commands.Runner", return_value=mock_runner):
            with pytest.raises(SystemExit):
                cmd_validate(_make_args())

        mock_runner.run_prompt.assert_not_called()


# ===========================================================================
# validation.md overwrite prompt — user answers 'n'
# ===========================================================================


class TestCmdValidateOverwriteNo:
    def test_aborts_when_user_declines_overwrite(self):
        """cmd_validate exits when validation.md exists and user answers 'n'."""
        project_name = "my-project"
        args = _make_args(project_name=project_name)

        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_ALL_COMPLETED_TASKS)), \
             patch("ralph.commands.subprocess.run", side_effect=_make_subprocess_run(project_name=project_name)), \
             patch("builtins.input", return_value="n"), \
             pytest.raises(SystemExit) as exc_info:
            cmd_validate(args)

        assert exc_info.value.code == 1

    def test_runner_not_called_when_user_declines_overwrite(self):
        """Runner is not invoked when the user says 'n' to overwriting validation.md."""
        mock_runner = MagicMock()
        project_name = "my-project"

        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_ALL_COMPLETED_TASKS)), \
             patch("ralph.commands.subprocess.run", side_effect=_make_subprocess_run(project_name=project_name)), \
             patch("builtins.input", return_value="n"), \
             patch("ralph.commands.Runner", return_value=mock_runner):
            with pytest.raises(SystemExit):
                cmd_validate(_make_args(project_name=project_name))

        mock_runner.run_prompt.assert_not_called()

    def test_input_loop_retries_until_valid_answer(self):
        """Input loop continues prompting until a valid y/n answer is provided."""
        project_name = "my-project"
        args = _make_args(project_name=project_name)
        inputs = iter(["", "maybe", "no"])

        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_ALL_COMPLETED_TASKS)), \
             patch("ralph.commands.subprocess.run", side_effect=_make_subprocess_run(project_name=project_name)), \
             patch("builtins.input", side_effect=lambda _: next(inputs)), \
             pytest.raises(SystemExit) as exc_info:
            cmd_validate(args)

        assert exc_info.value.code == 1


# ===========================================================================
# validation.md overwrite prompt — user answers 'y'
# ===========================================================================


class TestCmdValidateOverwriteYes:
    def test_proceeds_when_user_confirms_overwrite(self):
        """cmd_validate continues and calls Runner when user answers 'y' to overwrite."""
        project_name = "my-project"
        args = _make_args(project_name=project_name)
        mock_runner = MagicMock()

        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_ALL_COMPLETED_TASKS)), \
             patch("ralph.commands.subprocess.run", side_effect=_make_subprocess_run(project_name=project_name)), \
             patch("builtins.input", return_value="y"), \
             patch("ralph.commands.parse_validate_md", return_value="mock prompt"), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_verbose", return_value=False):
            cmd_validate(args)

        mock_runner.run_prompt.assert_called_once_with("mock prompt", "validate")

    def test_yes_answer_case_insensitive(self):
        """'YES' is accepted the same as 'y' to confirm overwrite."""
        project_name = "my-project"
        args = _make_args(project_name=project_name)
        mock_runner = MagicMock()

        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_ALL_COMPLETED_TASKS)), \
             patch("ralph.commands.subprocess.run", side_effect=_make_subprocess_run(project_name=project_name)), \
             patch("builtins.input", return_value="YES"), \
             patch("ralph.commands.parse_validate_md", return_value="mock prompt"), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_verbose", return_value=False):
            cmd_validate(args)

        mock_runner.run_prompt.assert_called_once()


# ===========================================================================
# Happy path — no existing validation.md
# ===========================================================================


class TestCmdValidateHappyPath:
    def test_runs_without_prompt_when_no_existing_validation(self):
        """No input() prompt is issued when validation.md does not already exist."""
        project_name = "my-project"
        args = _make_args(project_name=project_name)
        mock_runner = MagicMock()

        def mock_exists(path):
            return "validation.md" not in path

        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.os.path.exists", side_effect=mock_exists), \
             patch("builtins.open", mock_open(read_data=_ALL_COMPLETED_TASKS)), \
             patch("ralph.commands.subprocess.run", side_effect=_make_subprocess_run(project_name=project_name)), \
             patch("builtins.input") as mock_input, \
             patch("ralph.commands.parse_validate_md", return_value="prompt"), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_verbose", return_value=False):
            cmd_validate(args)

        mock_input.assert_not_called()
        mock_runner.run_prompt.assert_called_once_with("prompt", "validate")

    def test_runner_called_with_rendered_validate_prompt(self):
        """Runner.run_comment is called with the rendered validate.md prompt."""
        project_name = "my-project"
        args = _make_args(project_name=project_name)
        mock_runner = MagicMock()

        def mock_exists(path):
            return "validation.md" not in path

        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.os.path.exists", side_effect=mock_exists), \
             patch("builtins.open", mock_open(read_data=_ALL_COMPLETED_TASKS)), \
             patch("ralph.commands.subprocess.run", side_effect=_make_subprocess_run(project_name=project_name)), \
             patch("ralph.commands.parse_validate_md", return_value="rendered validate prompt") as mock_parse, \
             patch("ralph.commands.Runner", return_value=mock_runner) as mock_runner_cls, \
             patch("ralph.commands.get_verbose", return_value=False):
            cmd_validate(args)

        mock_parse.assert_called_once_with(project_name)
        mock_runner_cls.assert_called_once()
        assert mock_runner_cls.call_args[0][0] == project_name
        mock_runner.run_prompt.assert_called_once_with("rendered validate prompt", "validate")

    def test_git_checkout_project_branch_is_called(self):
        """cmd_validate checks out the project branch before running the agent."""
        project_name = "my-project"
        args = _make_args(project_name=project_name)
        mock_runner = MagicMock()
        checkout_calls = []

        def track_subprocess(cmd, **kwargs):
            if cmd[:2] == ["git", "checkout"]:
                checkout_calls.append(list(cmd))
            return _make_subprocess_run(project_name=project_name)(cmd, **kwargs)

        def mock_exists(path):
            return "validation.md" not in path

        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.os.path.exists", side_effect=mock_exists), \
             patch("builtins.open", mock_open(read_data=_ALL_COMPLETED_TASKS)), \
             patch("ralph.commands.subprocess.run", side_effect=track_subprocess), \
             patch("ralph.commands.parse_validate_md", return_value="prompt"), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_verbose", return_value=False):
            cmd_validate(args)

        assert ["git", "checkout", project_name] in checkout_calls

    def test_assert_project_exists_called_with_project_name(self):
        """cmd_validate calls _assert_project_exists with the correct project name."""
        project_name = "my-project"
        args = _make_args(project_name=project_name)
        mock_runner = MagicMock()

        def mock_exists(path):
            return "validation.md" not in path

        with patch("ralph.commands._assert_project_exists") as mock_assert, \
             patch("ralph.commands.os.path.exists", side_effect=mock_exists), \
             patch("builtins.open", mock_open(read_data=_ALL_COMPLETED_TASKS)), \
             patch("ralph.commands.subprocess.run", side_effect=_make_subprocess_run(project_name=project_name)), \
             patch("ralph.commands.parse_validate_md", return_value="prompt"), \
             patch("ralph.commands.Runner", return_value=mock_runner), \
             patch("ralph.commands.get_verbose", return_value=False):
            cmd_validate(args)

        mock_assert.assert_called_once_with(project_name)

    def test_runner_constructed_with_project_name(self):
        """Runner is instantiated with the correct project name."""
        project_name = "proj-abc"
        args = _make_args(project_name=project_name)
        mock_runner = MagicMock()

        def mock_exists(path):
            return "validation.md" not in path

        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.os.path.exists", side_effect=mock_exists), \
             patch("builtins.open", mock_open(read_data=_ALL_COMPLETED_TASKS)), \
             patch("ralph.commands.subprocess.run", side_effect=_make_subprocess_run(project_name=project_name)), \
             patch("ralph.commands.parse_validate_md", return_value="prompt"), \
             patch("ralph.commands.Runner", return_value=mock_runner) as mock_runner_cls, \
             patch("ralph.commands.get_verbose", return_value=False):
            cmd_validate(args)

        assert mock_runner_cls.call_args[0][0] == project_name
