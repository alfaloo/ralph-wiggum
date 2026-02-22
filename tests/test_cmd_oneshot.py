"""Unit tests for ralph/cli.py — cmd_oneshot / ralph oneshot subcommand."""

import argparse
from unittest.mock import mock_open, patch

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


_PASSED_VALIDATION_MD = "# Rating: passed\n\nAll tasks completed."
_FAILED_VALIDATION_MD = "# Rating: failed\n\nSome tasks were not completed."
_ATTENTION_VALIDATION_MD = "# Rating: requires attention\n\nMinor issues found."


# ===========================================================================
# Core functionality
# ===========================================================================


class TestCmdOneshotCore:
    """Verify that cmd_oneshot delegates to cmd_enrich, cmd_execute, cmd_validate, and cmd_pr in order."""

    def test_cmd_enrich_is_called(self):
        """cmd_oneshot calls cmd_enrich with the given args."""
        args = _args()
        with patch("ralph.cli.cmd_enrich") as mock_enrich, \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr"), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)
        mock_enrich.assert_called_once_with(args)

    def test_cmd_execute_is_called(self):
        """cmd_oneshot calls cmd_execute with the given args."""
        args = _args()
        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute") as mock_execute, \
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr"), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)
        mock_execute.assert_called_once_with(args)

    def test_cmd_validate_is_called(self):
        """cmd_oneshot calls cmd_validate with the given args."""
        args = _args()
        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_validate") as mock_validate, \
             patch("ralph.cli.cmd_pr"), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)
        mock_validate.assert_called_once_with(args)

    def test_cmd_pr_is_called(self):
        """cmd_oneshot calls cmd_pr with the given args."""
        args = _args()
        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr") as mock_pr, \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)
        mock_pr.assert_called_once_with(args)

    def test_enrich_execute_validate_pr_called_in_order(self):
        """cmd_oneshot calls cmd_enrich, cmd_execute, cmd_validate, cmd_pr in that exact order."""
        args = _args()
        call_order = []

        with patch("ralph.cli.cmd_enrich", side_effect=lambda _: call_order.append("enrich")), \
             patch("ralph.cli.cmd_execute", side_effect=lambda _: call_order.append("execute")), \
             patch("ralph.cli.cmd_validate", side_effect=lambda _: call_order.append("validate")), \
             patch("ralph.cli.cmd_pr", side_effect=lambda _: call_order.append("pr")), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        assert call_order == ["enrich", "execute", "validate", "pr"]

    def test_all_four_called_with_same_args_object(self):
        """All four internal calls receive the same args namespace."""
        args = _args(project_name="test-project")
        received = {}

        with patch("ralph.cli.cmd_enrich", side_effect=lambda a: received.update({"enrich": a})), \
             patch("ralph.cli.cmd_execute", side_effect=lambda a: received.update({"execute": a})), \
             patch("ralph.cli.cmd_validate", side_effect=lambda a: received.update({"validate": a})), \
             patch("ralph.cli.cmd_pr", side_effect=lambda a: received.update({"pr": a})), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        assert received["enrich"] is args
        assert received["execute"] is args
        assert received["validate"] is args
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
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr", side_effect=lambda a: received.update({"pr_verbose": a.verbose})), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
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
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr"), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        assert received["base"] == "feature-base"

    def test_asynchronous_flag_propagated_to_cmd_execute(self):
        """--asynchronous true is present in args when cmd_execute is called."""
        args = _args(asynchronous="true")
        received = {}

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute", side_effect=lambda a: received.update({"async": a.asynchronous})), \
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr"), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        assert received["async"] == "true"

    def test_provider_flag_propagated_to_cmd_pr(self):
        """--provider gitlab is present in args when cmd_pr is called."""
        args = _args(provider="gitlab")
        received = {}

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr", side_effect=lambda a: received.update({"provider": a.provider})), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        assert received["provider"] == "gitlab"

    def test_resume_flag_propagated_to_cmd_execute(self):
        """--resume is present in args when cmd_execute is called."""
        args = _args(resume=True)
        received = {}

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute", side_effect=lambda a: received.update({"resume": a.resume})), \
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr"), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        assert received["resume"] is True

    def test_limit_flag_propagated_to_cmd_execute(self):
        """--limit N is present in args when cmd_execute is called."""
        args = _args(limit=5)
        received = {}

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute", side_effect=lambda a: received.update({"limit": a.limit})), \
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr"), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        assert received["limit"] == 5

    def test_project_name_propagated_to_all_sub_commands(self):
        """The project_name is present in args for all four sub-command calls."""
        args = _args(project_name="special-project")
        received = {}

        with patch("ralph.cli.cmd_enrich", side_effect=lambda a: received.update({"enrich_proj": a.project_name})), \
             patch("ralph.cli.cmd_execute", side_effect=lambda a: received.update({"execute_proj": a.project_name})), \
             patch("ralph.cli.cmd_validate", side_effect=lambda a: received.update({"validate_proj": a.project_name})), \
             patch("ralph.cli.cmd_pr", side_effect=lambda a: received.update({"pr_proj": a.project_name})), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        assert received["enrich_proj"] == "special-project"
        assert received["execute_proj"] == "special-project"
        assert received["validate_proj"] == "special-project"
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
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr"):
            with pytest.raises(SystemExit) as exc_info:
                cmd_oneshot(args)

        assert exc_info.value.code == 1

    def test_cmd_execute_not_called_when_project_missing(self):
        """cmd_execute is not called when cmd_enrich aborts due to a missing project."""
        args = _args()

        with patch("ralph.cli.cmd_enrich", side_effect=SystemExit(1)), \
             patch("ralph.cli.cmd_execute") as mock_execute, \
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr"):
            with pytest.raises(SystemExit):
                cmd_oneshot(args)

        mock_execute.assert_not_called()

    def test_cmd_validate_not_called_when_project_missing(self):
        """cmd_validate is not called when cmd_enrich aborts due to a missing project."""
        args = _args()

        with patch("ralph.cli.cmd_enrich", side_effect=SystemExit(1)), \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_validate") as mock_validate, \
             patch("ralph.cli.cmd_pr"):
            with pytest.raises(SystemExit):
                cmd_oneshot(args)

        mock_validate.assert_not_called()

    def test_cmd_pr_not_called_when_project_missing(self):
        """cmd_pr is not called when cmd_enrich aborts due to a missing project."""
        args = _args()

        with patch("ralph.cli.cmd_enrich", side_effect=SystemExit(1)), \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_validate"), \
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
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr"):
            with pytest.raises(SystemExit) as exc_info:
                cmd_oneshot(args)

        assert exc_info.value.code == 1

    def test_cmd_validate_not_called_when_branch_exists(self):
        """cmd_validate is not called when cmd_execute aborts because the branch already exists."""
        args = _args()

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute", side_effect=SystemExit(1)), \
             patch("ralph.cli.cmd_validate") as mock_validate, \
             patch("ralph.cli.cmd_pr"):
            with pytest.raises(SystemExit):
                cmd_oneshot(args)

        mock_validate.assert_not_called()

    def test_cmd_pr_not_called_when_branch_exists(self):
        """cmd_pr is not called when cmd_execute aborts because the branch already exists."""
        args = _args()

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute", side_effect=SystemExit(1)), \
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr") as mock_pr:
            with pytest.raises(SystemExit):
                cmd_oneshot(args)

        mock_pr.assert_not_called()

    def test_cmd_enrich_already_ran_when_branch_exists(self):
        """cmd_enrich is still called even when cmd_execute later aborts."""
        args = _args()

        with patch("ralph.cli.cmd_enrich") as mock_enrich, \
             patch("ralph.cli.cmd_execute", side_effect=SystemExit(1)), \
             patch("ralph.cli.cmd_validate"), \
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
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr", side_effect=SystemExit(1)), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            with pytest.raises(SystemExit) as exc_info:
                cmd_oneshot(args)

        assert exc_info.value.code == 1

    def test_enrich_and_execute_already_ran_when_dirty_tree_detected(self):
        """cmd_enrich and cmd_execute have been called before cmd_pr aborts on dirty tree."""
        args = _args()

        with patch("ralph.cli.cmd_enrich") as mock_enrich, \
             patch("ralph.cli.cmd_execute") as mock_execute, \
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr", side_effect=SystemExit(1)), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            with pytest.raises(SystemExit):
                cmd_oneshot(args)

        mock_enrich.assert_called_once()
        mock_execute.assert_called_once()


# ===========================================================================
# Validate integration — rating-based behavior
# ===========================================================================


class TestCmdOneshotValidateIntegration:
    """Verify cmd_oneshot's behavior based on the rating in validation.md."""

    def test_validate_passed_proceeds_to_cmd_pr(self):
        """When validation rating is 'passed', cmd_pr is called."""
        args = _args()

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr") as mock_pr, \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        mock_pr.assert_called_once_with(args)

    def test_validate_failed_exits_without_calling_cmd_pr(self):
        """When validation rating is 'failed', sys.exit(1) is called and cmd_pr is not."""
        args = _args()

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr") as mock_pr, \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             pytest.raises(SystemExit) as exc_info:
            cmd_oneshot(args)

        assert exc_info.value.code == 1
        mock_pr.assert_not_called()

    def test_validate_failed_prints_warning(self, capsys):
        """When validation rating is 'failed', a warning is printed to stderr."""
        args = _args()

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr"), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             pytest.raises(SystemExit):
            cmd_oneshot(args)

        captured = capsys.readouterr()
        assert "[ralph]" in captured.err
        assert "failed" in captured.err.lower()

    def test_validate_requires_attention_proceeds_to_cmd_pr(self):
        """When validation rating is 'requires attention', cmd_pr is still called."""
        args = _args()

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr") as mock_pr, \
             patch("builtins.open", mock_open(read_data=_ATTENTION_VALIDATION_MD)):
            cmd_oneshot(args)

        mock_pr.assert_called_once_with(args)

    def test_validate_requires_attention_prints_warning(self, capsys):
        """When validation rating is 'requires attention', a warning is printed."""
        args = _args()

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr"), \
             patch("builtins.open", mock_open(read_data=_ATTENTION_VALIDATION_MD)):
            cmd_oneshot(args)

        captured = capsys.readouterr()
        assert "[ralph]" in captured.out

    def test_validation_md_unreadable_exits_without_pr(self):
        """When validation.md cannot be read, sys.exit(1) is called and cmd_pr is not."""
        args = _args()

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr") as mock_pr, \
             patch("builtins.open", side_effect=OSError("file not found")), \
             pytest.raises(SystemExit) as exc_info:
            cmd_oneshot(args)

        assert exc_info.value.code == 1
        mock_pr.assert_not_called()

    def test_validation_md_missing_rating_exits_without_pr(self):
        """When validation.md has no rating line, sys.exit(1) is called and cmd_pr is not."""
        args = _args()

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_validate"), \
             patch("ralph.cli.cmd_pr") as mock_pr, \
             patch("builtins.open", mock_open(read_data="No rating here at all.")), \
             pytest.raises(SystemExit) as exc_info:
            cmd_oneshot(args)

        assert exc_info.value.code == 1
        mock_pr.assert_not_called()

    def test_validate_called_before_pr(self):
        """cmd_validate is called before cmd_pr in oneshot."""
        args = _args()
        call_order = []

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute"), \
             patch("ralph.cli.cmd_validate", side_effect=lambda _: call_order.append("validate")), \
             patch("ralph.cli.cmd_pr", side_effect=lambda _: call_order.append("pr")), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        assert call_order.index("validate") < call_order.index("pr")

    def test_validate_called_after_execute(self):
        """cmd_validate is called after cmd_execute in oneshot."""
        args = _args()
        call_order = []

        with patch("ralph.cli.cmd_enrich"), \
             patch("ralph.cli.cmd_execute", side_effect=lambda _: call_order.append("execute")), \
             patch("ralph.cli.cmd_validate", side_effect=lambda _: call_order.append("validate")), \
             patch("ralph.cli.cmd_pr"), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        assert call_order.index("execute") < call_order.index("validate")
