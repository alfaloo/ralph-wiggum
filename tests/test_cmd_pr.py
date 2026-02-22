"""Unit tests for ralph pr command (cmd_pr)."""

import argparse
import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from ralph.cli import cmd_pr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(project_name="my-project", provider=None):
    """Build a minimal Namespace for cmd_pr."""
    return argparse.Namespace(project_name=project_name, provider=provider)


def _ok(stdout="", stderr=""):
    """Return a mock subprocess result with returncode=0."""
    m = MagicMock()
    m.returncode = 0
    m.stdout = stdout
    m.stderr = stderr
    return m


def _fail(stdout="", stderr="error"):
    """Return a mock subprocess result with returncode=1."""
    m = MagicMock()
    m.returncode = 1
    m.stdout = stdout
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# Subprocess side-effect factories
# ---------------------------------------------------------------------------


def _make_github_run(
    project_name="my-project",
    branch_stdout=None,
    tree_dirty=False,
    merge_base_ok=True,
    push_ok=True,
    gh_version_ok=True,
    pr_create_ok=True,
    pr_create_stdout="https://github.com/owner/repo/pull/1",
):
    """Return a side_effect for subprocess.run covering the GitHub path."""
    if branch_stdout is None:
        branch_stdout = project_name

    def _run(cmd, **kwargs):
        if cmd == ["gh", "--version"]:
            return _ok() if gh_version_ok else _fail()
        if cmd == ["git", "branch", "--show-current"]:
            return _ok(stdout=branch_stdout)
        if cmd == ["git", "status", "--porcelain"]:
            return _ok(stdout="M dirty.txt" if tree_dirty else "")
        if len(cmd) >= 2 and cmd[:2] == ["git", "merge-base"]:
            return _ok(stdout="abc123") if merge_base_ok else _fail()
        if len(cmd) >= 3 and cmd[:3] == ["git", "push", "-u"]:
            return _ok() if push_ok else _fail(stderr="push failed")
        if cmd[0] == "gh":
            return _ok(stdout=pr_create_stdout) if pr_create_ok else _fail(stderr="create failed")
        return _ok()

    return _run


def _make_gitlab_run(
    project_name="my-project",
    branch_stdout=None,
    tree_dirty=False,
    push_ok=True,
    glab_version_ok=True,
    mr_create_ok=True,
    mr_create_stdout="https://gitlab.com/owner/repo/-/merge_requests/1",
):
    """Return a side_effect for subprocess.run covering the GitLab path."""
    if branch_stdout is None:
        branch_stdout = project_name

    def _run(cmd, **kwargs):
        if cmd == ["glab", "--version"]:
            return _ok() if glab_version_ok else _fail()
        if cmd == ["git", "branch", "--show-current"]:
            return _ok(stdout=branch_stdout)
        if cmd == ["git", "status", "--porcelain"]:
            return _ok(stdout="M dirty.txt" if tree_dirty else "")
        if len(cmd) >= 3 and cmd[:3] == ["git", "push", "-u"]:
            return _ok() if push_ok else _fail(stderr="push failed")
        if cmd[0] == "glab":
            return _ok(stdout=mr_create_stdout) if mr_create_ok else _fail(stderr="create failed")
        return _ok()

    return _run


# ===========================================================================
# Core functionality — GitHub (happy path)
# ===========================================================================


class TestCmdPrHappyPathGitHub:
    def test_creates_pr_and_prints_success(self, capsys):
        """All preconditions met: gh installed, branch matches, clean tree, merge base ok,
        pr-description.md exists, push succeeds, gh pr create succeeds."""
        project_name = "my-project"
        args = _make_args(project_name=project_name, provider="github")
        pr_body = "## My PR\nSome description."

        with patch("ralph.cli.subprocess.run", side_effect=_make_github_run(project_name=project_name)), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("builtins.open", mock_open(read_data=pr_body)):
            cmd_pr(args)

        captured = capsys.readouterr()
        assert "Pull request created successfully" in captured.out

    def test_calls_gh_pr_create_with_correct_args(self):
        """Verifies 'gh pr create' is called with --title, --body, --base, --head."""
        project_name = "my-project"
        args = _make_args(project_name=project_name, provider="github")
        pr_body = "## My PR"
        calls = []

        def mock_run(cmd, **kwargs):
            calls.append(list(cmd))
            return _make_github_run(project_name=project_name)(cmd, **kwargs)

        with patch("ralph.cli.subprocess.run", side_effect=mock_run), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("builtins.open", mock_open(read_data=pr_body)):
            cmd_pr(args)

        gh_create_calls = [c for c in calls if c[:3] == ["gh", "pr", "create"]]
        assert len(gh_create_calls) == 1
        call_args = gh_create_calls[0]
        assert "--title" in call_args
        assert project_name in call_args
        assert "--body" in call_args
        assert "--base" in call_args
        assert "main" in call_args
        assert "--head" in call_args

    def test_pushes_branch_before_creating_pr(self):
        """'git push -u origin <project-name>' is called before 'gh pr create'."""
        project_name = "my-project"
        args = _make_args(project_name=project_name, provider="github")
        call_order = []

        def mock_run(cmd, **kwargs):
            if len(cmd) >= 3 and cmd[:3] == ["git", "push", "-u"]:
                call_order.append("push")
            elif cmd[:3] == ["gh", "pr", "create"]:
                call_order.append("pr_create")
            return _make_github_run(project_name=project_name)(cmd, **kwargs)

        with patch("ralph.cli.subprocess.run", side_effect=mock_run), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("builtins.open", mock_open(read_data="# PR")):
            cmd_pr(args)

        assert call_order == ["push", "pr_create"]

    def test_reads_pr_description_body(self):
        """The pr-description.md content is passed as --body to gh pr create."""
        project_name = "my-project"
        args = _make_args(project_name=project_name, provider="github")
        pr_body = "## Custom PR Body\n\nDetailed description here."
        calls = []

        def mock_run(cmd, **kwargs):
            calls.append(list(cmd))
            return _make_github_run(project_name=project_name)(cmd, **kwargs)

        with patch("ralph.cli.subprocess.run", side_effect=mock_run), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("builtins.open", mock_open(read_data=pr_body)):
            cmd_pr(args)

        gh_create = next(c for c in calls if c[:3] == ["gh", "pr", "create"])
        body_idx = gh_create.index("--body")
        assert gh_create[body_idx + 1] == pr_body


# ===========================================================================
# Core functionality — GitLab (happy path)
# ===========================================================================


class TestCmdPrHappyPathGitLab:
    def test_creates_mr_and_prints_success(self, capsys):
        """All preconditions met for GitLab: glab installed, branch matches, clean tree,
        pr-description.md exists, push ok, glab mr create succeeds."""
        project_name = "my-project"
        args = _make_args(project_name=project_name, provider="gitlab")
        pr_body = "## My MR"

        with patch("ralph.cli.subprocess.run", side_effect=_make_gitlab_run(project_name=project_name)), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("builtins.open", mock_open(read_data=pr_body)):
            cmd_pr(args)

        captured = capsys.readouterr()
        assert "Merge request created successfully" in captured.out

    def test_calls_glab_mr_create_with_correct_args(self):
        """Verifies 'glab mr create' is called with --title, --description, --source-branch,
        --target-branch."""
        project_name = "my-project"
        args = _make_args(project_name=project_name, provider="gitlab")
        pr_body = "## My MR"
        calls = []

        def mock_run(cmd, **kwargs):
            calls.append(list(cmd))
            return _make_gitlab_run(project_name=project_name)(cmd, **kwargs)

        with patch("ralph.cli.subprocess.run", side_effect=mock_run), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("builtins.open", mock_open(read_data=pr_body)):
            cmd_pr(args)

        glab_create = [c for c in calls if c[:3] == ["glab", "mr", "create"]]
        assert len(glab_create) == 1
        call_args = glab_create[0]
        assert "--title" in call_args
        assert project_name in call_args
        assert "--description" in call_args
        assert "--source-branch" in call_args
        assert "--target-branch" in call_args
        assert "main" in call_args


# ===========================================================================
# Failcase — project does not exist
# ===========================================================================


class TestCmdPrProjectNotExist:
    def test_project_directory_missing_exits(self, capsys):
        """Exits with code 1 when the project directory does not exist."""
        args = _make_args(project_name="nonexistent-project", provider="github")

        with patch("ralph.cli.os.path.exists", return_value=False), \
             pytest.raises(SystemExit) as exc_info:
            cmd_pr(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "nonexistent-project" in captured.err

    def test_spec_md_missing_exits(self, capsys):
        """Exits with code 1 when project dir exists but spec.md is absent."""
        project_name = "my-project"
        args = _make_args(project_name=project_name, provider="github")
        ralph_dir = os.path.join(".ralph", project_name)

        def mock_exists(path):
            if path == ralph_dir:
                return True  # project dir present
            return False  # spec.md and everything else missing

        with patch("ralph.cli.os.path.exists", side_effect=mock_exists), \
             pytest.raises(SystemExit) as exc_info:
            cmd_pr(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "spec.md" in captured.err


# ===========================================================================
# Failcase — provider CLI not installed
# ===========================================================================


class TestCmdPrCliNotInstalled:
    def test_gh_cli_not_installed_exits(self, capsys):
        """Exits with code 1 and prints a helpful message when 'gh --version' fails."""
        project_name = "my-project"
        args = _make_args(project_name=project_name, provider="github")

        with patch("ralph.cli.subprocess.run", side_effect=_make_github_run(gh_version_ok=False)), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             pytest.raises(SystemExit) as exc_info:
            cmd_pr(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "gh" in captured.err

    def test_glab_cli_not_installed_exits(self, capsys):
        """Exits with code 1 and prints a helpful message when 'glab --version' fails."""
        project_name = "my-project"
        args = _make_args(project_name=project_name, provider="gitlab")

        with patch("ralph.cli.subprocess.run", side_effect=_make_gitlab_run(glab_version_ok=False)), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             pytest.raises(SystemExit) as exc_info:
            cmd_pr(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "glab" in captured.err


# ===========================================================================
# Failcase — current branch does not match project name
# ===========================================================================


class TestCmdPrBranchMismatch:
    def test_github_branch_mismatch_exits(self, capsys):
        """Exits with code 1 when the current git branch differs from the project name
        (GitHub)."""
        project_name = "my-project"
        args = _make_args(project_name=project_name, provider="github")

        with patch(
            "ralph.cli.subprocess.run",
            side_effect=_make_github_run(project_name=project_name, branch_stdout="some-other-branch"),
        ), patch("ralph.cli.os.path.exists", return_value=True), \
             pytest.raises(SystemExit) as exc_info:
            cmd_pr(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "some-other-branch" in captured.err or "does not match" in captured.err

    def test_gitlab_branch_mismatch_exits(self, capsys):
        """Exits with code 1 when the current git branch differs from the project name
        (GitLab)."""
        project_name = "my-project"
        args = _make_args(project_name=project_name, provider="gitlab")

        with patch(
            "ralph.cli.subprocess.run",
            side_effect=_make_gitlab_run(project_name=project_name, branch_stdout="different-branch"),
        ), patch("ralph.cli.os.path.exists", return_value=True), \
             pytest.raises(SystemExit) as exc_info:
            cmd_pr(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "different-branch" in captured.err or "does not match" in captured.err


# ===========================================================================
# Failcase — dirty working tree
# ===========================================================================


class TestCmdPrDirtyWorkingTree:
    def test_github_dirty_tree_exits(self, capsys):
        """Exits with code 1 when there are uncommitted changes (GitHub)."""
        project_name = "my-project"
        args = _make_args(project_name=project_name, provider="github")

        with patch(
            "ralph.cli.subprocess.run",
            side_effect=_make_github_run(project_name=project_name, tree_dirty=True),
        ), patch("ralph.cli.os.path.exists", return_value=True), \
             pytest.raises(SystemExit) as exc_info:
            cmd_pr(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "uncommitted" in captured.err.lower()

    def test_gitlab_dirty_tree_exits(self, capsys):
        """Exits with code 1 when there are uncommitted changes (GitLab)."""
        project_name = "my-project"
        args = _make_args(project_name=project_name, provider="gitlab")

        with patch(
            "ralph.cli.subprocess.run",
            side_effect=_make_gitlab_run(project_name=project_name, tree_dirty=True),
        ), patch("ralph.cli.os.path.exists", return_value=True), \
             pytest.raises(SystemExit) as exc_info:
            cmd_pr(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "uncommitted" in captured.err.lower()


# ===========================================================================
# Failcase — pr-description.md missing
# ===========================================================================


class TestCmdPrDescriptionMissing:
    def test_github_pr_description_missing_exits(self, capsys):
        """Exits with code 1 when pr-description.md does not exist (GitHub)."""
        project_name = "my-project"
        args = _make_args(project_name=project_name, provider="github")
        pr_desc_path = os.path.join(".ralph", project_name, "pr-description.md")

        def mock_exists(path):
            return path != pr_desc_path  # False only for pr-description.md

        with patch("ralph.cli.subprocess.run", side_effect=_make_github_run(project_name=project_name)), \
             patch("ralph.cli.os.path.exists", side_effect=mock_exists), \
             patch("ralph.cli.get_base", return_value="main"), \
             pytest.raises(SystemExit) as exc_info:
            cmd_pr(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "pr-description.md" in captured.err

    def test_gitlab_pr_description_missing_exits(self, capsys):
        """Exits with code 1 when pr-description.md does not exist (GitLab)."""
        project_name = "my-project"
        args = _make_args(project_name=project_name, provider="gitlab")
        pr_desc_path = os.path.join(".ralph", project_name, "pr-description.md")

        def mock_exists(path):
            return path != pr_desc_path  # False only for pr-description.md

        with patch("ralph.cli.subprocess.run", side_effect=_make_gitlab_run(project_name=project_name)), \
             patch("ralph.cli.os.path.exists", side_effect=mock_exists), \
             patch("ralph.cli.get_base", return_value="main"), \
             pytest.raises(SystemExit) as exc_info:
            cmd_pr(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "pr-description.md" in captured.err


# ===========================================================================
# Failcase — no merge base (GitHub only)
# ===========================================================================


class TestCmdPrMergeBaseMissing:
    def test_no_merge_base_exits(self, capsys):
        """Exits with code 1 when 'git merge-base' fails (GitHub)."""
        project_name = "my-project"
        args = _make_args(project_name=project_name, provider="github")

        with patch(
            "ralph.cli.subprocess.run",
            side_effect=_make_github_run(project_name=project_name, merge_base_ok=False),
        ), patch("ralph.cli.os.path.exists", return_value=True), \
             patch("ralph.cli.get_base", return_value="main"), \
             pytest.raises(SystemExit) as exc_info:
            cmd_pr(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "merge" in captured.err.lower()


# ===========================================================================
# Provider flag — --provider gitlab uses glab, --provider github uses gh
# ===========================================================================


class TestCmdPrProviderFlag:
    def test_provider_gitlab_uses_glab_not_gh(self):
        """When --provider gitlab is passed, glab commands are invoked, not gh."""
        project_name = "my-project"
        args = _make_args(project_name=project_name, provider="gitlab")
        calls = []

        def mock_run(cmd, **kwargs):
            calls.append(tuple(cmd))
            return _make_gitlab_run(project_name=project_name)(cmd, **kwargs)

        with patch("ralph.cli.subprocess.run", side_effect=mock_run), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("builtins.open", mock_open(read_data="## MR")):
            cmd_pr(args)

        glab_calls = [c for c in calls if c[0] == "glab"]
        gh_calls = [c for c in calls if c[0] == "gh"]
        assert len(glab_calls) >= 1
        assert gh_calls == []

    def test_provider_github_uses_gh_not_glab(self):
        """When --provider github is passed, gh commands are invoked, not glab."""
        project_name = "my-project"
        args = _make_args(project_name=project_name, provider="github")
        calls = []

        def mock_run(cmd, **kwargs):
            calls.append(tuple(cmd))
            return _make_github_run(project_name=project_name)(cmd, **kwargs)

        with patch("ralph.cli.subprocess.run", side_effect=mock_run), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("builtins.open", mock_open(read_data="## PR")):
            cmd_pr(args)

        gh_calls = [c for c in calls if c[0] == "gh"]
        glab_calls = [c for c in calls if c[0] == "glab"]
        assert len(gh_calls) >= 1
        assert glab_calls == []

    def test_provider_defaults_to_github_when_not_set(self):
        """When provider is not passed in args, it falls back to the persisted setting."""
        project_name = "my-project"
        # provider=None → _resolve_provider calls get_provider()
        args = _make_args(project_name=project_name, provider=None)
        calls = []

        def mock_run(cmd, **kwargs):
            calls.append(tuple(cmd))
            return _make_github_run(project_name=project_name)(cmd, **kwargs)

        with patch("ralph.cli.subprocess.run", side_effect=mock_run), \
             patch("ralph.cli.os.path.exists", return_value=True), \
             patch("ralph.cli.get_base", return_value="main"), \
             patch("ralph.cli.get_provider", return_value="github"), \
             patch("builtins.open", mock_open(read_data="## PR")):
            cmd_pr(args)

        gh_calls = [c for c in calls if c[0] == "gh"]
        assert len(gh_calls) >= 1
