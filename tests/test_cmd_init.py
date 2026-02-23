"""Unit tests for ralph/cli.py — cmd_init / ralph init subcommand."""

import argparse
import json
from unittest.mock import MagicMock, patch

import pytest

from ralph.cli import cmd_init


def _make_args(project_name: str, verbose: str | None = None) -> argparse.Namespace:
    """Build a minimal Namespace that cmd_init expects."""
    return argparse.Namespace(project_name=project_name, verbose=verbose)


def _git_branch_result(branch: str) -> MagicMock:
    """Return a mock CompletedProcess for 'git branch --show-current'."""
    m = MagicMock()
    m.returncode = 0
    m.stdout = f"{branch}\n"
    return m


# ===========================================================================
# Core functionality
# ===========================================================================


class TestCmdInitCore:
    def test_creates_project_directory(self, tmp_path, monkeypatch):
        """cmd_init creates the .ralph/<project-name>/ directory."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("ralph.commands.subprocess.run", return_value=_git_branch_result("main")),
            patch("ralph.commands.ensure_defaults"),
            patch("ralph.commands.get_base", return_value="main"),
        ):
            cmd_init(_make_args("myproject"))

        assert (tmp_path / ".ralph" / "myproject").is_dir()

    def test_creates_spec_md(self, tmp_path, monkeypatch):
        """cmd_init writes spec.md inside the project directory."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("ralph.commands.subprocess.run", return_value=_git_branch_result("main")),
            patch("ralph.commands.ensure_defaults"),
            patch("ralph.commands.get_base", return_value="main"),
        ):
            cmd_init(_make_args("myproject"))

        spec_path = tmp_path / ".ralph" / "myproject" / "spec.md"
        assert spec_path.exists()
        assert "myproject" in spec_path.read_text()

    def test_creates_state_json_as_empty_list(self, tmp_path, monkeypatch):
        """cmd_init writes state.json as an empty JSON list."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("ralph.commands.subprocess.run", return_value=_git_branch_result("main")),
            patch("ralph.commands.ensure_defaults"),
            patch("ralph.commands.get_base", return_value="main"),
        ):
            cmd_init(_make_args("myproject"))

        state = json.loads((tmp_path / ".ralph" / "myproject" / "state.json").read_text())
        assert state == []

    def test_creates_obstacles_json(self, tmp_path, monkeypatch):
        """cmd_init writes obstacles.json with an empty obstacles list."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("ralph.commands.subprocess.run", return_value=_git_branch_result("main")),
            patch("ralph.commands.ensure_defaults"),
            patch("ralph.commands.get_base", return_value="main"),
        ):
            cmd_init(_make_args("myproject"))

        obstacles = json.loads(
            (tmp_path / ".ralph" / "myproject" / "obstacles.json").read_text()
        )
        assert obstacles == {"obstacles": []}

    def test_creates_tasks_json_as_empty_dict(self, tmp_path, monkeypatch):
        """cmd_init writes tasks.json as an empty JSON dict."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("ralph.commands.subprocess.run", return_value=_git_branch_result("main")),
            patch("ralph.commands.ensure_defaults"),
            patch("ralph.commands.get_base", return_value="main"),
        ):
            cmd_init(_make_args("myproject"))

        tasks = json.loads((tmp_path / ".ralph" / "myproject" / "tasks.json").read_text())
        assert tasks == {}

    def test_calls_ensure_defaults(self, tmp_path, monkeypatch):
        """cmd_init calls ensure_defaults() to initialise settings.json."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("ralph.commands.subprocess.run", return_value=_git_branch_result("main")),
            patch("ralph.commands.ensure_defaults") as mock_ensure,
            patch("ralph.commands.get_base", return_value="main"),
        ):
            cmd_init(_make_args("myproject"))

        mock_ensure.assert_called_once()

    def test_all_expected_files_created(self, tmp_path, monkeypatch):
        """cmd_init creates exactly the four expected project files."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("ralph.commands.subprocess.run", return_value=_git_branch_result("main")),
            patch("ralph.commands.ensure_defaults"),
            patch("ralph.commands.get_base", return_value="main"),
        ):
            cmd_init(_make_args("myproject"))

        project_dir = tmp_path / ".ralph" / "myproject"
        for filename in ("spec.md", "state.json", "obstacles.json", "tasks.json"):
            assert (project_dir / filename).exists(), f"Expected {filename} to be created"


# ===========================================================================
# Failcase — project already exists
# ===========================================================================


class TestCmdInitProjectAlreadyExists:
    def test_aborts_when_project_directory_exists(self, tmp_path, monkeypatch):
        """cmd_init exits with status 1 if the project directory already exists."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ralph" / "myproject").mkdir(parents=True)

        with pytest.raises(SystemExit) as exc_info:
            cmd_init(_make_args("myproject"))

        assert exc_info.value.code == 1

    def test_prints_error_message_when_project_exists(self, tmp_path, monkeypatch, capsys):
        """cmd_init prints an error message to stderr when the project already exists."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ralph" / "myproject").mkdir(parents=True)

        with pytest.raises(SystemExit):
            cmd_init(_make_args("myproject"))

        captured = capsys.readouterr()
        assert "already exists" in captured.err
        assert "myproject" in captured.err

    def test_does_not_overwrite_existing_project_files(self, tmp_path, monkeypatch):
        """cmd_init leaves existing project files untouched when the project exists."""
        monkeypatch.chdir(tmp_path)
        project_dir = tmp_path / ".ralph" / "myproject"
        project_dir.mkdir(parents=True)
        sentinel = project_dir / "sentinel.txt"
        sentinel.write_text("original content")

        with pytest.raises(SystemExit):
            cmd_init(_make_args("myproject"))

        assert sentinel.read_text() == "original content"


# ===========================================================================
# Failcase — branch mismatch warning
# ===========================================================================


class TestCmdInitBranchMismatch:
    def test_warns_when_current_branch_differs_from_base(self, tmp_path, monkeypatch, capsys):
        """cmd_init warns the user when the current git branch differs from the base branch."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("ralph.commands.subprocess.run", return_value=_git_branch_result("feature-x")),
            patch("ralph.commands.ensure_defaults"),
            patch("ralph.commands.get_base", return_value="main"),
            patch("builtins.input", return_value="n"),
        ):
            cmd_init(_make_args("myproject"))

        captured = capsys.readouterr()
        assert "feature-x" in captured.out
        assert "main" in captured.out

    def test_no_warning_when_branch_matches_base(self, tmp_path, monkeypatch, capsys):
        """cmd_init does not print a mismatch warning when branch matches the base."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("ralph.commands.subprocess.run", return_value=_git_branch_result("main")),
            patch("ralph.commands.ensure_defaults"),
            patch("ralph.commands.get_base", return_value="main"),
        ):
            cmd_init(_make_args("myproject"))

        captured = capsys.readouterr()
        assert "Heads up" not in captured.out
        assert "Heads up" not in captured.err

    def test_updates_base_branch_when_user_confirms(self, tmp_path, monkeypatch):
        """cmd_init updates the persisted base branch when the user answers 'y'."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("ralph.commands.subprocess.run", return_value=_git_branch_result("feature-x")),
            patch("ralph.commands.ensure_defaults"),
            patch("ralph.commands.get_base", return_value="main"),
            patch("ralph.commands.set_base") as mock_set_base,
            patch("builtins.input", return_value="y"),
        ):
            cmd_init(_make_args("myproject"))

        mock_set_base.assert_called_once_with("feature-x")

    def test_does_not_update_base_branch_when_user_declines(self, tmp_path, monkeypatch):
        """cmd_init does not update the base branch when the user answers 'n'."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("ralph.commands.subprocess.run", return_value=_git_branch_result("feature-x")),
            patch("ralph.commands.ensure_defaults"),
            patch("ralph.commands.get_base", return_value="main"),
            patch("ralph.commands.set_base") as mock_set_base,
            patch("builtins.input", return_value="n"),
        ):
            cmd_init(_make_args("myproject"))

        mock_set_base.assert_not_called()

    def test_no_warning_when_git_returns_empty_branch(self, tmp_path, monkeypatch, capsys):
        """cmd_init skips the branch check when git returns an empty branch name."""
        monkeypatch.chdir(tmp_path)
        empty_result = MagicMock()
        empty_result.returncode = 0
        empty_result.stdout = ""

        with (
            patch("ralph.commands.subprocess.run", return_value=empty_result),
            patch("ralph.commands.ensure_defaults"),
            patch("ralph.commands.get_base", return_value="main"),
        ):
            cmd_init(_make_args("myproject"))

        captured = capsys.readouterr()
        assert "Heads up" not in captured.out
        assert "Heads up" not in captured.err
