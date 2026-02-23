"""Unit tests for ralph/cli.py — cmd_undo / ralph undo subcommand."""

import argparse
import copy
import json
from unittest.mock import MagicMock, mock_open, patch

import pytest

from ralph.cli import cmd_undo


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FAILED_VALIDATION_MD = "# Rating: failed\n\nSome tasks were not completed."
_PASSED_VALIDATION_MD = "# Rating: passed\n\nAll tasks completed."
_ATTENTION_VALIDATION_MD = "# Rating: requires attention\n\nMinor issues found."
_NO_RATING_VALIDATION_MD = "No rating here at all."

_SAMPLE_TASKS_DATA = {
    "tasks": [
        {
            "id": "T1",
            "title": "First task",
            "description": "Do the first thing",
            "dependencies": [],
            "max_attempts": 3,
            "status": "completed",
            "attempts": 2,
            "blocked": False,
        },
        {
            "id": "T2",
            "title": "Second task",
            "description": "Do the second thing",
            "dependencies": ["T1"],
            "max_attempts": 3,
            "status": "in_progress",
            "attempts": 1,
            "blocked": True,
        },
    ]
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(project_name: str = "my-project", force: bool = False) -> argparse.Namespace:
    """Build a minimal Namespace for cmd_undo."""
    return argparse.Namespace(project_name=project_name, force=force)


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


def _make_subprocess_run(checkout_ok: bool = True, delete_ok: bool = True):
    """Return a side_effect for subprocess.run covering the undo git commands."""

    def _run(cmd, **kwargs):
        if cmd[:2] == ["git", "checkout"]:
            return _ok() if checkout_ok else _fail(stderr="checkout failed")
        if cmd[:3] == ["git", "branch", "-D"]:
            return _ok() if delete_ok else _fail(stderr="delete failed")
        return _ok()

    return _run


# ===========================================================================
# Failcase — project does not exist
# ===========================================================================


class TestCmdUndoProjectNotExist:
    def test_aborts_with_exit_code_1_when_project_missing(self):
        """cmd_undo exits with code 1 when the project does not exist."""
        with patch("ralph.cli._assert_project_exists", side_effect=SystemExit(1)):
            with pytest.raises(SystemExit) as exc_info:
                cmd_undo(_make_args())

        assert exc_info.value.code == 1

    def test_no_further_checks_when_project_missing(self):
        """No subprocess or os.path.exists calls are made when the project does not exist."""
        with patch("ralph.cli._assert_project_exists", side_effect=SystemExit(1)), \
             patch("ralph.cli.subprocess.run") as mock_sub, \
             patch("ralph.cli.os.path.exists") as mock_exists:
            with pytest.raises(SystemExit):
                cmd_undo(_make_args())

        mock_sub.assert_not_called()
        mock_exists.assert_not_called()


# ===========================================================================
# Failcase — validation.md missing
# ===========================================================================


class TestCmdUndoValidationMissing:
    def test_aborts_when_validation_md_missing(self, capsys):
        """cmd_undo exits with code 1 when validation.md does not exist."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=False), \
             pytest.raises(SystemExit) as exc_info:
            cmd_undo(_make_args())

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "validation.md" in captured.err

    def test_no_subprocess_when_validation_missing(self):
        """No subprocess calls are made when validation.md does not exist."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=False), \
             patch("ralph.cli.subprocess.run") as mock_sub:
            with pytest.raises(SystemExit):
                cmd_undo(_make_args())

        mock_sub.assert_not_called()


# ===========================================================================
# Rating: "failed" — proceeds without --force
# ===========================================================================


class TestCmdUndoRatingFailed:
    def test_proceeds_normally_with_failed_rating(self):
        """cmd_undo proceeds when validation rating is 'failed' without --force."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("builtins.input", return_value="y"), \
             patch("ralph.cli.json.load", return_value=copy.deepcopy(_SAMPLE_TASKS_DATA)), \
             patch("ralph.cli.json.dump"):
            cmd_undo(_make_args(force=False))  # Should not raise

    def test_git_checkout_called_with_base_branch(self):
        """cmd_undo calls git checkout <base_branch> before deletion."""
        checkout_calls = []

        def track_subprocess(cmd, **kwargs):
            if cmd[:2] == ["git", "checkout"]:
                checkout_calls.append(list(cmd))
            return _ok()

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=track_subprocess), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("builtins.input", return_value="y"), \
             patch("ralph.cli.json.load", return_value=copy.deepcopy(_SAMPLE_TASKS_DATA)), \
             patch("ralph.cli.json.dump"):
            cmd_undo(_make_args())

        assert ["git", "checkout", "main"] in checkout_calls

    def test_git_branch_delete_called(self):
        """cmd_undo calls git branch -D <project_name> after confirmation."""
        delete_calls = []

        def track_subprocess(cmd, **kwargs):
            if cmd[:3] == ["git", "branch", "-D"]:
                delete_calls.append(list(cmd))
            return _ok()

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=track_subprocess), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("builtins.input", return_value="y"), \
             patch("ralph.cli.json.load", return_value=copy.deepcopy(_SAMPLE_TASKS_DATA)), \
             patch("ralph.cli.json.dump"):
            cmd_undo(_make_args())

        assert ["git", "branch", "-D", "my-project"] in delete_calls

    def test_input_prompt_called_for_confirmation(self):
        """cmd_undo calls input() to prompt for y/n confirmation."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("builtins.input", return_value="y") as mock_input, \
             patch("ralph.cli.json.load", return_value=copy.deepcopy(_SAMPLE_TASKS_DATA)), \
             patch("ralph.cli.json.dump"):
            cmd_undo(_make_args())

        mock_input.assert_called_once()


# ===========================================================================
# Rating not "failed" (passed / requires attention) — force required
# ===========================================================================


class TestCmdUndoRatingNotFailed_NoForce:
    def test_aborts_when_rating_is_passed_without_force(self, capsys):
        """cmd_undo exits with code 1 when rating is 'passed' and --force is not provided."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)), \
             pytest.raises(SystemExit) as exc_info:
            cmd_undo(_make_args(force=False))

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "[ralph]" in captured.err

    def test_aborts_when_rating_is_requires_attention_without_force(self, capsys):
        """cmd_undo exits with code 1 when rating is 'requires attention' and --force not set."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_ATTENTION_VALIDATION_MD)), \
             pytest.raises(SystemExit) as exc_info:
            cmd_undo(_make_args(force=False))

        assert exc_info.value.code == 1

    def test_no_subprocess_when_non_failed_rating_no_force(self):
        """No subprocess calls are made when rating is not 'failed' and --force is not set."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run") as mock_sub:
            with pytest.raises(SystemExit):
                cmd_undo(_make_args(force=False))

        mock_sub.assert_not_called()


class TestCmdUndoRatingNotFailed_Force:
    def test_proceeds_when_rating_is_passed_with_force(self):
        """cmd_undo proceeds when rating is 'passed' and --force is True."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("builtins.input", return_value="y"), \
             patch("ralph.cli.json.load", return_value=copy.deepcopy(_SAMPLE_TASKS_DATA)), \
             patch("ralph.cli.json.dump"):
            cmd_undo(_make_args(force=True))  # Should not raise

    def test_proceeds_when_rating_is_requires_attention_with_force(self):
        """cmd_undo proceeds when rating is 'requires attention' and --force is True."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_ATTENTION_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("builtins.input", return_value="y"), \
             patch("ralph.cli.json.load", return_value=copy.deepcopy(_SAMPLE_TASKS_DATA)), \
             patch("ralph.cli.json.dump"):
            cmd_undo(_make_args(force=True))  # Should not raise


# ===========================================================================
# No rating found
# ===========================================================================


class TestCmdUndoRatingNotFound_NoForce:
    def test_aborts_when_no_rating_found_without_force(self, capsys):
        """cmd_undo exits with code 1 when no rating found and --force is not provided."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_NO_RATING_VALIDATION_MD)), \
             pytest.raises(SystemExit) as exc_info:
            cmd_undo(_make_args(force=False))

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "[ralph]" in captured.err

    def test_no_subprocess_when_no_rating_no_force(self):
        """No subprocess calls made when no rating found and --force is not set."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_NO_RATING_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run") as mock_sub:
            with pytest.raises(SystemExit):
                cmd_undo(_make_args(force=False))

        mock_sub.assert_not_called()


class TestCmdUndoRatingNotFound_Force:
    def test_proceeds_when_no_rating_with_force(self):
        """cmd_undo proceeds when no rating found and --force is True."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_NO_RATING_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("builtins.input", return_value="y"), \
             patch("ralph.cli.json.load", return_value=copy.deepcopy(_SAMPLE_TASKS_DATA)), \
             patch("ralph.cli.json.dump"):
            cmd_undo(_make_args(force=True))  # Should not raise


# ===========================================================================
# Base branch same as project branch
# ===========================================================================


class TestCmdUndoBaseBranchSameAsProject:
    def test_aborts_when_base_branch_equals_project_name(self, capsys):
        """cmd_undo exits with code 1 when base branch == project_name."""
        project_name = "my-project"
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.get_base", return_value=project_name), \
             patch("ralph.cli.set_base"), \
             pytest.raises(SystemExit) as exc_info:
            cmd_undo(_make_args(project_name=project_name))

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "[ralph]" in captured.err

    def test_no_git_commands_when_base_same_as_project(self):
        """No git checkout or git branch -D is called when base branch == project name."""
        project_name = "my-project"
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.get_base", return_value=project_name), \
             patch("ralph.cli.set_base"), \
             patch("ralph.cli.subprocess.run") as mock_sub:
            with pytest.raises(SystemExit):
                cmd_undo(_make_args(project_name=project_name))

        mock_sub.assert_not_called()


# ===========================================================================
# Base branch not set
# ===========================================================================


class TestCmdUndoBaseBranchNotSet:
    def test_set_base_called_with_main_when_base_is_empty(self):
        """When get_base() returns empty string, set_base('main') is called."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.get_base", return_value=""), \
             patch("ralph.cli.set_base") as mock_set_base, \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("builtins.input", return_value="y"), \
             patch("ralph.cli.json.load", return_value=copy.deepcopy(_SAMPLE_TASKS_DATA)), \
             patch("ralph.cli.json.dump"):
            cmd_undo(_make_args())

        mock_set_base.assert_called_once_with("main")

    def test_main_used_as_base_branch_when_unset(self):
        """'main' is used as the base branch when get_base() returns empty string."""
        checkout_calls = []

        def track_subprocess(cmd, **kwargs):
            if cmd[:2] == ["git", "checkout"]:
                checkout_calls.append(list(cmd))
            return _ok()

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.get_base", return_value=""), \
             patch("ralph.cli.set_base"), \
             patch("ralph.cli.subprocess.run", side_effect=track_subprocess), \
             patch("builtins.input", return_value="y"), \
             patch("ralph.cli.json.load", return_value=copy.deepcopy(_SAMPLE_TASKS_DATA)), \
             patch("ralph.cli.json.dump"):
            cmd_undo(_make_args())

        assert ["git", "checkout", "main"] in checkout_calls


# ===========================================================================
# Git checkout fails
# ===========================================================================


class TestCmdUndoGitCheckoutFails:
    def test_aborts_when_git_checkout_fails(self, capsys):
        """cmd_undo exits with code 1 when git checkout returns non-zero."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run(checkout_ok=False)), \
             pytest.raises(SystemExit) as exc_info:
            cmd_undo(_make_args())

        assert exc_info.value.code == 1

    def test_input_not_called_when_checkout_fails(self):
        """input() is not called when git checkout fails."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run(checkout_ok=False)), \
             patch("builtins.input") as mock_input:
            with pytest.raises(SystemExit):
                cmd_undo(_make_args())

        mock_input.assert_not_called()


# ===========================================================================
# User confirmation — 'n'
# ===========================================================================


class TestCmdUndoUserConfirmationNo:
    def test_aborts_when_user_answers_no(self):
        """cmd_undo exits when the user enters 'n' at the confirmation prompt."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("builtins.input", return_value="n"), \
             pytest.raises(SystemExit):
            cmd_undo(_make_args())

    def test_branch_not_deleted_when_user_answers_no(self):
        """git branch -D is not called when the user enters 'n'."""
        delete_calls = []

        def track_subprocess(cmd, **kwargs):
            if cmd[:3] == ["git", "branch", "-D"]:
                delete_calls.append(list(cmd))
            return _ok()

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("ralph.cli.subprocess.run", side_effect=track_subprocess), \
             patch("builtins.input", return_value="n"):
            with pytest.raises(SystemExit):
                cmd_undo(_make_args())

        assert delete_calls == []

    def test_no_file_writes_when_user_answers_no(self):
        """No json.dump calls are made when user declines confirmation."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("builtins.input", return_value="n"), \
             patch("ralph.cli.json.dump") as mock_dump:
            with pytest.raises(SystemExit):
                cmd_undo(_make_args())

        mock_dump.assert_not_called()


# ===========================================================================
# User confirmation — 'y'
# ===========================================================================


class TestCmdUndoUserConfirmationYes:
    def test_proceeds_when_user_answers_yes(self):
        """cmd_undo proceeds with branch deletion when user enters 'y'."""
        delete_calls = []

        def track_subprocess(cmd, **kwargs):
            if cmd[:3] == ["git", "branch", "-D"]:
                delete_calls.append(list(cmd))
            return _ok()

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("ralph.cli.subprocess.run", side_effect=track_subprocess), \
             patch("builtins.input", return_value="y"), \
             patch("ralph.cli.json.load", return_value=copy.deepcopy(_SAMPLE_TASKS_DATA)), \
             patch("ralph.cli.json.dump"):
            cmd_undo(_make_args())

        assert ["git", "branch", "-D", "my-project"] in delete_calls

    def test_yes_answer_case_insensitive(self):
        """'YES' is accepted as a confirmation answer."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("builtins.input", return_value="YES"), \
             patch("ralph.cli.json.load", return_value=copy.deepcopy(_SAMPLE_TASKS_DATA)), \
             patch("ralph.cli.json.dump"):
            cmd_undo(_make_args())  # Should not raise


# ===========================================================================
# Git branch -D fails
# ===========================================================================


class TestCmdUndoGitBranchDeleteFails:
    def test_aborts_when_branch_delete_fails(self, capsys):
        """cmd_undo exits with code 1 when git branch -D returns non-zero."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run(delete_ok=False)), \
             patch("builtins.input", return_value="y"), \
             pytest.raises(SystemExit) as exc_info:
            cmd_undo(_make_args())

        assert exc_info.value.code == 1

    def test_file_resets_not_performed_when_branch_delete_fails(self):
        """No json.dump calls are made when git branch -D fails."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run(delete_ok=False)), \
             patch("builtins.input", return_value="y"), \
             patch("ralph.cli.json.dump") as mock_dump:
            with pytest.raises(SystemExit):
                cmd_undo(_make_args())

        mock_dump.assert_not_called()


# ===========================================================================
# Missing JSON files — created with blank template
# ===========================================================================


class TestCmdUndoMissingJsonFiles:
    def test_tasks_json_created_when_missing(self):
        """tasks.json is created as blank ({}) when it does not exist; state.json and obstacles.json are still reset."""

        def exists_side_effect(path):
            if "tasks.json" in str(path):
                return False
            return True

        json_dump_calls = []

        def capture_dump(obj, f, **kwargs):
            json_dump_calls.append(obj)

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", side_effect=exists_side_effect), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("builtins.input", return_value="y"), \
             patch("ralph.cli.json.dump", side_effect=capture_dump):
            cmd_undo(_make_args())

        assert [] in json_dump_calls
        assert {"obstacles": []} in json_dump_calls
        assert {} in json_dump_calls


# ===========================================================================
# Happy path — full success
# ===========================================================================


class TestCmdUndoHappyPath:
    def test_state_json_written_as_empty_list(self):
        """On happy path, state.json is written as []."""
        json_dump_calls = []

        def capture_dump(obj, f, **kwargs):
            json_dump_calls.append(obj)

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("builtins.input", return_value="y"), \
             patch("ralph.cli.json.load", return_value=copy.deepcopy(_SAMPLE_TASKS_DATA)), \
             patch("ralph.cli.json.dump", side_effect=capture_dump):
            cmd_undo(_make_args())

        assert [] in json_dump_calls

    def test_obstacles_json_written_as_empty_obstacles(self):
        """On happy path, obstacles.json is written as {"obstacles": []}."""
        json_dump_calls = []

        def capture_dump(obj, f, **kwargs):
            json_dump_calls.append(obj)

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("builtins.input", return_value="y"), \
             patch("ralph.cli.json.load", return_value=copy.deepcopy(_SAMPLE_TASKS_DATA)), \
             patch("ralph.cli.json.dump", side_effect=capture_dump):
            cmd_undo(_make_args())

        assert {"obstacles": []} in json_dump_calls

    def test_tasks_json_reset_with_pending_status_zero_attempts_unblocked(self):
        """On happy path, all tasks have status='pending', attempts=0, blocked=False."""
        json_dump_calls = []

        def capture_dump(obj, f, **kwargs):
            json_dump_calls.append(obj)

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("builtins.input", return_value="y"), \
             patch("ralph.cli.json.load", return_value=copy.deepcopy(_SAMPLE_TASKS_DATA)), \
             patch("ralph.cli.json.dump", side_effect=capture_dump):
            cmd_undo(_make_args())

        tasks_writes = [c for c in json_dump_calls if isinstance(c, dict) and "tasks" in c]
        assert len(tasks_writes) == 1
        for task in tasks_writes[0]["tasks"]:
            assert task["status"] == "pending"
            assert task["attempts"] == 0
            assert task["blocked"] is False

    def test_tasks_json_preserves_non_reset_fields(self):
        """On happy path, title, description, dependencies, id, max_attempts are preserved."""
        json_dump_calls = []

        def capture_dump(obj, f, **kwargs):
            json_dump_calls.append(obj)

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("builtins.input", return_value="y"), \
             patch("ralph.cli.json.load", return_value=copy.deepcopy(_SAMPLE_TASKS_DATA)), \
             patch("ralph.cli.json.dump", side_effect=capture_dump):
            cmd_undo(_make_args())

        tasks_writes = [c for c in json_dump_calls if isinstance(c, dict) and "tasks" in c]
        task_list = tasks_writes[0]["tasks"]
        assert task_list[0]["id"] == "T1"
        assert task_list[0]["title"] == "First task"
        assert task_list[0]["description"] == "Do the first thing"
        assert task_list[0]["dependencies"] == []
        assert task_list[0]["max_attempts"] == 3
        assert task_list[1]["id"] == "T2"
        assert task_list[1]["title"] == "Second task"
        assert task_list[1]["dependencies"] == ["T1"]

    def test_assert_project_exists_called_with_project_name(self):
        """_assert_project_exists is called with the correct project name."""
        with patch("ralph.cli._assert_project_exists") as mock_assert, \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.set_base"), \
             patch("builtins.input", return_value="y"), \
             patch("ralph.cli.json.load", return_value=copy.deepcopy(_SAMPLE_TASKS_DATA)), \
             patch("ralph.cli.json.dump"):
            cmd_undo(_make_args(project_name="my-project"))

        mock_assert.assert_called_once_with("my-project")
