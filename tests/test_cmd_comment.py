"""Unit tests for ralph comment command."""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from ralph.cli import cmd_comment


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _args(project_name="my-project", comment="Add OAuth login", verbose=None):
    """Build a minimal argparse.Namespace for cmd_comment."""
    return argparse.Namespace(
        project_name=project_name,
        comment=comment,
        verbose=verbose,
    )


def _exists_for_project(project_name):
    """Return a side_effect for os.path.exists that simulates a valid project."""
    def exists(path):
        return True
    return exists


# ===========================================================================
# Core functionality
# ===========================================================================


class TestCmdCommentCoreFunc:
    """Core functionality tests for cmd_comment."""

    def test_assert_project_exists_called_with_project_name(self):
        """cmd_comment calls _assert_project_exists with the correct project name."""
        args = _args()
        with patch("ralph.commands._assert_project_exists") as mock_assert, \
             patch("ralph.commands.parse_generate_tasks_md", return_value="prompt"), \
             patch("ralph.commands.Runner") as MockRunner:
            MockRunner.return_value.run_prompt = MagicMock()
            cmd_comment(args)
        mock_assert.assert_called_once_with("my-project")

    def test_parse_generate_tasks_md_called_with_project_name_and_comment(self):
        """cmd_comment passes project_name and user_comment to parse_generate_tasks_md."""
        args = _args(project_name="test-proj", comment="Add tests")
        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.parse_generate_tasks_md", return_value="the-prompt") as mock_parse, \
             patch("ralph.commands.Runner") as MockRunner:
            MockRunner.return_value.run_prompt = MagicMock()
            cmd_comment(args)
        mock_parse.assert_called_once_with("test-proj", user_comment="Add tests")

    def test_runner_run_prompt_called_with_generated_prompt(self):
        """cmd_comment calls Runner.run_prompt with the prompt returned by parse_generate_tasks_md."""
        args = _args()
        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.parse_generate_tasks_md", return_value="generated-prompt"), \
             patch("ralph.commands.Runner") as MockRunner:
            mock_instance = MagicMock()
            MockRunner.return_value = mock_instance
            cmd_comment(args)
        mock_instance.run_prompt.assert_called_once_with("generated-prompt", "comment")

    def test_runner_initialised_with_correct_project_name(self):
        """cmd_comment constructs Runner with the correct project_name."""
        args = _args(project_name="proj-xyz")
        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.parse_generate_tasks_md", return_value="prompt"), \
             patch("ralph.commands.Runner") as MockRunner:
            MockRunner.return_value.run_prompt = MagicMock()
            cmd_comment(args)
        call_args, _ = MockRunner.call_args
        assert call_args[0] == "proj-xyz"

    def test_verbose_true_forwarded_to_runner(self):
        """cmd_comment forwards verbose=True to Runner when --verbose true is passed."""
        args = _args(verbose="true")
        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.parse_generate_tasks_md", return_value="prompt"), \
             patch("ralph.commands.Runner") as MockRunner:
            MockRunner.return_value.run_prompt = MagicMock()
            cmd_comment(args)
        _, kwargs = MockRunner.call_args
        assert kwargs["verbose"] is True

    def test_verbose_false_forwarded_to_runner(self):
        """cmd_comment forwards verbose=False to Runner when --verbose false is passed."""
        args = _args(verbose="false")
        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.parse_generate_tasks_md", return_value="prompt"), \
             patch("ralph.commands.Runner") as MockRunner:
            MockRunner.return_value.run_prompt = MagicMock()
            cmd_comment(args)
        _, kwargs = MockRunner.call_args
        assert kwargs["verbose"] is False

    def test_verbose_none_falls_back_to_persisted_setting(self):
        """When --verbose is absent, Runner receives the verbose value from settings.json."""
        args = _args(verbose=None)
        with patch("ralph.commands._assert_project_exists"), \
             patch("ralph.commands.parse_generate_tasks_md", return_value="prompt"), \
             patch("ralph.commands.get_verbose", return_value=True), \
             patch("ralph.commands.Runner") as MockRunner:
            MockRunner.return_value.run_prompt = MagicMock()
            cmd_comment(args)
        _, kwargs = MockRunner.call_args
        assert kwargs["verbose"] is True

    def test_all_three_steps_invoked_in_order(self):
        """_assert_project_exists, parse_generate_tasks_md, and run_prompt are all called."""
        args = _args(comment="Enable dark mode")
        call_log = []

        def mock_assert(name):
            call_log.append("assert")

        def mock_parse(name, *, user_comment):
            call_log.append("parse")
            return "my-prompt"

        with patch("ralph.commands._assert_project_exists", side_effect=mock_assert), \
             patch("ralph.commands.parse_generate_tasks_md", side_effect=mock_parse), \
             patch("ralph.commands.Runner") as MockRunner:
            mock_instance = MagicMock()
            mock_instance.run_prompt.side_effect = lambda p, n: call_log.append("run_prompt")
            MockRunner.return_value = mock_instance
            cmd_comment(args)

        assert call_log == ["assert", "parse", "run_prompt"]


# ===========================================================================
# Failcases
# ===========================================================================


class TestCmdCommentFailcases:
    """Failcase tests for cmd_comment."""

    def test_missing_project_directory_aborts_with_exit_code_1(self):
        """cmd_comment exits with code 1 when the project directory does not exist."""
        args = _args(project_name="no-such-project")
        with patch("ralph.commands.os.path.exists", return_value=False):
            with pytest.raises(SystemExit) as exc_info:
                cmd_comment(args)
        assert exc_info.value.code == 1

    def test_missing_spec_md_aborts_with_exit_code_1(self):
        """cmd_comment exits with code 1 when spec.md is missing from the project directory."""
        args = _args(project_name="my-project")

        def exists_side_effect(path):
            # Project dir exists but spec.md does not.
            if "spec.md" in path:
                return False
            return True

        with patch("ralph.commands.os.path.exists", side_effect=exists_side_effect):
            with pytest.raises(SystemExit) as exc_info:
                cmd_comment(args)
        assert exc_info.value.code == 1

    def test_run_prompt_not_called_when_project_missing(self):
        """Runner.run_prompt is never invoked when the project does not exist."""
        args = _args()
        with patch("ralph.commands.os.path.exists", return_value=False), \
             patch("ralph.commands.Runner") as MockRunner:
            with pytest.raises(SystemExit):
                cmd_comment(args)
        MockRunner.assert_not_called()

    def test_parse_generate_tasks_md_not_called_when_project_missing(self):
        """parse_generate_tasks_md is never invoked when the project does not exist."""
        args = _args()
        with patch("ralph.commands.os.path.exists", return_value=False), \
             patch("ralph.commands.parse_generate_tasks_md") as mock_parse:
            with pytest.raises(SystemExit):
                cmd_comment(args)
        mock_parse.assert_not_called()
