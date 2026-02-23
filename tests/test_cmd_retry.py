"""Unit tests for ralph/cli.py — cmd_retry / ralph retry subcommand."""

import argparse
from unittest.mock import MagicMock, mock_open, patch

import pytest

from ralph.cli import cmd_retry


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REQUIRES_ATTENTION_VALIDATION_MD = "# Rating: requires attention\n\nMinor issues found."
_PASSED_VALIDATION_MD = "# Rating: passed\n\nAll tasks completed."
_FAILED_VALIDATION_MD = "# Rating: failed\n\nSome tasks were not completed."
_NO_RATING_VALIDATION_MD = "No rating here at all."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(
    project_name: str = "my-project",
    force: bool = False,
    verbose: str | None = None,
) -> argparse.Namespace:
    """Build a minimal Namespace for cmd_retry."""
    return argparse.Namespace(project_name=project_name, force=force, verbose=verbose)


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
    dirty_tree: bool = False,
    branch_exists: bool = True,
    checkout_ok: bool = True,
):
    """Return a side_effect for subprocess.run covering the retry git commands."""

    def _run(cmd, **kwargs):
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return _ok(stdout="M some/file.py\n") if dirty_tree else _ok(stdout="")
        if cmd[:3] == ["git", "branch", "--list"]:
            return _ok(stdout=project_name + "\n") if branch_exists else _ok(stdout="")
        if cmd[:2] == ["git", "checkout"]:
            return _ok() if checkout_ok else _fail(stderr="checkout failed")
        return _ok()

    return _run


# ===========================================================================
# Failcase — project does not exist
# ===========================================================================


class TestCmdRetryProjectNotExist:
    def test_aborts_with_exit_code_1_when_project_missing(self):
        """cmd_retry exits with code 1 when the project does not exist."""
        with patch("ralph.cli._assert_project_exists", side_effect=SystemExit(1)):
            with pytest.raises(SystemExit) as exc_info:
                cmd_retry(_make_args())

        assert exc_info.value.code == 1

    def test_no_further_checks_when_project_missing(self):
        """No subprocess or os.path.exists calls are made when the project does not exist."""
        with patch("ralph.cli._assert_project_exists", side_effect=SystemExit(1)), \
             patch("ralph.cli.subprocess.run") as mock_sub, \
             patch("ralph.cli.os.path.exists") as mock_exists:
            with pytest.raises(SystemExit):
                cmd_retry(_make_args())

        mock_sub.assert_not_called()
        mock_exists.assert_not_called()

    def test_runner_not_called_when_project_missing(self):
        """Runner is not invoked when the project does not exist."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists", side_effect=SystemExit(1)), \
             patch("ralph.cli.Runner", return_value=mock_runner):
            with pytest.raises(SystemExit):
                cmd_retry(_make_args())

        mock_runner.run_comment.assert_not_called()


# ===========================================================================
# Failcase — validation.md missing
# ===========================================================================


class TestCmdRetryValidationMissing:
    def test_aborts_when_validation_md_missing(self, capsys):
        """cmd_retry exits with code 1 when validation.md does not exist."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=False), \
             pytest.raises(SystemExit) as exc_info:
            cmd_retry(_make_args())

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "validation.md" in captured.err

    def test_runner_not_called_when_validation_missing(self):
        """Runner is not invoked when validation.md is missing."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=False), \
             patch("ralph.cli.Runner", return_value=mock_runner):
            with pytest.raises(SystemExit):
                cmd_retry(_make_args())

        mock_runner.run_comment.assert_not_called()

    def test_no_subprocess_when_validation_missing(self):
        """No subprocess calls are made when validation.md does not exist."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=False), \
             patch("ralph.cli.subprocess.run") as mock_sub:
            with pytest.raises(SystemExit):
                cmd_retry(_make_args())

        mock_sub.assert_not_called()


# ===========================================================================
# Rating: "requires attention" — proceeds without --force
# ===========================================================================


class TestCmdRetryRatingRequiresAttention:
    def test_proceeds_without_force(self):
        """cmd_retry proceeds when rating is 'requires attention' without --force."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_REQUIRES_ATTENTION_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.parse_retry_md", return_value="mock prompt"), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.get_verbose", return_value=False):
            cmd_retry(_make_args(force=False))  # Should not raise

        mock_runner.run_comment.assert_called_once_with("mock prompt")

    def test_runner_called_when_requires_attention(self):
        """Runner.run_comment is called when rating is 'requires attention'."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_REQUIRES_ATTENTION_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.parse_retry_md", return_value="retry prompt"), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.get_verbose", return_value=False):
            cmd_retry(_make_args())

        mock_runner.run_comment.assert_called_once()


# ===========================================================================
# Rating: "passed" — force required
# ===========================================================================


class TestCmdRetryRatingPassed_NoForce:
    def test_aborts_when_rating_is_passed_without_force(self, capsys):
        """cmd_retry exits with code 1 when rating is 'passed' and --force is not provided."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)), \
             pytest.raises(SystemExit) as exc_info:
            cmd_retry(_make_args(force=False))

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "[ralph]" in captured.err

    def test_runner_not_called_when_passed_no_force(self):
        """Runner is not invoked when rating is 'passed' and --force is not set."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)), \
             patch("ralph.cli.Runner", return_value=mock_runner):
            with pytest.raises(SystemExit):
                cmd_retry(_make_args(force=False))

        mock_runner.run_comment.assert_not_called()

    def test_no_subprocess_when_passed_no_force(self):
        """No subprocess calls are made when rating is 'passed' and --force is not set."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run") as mock_sub:
            with pytest.raises(SystemExit):
                cmd_retry(_make_args(force=False))

        mock_sub.assert_not_called()


class TestCmdRetryRatingPassed_Force:
    def test_proceeds_when_rating_is_passed_with_force(self):
        """cmd_retry proceeds when rating is 'passed' and --force is True."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.parse_retry_md", return_value="mock prompt"), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.get_verbose", return_value=False):
            cmd_retry(_make_args(force=True))  # Should not raise

        mock_runner.run_comment.assert_called_once_with("mock prompt")

    def test_runner_called_when_passed_with_force(self):
        """Runner is called when rating is 'passed' and --force is True."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.parse_retry_md", return_value="mock prompt"), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.get_verbose", return_value=False):
            cmd_retry(_make_args(force=True))

        mock_runner.run_comment.assert_called_once()


# ===========================================================================
# Rating: "failed" — force required
# ===========================================================================


class TestCmdRetryRatingFailed_NoForce:
    def test_aborts_when_rating_is_failed_without_force(self, capsys):
        """cmd_retry exits with code 1 when rating is 'failed' and --force is not provided."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             pytest.raises(SystemExit) as exc_info:
            cmd_retry(_make_args(force=False))

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "[ralph]" in captured.err

    def test_runner_not_called_when_failed_no_force(self):
        """Runner is not invoked when rating is 'failed' and --force is not set."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.Runner", return_value=mock_runner):
            with pytest.raises(SystemExit):
                cmd_retry(_make_args(force=False))

        mock_runner.run_comment.assert_not_called()

    def test_no_subprocess_when_failed_no_force(self):
        """No subprocess calls are made when rating is 'failed' and --force is not set."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run") as mock_sub:
            with pytest.raises(SystemExit):
                cmd_retry(_make_args(force=False))

        mock_sub.assert_not_called()

    def test_message_mentions_undo_when_failed_no_force(self, capsys):
        """Error message mentions 'undo' when rating is 'failed' and --force not provided."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)):
            with pytest.raises(SystemExit):
                cmd_retry(_make_args(force=False))

        captured = capsys.readouterr()
        assert "undo" in captured.err.lower()


class TestCmdRetryRatingFailed_Force:
    def test_proceeds_when_rating_is_failed_with_force(self):
        """cmd_retry proceeds when rating is 'failed' and --force is True."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.parse_retry_md", return_value="mock prompt"), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.get_verbose", return_value=False):
            cmd_retry(_make_args(force=True))  # Should not raise

        mock_runner.run_comment.assert_called_once_with("mock prompt")

    def test_runner_called_when_failed_with_force(self):
        """Runner is called when rating is 'failed' and --force is True."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.parse_retry_md", return_value="mock prompt"), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.get_verbose", return_value=False):
            cmd_retry(_make_args(force=True))

        mock_runner.run_comment.assert_called_once()


# ===========================================================================
# No rating found
# ===========================================================================


class TestCmdRetryRatingNotFound_NoForce:
    def test_aborts_when_no_rating_found_without_force(self, capsys):
        """cmd_retry exits with code 1 when no rating found and --force is not provided."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_NO_RATING_VALIDATION_MD)), \
             pytest.raises(SystemExit) as exc_info:
            cmd_retry(_make_args(force=False))

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "[ralph]" in captured.err

    def test_runner_not_called_when_no_rating_no_force(self):
        """Runner is not invoked when no rating found and --force is not set."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_NO_RATING_VALIDATION_MD)), \
             patch("ralph.cli.Runner", return_value=mock_runner):
            with pytest.raises(SystemExit):
                cmd_retry(_make_args(force=False))

        mock_runner.run_comment.assert_not_called()

    def test_no_subprocess_when_no_rating_no_force(self):
        """No subprocess calls made when no rating found and --force is not set."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_NO_RATING_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run") as mock_sub:
            with pytest.raises(SystemExit):
                cmd_retry(_make_args(force=False))

        mock_sub.assert_not_called()


class TestCmdRetryRatingNotFound_Force:
    def test_proceeds_when_no_rating_with_force(self):
        """cmd_retry proceeds when no rating found and --force is True."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_NO_RATING_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.parse_retry_md", return_value="mock prompt"), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.get_verbose", return_value=False):
            cmd_retry(_make_args(force=True))  # Should not raise

        mock_runner.run_comment.assert_called_once_with("mock prompt")

    def test_runner_called_when_no_rating_with_force(self):
        """Runner is called when no rating found and --force is True."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_NO_RATING_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.parse_retry_md", return_value="mock prompt"), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.get_verbose", return_value=False):
            cmd_retry(_make_args(force=True))

        mock_runner.run_comment.assert_called_once()


# ===========================================================================
# Dirty working tree
# ===========================================================================


class TestCmdRetryDirtyWorkingTree:
    def test_aborts_when_working_tree_is_dirty(self, capsys):
        """cmd_retry exits with code 1 when there are uncommitted changes."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_REQUIRES_ATTENTION_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run(dirty_tree=True)), \
             pytest.raises(SystemExit) as exc_info:
            cmd_retry(_make_args())

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "[ralph]" in captured.err

    def test_runner_not_called_when_dirty_tree(self):
        """Runner is not invoked when there are uncommitted changes."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_REQUIRES_ATTENTION_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run(dirty_tree=True)), \
             patch("ralph.cli.Runner", return_value=mock_runner):
            with pytest.raises(SystemExit):
                cmd_retry(_make_args())

        mock_runner.run_comment.assert_not_called()

    def test_branch_check_not_called_when_dirty_tree(self):
        """git branch --list is not called when working tree is dirty."""
        branch_checks = []

        def track_subprocess(cmd, **kwargs):
            if cmd[:3] == ["git", "branch", "--list"]:
                branch_checks.append(list(cmd))
            if cmd[:3] == ["git", "status", "--porcelain"]:
                return _ok(stdout="M file.py\n")
            return _ok(stdout="")

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_REQUIRES_ATTENTION_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=track_subprocess):
            with pytest.raises(SystemExit):
                cmd_retry(_make_args())

        assert branch_checks == []


# ===========================================================================
# Branch missing
# ===========================================================================


class TestCmdRetryBranchMissing:
    def test_aborts_when_project_branch_not_found(self, capsys):
        """cmd_retry exits with code 1 when the project branch does not exist."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_REQUIRES_ATTENTION_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run(branch_exists=False)), \
             pytest.raises(SystemExit) as exc_info:
            cmd_retry(_make_args())

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "my-project" in captured.err

    def test_runner_not_called_when_branch_missing(self):
        """Runner is not invoked when the project branch is missing."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_REQUIRES_ATTENTION_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run(branch_exists=False)), \
             patch("ralph.cli.Runner", return_value=mock_runner):
            with pytest.raises(SystemExit):
                cmd_retry(_make_args())

        mock_runner.run_comment.assert_not_called()

    def test_checkout_not_called_when_branch_missing(self):
        """git checkout is not called when the project branch is missing."""
        checkout_calls = []

        def track_subprocess(cmd, **kwargs):
            if cmd[:2] == ["git", "checkout"]:
                checkout_calls.append(list(cmd))
            if cmd[:3] == ["git", "branch", "--list"]:
                return _ok(stdout="")
            if cmd[:3] == ["git", "status", "--porcelain"]:
                return _ok(stdout="")
            return _ok()

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_REQUIRES_ATTENTION_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=track_subprocess):
            with pytest.raises(SystemExit):
                cmd_retry(_make_args())

        assert checkout_calls == []


# ===========================================================================
# Git checkout fails
# ===========================================================================


class TestCmdRetryCheckoutFails:
    def test_aborts_when_git_checkout_fails(self, capsys):
        """cmd_retry exits with code 1 when git checkout returns non-zero."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_REQUIRES_ATTENTION_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run(checkout_ok=False)), \
             pytest.raises(SystemExit) as exc_info:
            cmd_retry(_make_args())

        assert exc_info.value.code == 1

    def test_runner_not_called_when_checkout_fails(self):
        """Runner is not invoked when git checkout returns non-zero."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_REQUIRES_ATTENTION_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run(checkout_ok=False)), \
             patch("ralph.cli.Runner", return_value=mock_runner):
            with pytest.raises(SystemExit):
                cmd_retry(_make_args())

        mock_runner.run_comment.assert_not_called()


# ===========================================================================
# Happy path — full success
# ===========================================================================


class TestCmdRetryHappyPath:
    def test_git_status_porcelain_checked(self):
        """cmd_retry runs git status --porcelain to check for uncommitted changes."""
        status_calls = []
        mock_runner = MagicMock()

        def track_subprocess(cmd, **kwargs):
            if cmd[:3] == ["git", "status", "--porcelain"]:
                status_calls.append(list(cmd))
            return _make_subprocess_run()(cmd, **kwargs)

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_REQUIRES_ATTENTION_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=track_subprocess), \
             patch("ralph.cli.parse_retry_md", return_value="prompt"), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.get_verbose", return_value=False):
            cmd_retry(_make_args())

        assert ["git", "status", "--porcelain"] in status_calls

    def test_git_branch_list_checked(self):
        """cmd_retry checks that the project branch exists via git branch --list."""
        branch_checks = []
        mock_runner = MagicMock()

        def track_subprocess(cmd, **kwargs):
            if cmd[:3] == ["git", "branch", "--list"]:
                branch_checks.append(list(cmd))
            return _make_subprocess_run()(cmd, **kwargs)

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_REQUIRES_ATTENTION_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=track_subprocess), \
             patch("ralph.cli.parse_retry_md", return_value="prompt"), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.get_verbose", return_value=False):
            cmd_retry(_make_args())

        assert any(c[:3] == ["git", "branch", "--list"] for c in branch_checks)

    def test_git_checkout_project_branch_called(self):
        """cmd_retry checks out the project branch before spawning the agent."""
        checkout_calls = []
        mock_runner = MagicMock()

        def track_subprocess(cmd, **kwargs):
            if cmd[:2] == ["git", "checkout"]:
                checkout_calls.append(list(cmd))
            return _make_subprocess_run()(cmd, **kwargs)

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_REQUIRES_ATTENTION_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=track_subprocess), \
             patch("ralph.cli.parse_retry_md", return_value="prompt"), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.get_verbose", return_value=False):
            cmd_retry(_make_args())

        assert ["git", "checkout", "my-project"] in checkout_calls

    def test_parse_retry_md_called_with_project_name(self):
        """parse_retry_md is called with the project name."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_REQUIRES_ATTENTION_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.parse_retry_md", return_value="prompt") as mock_parse, \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.get_verbose", return_value=False):
            cmd_retry(_make_args(project_name="my-project"))

        mock_parse.assert_called_once_with("my-project")

    def test_runner_constructed_with_project_name(self):
        """Runner is instantiated with the correct project name."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_REQUIRES_ATTENTION_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run(project_name="proj-abc")), \
             patch("ralph.cli.parse_retry_md", return_value="prompt"), \
             patch("ralph.cli.Runner", return_value=mock_runner) as mock_runner_cls, \
             patch("ralph.cli.get_verbose", return_value=False):
            cmd_retry(_make_args(project_name="proj-abc"))

        assert mock_runner_cls.call_args[0][0] == "proj-abc"

    def test_runner_run_comment_called_with_rendered_prompt(self):
        """Runner.run_comment is called with the rendered retry.md prompt."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_REQUIRES_ATTENTION_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.parse_retry_md", return_value="rendered retry prompt") as mock_parse, \
             patch("ralph.cli.Runner", return_value=mock_runner) as mock_runner_cls, \
             patch("ralph.cli.get_verbose", return_value=False):
            cmd_retry(_make_args())

        mock_parse.assert_called_once_with("my-project")
        mock_runner_cls.assert_called_once()
        assert mock_runner_cls.call_args[0][0] == "my-project"
        mock_runner.run_comment.assert_called_once_with("rendered retry prompt")

    def test_assert_project_exists_called_with_project_name(self):
        """_assert_project_exists is called with the correct project name."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists") as mock_assert, \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=_REQUIRES_ATTENTION_VALIDATION_MD)), \
             patch("ralph.cli.subprocess.run", side_effect=_make_subprocess_run()), \
             patch("ralph.cli.parse_retry_md", return_value="prompt"), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.get_verbose", return_value=False):
            cmd_retry(_make_args(project_name="my-project"))

        mock_assert.assert_called_once_with("my-project")
