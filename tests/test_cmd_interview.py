"""Unit tests for ralph/cli.py — cmd_interview command."""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from ralph.cli import cmd_interview


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(
    project_name: str = "my-project",
    verbose: str | None = None,
    rounds: int | None = None,
) -> argparse.Namespace:
    """Build a minimal Namespace for cmd_interview."""
    return argparse.Namespace(
        project_name=project_name,
        verbose=verbose,
        rounds=rounds,
    )


# ===========================================================================
# Core functionality
# ===========================================================================


class TestCmdInterviewCoreFunction:
    """Happy-path tests for cmd_interview."""

    def test_calls_assert_project_exists(self):
        """cmd_interview must call _assert_project_exists with the project name."""
        with (
            patch("ralph.commands._assert_project_exists") as mock_assert,
            patch("ralph.commands.Runner") as MockRunner,
            patch("ralph.commands.parse_questions_md", return_value="q-prompt"),
            patch("ralph.commands.parse_generate_tasks_md", return_value="a-prompt"),
            patch("ralph.commands.get_rounds", return_value=1),
            patch("ralph.commands.get_verbose", return_value=False),
        ):
            MockRunner.return_value.run_interview_loop = MagicMock()
            cmd_interview(_make_args(project_name="my-project"))
            mock_assert.assert_called_once_with("my-project")

    def test_calls_run_interview_loop(self):
        """cmd_interview must call Runner.run_interview_loop()."""
        with (
            patch("ralph.commands._assert_project_exists"),
            patch("ralph.commands.Runner") as MockRunner,
            patch("ralph.commands.parse_questions_md", return_value="q"),
            patch("ralph.commands.parse_generate_tasks_md", return_value="a"),
            patch("ralph.commands.get_rounds", return_value=1),
            patch("ralph.commands.get_verbose", return_value=False),
        ):
            mock_runner = MockRunner.return_value
            cmd_interview(_make_args())
            mock_runner.run_interview_loop.assert_called_once()

    def test_runner_created_with_project_name_and_verbose(self):
        """Runner must be instantiated with the correct project name and verbose flag."""
        with (
            patch("ralph.commands._assert_project_exists"),
            patch("ralph.commands.Runner") as MockRunner,
            patch("ralph.commands.parse_questions_md", return_value="q"),
            patch("ralph.commands.parse_generate_tasks_md", return_value="a"),
            patch("ralph.commands.get_rounds", return_value=1),
            patch("ralph.commands.get_verbose", return_value=False),
        ):
            MockRunner.return_value.run_interview_loop = MagicMock()
            cmd_interview(_make_args(project_name="test-proj", verbose=None))
            MockRunner.assert_called_once_with("test-proj", verbose=False)

    def test_verbose_true_forwarded_to_runner(self):
        """--verbose true must be resolved to True and forwarded to Runner."""
        with (
            patch("ralph.commands._assert_project_exists"),
            patch("ralph.commands.Runner") as MockRunner,
            patch("ralph.commands.parse_questions_md", return_value="q"),
            patch("ralph.commands.parse_generate_tasks_md", return_value="a"),
            patch("ralph.commands.get_rounds", return_value=1),
            patch("ralph.commands.get_verbose", return_value=False),
        ):
            MockRunner.return_value.run_interview_loop = MagicMock()
            cmd_interview(_make_args(verbose="true"))
            MockRunner.assert_called_once_with("my-project", verbose=True)

    def test_verbose_false_forwarded_to_runner(self):
        """--verbose false must be resolved to False and forwarded to Runner."""
        with (
            patch("ralph.commands._assert_project_exists"),
            patch("ralph.commands.Runner") as MockRunner,
            patch("ralph.commands.parse_questions_md", return_value="q"),
            patch("ralph.commands.parse_generate_tasks_md", return_value="a"),
            patch("ralph.commands.get_rounds", return_value=1),
            patch("ralph.commands.get_verbose", return_value=True),
        ):
            MockRunner.return_value.run_interview_loop = MagicMock()
            cmd_interview(_make_args(verbose="false"))
            MockRunner.assert_called_once_with("my-project", verbose=False)

    def test_uses_cli_rounds_when_provided(self):
        """When --rounds is explicitly given on the CLI, it overrides the persisted setting."""
        with (
            patch("ralph.commands._assert_project_exists"),
            patch("ralph.commands.Runner") as MockRunner,
            patch("ralph.commands.parse_questions_md", return_value="q") as mock_parse_q,
            patch("ralph.commands.parse_generate_tasks_md", return_value="a"),
            patch("ralph.commands.get_rounds", return_value=99),
            patch("ralph.commands.get_verbose", return_value=False),
        ):
            MockRunner.return_value.run_interview_loop = MagicMock()
            cmd_interview(_make_args(rounds=2))
            assert mock_parse_q.call_count == 2

    def test_uses_settings_rounds_when_not_provided(self):
        """When --rounds is absent, the value from get_rounds() must be used."""
        with (
            patch("ralph.commands._assert_project_exists"),
            patch("ralph.commands.Runner") as MockRunner,
            patch("ralph.commands.parse_questions_md", return_value="q") as mock_parse_q,
            patch("ralph.commands.parse_generate_tasks_md", return_value="a"),
            patch("ralph.commands.get_rounds", return_value=3),
            patch("ralph.commands.get_verbose", return_value=False),
        ):
            MockRunner.return_value.run_interview_loop = MagicMock()
            cmd_interview(_make_args(rounds=None))
            assert mock_parse_q.call_count == 3

    def test_question_prompts_list_has_one_entry_per_round(self):
        """The question_prompts list passed to run_interview_loop must have one entry per round."""
        with (
            patch("ralph.commands._assert_project_exists"),
            patch("ralph.commands.Runner") as MockRunner,
            patch("ralph.commands.parse_questions_md", return_value="q-prompt"),
            patch("ralph.commands.parse_generate_tasks_md", return_value="a-prompt"),
            patch("ralph.commands.get_rounds", return_value=2),
            patch("ralph.commands.get_verbose", return_value=False),
        ):
            mock_runner = MockRunner.return_value
            cmd_interview(_make_args(rounds=2))
            question_prompts = mock_runner.run_interview_loop.call_args[0][0]
            assert question_prompts == ["q-prompt", "q-prompt"]

    def test_amend_fns_list_has_one_callable_per_round(self):
        """The amend_fns list passed to run_interview_loop must have one callable per round."""
        with (
            patch("ralph.commands._assert_project_exists"),
            patch("ralph.commands.Runner") as MockRunner,
            patch("ralph.commands.parse_questions_md", return_value="q"),
            patch("ralph.commands.parse_generate_tasks_md", return_value="a"),
            patch("ralph.commands.get_rounds", return_value=3),
            patch("ralph.commands.get_verbose", return_value=False),
        ):
            mock_runner = MockRunner.return_value
            cmd_interview(_make_args(rounds=3))
            amend_fns = mock_runner.run_interview_loop.call_args[0][1]
            assert len(amend_fns) == 3
            assert all(callable(fn) for fn in amend_fns)

    def test_parse_questions_md_called_with_correct_args(self):
        """parse_questions_md must be called with project_name, round_num, and total_rounds."""
        with (
            patch("ralph.commands._assert_project_exists"),
            patch("ralph.commands.Runner") as MockRunner,
            patch("ralph.commands.parse_questions_md", return_value="q") as mock_parse_q,
            patch("ralph.commands.parse_generate_tasks_md", return_value="a"),
            patch("ralph.commands.get_rounds", return_value=2),
            patch("ralph.commands.get_verbose", return_value=False),
        ):
            MockRunner.return_value.run_interview_loop = MagicMock()
            cmd_interview(_make_args(project_name="proj", rounds=2))
            mock_parse_q.assert_any_call("proj", round_num=1, total_rounds=2)
            mock_parse_q.assert_any_call("proj", round_num=2, total_rounds=2)


# ===========================================================================
# Failcases
# ===========================================================================


class TestCmdInterviewFailcases:
    """Tests for precondition failures in cmd_interview."""

    def test_project_not_exists_aborts(self):
        """If the project directory is missing, cmd_interview must abort with sys.exit(1)."""
        with (
            patch("ralph.commands.os.path.exists", return_value=False),
            patch("ralph.commands.Runner") as MockRunner,
        ):
            with pytest.raises(SystemExit) as exc_info:
                cmd_interview(_make_args(project_name="missing-project"))
            assert exc_info.value.code == 1
            MockRunner.assert_not_called()

    def test_run_interview_loop_not_called_when_project_missing(self):
        """run_interview_loop must not be invoked if the project precondition fails."""
        with (
            patch("ralph.commands._assert_project_exists", side_effect=SystemExit(1)),
            patch("ralph.commands.Runner") as MockRunner,
        ):
            with pytest.raises(SystemExit):
                cmd_interview(_make_args(project_name="missing-project"))
            MockRunner.return_value.run_interview_loop.assert_not_called()
