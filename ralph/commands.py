"""Command implementations for Ralph Wiggum CLI.

Each public class corresponds to a ralph subcommand and owns its own
precondition checks and runner call, keeping all orchestration logic in
one place per command.
"""

from __future__ import annotations

import abc
import argparse
import json
import os
import re
import subprocess
import sys
from typing import Callable

from ralph.config import (
    ensure_defaults,
    get_asynchronous,
    get_base,
    get_limit,
    get_provider,
    get_rounds,
    get_single,
    get_verbose,
    set_base,
)
from ralph.parse import (
    parse_generate_tasks_md,
    parse_questions_md,
    parse_retry_md,
    parse_validate_md,
)
from ralph.run import Runner


_DEFAULT_LIMIT = 20

_ENRICH_COMMENT = (
    "You are an expert software engineer reviewing this project for the first time. "
    "Carefully read spec.md and all relevant source files, tests, and configuration in the "
    "codebase to gain a thorough understanding of the problem domain and existing implementation "
    "patterns. Then, enhance spec.md in-place by filling in any missing context, clarifying "
    "ambiguous requirements, and adding technical details implied by the existing code — "
    "ensuring the specification is precise and complete enough to drive accurate task "
    "generation. Do not remove any existing content that remains valid."
)

_SPEC_MD_TEMPLATE = """\
# {project_name} — Project Spec

## Overview
<!-- Describe the project in 1-3 sentences -->

## Goals
<!-- What should this project accomplish? -->

## Requirements
<!-- List the key requirements or features -->

## Out of Scope
<!-- What is explicitly NOT part of this project? -->

## Technical Notes
<!-- Any specific technologies, libraries, constraints, or design decisions -->
"""

_TEST_INSTRUCTIONS_TEMPLATE = """\
# Please define the instructions for how to run tests for this project
"""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _validate_branch_exists(branch: str) -> None:
    """Verify that the given branch exists in the current repo; exit if not."""
    result = subprocess.run(["git", "branch", "--list", branch], capture_output=True, text=True)
    if not result.stdout.strip():
        print(f"[ralph] Uh oh! I looked everywhere but I can't find branch '{branch}'. I'm going home now.", file=sys.stderr)
        sys.exit(1)


def _resolve_verbose(args: argparse.Namespace) -> bool:
    """Return effective verbose: per-command CLI flag > persisted setting."""
    if args.verbose is not None:
        return args.verbose == "true"
    return get_verbose()


def _resolve_asynchronous(args: argparse.Namespace) -> bool:
    """Return effective asynchronous: per-command CLI flag > persisted setting."""
    if args.asynchronous is not None:
        return args.asynchronous == "true"
    return get_asynchronous()


def _resolve_single(args: argparse.Namespace) -> bool:
    """Return effective single: per-command CLI flag > persisted setting."""
    if getattr(args, "single", None) is not None:
        return args.single == "true"
    return get_single()


def _resolve_provider(args: argparse.Namespace) -> str:
    """Return effective provider: per-command CLI flag > persisted setting."""
    if getattr(args, "provider", None) is not None:
        return args.provider
    return get_provider()


def _validate_provider_cli(provider: str) -> bool:
    """Check that the selected provider's CLI tool is installed and authenticated.

    Returns True only if the CLI is found and auth succeeds, False otherwise.
    """
    if provider == "github":
        try:
            result = subprocess.run(["gh", "auth", "status"], capture_output=True)
        except FileNotFoundError:
            print(
                "[ralph] I can't find the 'gh' thingy! "
                "You gotta get it from https://cli.github.com and then do 'gh auth login'.",
                file=sys.stderr,
            )
            return False
        if result.returncode != 0:
            print(
                "[ralph] The 'gh' thingy doesn't know who you are! "
                "Do 'gh auth login' to tell it who you are.",
                file=sys.stderr,
            )
            return False
        return True
    elif provider == "gitlab":
        try:
            result = subprocess.run(["glab", "auth", "status"], capture_output=True)
        except FileNotFoundError:
            print(
                "[ralph] I can't find the 'glab' thingy! "
                "You gotta get it from https://gitlab.com/gitlab-org/cli and then do 'glab auth login'.",
                file=sys.stderr,
            )
            return False
        if result.returncode != 0:
            print(
                "[ralph] The 'glab' thingy doesn't know who you are! "
                "Do 'glab auth login' to tell it who you are.",
                file=sys.stderr,
            )
            return False
        return True
    else:
        print(f"[ralph] I don't know what '{provider}' is! Try 'github' or 'gitlab'.", file=sys.stderr)
        return False


def _print_validate_summary(project_name: str, json_result: str | None) -> None:
    """Parse validate agent JSON output and pretty-print a summary matching ralph status style."""
    if not json_result:
        print("[ralph] Hmm, I didn't get any info back from the validation thingy. I can't show you a summary!", file=sys.stderr)
        return

    try:
        data = json.loads(json_result)
    except (json.JSONDecodeError, ValueError):
        print("[ralph] Uh oh! The validation info came back all jumbled up and I can't read it. No summary for you!", file=sys.stderr)
        return

    sep = "─" * 60
    overall_status = data.get("overall_status", "unknown")
    tasks = data.get("tasks", [])
    obstacles = data.get("obstacles", [])
    error_description = data.get("error_description", "")

    status_icon = "✓" if overall_status == "passed" else "✗"

    print()
    print(f"[ralph] Validation Summary for '{project_name}'")
    print(sep)
    print(f"[ralph] Overall Status  : {status_icon} {overall_status}")
    print(sep)

    if tasks:
        print("[ralph] Tasks")
        print(sep)
        for task in tasks:
            task_id = task.get("id", "?")
            title = task.get("title", "(no title)")
            task_status = task.get("status", "unknown")
            issue = task.get("issue", "")
            task_icon = "✓" if task_status == "completed" else "✗"
            row = f"[ralph]   {task_id:<4}  {task_icon} {task_status:<12}  {title}"
            if issue:
                row += f"  — {issue}"
            print(row)
        print(sep)

    if obstacles:
        print("[ralph] Obstacles")
        print(sep)
        for obs in obstacles:
            description = obs.get("description", "")
            resolved = obs.get("resolved", False)
            obs_icon = "✓" if resolved else "✗"
            resolved_str = "resolved" if resolved else "unresolved"
            print(f"[ralph]   {obs_icon} {resolved_str:<12}  {description}")
        print(sep)

    if overall_status in ("requires_attention", "failed") and error_description:
        print(f"[ralph] What went wrong: {error_description}")
        print(sep)

    print()


def _assert_project_exists(project_name: str) -> None:
    """Assert that the project directory and spec.md exist; exit with an error if not."""
    ralph_dir = os.path.join(".ralph", project_name)
    if not os.path.exists(ralph_dir):
        print(
            f"[ralph] I can't find project '{project_name}'! "
            f"I was looking for '{ralph_dir}' but it wasn't there. "
            "Did you forget to run 'ralph init' first?",
            file=sys.stderr,
        )
        sys.exit(1)
    spec_path = os.path.join(ralph_dir, "spec.md")
    if not os.path.exists(spec_path):
        print(
            f"[ralph] Project '{project_name}' doesn't have a 'spec.md'! "
            f"I was looking for '{spec_path}' but it wasn't there.",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Command base class
# ---------------------------------------------------------------------------


class Command(abc.ABC):
    """Base class for all Ralph Wiggum commands.

    Subclasses own their precondition checks and runner call inside execute().
    """

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args

    @abc.abstractmethod
    def execute(self) -> None:
        """Run the command."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Concrete command implementations
# ---------------------------------------------------------------------------


class InitCommand(Command):
    """ralph init — initialise a new project directory."""

    def execute(self) -> None:
        args = self.args
        project_name = args.project_name
        ralph_dir = os.path.join(".ralph", project_name)

        print(f"[ralph] Ooh, I'm making a new project called '{project_name}'!")

        if os.path.exists(ralph_dir):
            print(f"[ralph] A project called '{project_name}' already lives at '{ralph_dir}'! I can't make another one!", file=sys.stderr)
            sys.exit(1)

        os.makedirs(ralph_dir)
        print(f"[ralph] I made a brand new folder at '{ralph_dir}'!")

        spec_path = os.path.join(ralph_dir, "spec.md")
        with open(spec_path, "w") as f:
            f.write(_SPEC_MD_TEMPLATE.format(project_name=project_name))

        state_path = os.path.join(ralph_dir, "state.json")
        with open(state_path, "w") as f:
            json.dump([], f)

        obstacles_path = os.path.join(ralph_dir, "obstacles.json")
        with open(obstacles_path, "w") as f:
            json.dump({"obstacles": []}, f)

        tasks_path = os.path.join(ralph_dir, "tasks.json")
        with open(tasks_path, "w") as f:
            json.dump({}, f)

        test_instructions_path = os.path.join(ralph_dir, "test-instructions.md")
        with open(test_instructions_path, "w") as f:
            json.dump(_TEST_INSTRUCTIONS_TEMPLATE, f)

        ensure_defaults()

        # Branch mismatch check: compare current branch with the persisted base branch.
        branch_result = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
        if branch_result.returncode == 0 and branch_result.stdout.strip():
            current_branch = branch_result.stdout.strip()
            base_branch = get_base()
            if current_branch != base_branch:
                print(
                    f"[ralph] Hey! You're on branch '{current_branch}' but your base branch is '{base_branch}'. Those are different!"
                )
                while True:
                    answer = input(f"Should I change the base branch to '{current_branch}'? (y/n): ").strip().lower()
                    if answer in ("y", "yes"):
                        set_base(current_branch)
                        print(f"[ralph] Okay! I changed the base branch to '{current_branch}'!")
                        break
                    elif answer in ("n", "no"):
                        break

        print(f"[ralph] Yay! Project '{project_name}' is all set up in '{ralph_dir}'! You're all ready to go!")


class InterviewCommand(Command):
    """ralph interview — run interview agents to refine the spec."""

    def execute(self) -> None:
        args = self.args
        _assert_project_exists(args.project_name)
        verbose = _resolve_verbose(args)
        # Rounds: use explicit CLI value if provided; only fall back to settings.json if absent.
        rounds = args.rounds if args.rounds is not None else get_rounds()

        print(f"[ralph] Ooh, I'm doing the interview for '{args.project_name}'!")

        question_prompts = [
            parse_questions_md(args.project_name, round_num=i + 1, total_rounds=rounds)
            for i in range(rounds)
        ]

        def make_amend_prompt(round_num: int) -> Callable[[str], str]:
            def build(qa_json: str) -> str:
                return parse_generate_tasks_md(
                    args.project_name,
                    round_num=round_num,
                    total_rounds=rounds,
                    qa_json=qa_json,
                )
            return build

        amend_fns = [make_amend_prompt(i + 1) for i in range(rounds)]
        Runner(args.project_name, verbose=verbose).run_interview_loop(question_prompts, amend_fns)


class CommentCommand(Command):
    """ralph comment — refine spec and regenerate tasks with a user comment."""

    def execute(self) -> None:
        args = self.args
        _assert_project_exists(args.project_name)
        print(f"[ralph] Okay, I'm adding your comment to '{args.project_name}'!")
        prompt = parse_generate_tasks_md(args.project_name, user_comment=args.comment)
        Runner(args.project_name, verbose=_resolve_verbose(args)).run_prompt(prompt, "comment")


class EnrichCommand(Command):
    """ralph enrich — enrich spec.md and regenerate tasks using the codebase."""

    def execute(self) -> None:
        args = self.args
        _assert_project_exists(args.project_name)
        print(f"[ralph] I'm gonna make the spec for '{args.project_name}' even better!")
        prompt = parse_generate_tasks_md(args.project_name, user_comment=_ENRICH_COMMENT)
        Runner(args.project_name, verbose=_resolve_verbose(args)).run_prompt(prompt, "enrich")


class ExecuteCommand(Command):
    """ralph execute — run execute agents to implement the project."""

    def execute(self) -> None:
        args = self.args
        _assert_project_exists(args.project_name)
        verbose = _resolve_verbose(args)
        asynchronous = _resolve_asynchronous(args)
        limit = args.limit if args.limit is not None else get_limit()
        base = args.base if args.base is not None else get_base()
        if args.base is not None:
            _validate_branch_exists(args.base)

        project_name = args.project_name

        print(f"[ralph] Okay okay okay! I'm starting the execute for '{project_name}'! Exciting!")

        if args.resume:
            # Ensure that the project branch already exists; abort if not found.
            branch_check = subprocess.run(["git", "branch", "--list", project_name], capture_output=True, text=True)
            if not branch_check.stdout.strip():
                print(f"[ralph] I can't find branch '{project_name}'. I'm going home.", file=sys.stderr)
                sys.exit(1)

            # Checkout to the existing project branch.
            checkout_branch = subprocess.run(["git", "checkout", project_name], capture_output=True, text=True)
            if checkout_branch.returncode != 0:
                print(f"[ralph] I couldn't get to branch '{project_name}': {checkout_branch.stderr.strip()}", file=sys.stderr)
                sys.exit(1)
        else:
            # Check whether the project branch already exists; abort if it does.
            branch_check = subprocess.run(["git", "branch", "--list", project_name], capture_output=True, text=True)
            if branch_check.stdout.strip():
                print(f"[ralph] Branch '{project_name}' already exists! I can't make another one!", file=sys.stderr)
                sys.exit(1)

            # Checkout the base branch.
            checkout_base = subprocess.run(["git", "checkout", base], capture_output=True, text=True)
            if checkout_base.returncode != 0:
                print(f"[ralph] I couldn't get to base branch '{base}': {checkout_base.stderr.strip()}", file=sys.stderr)
                sys.exit(1)

            # Create and checkout the project branch.
            create_branch = subprocess.run(["git", "checkout", "-b", project_name], capture_output=True, text=True)
            if create_branch.returncode != 0:
                print(f"[ralph] I couldn't make branch '{project_name}': {create_branch.stderr.strip()}", file=sys.stderr)
                sys.exit(1)

        # Verify tasks.json exists and has been populated (e.g. by ralph enrich or ralph comment).
        tasks_path = os.path.join(".ralph", project_name, "tasks.json")
        if not os.path.exists(tasks_path):
            print(
                f"[ralph] I can't find a tasks.json for project '{project_name}'! "
                f"Run 'ralph enrich {project_name}' or 'ralph comment {project_name}' to make some tasks first.",
                file=sys.stderr,
            )
            sys.exit(1)
        with open(tasks_path) as f:
            tasks_data = json.load(f)
        if not tasks_data.get("tasks"):
            print(
                f"[ralph] There aren't any tasks in tasks.json for project '{project_name}'! "
                f"Run 'ralph enrich {project_name}' or 'ralph comment {project_name}' to make some tasks first.",
                file=sys.stderr,
            )
            sys.exit(1)

        single = _resolve_single(args)

        if single and asynchronous:
            print("[ralph] Error: --single and --asynchronous cannot both be true.")
            sys.exit(1)

        Runner(project_name, verbose=verbose).run_execute_loop(limit, asynchronous=asynchronous, single=single, resume=args.resume)


class ValidateCommand(Command):
    """ralph validate — run a validation agent to assess the project."""

    def execute(self) -> None:
        args = self.args
        _assert_project_exists(args.project_name)
        
        # Check pr-description.md exists.
        pr_desc_path = os.path.join(".ralph", args.project_name, "pr-description.md")
        if not os.path.exists(pr_desc_path):
            print(
                f"[ralph] I can't find 'pr-description.md' at '{pr_desc_path}'! "
                "Did you run 'ralph execute' first?",
                file=sys.stderr,
            )
            sys.exit(1)

        # Check all tasks in tasks.json are completed.
        tasks_path = os.path.join(".ralph", args.project_name, "tasks.json")
        with open(tasks_path) as f:
            tasks_data = json.load(f)
        incomplete = [t for t in tasks_data.get("tasks", []) if t.get("status") != "completed"]
        if incomplete:
            print(
                f"[ralph] Not all the tasks are done for '{args.project_name}'! "
                "Run 'ralph execute' to finish all the tasks first.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Check that the project branch exists.
        _validate_branch_exists(args.project_name)

        # If validation.md already exists, ask whether to overwrite.
        validation_path = os.path.join(".ralph", args.project_name, "validation.md")
        if os.path.exists(validation_path):
            while True:
                answer = input(f"'{validation_path}' already exists! Should I write over it? (y/n): ").strip().lower()
                if answer in ("y", "yes"):
                    break
                elif answer in ("n", "no"):
                    sys.exit(1)

        # Checkout the project branch.
        checkout_result = subprocess.run(["git", "checkout", args.project_name], capture_output=True, text=True)
        if checkout_result.returncode != 0:
            print(
                f"[ralph] I couldn't get to branch '{args.project_name}': {checkout_result.stderr.strip()}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Render the validate prompt and run the validation agent with JSON output mode.
        prompt = parse_validate_md(args.project_name)
        runner = Runner(args.project_name, verbose=_resolve_verbose(args))
        validate_json_result = runner.run_prompt(prompt, "validate", json_output=True)

        # Pretty-print the validation summary to the console.
        _print_validate_summary(args.project_name, validate_json_result)


class UndoCommand(Command):
    """ralph undo — undo code changes from a previous ralph execute."""

    def execute(self) -> None:
        args = self.args
        _assert_project_exists(args.project_name)

        print(f"[ralph] Uh oh, we're doing the undo thing for '{args.project_name}'! This is a big deal!")

        # Check that validation.md exists.
        validation_path = os.path.join(".ralph", args.project_name, "validation.md")
        if not os.path.exists(validation_path):
            print(
                f"[ralph] I can't find 'validation.md' at '{validation_path}'! "
                "Run 'ralph validate' first.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Parse the rating from validation.md.
        rating = None
        with open(validation_path) as f:
            for line in f:
                m = re.match(r"#\s*[Rr]ating:\s*(.+)", line.strip(), re.IGNORECASE)
                if m:
                    rating = m.group(1).strip().lower()
                    break

        if rating is None and not args.force:
            print(
                f"[ralph] Hmm, I couldn't find a rating in '{validation_path}'. "
                "Use --force to undo anyway.",
                file=sys.stderr,
            )
            sys.exit(1)
        elif rating != "failed" and not args.force:
            print(
                f"[ralph] The validation rating is '{rating}', not 'failed'. "
                "Use --force to undo anyway.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Prompt user for confirmation before deleting the project branch.
        answer = input(f"Do you really want to delete branch '{args.project_name}'? This cannot be undone! (y/n): ").strip().lower()
        if answer not in ("y", "yes"):
            print("[ralph] Okay! We're not doing the undo. Everything stays the same!")
            sys.exit(0)

        # Resolve base branch.
        base_branch = get_base()
        if not base_branch:
            set_base("main")
            base_branch = "main"

        # Abort if base branch and project branch are the same.
        if base_branch == args.project_name:
            print(
                f"[ralph] Uh oh! The base branch '{base_branch}' is the same as the project branch! I can't do that!",
                file=sys.stderr,
            )
            sys.exit(1)

        # Checkout the base branch.
        checkout_result = subprocess.run(["git", "checkout", base_branch], capture_output=True, text=True)
        if checkout_result.returncode != 0:
            print(f"[ralph] I couldn't get to branch '{base_branch}': {checkout_result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)

        # Force-delete the project branch.
        delete_result = subprocess.run(["git", "branch", "-D", args.project_name], capture_output=True, text=True)
        if delete_result.returncode != 0:
            print(f"[ralph] I couldn't delete branch '{args.project_name}': {delete_result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)

        ralph_dir = os.path.join(".ralph", args.project_name)

        # Reset state.json.
        state_path = os.path.join(ralph_dir, "state.json")
        try:
            with open(state_path, "w") as f:
                json.dump([], f)
        except OSError as e:
            print(f"[ralph] Oops, I couldn't reset '{state_path}': {e}", file=sys.stderr)
            sys.exit(1)

        # Reset obstacles.json.
        obstacles_path = os.path.join(ralph_dir, "obstacles.json")
        try:
            with open(obstacles_path, "w") as f:
                json.dump({"obstacles": []}, f)
        except OSError as e:
            print(f"[ralph] Oops, I couldn't reset '{obstacles_path}': {e}", file=sys.stderr)
            sys.exit(1)

        # Reset tasks.json — reset task fields; preserve all other fields.
        tasks_path = os.path.join(ralph_dir, "tasks.json")
        tasks_existed = os.path.exists(tasks_path)
        try:
            if not tasks_existed:
                with open(tasks_path, "w") as f:
                    json.dump({}, f)
            else:
                with open(tasks_path) as f:
                    tasks_data = json.load(f)
                for task in tasks_data.get("tasks", []):
                    task["status"] = "pending"
                    task["attempts"] = 0
                    task["blocked"] = False
                with open(tasks_path, "w") as f:
                    json.dump(tasks_data, f, indent=2)
        except (OSError, json.JSONDecodeError) as e:
            print(f"[ralph] Oops, I couldn't reset '{tasks_path}': {e}", file=sys.stderr)
            sys.exit(1)

        print(f"[ralph] Yay! Undo is all done! Project '{args.project_name}' is all cleaned up and ready to start fresh!")


class RetryCommand(Command):
    """ralph retry — spawn an agent to fix issues identified during validation."""

    def execute(self) -> None:
        args = self.args
        _assert_project_exists(args.project_name)

        print(f"[ralph] I'm gonna try to fix '{args.project_name}'! Here we go!")

        # Check that validation.md exists.
        validation_path = os.path.join(".ralph", args.project_name, "validation.md")
        if not os.path.exists(validation_path):
            print(
                f"[ralph] I can't find 'validation.md' at '{validation_path}'! "
                "Run 'ralph validate' first.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Parse the rating from validation.md.
        rating = None
        with open(validation_path) as f:
            for line in f:
                m = re.match(r"#\s*[Rr]ating:\s*(.+)", line.strip(), re.IGNORECASE)
                if m:
                    rating = m.group(1).strip().lower()
                    break

        if rating is None:
            print(
                f"[ralph] Hmm, I couldn't find a rating in '{validation_path}'.",
                file=sys.stderr,
            )
            if not args.force:
                sys.exit(1)
        elif rating == "passed":
            print(
                "[ralph] The validation passed — everything is already good! "
                "Use --force to retry anyway.",
                file=sys.stderr,
            )
            if not args.force:
                sys.exit(1)
        elif rating == "failed":
            print(
                "[ralph] The validation failed! It would be better to run 'ralph undo' and then "
                "'ralph execute' again for better results. "
                "Use --force to retry anyway.",
                file=sys.stderr,
            )
            if not args.force:
                sys.exit(1)
        # "requires attention" proceeds normally without --force

        # Check for a dirty working tree.
        status_result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status_result.stdout.strip():
            print(
                "[ralph] There are uncommitted changes in the working tree! "
                "Please put them away before doing retry.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Check that the project branch exists.
        branch_check = subprocess.run(["git", "branch", "--list", args.project_name], capture_output=True, text=True)
        if not branch_check.stdout.strip():
            print(f"[ralph] I can't find branch '{args.project_name}'. I'm going home.", file=sys.stderr)
            sys.exit(1)

        # Checkout the project branch.
        checkout_result = subprocess.run(["git", "checkout", args.project_name], capture_output=True, text=True)
        if checkout_result.returncode != 0:
            print(f"[ralph] I couldn't get to branch '{args.project_name}': {checkout_result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)

        # Render the retry prompt and spawn the agent.
        prompt = parse_retry_md(args.project_name)
        Runner(args.project_name, verbose=_resolve_verbose(args)).run_prompt(prompt, "retry")


class OneshotCommand(Command):
    """ralph oneshot — enrich, execute, validate, and create a PR in one call."""

    def execute(self) -> None:
        args = self.args

        print(f"[ralph] Ooh ooh! I'm doing ALL the things for '{args.project_name}'! Enrich, execute, validate, and PR!")

        EnrichCommand(args).execute()
        ExecuteCommand(args).execute()
        ValidateCommand(args).execute()

        # Read validation.md and parse the rating.
        validation_path = os.path.join(".ralph", args.project_name, "validation.md")
        rating = None
        try:
            with open(validation_path) as f:
                for line in f:
                    m = re.match(r"#\s*Rating:\s*(.+)", line.strip(), re.IGNORECASE)
                    if m:
                        rating = m.group(1).strip().lower()
                        break
        except OSError:
            pass

        if rating is None:
            print(
                f"[ralph] Hmm, I couldn't read or find the rating in '{validation_path}'. "
                "I can't make the PR without it.",
                file=sys.stderr,
            )
            sys.exit(1)

        if rating == "failed":
            print(
                f"[ralph] The validation failed! Look at '{validation_path}' and fix the problems before making a PR.",
                file=sys.stderr,
            )
            sys.exit(1)

        if rating == "requires attention":
            print(
                f"[ralph] The validation needs attention! Look at '{validation_path}' for details. I'll make the PR anyway!"
            )

        PrCommand(args).execute()


class StatusCommand(Command):
    """ralph status — display project status, task progress, and obstacles."""

    def execute(self) -> None:
        args = self.args
        _assert_project_exists(args.project_name)

        project_name = args.project_name
        ralph_dir = os.path.join(".ralph", project_name)

        sep = "─" * 60

        print()
        print(f"[ralph] Project: {project_name}")
        print(sep)

        # --- Git branch info ---
        branch_result = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
        current_branch = branch_result.stdout.strip()
        base_branch = get_base()
        print(f"[ralph] Current branch : {current_branch}")
        print(f"[ralph] Base branch    : {base_branch}")

        # --- Execution-relevant config flags ---
        limit = get_limit()
        asynchronous = get_asynchronous()
        single = get_single()
        print(f"[ralph] Limit          : {limit}")
        print(f"[ralph] Asynchronous   : {asynchronous}")
        print(f"[ralph] Single         : {single}")

        # --- Validation rating ---
        validation_path = os.path.join(ralph_dir, "validation.md")
        if os.path.exists(validation_path):
            rating = None
            with open(validation_path) as f:
                for line in f:
                    m = re.match(r"#\s*Rating:\s*(.+)", line.strip(), re.IGNORECASE)
                    if m:
                        rating = m.group(1).strip()
                        break
            if rating:
                print(f"[ralph] Validation     : {rating}")

        print(sep)

        # --- Tasks ---
        tasks_path = os.path.join(ralph_dir, "tasks.json")
        tasks_data = None
        if os.path.exists(tasks_path):
            try:
                with open(tasks_path) as f:
                    tasks_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                tasks_data = None

        # Empty dict `{}` or missing file: no tasks to display
        if not tasks_data or not isinstance(tasks_data, dict) or not tasks_data.get("tasks"):
            print("[ralph] I don't see any tasks or obstacles here!")
            print()
            return

        tasks = tasks_data["tasks"]

        print("[ralph] Tasks")
        print(sep)

        status_counts: dict[str, int] = {}
        for task in tasks:
            task_id = task.get("id", "?")
            title = task.get("title", "(no title)")
            status = task.get("status", "unknown")
            blocked = task.get("blocked", False)

            status_counts[status] = status_counts.get(status, 0) + 1

            suffix = ""
            if status == "in_progress":
                suffix = "  [BLOCKED]" if blocked else "  [running]"

            print(f"[ralph]   {task_id:<4}  {status:<12}  {title}{suffix}")

        print(sep)
        total = len(tasks)
        completed = status_counts.get("completed", 0)
        in_progress = status_counts.get("in_progress", 0)
        pending = status_counts.get("pending", 0)
        print(f"[ralph] Summary: {completed} completed / {in_progress} in_progress / {pending} pending  (total: {total})")
        print(sep)

        # --- Obstacles ---
        obstacles_path = os.path.join(ralph_dir, "obstacles.json")
        obstacles_data = None
        if os.path.exists(obstacles_path):
            try:
                with open(obstacles_path) as f:
                    obstacles_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                obstacles_data = None

        obstacles = []
        if isinstance(obstacles_data, dict):
            obstacles = obstacles_data.get("obstacles", [])

        if obstacles:
            print("[ralph] Obstacles")
            print(sep)

            # Group by task_id
            grouped: dict[str, list] = {}
            for obs in obstacles:
                tid = obs.get("task_id", "?")
                grouped.setdefault(tid, []).append(obs)

            for tid, obs_list in grouped.items():
                print(f"[ralph]   Task {tid}:")
                for obs in obs_list:
                    resolved = obs.get("resolved", False)
                    resolved_str = "resolved" if resolved else "unresolved"
                    print(
                        f"[ralph]     {obs.get('id', '?')}"
                        f"  [iter {obs.get('iteration', '?')}]"
                        f"  [{resolved_str}]"
                        f"  {obs.get('message', '')}"
                    )

            print(sep)

        print()


class PrCommand(Command):
    """ralph pr — create a pull/merge request for the project."""

    def execute(self) -> None:
        args = self.args
        _assert_project_exists(args.project_name)

        provider = _resolve_provider(args)

        print(f"[ralph] I'm making a pull request for '{args.project_name}'! Exciting!")

        if provider == "github":
            # Check gh CLI is installed.
            gh_check = subprocess.run(["gh", "--version"], capture_output=True)
            if gh_check.returncode != 0:
                print(
                    "[ralph] I can't find the 'gh' thingy! Please get it from https://cli.github.com/",
                    file=sys.stderr,
                )
                sys.exit(1)

            # Check current branch matches project name.
            branch_result = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
            current_branch = branch_result.stdout.strip()
            if current_branch != args.project_name:
                print(
                    f"[ralph] I'm on branch '{current_branch}' but the project is '{args.project_name}'. "
                    "Please get on the right branch first!",
                    file=sys.stderr,
                )
                sys.exit(1)

            # Check working tree is clean.
            status_result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
            if status_result.stdout:
                print(
                    "[ralph] There are uncommitted changes in the working tree! Please put them away before making a PR.",
                    file=sys.stderr,
                )
                sys.exit(1)

            # Detect base branch.
            base_branch = get_base()
            merge_base_result = subprocess.run(
                ["git", "merge-base", "HEAD", base_branch], capture_output=True, text=True
            )
            if merge_base_result.returncode != 0:
                print(
                    f"[ralph] I couldn't figure out where HEAD and '{base_branch}' come together. "
                    "Make sure the base branch exists and shares history with the current branch.",
                    file=sys.stderr,
                )
                sys.exit(1)

            # Check pr-description.md exists.
            pr_desc_path = os.path.join(".ralph", args.project_name, "pr-description.md")
            if not os.path.exists(pr_desc_path):
                print(
                    f"[ralph] I can't find 'pr-description.md' at '{pr_desc_path}'! "
                    "Did you run 'ralph execute' first?",
                    file=sys.stderr,
                )
                sys.exit(1)

            # Push branch to origin.
            push_result = subprocess.run(
                ["git", "push", "-u", "origin", args.project_name], capture_output=True, text=True
            )
            if push_result.returncode != 0:
                print(push_result.stderr, file=sys.stderr)
                sys.exit(1)

            # Read pr-description.md.
            with open(pr_desc_path) as f:
                pr_body = f.read()

            # Create PR non-interactively.
            result = subprocess.run(
                [
                    "gh", "pr", "create",
                    "--title", args.project_name,
                    "--body", pr_body,
                    "--base", base_branch,
                    "--head", args.project_name,
                ],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                print(result.stderr, file=sys.stderr)
                sys.exit(1)

            print("[ralph] The pull request is all done! You can see it now!")
            print(result.stdout)

        elif provider == "gitlab":
            # Check glab CLI is installed.
            glab_check = subprocess.run(["glab", "--version"], capture_output=True)
            if glab_check.returncode != 0:
                print(
                    "[ralph] I can't find the 'glab' thingy! Please get it from https://gitlab.com/gitlab-org/cli",
                    file=sys.stderr,
                )
                sys.exit(1)

            # Check current branch matches project name.
            branch_result = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
            current_branch = branch_result.stdout.strip()
            if current_branch != args.project_name:
                print(
                    f"[ralph] I'm on branch '{current_branch}' but the project is '{args.project_name}'. "
                    "Please get on the right branch first!",
                    file=sys.stderr,
                )
                sys.exit(1)

            # Check working tree is clean.
            status_result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
            if status_result.stdout:
                print(
                    "[ralph] There are uncommitted changes in the working tree! Please put them away before making a MR.",
                    file=sys.stderr,
                )
                sys.exit(1)

            # Detect base branch.
            base_branch = get_base()

            # Check pr-description.md exists.
            pr_desc_path = os.path.join(".ralph", args.project_name, "pr-description.md")
            if not os.path.exists(pr_desc_path):
                print(
                    f"[ralph] I can't find 'pr-description.md' at '{pr_desc_path}'! "
                    "Did you run 'ralph execute' first?",
                    file=sys.stderr,
                )
                sys.exit(1)

            # Push branch to origin.
            push_result = subprocess.run(
                ["git", "push", "-u", "origin", args.project_name], capture_output=True, text=True
            )
            if push_result.returncode != 0:
                print(push_result.stderr, file=sys.stderr)
                sys.exit(1)

            # Read pr-description.md.
            with open(pr_desc_path) as f:
                pr_body = f.read()

            # Create MR non-interactively.
            result = subprocess.run(
                [
                    "glab", "mr", "create",
                    "--title", args.project_name,
                    "--description", pr_body,
                    "--source-branch", args.project_name,
                    "--target-branch", base_branch,
                ],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                print(result.stderr, file=sys.stderr)
                sys.exit(1)

            print("[ralph] The merge request is all done! You can see it now!")
            print(result.stdout)
