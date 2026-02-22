"""Unit tests for ralph/cli.py — cmd_oneshot / ralph oneshot subcommand."""

import argparse
from unittest.mock import patch

import pytest

from ralph.cli import cmd_oneshot


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
    provider: str | None = None,
) -> argparse.Namespace:
    """Build a minimal argparse.Namespace for cmd_oneshot."""
    return argparse.Namespace(
        project_name=project_name,
        verbose=verbose,
        asynchronous=asynchronous,
        limit=limit,
        base=base,
        resume=resume,
        provider=provider,
    )


# ===========================================================================
# Core functionality
# ===========================================================================


class TestCmdOneshotCore:
    """Verify that cmd_oneshot delegates to cmd_enrich, cmd_execute, and cmd_pr in order."""

    def test_cmd_enrich_is_called(self):
        """cmd_oneshot calls cmd_enrich with the given args."""
        args = _args()
        with patch("ralph.cli.cmd_enrich") as mock_enrich, \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_pr"):
            cmd_oneshot(args)
        mock_enrich.assert_called_once_with(args)

    def test_cmd_execute_is_called(self):
        """cmd_oneshot calls cmd_execute with the given args."""
        args = _args()
        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute") as mock_execute, \
             patch("ralph.cli.cmd_pr"):
            cmd_oneshot(args)
        mock_execute.assert_called_once_with(args)

    def test_cmd_pr_is_called(self):
        """cmd_oneshot calls cmd_pr with the given args."""
        args = _args()
        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_pr") as mock_pr:
            cmd_oneshot(args)
        mock_pr.assert_called_once_with(args)

    def test_enrich_execute_pr_called_in_order(self):
        """cmd_oneshot calls cmd_enrich, cmd_execute, cmd_pr in that exact order."""
        args = _args()
        call_order = []

        with patch("ralph.cli.cmd_enrich", side_effect=lambda _: call_order.append("enrich")), \
             patch("ralph.cli.cmd_execute", side_effect=lambda _: call_order.append("execute")), \
             patch("ralph.cli.cmd_pr", side_effect=lambda _: call_order.append("pr")):
            cmd_oneshot(args)

        assert call_order == ["enrich", "execute", "pr"]

    def test_all_three_called_with_same_args_object(self):
        """All three internal calls receive the same args namespace."""
        args = _args(project_name="test-project")
        received = {}

        with patch("ralph.cli.cmd_enrich", side_effect=lambda a: received.update({"enrich": a})), \
             patch("ralph.cli.cmd_execute", side_effect=lambda a: received.update({"execute": a})), \
             patch("ralph.cli.cmd_pr", side_effect=lambda a: received.update({"pr": a})):
            cmd_oneshot(args)

        assert received["enrich"] is args
        assert received["execute"] is args
        assert received["pr"] is args


# ===========================================================================
# Flag propagation
# ===========================================================================


class TestCmdOneshotFlagPropagation:
    """Flags in the args namespace are visible to each internal cmd_ call."""

    def test_verbose_flag_propagated_to_all_sub_commands(self):
        """--verbose true is present in args when each sub-command is called."""
        args = _args(verbose="true")
        received = {}

        with patch("ralph.cli.cmd_enrich", side_effect=lambda a: received.update({"enrich_verbose": a.verbose})), \
             patch("ralph.cli.cmd_execute", side_effect=lambda a: received.update({"execute_verbose": a.verbose})), \
             patch("ralph.cli.cmd_pr", side_effect=lambda a: received.update({"pr_verbose": a.verbose})):
            cmd_oneshot(args)

        assert received["enrich_verbose"] == "true"
        assert received["execute_verbose"] == "true"
        assert received["pr_verbose"] == "true"

    def test_base_flag_propagated_to_cmd_execute(self):
        """--base <branch> is present in args when cmd_execute is called."""
        args = _args(base="feature-base")
        received = {}

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute", side_effect=lambda a: received.update({"base": a.base})), \
             patch("ralph.cli.cmd_pr"):
            cmd_oneshot(args)

        assert received["base"] == "feature-base"

    def test_asynchronous_flag_propagated_to_cmd_execute(self):
        """--asynchronous true is present in args when cmd_execute is called."""
        args = _args(asynchronous="true")
        received = {}

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute", side_effect=lambda a: received.update({"async": a.asynchronous})), \
             patch("ralph.cli.cmd_pr"):
            cmd_oneshot(args)

        assert received["async"] == "true"

    def test_provider_flag_propagated_to_cmd_pr(self):
        """--provider gitlab is present in args when cmd_pr is called."""
        args = _args(provider="gitlab")
        received = {}

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_pr", side_effect=lambda a: received.update({"provider": a.provider})):
            cmd_oneshot(args)

        assert received["provider"] == "gitlab"

    def test_resume_flag_propagated_to_cmd_execute(self):
        """--resume is present in args when cmd_execute is called."""
        args = _args(resume=True)
        received = {}

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute", side_effect=lambda a: received.update({"resume": a.resume})), \
             patch("ralph.cli.cmd_pr"):
            cmd_oneshot(args)

        assert received["resume"] is True

    def test_limit_flag_propagated_to_cmd_execute(self):
        """--limit N is present in args when cmd_execute is called."""
        args = _args(limit=5)
        received = {}

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute", side_effect=lambda a: received.update({"limit": a.limit})), \
             patch("ralph.cli.cmd_pr"):
            cmd_oneshot(args)

        assert received["limit"] == 5

    def test_project_name_propagated_to_all_sub_commands(self):
        """The project_name is present in args for all three sub-command calls."""
        args = _args(project_name="special-project")
        received = {}

        with patch("ralph.cli.cmd_enrich", side_effect=lambda a: received.update({"enrich_proj": a.project_name})), \
             patch("ralph.cli.cmd_execute", side_effect=lambda a: received.update({"execute_proj": a.project_name})), \
             patch("ralph.cli.cmd_pr", side_effect=lambda a: received.update({"pr_proj": a.project_name})):
            cmd_oneshot(args)

        assert received["enrich_proj"] == "special-project"
        assert received["execute_proj"] == "special-project"
        assert received["pr_proj"] == "special-project"


# ===========================================================================
# Failcase — project does not exist (guard in cmd_enrich)
# ===========================================================================


class TestCmdOneshotProjectNotExist:
    def test_aborts_with_exit_code_1_when_project_missing(self):
        """cmd_oneshot exits with code 1 when the project does not exist
        (guard is enforced by cmd_enrich)."""
        args = _args(project_name="nonexistent-project")

        with patch("ralph.cli.cmd_enrich", side_effect=SystemExit(1)), \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_pr"):
            with pytest.raises(SystemExit) as exc_info:
                cmd_oneshot(args)

        assert exc_info.value.code == 1

    def test_cmd_execute_not_called_when_project_missing(self):
        """cmd_execute is not called when cmd_enrich aborts due to a missing project."""
        args = _args()

        with patch("ralph.cli.cmd_enrich", side_effect=SystemExit(1)), \
             patch("ralph.cli.cmd_execute") as mock_execute, \
             patch("ralph.cli.cmd_pr"):
            with pytest.raises(SystemExit):
                cmd_oneshot(args)

        mock_execute.assert_not_called()

    def test_cmd_pr_not_called_when_project_missing(self):
        """cmd_pr is not called when cmd_enrich aborts due to a missing project."""
        args = _args()

        with patch("ralph.cli.cmd_enrich", side_effect=SystemExit(1)), \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_pr") as mock_pr:
            with pytest.raises(SystemExit):
                cmd_oneshot(args)

        mock_pr.assert_not_called()


# ===========================================================================
# Failcase — project branch already exists (guard in cmd_execute)
# ===========================================================================


class TestCmdOneshotBranchAlreadyExists:
    def test_aborts_with_exit_code_1_when_branch_exists(self):
        """cmd_oneshot exits with code 1 when the project branch already exists
        (guard is enforced by cmd_execute)."""
        args = _args()

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute", side_effect=SystemExit(1)), \
             patch("ralph.cli.cmd_pr"):
            with pytest.raises(SystemExit) as exc_info:
                cmd_oneshot(args)

        assert exc_info.value.code == 1

    def test_cmd_pr_not_called_when_branch_exists(self):
        """cmd_pr is not called when cmd_execute aborts because the branch already exists."""
        args = _args()

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute", side_effect=SystemExit(1)), \
             patch("ralph.cli.cmd_pr") as mock_pr:
            with pytest.raises(SystemExit):
                cmd_oneshot(args)

        mock_pr.assert_not_called()

    def test_cmd_enrich_already_ran_when_branch_exists(self):
        """cmd_enrich is still called even when cmd_execute later aborts."""
        args = _args()

        with patch("ralph.cli.cmd_enrich") as mock_enrich, \
             patch("ralph.cli.cmd_execute", side_effect=SystemExit(1)), \
             patch("ralph.cli.cmd_pr"):
            with pytest.raises(SystemExit):
                cmd_oneshot(args)

        mock_enrich.assert_called_once()


# ===========================================================================
# Failcase — dirty working tree (guard in cmd_pr)
# ===========================================================================


class TestCmdOneshotDirtyWorkingTree:
    def test_aborts_with_exit_code_1_when_working_tree_dirty(self):
        """cmd_oneshot exits with code 1 when the working tree is dirty
        (guard is enforced by cmd_pr)."""
        args = _args()

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_pr", side_effect=SystemExit(1)):
            with pytest.raises(SystemExit) as exc_info:
                cmd_oneshot(args)

        assert exc_info.value.code == 1

    def test_enrich_and_execute_already_ran_when_dirty_tree_detected(self):
        """cmd_enrich and cmd_execute have been called before cmd_pr aborts on dirty tree."""
        args = _args()

        with patch("ralph.cli.cmd_enrich") as mock_enrich, \
             patch("ralph.cli.cmd_execute") as mock_execute, \
             patch("ralph.cli.cmd_pr", side_effect=SystemExit(1)):
            with pytest.raises(SystemExit):
                cmd_oneshot(args)

        mock_enrich.assert_called_once()
        mock_execute.assert_called_once()
