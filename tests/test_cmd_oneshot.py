"""Unit tests for ralph/cli.py — cmd_oneshot / ralph oneshot subcommand."""

import argparse
from unittest.mock import MagicMock, mock_open, patch

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
    """Verify that cmd_oneshot delegates to EnrichCommand, ExecuteCommand, ValidateCommand,
    and PrCommand in order."""

    def test_enrich_command_is_called(self):
        """cmd_oneshot instantiates and executes EnrichCommand with the given args."""
        args = _args()
        with patch("ralph.commands.EnrichCommand") as MockEnrich, \
             patch("ralph.commands.ExecuteCommand"), \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand"), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)
        MockEnrich.assert_called_once_with(args)
        MockEnrich.return_value.execute.assert_called_once()

    def test_execute_command_is_called(self):
        """cmd_oneshot instantiates and executes ExecuteCommand with the given args."""
        args = _args()
        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand") as MockExecute, \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand"), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)
        MockExecute.assert_called_once_with(args)
        MockExecute.return_value.execute.assert_called_once()

    def test_validate_command_is_called(self):
        """cmd_oneshot instantiates and executes ValidateCommand with the given args."""
        args = _args()
        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand"), \
             patch("ralph.commands.ValidateCommand") as MockValidate, \
             patch("ralph.commands.PrCommand"), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)
        MockValidate.assert_called_once_with(args)
        MockValidate.return_value.execute.assert_called_once()

    def test_pr_command_is_called(self):
        """cmd_oneshot instantiates and executes PrCommand with the given args."""
        args = _args()
        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand"), \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand") as MockPr, \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)
        MockPr.assert_called_once_with(args)
        MockPr.return_value.execute.assert_called_once()

    def test_enrich_execute_validate_pr_called_in_order(self):
        """cmd_oneshot calls enrich, execute, validate, pr in that exact order."""
        args = _args()
        call_order = []

        with patch("ralph.commands.EnrichCommand") as MockEnrich, \
             patch("ralph.commands.ExecuteCommand") as MockExecute, \
             patch("ralph.commands.ValidateCommand") as MockValidate, \
             patch("ralph.commands.PrCommand") as MockPr, \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            MockEnrich.return_value.execute.side_effect = lambda: call_order.append("enrich")
            MockExecute.return_value.execute.side_effect = lambda: call_order.append("execute")
            MockValidate.return_value.execute.side_effect = lambda: call_order.append("validate")
            MockPr.return_value.execute.side_effect = lambda: call_order.append("pr")
            cmd_oneshot(args)

        assert call_order == ["enrich", "execute", "validate", "pr"]

    def test_all_four_called_with_same_args_object(self):
        """All four command classes receive the same args namespace."""
        args = _args(project_name="test-project")

        with patch("ralph.commands.EnrichCommand") as MockEnrich, \
             patch("ralph.commands.ExecuteCommand") as MockExecute, \
             patch("ralph.commands.ValidateCommand") as MockValidate, \
             patch("ralph.commands.PrCommand") as MockPr, \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        assert MockEnrich.call_args[0][0] is args
        assert MockExecute.call_args[0][0] is args
        assert MockValidate.call_args[0][0] is args
        assert MockPr.call_args[0][0] is args


# ===========================================================================
# Flag propagation
# ===========================================================================


class TestCmdOneshotFlagPropagation:
    """Flags in the args namespace are visible to each internal command call."""

    def test_verbose_flag_propagated_to_all_sub_commands(self):
        """--verbose true is present in args when each sub-command is called."""
        args = _args(verbose="true")

        with patch("ralph.commands.EnrichCommand") as MockEnrich, \
             patch("ralph.commands.ExecuteCommand") as MockExecute, \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand") as MockPr, \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        assert MockEnrich.call_args[0][0].verbose == "true"
        assert MockExecute.call_args[0][0].verbose == "true"
        assert MockPr.call_args[0][0].verbose == "true"

    def test_base_flag_propagated_to_execute_command(self):
        """--base <branch> is present in args when ExecuteCommand is called."""
        args = _args(base="feature-base")

        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand") as MockExecute, \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand"), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        assert MockExecute.call_args[0][0].base == "feature-base"

    def test_asynchronous_flag_propagated_to_execute_command(self):
        """--asynchronous true is present in args when ExecuteCommand is called."""
        args = _args(asynchronous="true")

        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand") as MockExecute, \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand"), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        assert MockExecute.call_args[0][0].asynchronous == "true"

    def test_provider_flag_propagated_to_pr_command(self):
        """--provider gitlab is present in args when PrCommand is called."""
        args = _args(provider="gitlab")

        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand"), \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand") as MockPr, \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        assert MockPr.call_args[0][0].provider == "gitlab"

    def test_resume_flag_propagated_to_execute_command(self):
        """--resume is present in args when ExecuteCommand is called."""
        args = _args(resume=True)

        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand") as MockExecute, \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand"), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        assert MockExecute.call_args[0][0].resume is True

    def test_limit_flag_propagated_to_execute_command(self):
        """--limit N is present in args when ExecuteCommand is called."""
        args = _args(limit=5)

        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand") as MockExecute, \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand"), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        assert MockExecute.call_args[0][0].limit == 5

    def test_project_name_propagated_to_all_sub_commands(self):
        """The project_name is present in args for all four command calls."""
        args = _args(project_name="special-project")

        with patch("ralph.commands.EnrichCommand") as MockEnrich, \
             patch("ralph.commands.ExecuteCommand") as MockExecute, \
             patch("ralph.commands.ValidateCommand") as MockValidate, \
             patch("ralph.commands.PrCommand") as MockPr, \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        assert MockEnrich.call_args[0][0].project_name == "special-project"
        assert MockExecute.call_args[0][0].project_name == "special-project"
        assert MockValidate.call_args[0][0].project_name == "special-project"
        assert MockPr.call_args[0][0].project_name == "special-project"


# ===========================================================================
# Failcase — project does not exist (guard in EnrichCommand)
# ===========================================================================


class TestCmdOneshotProjectNotExist:
    def test_aborts_with_exit_code_1_when_project_missing(self):
        """cmd_oneshot exits with code 1 when the project does not exist
        (guard is enforced by EnrichCommand)."""
        args = _args(project_name="nonexistent-project")

        with patch("ralph.commands.EnrichCommand") as MockEnrich, \
             patch("ralph.commands.ExecuteCommand"), \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand"):
            MockEnrich.return_value.execute.side_effect = SystemExit(1)
            with pytest.raises(SystemExit) as exc_info:
                cmd_oneshot(args)

        assert exc_info.value.code == 1

    def test_execute_not_called_when_project_missing(self):
        """ExecuteCommand is not called when EnrichCommand aborts due to a missing project."""
        args = _args()

        with patch("ralph.commands.EnrichCommand") as MockEnrich, \
             patch("ralph.commands.ExecuteCommand") as MockExecute, \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand"):
            MockEnrich.return_value.execute.side_effect = SystemExit(1)
            with pytest.raises(SystemExit):
                cmd_oneshot(args)

        MockExecute.return_value.execute.assert_not_called()

    def test_validate_not_called_when_project_missing(self):
        """ValidateCommand is not called when EnrichCommand aborts due to a missing project."""
        args = _args()

        with patch("ralph.commands.EnrichCommand") as MockEnrich, \
             patch("ralph.commands.ExecuteCommand"), \
             patch("ralph.commands.ValidateCommand") as MockValidate, \
             patch("ralph.commands.PrCommand"):
            MockEnrich.return_value.execute.side_effect = SystemExit(1)
            with pytest.raises(SystemExit):
                cmd_oneshot(args)

        MockValidate.return_value.execute.assert_not_called()

    def test_pr_not_called_when_project_missing(self):
        """PrCommand is not called when EnrichCommand aborts due to a missing project."""
        args = _args()

        with patch("ralph.commands.EnrichCommand") as MockEnrich, \
             patch("ralph.commands.ExecuteCommand"), \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand") as MockPr:
            MockEnrich.return_value.execute.side_effect = SystemExit(1)
            with pytest.raises(SystemExit):
                cmd_oneshot(args)

        MockPr.return_value.execute.assert_not_called()


# ===========================================================================
# Failcase — project branch already exists (guard in ExecuteCommand)
# ===========================================================================


class TestCmdOneshotBranchAlreadyExists:
    def test_aborts_with_exit_code_1_when_branch_exists(self):
        """cmd_oneshot exits with code 1 when the project branch already exists
        (guard is enforced by ExecuteCommand)."""
        args = _args()

        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand") as MockExecute, \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand"):
            MockExecute.return_value.execute.side_effect = SystemExit(1)
            with pytest.raises(SystemExit) as exc_info:
                cmd_oneshot(args)

        assert exc_info.value.code == 1

    def test_validate_not_called_when_branch_exists(self):
        """ValidateCommand is not called when ExecuteCommand aborts because the branch already exists."""
        args = _args()

        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand") as MockExecute, \
             patch("ralph.commands.ValidateCommand") as MockValidate, \
             patch("ralph.commands.PrCommand"):
            MockExecute.return_value.execute.side_effect = SystemExit(1)
            with pytest.raises(SystemExit):
                cmd_oneshot(args)

        MockValidate.return_value.execute.assert_not_called()

    def test_pr_not_called_when_branch_exists(self):
        """PrCommand is not called when ExecuteCommand aborts because the branch already exists."""
        args = _args()

        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand") as MockExecute, \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand") as MockPr:
            MockExecute.return_value.execute.side_effect = SystemExit(1)
            with pytest.raises(SystemExit):
                cmd_oneshot(args)

        MockPr.return_value.execute.assert_not_called()

    def test_enrich_already_ran_when_branch_exists(self):
        """EnrichCommand is still called even when ExecuteCommand later aborts."""
        args = _args()

        with patch("ralph.commands.EnrichCommand") as MockEnrich, \
             patch("ralph.commands.ExecuteCommand") as MockExecute, \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand"):
            MockExecute.return_value.execute.side_effect = SystemExit(1)
            with pytest.raises(SystemExit):
                cmd_oneshot(args)

        MockEnrich.return_value.execute.assert_called_once()


# ===========================================================================
# Failcase — dirty working tree (guard in PrCommand)
# ===========================================================================


class TestCmdOneshotDirtyWorkingTree:
    def test_aborts_with_exit_code_1_when_working_tree_dirty(self):
        """cmd_oneshot exits with code 1 when the working tree is dirty
        (guard is enforced by PrCommand)."""
        args = _args()

        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand"), \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand") as MockPr, \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            MockPr.return_value.execute.side_effect = SystemExit(1)
            with pytest.raises(SystemExit) as exc_info:
                cmd_oneshot(args)

        assert exc_info.value.code == 1

    def test_enrich_and_execute_already_ran_when_dirty_tree_detected(self):
        """EnrichCommand and ExecuteCommand have been called before PrCommand aborts on dirty tree."""
        args = _args()

        with patch("ralph.commands.EnrichCommand") as MockEnrich, \
             patch("ralph.commands.ExecuteCommand") as MockExecute, \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand") as MockPr, \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            MockPr.return_value.execute.side_effect = SystemExit(1)
            with pytest.raises(SystemExit):
                cmd_oneshot(args)

        MockEnrich.return_value.execute.assert_called_once()
        MockExecute.return_value.execute.assert_called_once()


# ===========================================================================
# Validate integration — rating-based behavior
# ===========================================================================


class TestCmdOneshotValidateIntegration:
    """Verify cmd_oneshot's behavior based on the rating in validation.md."""

    def test_validate_passed_proceeds_to_pr_command(self):
        """When validation rating is 'passed', PrCommand is called."""
        args = _args()

        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand"), \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand") as MockPr, \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            cmd_oneshot(args)

        MockPr.assert_called_once_with(args)
        MockPr.return_value.execute.assert_called_once()

    def test_validate_failed_exits_without_calling_pr_command(self):
        """When validation rating is 'failed', sys.exit(1) is called and PrCommand is not."""
        args = _args()

        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand"), \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand") as MockPr, \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             pytest.raises(SystemExit) as exc_info:
            cmd_oneshot(args)

        assert exc_info.value.code == 1
        MockPr.return_value.execute.assert_not_called()

    def test_validate_failed_prints_warning(self, capsys):
        """When validation rating is 'failed', a warning is printed to stderr."""
        args = _args()

        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand"), \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand"), \
             patch("builtins.open", mock_open(read_data=_FAILED_VALIDATION_MD)), \
             pytest.raises(SystemExit):
            cmd_oneshot(args)

        captured = capsys.readouterr()
        assert "[ralph]" in captured.err
        assert "failed" in captured.err.lower()

    def test_validate_requires_attention_proceeds_to_pr_command(self):
        """When validation rating is 'requires attention', PrCommand is still called."""
        args = _args()

        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand"), \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand") as MockPr, \
             patch("builtins.open", mock_open(read_data=_ATTENTION_VALIDATION_MD)):
            cmd_oneshot(args)

        MockPr.assert_called_once_with(args)
        MockPr.return_value.execute.assert_called_once()

    def test_validate_requires_attention_prints_warning(self, capsys):
        """When validation rating is 'requires attention', a warning is printed."""
        args = _args()

        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand"), \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand"), \
             patch("builtins.open", mock_open(read_data=_ATTENTION_VALIDATION_MD)):
            cmd_oneshot(args)

        captured = capsys.readouterr()
        assert "[ralph]" in captured.out

    def test_validation_md_unreadable_exits_without_pr(self):
        """When validation.md cannot be read, sys.exit(1) is called and PrCommand is not."""
        args = _args()

        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand"), \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand") as MockPr, \
             patch("builtins.open", side_effect=OSError("file not found")), \
             pytest.raises(SystemExit) as exc_info:
            cmd_oneshot(args)

        assert exc_info.value.code == 1
        MockPr.return_value.execute.assert_not_called()

    def test_validation_md_missing_rating_exits_without_pr(self):
        """When validation.md has no rating line, sys.exit(1) is called and PrCommand is not."""
        args = _args()

        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand"), \
             patch("ralph.commands.ValidateCommand"), \
             patch("ralph.commands.PrCommand") as MockPr, \
             patch("builtins.open", mock_open(read_data="No rating here at all.")), \
             pytest.raises(SystemExit) as exc_info:
            cmd_oneshot(args)

        assert exc_info.value.code == 1
        MockPr.return_value.execute.assert_not_called()

    def test_validate_called_before_pr(self):
        """ValidateCommand is called before PrCommand in oneshot."""
        args = _args()
        call_order = []

        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand"), \
             patch("ralph.commands.ValidateCommand") as MockValidate, \
             patch("ralph.commands.PrCommand") as MockPr, \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            MockValidate.return_value.execute.side_effect = lambda: call_order.append("validate")
            MockPr.return_value.execute.side_effect = lambda: call_order.append("pr")
            cmd_oneshot(args)

        assert call_order.index("validate") < call_order.index("pr")

    def test_validate_called_after_execute(self):
        """ValidateCommand is called after ExecuteCommand in oneshot."""
        args = _args()
        call_order = []

        with patch("ralph.commands.EnrichCommand"), \
             patch("ralph.commands.ExecuteCommand") as MockExecute, \
             patch("ralph.commands.ValidateCommand") as MockValidate, \
             patch("ralph.commands.PrCommand"), \
             patch("builtins.open", mock_open(read_data=_PASSED_VALIDATION_MD)):
            MockExecute.return_value.execute.side_effect = lambda: call_order.append("execute")
            MockValidate.return_value.execute.side_effect = lambda: call_order.append("validate")
            cmd_oneshot(args)

        assert call_order.index("execute") < call_order.index("validate")
