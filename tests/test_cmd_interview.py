"""Unit tests for ralph/cli.py — cmd_interview command."""

import argparse
import json
from unittest.mock import MagicMock, patch

import pytest

from ralph.cli import cmd_interview
from ralph.run import (
    Runner,
    _collect_guided_answers,
    _open_multiline_editor,
    _parse_questions_json,
)


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


# ===========================================================================
# Tests for _parse_questions_json()
# ===========================================================================


class TestParseQuestionsJson:
    """Tests for the _parse_questions_json() helper in ralph/run.py."""

    def test_valid_json_string(self):
        """Returns the questions list from a valid bare JSON string."""
        raw = json.dumps({
            "questions": [
                {"id": 1, "question": "Q1?", "options": ["A", "B"]},
                {"id": 2, "question": "Q2?", "options": ["X", "Y", "Z"]},
            ]
        })
        result = _parse_questions_json(raw)
        assert result == [
            {"id": 1, "question": "Q1?", "options": ["A", "B"]},
            {"id": 2, "question": "Q2?", "options": ["X", "Y", "Z"]},
        ]

    def test_valid_json_inside_markdown_fence(self):
        """Strips ```json ... ``` fences and returns the questions list."""
        inner = json.dumps({"questions": [{"id": 1, "question": "Q?", "options": ["A"]}]})
        raw = f"```json\n{inner}\n```"
        result = _parse_questions_json(raw)
        assert result == [{"id": 1, "question": "Q?", "options": ["A"]}]

    def test_valid_json_inside_plain_fence(self):
        """Strips plain ``` ... ``` fences (no language tag) and parses correctly."""
        inner = json.dumps({"questions": [{"id": 1, "question": "Q?", "options": ["A"]}]})
        raw = f"```\n{inner}\n```"
        result = _parse_questions_json(raw)
        assert result == [{"id": 1, "question": "Q?", "options": ["A"]}]

    def test_malformed_json_returns_none(self):
        """Returns None when the input is not valid JSON."""
        result = _parse_questions_json("This is not JSON at all.")
        assert result is None

    def test_empty_questions_array_returns_empty_list(self):
        """Returns [] (not None) when the questions array is empty."""
        raw = json.dumps({"questions": []})
        result = _parse_questions_json(raw)
        assert result == []

    def test_whitespace_stripped_before_parsing(self):
        """Leading/trailing whitespace is stripped before attempting to parse."""
        raw = "   " + json.dumps({"questions": [{"id": 1, "question": "Q?", "options": []}]}) + "\n"
        result = _parse_questions_json(raw)
        assert result == [{"id": 1, "question": "Q?", "options": []}]

    def test_json_without_questions_key_returns_none(self):
        """Returns None when the JSON object has no 'questions' key (AttributeError path)."""
        raw = json.dumps(["not", "an", "object"])
        result = _parse_questions_json(raw)
        assert result is None


# ===========================================================================
# Tests for _open_multiline_editor()
# ===========================================================================


class TestOpenMultilineEditor:
    """Tests for the _open_multiline_editor() helper in ralph/run.py."""

    def test_tty_path_preamble_printed_and_return_value_passed_through(self, capsys):
        """TTY path: preamble is printed and the prompt_toolkit return value is returned."""
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("prompt_toolkit.prompt", return_value="  typed answer  "),
        ):
            result = _open_multiline_editor("Enter your response:")

        assert result == "typed answer"  # .strip() applied
        captured = capsys.readouterr()
        assert "Enter your response:" in captured.out

    def test_nontty_path_reads_without_exhausting_stdin(self, capsys):
        """Non-TTY path: reads lines until sentinel; subsequent lines remain unconsumed."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        mock_stdin.readline.side_effect = ["line1\n", "line2\n", ".\n", "unconsumed\n"]

        with patch("sys.stdin", mock_stdin):
            result = _open_multiline_editor("Preamble text:")

        assert result == "line1\nline2"
        # Exactly 3 readline calls: line1, line2, sentinel — not the 4th
        assert mock_stdin.readline.call_count == 3

    def test_nontty_path_preamble_printed(self, capsys):
        """Non-TTY path: preamble text is printed to stdout."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        mock_stdin.readline.side_effect = [".\n"]

        with patch("sys.stdin", mock_stdin):
            _open_multiline_editor("My preamble message")

        captured = capsys.readouterr()
        assert "My preamble message" in captured.out

    def test_nontty_path_empty_input_after_sentinel(self, capsys):
        """Non-TTY path: immediate sentinel yields empty string result."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        mock_stdin.readline.side_effect = [".\n", "not_read\n"]

        with patch("sys.stdin", mock_stdin):
            result = _open_multiline_editor("Preamble:")

        assert result == ""
        assert mock_stdin.readline.call_count == 1


# ===========================================================================
# Tests for _collect_guided_answers()
# ===========================================================================


class TestCollectGuidedAnswers:
    """Tests for the _collect_guided_answers() helper in ralph/run.py."""

    _QUESTIONS = [
        {"id": 1, "question": "Auth method?", "options": ["Email only", "OAuth only", "Both"]},
        {"id": 2, "question": "Error display?", "options": ["Inline", "Banner"]},
    ]

    def _make_non_tty_stdin(self, readline_responses: list[str]) -> MagicMock:
        mock = MagicMock()
        mock.isatty.return_value = False
        mock.readline.side_effect = readline_responses
        return mock

    def test_valid_in_range_selection_returns_correct_json(self):
        """Selecting a valid option number returns JSON with matching answer text."""
        mock_stdin = self._make_non_tty_stdin(["2\n", "1\n"])  # Q1→"OAuth only", Q2→"Inline"

        with patch("sys.stdin", mock_stdin):
            result = _collect_guided_answers(self._QUESTIONS)

        pairs = json.loads(result)
        assert len(pairs) == 2
        assert pairs[0] == {"question": "Auth method?", "answer": "OAuth only"}
        assert pairs[1] == {"question": "Error display?", "answer": "Inline"}

    def test_out_of_range_selection_reprompts_then_accepts_valid(self):
        """Out-of-range input triggers re-prompt; the subsequent valid input is accepted."""
        # 4 options total (3 + Describe yourself...), so 5 is out of range; then 3 is valid
        mock_stdin = self._make_non_tty_stdin(["5\n", "3\n", "2\n"])

        with patch("sys.stdin", mock_stdin):
            result = _collect_guided_answers(self._QUESTIONS)

        pairs = json.loads(result)
        assert pairs[0]["answer"] == "Both"

    def test_non_integer_input_reprompts_then_accepts_valid(self, capsys):
        """Non-integer input triggers re-prompt."""
        mock_stdin = self._make_non_tty_stdin(["abc\n", "1\n", "1\n"])

        with patch("sys.stdin", mock_stdin):
            result = _collect_guided_answers(self._QUESTIONS)

        pairs = json.loads(result)
        assert pairs[0]["answer"] == "Email only"

    def test_describe_yourself_selection_opens_editor(self):
        """Selecting 'Describe yourself...' calls _open_multiline_editor and uses its result."""
        # Q1 has 3 options + "Describe yourself..." = option 4
        # Q2: select option 1
        mock_stdin = self._make_non_tty_stdin([
            "4\n",           # Q1: select "Describe yourself..."
            "custom text\n", # editor: first line
            ".\n",           # editor: sentinel (submit)
            "1\n",           # Q2: select "Inline"
        ])

        with patch("sys.stdin", mock_stdin):
            result = _collect_guided_answers(self._QUESTIONS)

        pairs = json.loads(result)
        assert pairs[0] == {"question": "Auth method?", "answer": "custom text"}
        assert pairs[1] == {"question": "Error display?", "answer": "Inline"}

    def test_ctrl_c_during_selection_exits_zero(self):
        """KeyboardInterrupt during selection prints message and calls sys.exit(0)."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        mock_stdin.readline.side_effect = KeyboardInterrupt()

        with patch("sys.stdin", mock_stdin):
            with pytest.raises(SystemExit) as exc_info:
                _collect_guided_answers(self._QUESTIONS)

        assert exc_info.value.code == 0

    def test_ctrl_c_message_printed(self, capsys):
        """KeyboardInterrupt prints the stopping message before exiting."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        mock_stdin.readline.side_effect = KeyboardInterrupt()

        with patch("sys.stdin", mock_stdin):
            with pytest.raises(SystemExit):
                _collect_guided_answers(self._QUESTIONS)

        captured = capsys.readouterr()
        assert "I'm gonna stop the interview now" in captured.out

    def test_result_is_valid_json_string(self):
        """Return value is always a valid JSON-encoded string."""
        mock_stdin = self._make_non_tty_stdin(["1\n", "1\n"])

        with patch("sys.stdin", mock_stdin):
            result = _collect_guided_answers(self._QUESTIONS)

        # Should parse without raising
        parsed = json.loads(result)
        assert isinstance(parsed, list)

    def test_single_question_single_answer(self):
        """Single question with one valid selection returns a single-element JSON array."""
        questions = [{"id": 1, "question": "Pick one?", "options": ["Yes", "No"]}]
        mock_stdin = self._make_non_tty_stdin(["2\n"])  # select "No"

        with patch("sys.stdin", mock_stdin):
            result = _collect_guided_answers(questions)

        pairs = json.loads(result)
        assert pairs == [{"question": "Pick one?", "answer": "No"}]


# ===========================================================================
# Tests for run_interview_loop() — guided and fallback branches
# ===========================================================================


class TestRunInterviewLoop:
    """Tests for the two code paths in Runner.run_interview_loop()."""

    def _make_runner(self) -> Runner:
        return Runner("test-project")

    def _mock_noninteractive(self, stdout: str = "", returncode: int = 0) -> MagicMock:
        m = MagicMock()
        m.stdout = stdout
        m.returncode = returncode
        m.stderr = ""
        return m

    def test_guided_path_calls_collect_guided_answers(self):
        """Guided path: _collect_guided_answers is called when _parse_questions_json succeeds."""
        runner = self._make_runner()
        questions_data = [{"id": 1, "question": "Q?", "options": ["A", "B"]}]
        qa_json_str = json.dumps([{"question": "Q?", "answer": "A"}])

        q_result = self._mock_noninteractive(stdout="raw json output")
        amend_result = self._mock_noninteractive()
        make_amend_fn = MagicMock(return_value="amend-prompt")

        with (
            patch("ralph.run.run_noninteractive", side_effect=[q_result, amend_result]),
            patch("ralph.run._parse_questions_json", return_value=questions_data),
            patch("ralph.run._collect_guided_answers", return_value=qa_json_str) as mock_guided,
        ):
            runner.run_interview_loop(["q-prompt"], [make_amend_fn])

        mock_guided.assert_called_once_with(questions_data)

    def test_guided_path_passes_qa_json_to_amend_fn(self):
        """Guided path: make_amend_prompts[i] is called with the qa_json from _collect_guided_answers."""
        runner = self._make_runner()
        questions_data = [{"id": 1, "question": "Q?", "options": ["A"]}]
        qa_json_str = json.dumps([{"question": "Q?", "answer": "A"}])

        q_result = self._mock_noninteractive(stdout="raw output")
        amend_result = self._mock_noninteractive()
        make_amend_fn = MagicMock(return_value="amend-prompt")

        with (
            patch("ralph.run.run_noninteractive", side_effect=[q_result, amend_result]),
            patch("ralph.run._parse_questions_json", return_value=questions_data),
            patch("ralph.run._collect_guided_answers", return_value=qa_json_str),
        ):
            runner.run_interview_loop(["q-prompt"], [make_amend_fn])

        make_amend_fn.assert_called_once_with(qa_json_str)

    def test_fallback_path_triggered_when_parse_returns_none(self, capsys):
        """Fallback path: activates when _parse_questions_json returns None."""
        runner = self._make_runner()
        raw_questions = "1. What auth?\n2. What layout?"
        free_form = "My free-form answer"

        q_result = self._mock_noninteractive(stdout=raw_questions)
        amend_result = self._mock_noninteractive()
        make_amend_fn = MagicMock(return_value="amend-prompt")

        with (
            patch("ralph.run.run_noninteractive", side_effect=[q_result, amend_result]),
            patch("ralph.run._parse_questions_json", return_value=None),
            patch("ralph.run._collect_user_answers", return_value=free_form),
        ):
            runner.run_interview_loop(["q-prompt"], [make_amend_fn])

        captured = capsys.readouterr()
        assert "couldn't make the questions come out right" in captured.out

    def test_fallback_path_wraps_in_json_and_passes_to_amend_fn(self):
        """Fallback path: amend fn receives JSON-wrapped raw output + free-form answer."""
        runner = self._make_runner()
        raw_questions = "1. Question one?\n2. Question two?"
        free_form = "My free-form answer"

        q_result = self._mock_noninteractive(stdout=raw_questions)
        amend_result = self._mock_noninteractive()
        make_amend_fn = MagicMock(return_value="amend-prompt")

        with (
            patch("ralph.run.run_noninteractive", side_effect=[q_result, amend_result]),
            patch("ralph.run._parse_questions_json", return_value=None),
            patch("ralph.run._collect_user_answers", return_value=free_form),
        ):
            runner.run_interview_loop(["q-prompt"], [make_amend_fn])

        expected_qa_json = json.dumps([{"question": raw_questions.strip(), "answer": free_form}])
        make_amend_fn.assert_called_once_with(expected_qa_json)

    def test_fallback_path_triggered_when_parse_returns_empty_list(self, capsys):
        """Fallback path: activates when _parse_questions_json returns [] (empty list is falsy)."""
        runner = self._make_runner()
        free_form = "free-form answer"

        q_result = self._mock_noninteractive(stdout='{"questions": []}')
        amend_result = self._mock_noninteractive()
        make_amend_fn = MagicMock(return_value="amend-prompt")

        with (
            patch("ralph.run.run_noninteractive", side_effect=[q_result, amend_result]),
            patch("ralph.run._parse_questions_json", return_value=[]),
            patch("ralph.run._collect_user_answers", return_value=free_form),
        ):
            runner.run_interview_loop(["q-prompt"], [make_amend_fn])

        captured = capsys.readouterr()
        assert "couldn't make the questions come out right" in captured.out

    def test_guided_path_not_called_on_fallback(self):
        """_collect_guided_answers must not be called on the fallback path."""
        runner = self._make_runner()

        q_result = self._mock_noninteractive(stdout="plain text")
        amend_result = self._mock_noninteractive()
        make_amend_fn = MagicMock(return_value="amend-prompt")

        with (
            patch("ralph.run.run_noninteractive", side_effect=[q_result, amend_result]),
            patch("ralph.run._parse_questions_json", return_value=None),
            patch("ralph.run._collect_user_answers", return_value="answer"),
            patch("ralph.run._collect_guided_answers") as mock_guided,
        ):
            runner.run_interview_loop(["q-prompt"], [make_amend_fn])

        mock_guided.assert_not_called()

    def test_multiple_rounds_each_uses_correct_amend_fn(self):
        """With multiple rounds, each round's amend fn is called with that round's qa_json."""
        runner = self._make_runner()
        questions_round1 = [{"id": 1, "question": "Q1?", "options": ["A"]}]
        questions_round2 = [{"id": 1, "question": "Q2?", "options": ["B"]}]
        qa_json_round1 = json.dumps([{"question": "Q1?", "answer": "A"}])
        qa_json_round2 = json.dumps([{"question": "Q2?", "answer": "B"}])

        mock_results = [
            self._mock_noninteractive(stdout="raw1"),
            self._mock_noninteractive(),
            self._mock_noninteractive(stdout="raw2"),
            self._mock_noninteractive(),
        ]
        make_amend_fn1 = MagicMock(return_value="amend1")
        make_amend_fn2 = MagicMock(return_value="amend2")

        with (
            patch("ralph.run.run_noninteractive", side_effect=mock_results),
            patch("ralph.run._parse_questions_json", side_effect=[questions_round1, questions_round2]),
            patch("ralph.run._collect_guided_answers", side_effect=[qa_json_round1, qa_json_round2]),
        ):
            runner.run_interview_loop(
                ["q-prompt1", "q-prompt2"],
                [make_amend_fn1, make_amend_fn2],
            )

        make_amend_fn1.assert_called_once_with(qa_json_round1)
        make_amend_fn2.assert_called_once_with(qa_json_round2)
