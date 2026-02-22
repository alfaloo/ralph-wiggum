"""Unit tests for ralph/cli.py — cmd_execute / ralph execute subcommand."""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from ralph.cli import cmd_execute


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _args(
    project_name: str = "my-project",
    verbose: str | None = None,
    asynchronous: str | None = None,
    limit: int | None = None,
    base: str | None = None,
    resume: bool = False,
) -> argparse.Namespace:
    """Build a minimal argparse.Namespace for cmd_execute."""
    return argparse.Namespace(
        project_name=project_name,
        verbose=verbose,
        asynchronous=asynchronous,
        limit=limit,
        base=base,
        resume=resume,
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

    def test_assert_project_exists_is_called(self):
        """cmd_execute calls _assert_project_exists with the correct project name."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists") as mock_assert, \
             patch("ralph.cli.subprocess.run", side_effect=[
                 _ok(),   # git branch --list my-project (empty → branch absent)
                 _ok(),   # git checkout main
                 _ok(),   # git checkout -b my-project
             ]), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.parse_execute_md", return_value="prompt"), \
             patch("ralph.cli.get_limit", return_value=1), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False):
            cmd_execute(_args())

        mock_assert.assert_called_once_with("my-project")

    def test_run_execute_loop_is_called(self):
        """cmd_execute calls Runner.run_execute_loop after setting up the branch."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.parse_execute_md", return_value="prompt"), \
             patch("ralph.cli.get_limit", return_value=1), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False):
            cmd_execute(_args())

        mock_runner.run_execute_loop.assert_called_once()

    def test_run_execute_loop_receives_limit_from_settings(self):
        """cmd_execute passes the settings limit to run_execute_loop when --limit is absent."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.parse_execute_md", return_value="prompt"), \
             patch("ralph.cli.get_limit", return_value=7), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False):
            cmd_execute(_args(limit=None))

        pos_args, _ = mock_runner.run_execute_loop.call_args
        assert pos_args[1] == 7

    def test_limit_from_args_overrides_settings(self):
        """When --limit N is passed, it takes precedence over the persisted setting."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.parse_execute_md", return_value="prompt"), \
             patch("ralph.cli.get_limit", return_value=999), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False):
            cmd_execute(_args(limit=4))

        pos_args, _ = mock_runner.run_execute_loop.call_args
        assert pos_args[1] == 4

    def test_project_branch_created_via_git_checkout_b(self):
        """cmd_execute creates the project branch via 'git checkout -b <project>'."""
        mock_runner = MagicMock()
        subprocess_calls = []

        def capture_subprocess(cmd, **kwargs):
            subprocess_calls.append(cmd)
            return _ok()

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", side_effect=capture_subprocess), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.parse_execute_md", return_value="prompt"), \
             patch("ralph.cli.get_limit", return_value=1), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False):
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

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", side_effect=capture_subprocess), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.parse_execute_md", return_value="prompt"), \
             patch("ralph.cli.get_limit", return_value=1), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False):
            cmd_execute(_args(project_name="my-project"))

        assert len(checkout_calls) == 2
        assert checkout_calls[0] == ["git", "checkout", "main"]
        assert checkout_calls[1] == ["git", "checkout", "-b", "my-project"]

    def test_runner_constructed_with_project_name(self):
        """Runner is instantiated with the correct project name."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.cli.Runner", return_value=mock_runner) as mock_runner_cls, \
             patch("ralph.cli.parse_execute_md", return_value="prompt"), \
             patch("ralph.cli.get_limit", return_value=1), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False):
            cmd_execute(_args(project_name="proj-123"))

        assert mock_runner_cls.call_args[0][0] == "proj-123"

    def test_parse_execute_md_called_for_each_iteration(self):
        """parse_execute_md is called once per iteration up to the limit."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.parse_execute_md", return_value="prompt") as mock_parse, \
             patch("ralph.cli.get_limit", return_value=3), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False):
            cmd_execute(_args())

        assert mock_parse.call_count == 3


# ===========================================================================
# Failcase — project does not exist
# ===========================================================================


class TestCmdExecuteProjectNotExist:
    def test_aborts_with_exit_code_1_when_project_missing(self):
        """cmd_execute exits with code 1 when _assert_project_exists raises SystemExit(1)."""
        with patch("ralph.cli._assert_project_exists", side_effect=SystemExit(1)):
            with pytest.raises(SystemExit) as exc_info:
                cmd_execute(_args())
        assert exc_info.value.code == 1

    def test_no_git_calls_when_project_missing(self):
        """No subprocess calls are made when the project does not exist."""
        with patch("ralph.cli._assert_project_exists", side_effect=SystemExit(1)), \
             patch("ralph.cli.subprocess.run") as mock_sub:
            with pytest.raises(SystemExit):
                cmd_execute(_args())
        mock_sub.assert_not_called()

    def test_run_execute_loop_not_called_when_project_missing(self):
        """Runner.run_execute_loop is not called when the project is missing."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists", side_effect=SystemExit(1)), \
             patch("ralph.cli.Runner", return_value=mock_runner):
            with pytest.raises(SystemExit):
                cmd_execute(_args())
        mock_runner.run_execute_loop.assert_not_called()


# ===========================================================================
# Failcase — project branch already exists (without --resume)
# ===========================================================================


class TestCmdExecuteBranchAlreadyExists:
    def test_aborts_when_project_branch_already_exists(self):
        """cmd_execute exits when the project branch exists and --resume is not passed."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", return_value=_ok(stdout="my-project\n")), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False), \
             patch("ralph.cli.get_limit", return_value=1):
            with pytest.raises(SystemExit) as exc_info:
                cmd_execute(_args(project_name="my-project", resume=False))
        assert exc_info.value.code == 1

    def test_run_execute_loop_not_called_when_branch_exists(self):
        """run_execute_loop is not called when the project branch already exists."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", return_value=_ok(stdout="my-project\n")), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False), \
             patch("ralph.cli.get_limit", return_value=1):
            with pytest.raises(SystemExit):
                cmd_execute(_args(project_name="my-project", resume=False))
        mock_runner.run_execute_loop.assert_not_called()


# ===========================================================================
# Failcase — base branch does not exist
# ===========================================================================


class TestCmdExecuteBaseBranchNotExist:
    def test_aborts_when_specified_base_branch_not_found(self):
        """cmd_execute exits when --base specifies a branch that does not exist in the repo."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", return_value=_ok(stdout="")), \
             patch("ralph.cli.get_limit", return_value=1), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False):
            with pytest.raises(SystemExit) as exc_info:
                cmd_execute(_args(base="no-such-branch"))
        assert exc_info.value.code == 1

    def test_run_execute_loop_not_called_when_base_missing(self):
        """run_execute_loop is not called when the specified base branch does not exist."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", return_value=_ok(stdout="")), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.get_limit", return_value=1), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False):
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
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", side_effect=capture_subprocess), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.parse_execute_md", return_value="prompt"), \
             patch("ralph.cli.get_limit", return_value=1), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False):
            cmd_execute(_args(base="feature-branch"))

        # The first branch --list check should be for "feature-branch" (from _validate_branch_exists)
        assert validated[0] == "feature-branch"


# ===========================================================================
# Flag: --resume
# ===========================================================================


class TestCmdExecuteResumeFlag:
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

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", side_effect=track_subproc), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.parse_execute_md", return_value="prompt"), \
             patch("ralph.cli.get_limit", return_value=1), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False):
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

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", side_effect=track_subproc), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.parse_execute_md", return_value="prompt"), \
             patch("ralph.cli.get_limit", return_value=1), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False):
            cmd_execute(_args(project_name="my-project", resume=True))

        create_branch_calls = [c for c in subprocess_calls if c[:3] == ["git", "checkout", "-b"]]
        assert create_branch_calls == []

    def test_resume_aborts_when_project_branch_not_found(self):
        """With --resume, cmd_execute exits when the project branch does not exist."""
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", return_value=_ok(stdout="")), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False), \
             patch("ralph.cli.get_limit", return_value=1):
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

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", side_effect=track_subproc), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.parse_execute_md", return_value="prompt"), \
             patch("ralph.cli.get_limit", return_value=1), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False):
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

        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", side_effect=track_subproc), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.parse_execute_md", return_value="prompt"), \
             patch("ralph.cli.get_limit", return_value=1), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False):
            cmd_execute(_args(project_name="my-project", resume=True))

        base_checkouts = [c for c in checkout_calls if c == ["git", "checkout", "main"]]
        assert base_checkouts == []


# ===========================================================================
# Flag: --asynchronous true
# ===========================================================================


class TestCmdExecuteAsynchronousFlag:
    def test_asynchronous_true_forwarded_to_run_execute_loop(self):
        """When --asynchronous true is passed, run_execute_loop receives asynchronous=True."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.parse_execute_md", return_value="prompt"), \
             patch("ralph.cli.get_limit", return_value=1), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=False):
            cmd_execute(_args(asynchronous="true"))

        _, kw = mock_runner.run_execute_loop.call_args
        assert kw["asynchronous"] is True

    def test_asynchronous_false_forwarded_to_run_execute_loop(self):
        """When --asynchronous false is passed, run_execute_loop receives asynchronous=False."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.parse_execute_md", return_value="prompt"), \
             patch("ralph.cli.get_limit", return_value=1), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=True):
            cmd_execute(_args(asynchronous="false"))

        _, kw = mock_runner.run_execute_loop.call_args
        assert kw["asynchronous"] is False

    def test_asynchronous_defaults_to_settings_when_not_passed(self):
        """When --asynchronous is absent, the value from settings.json is forwarded."""
        mock_runner = MagicMock()
        with patch("ralph.cli._assert_project_exists"), \
             patch("ralph.cli.subprocess.run", side_effect=[_ok(), _ok(), _ok()]), \
             patch("ralph.cli.Runner", return_value=mock_runner), \
             patch("ralph.cli.parse_execute_md", return_value="prompt"), \
             patch("ralph.cli.get_limit", return_value=1), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_verbose", return_value=False), \
             patch("ralph.cli.get_asynchronous", return_value=True):
            cmd_execute(_args(asynchronous=None))

        _, kw = mock_runner.run_execute_loop.call_args
        assert kw["asynchronous"] is True
