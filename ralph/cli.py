"""Ralph Wiggum CLI entry point."""

import argparse
import json
import os
import subprocess
import sys
from typing import Callable

from ralph.config import ensure_defaults, get_asynchronous, get_base, get_limit, get_provider, get_rounds, get_verbose, set_asynchronous, set_base, set_limit, set_provider, set_rounds, set_verbose
from ralph.parse import parse_execute_md, parse_generate_tasks_md, parse_questions_md
from ralph.run import Runner

_DEFAULT_LIMIT = 20

RALPH_BANNER = """\
██████╗  █████╗ ██╗     ██████╗ ██╗  ██╗
██╔══██╗██╔══██╗██║     ██╔══██╗██║  ██║
██████╔╝███████║██║     ██████╔╝███████║
██╔══██╗██╔══██║██║     ██╔═══╝ ██╔══██║
██║  ██║██║  ██║███████╗██║     ██║  ██║
╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝  ╚═╝

    ── R A L P H   W I G G U M ──
"Me fail English? That's unpossible"\
"""

_ENRICH_COMMENT = (
    "You are an expert software engineer reviewing this project for the first time. "
    "Carefully read spec.md and all relevant source files, tests, and configuration in the "
    "codebase to gain a thorough understanding of the problem domain and existing implementation "
    "patterns. Then, enhance spec.md in-place by filling in any missing context, clarifying "
    "ambiguous requirements, and adding technical details implied by the existing code — "
    "ensuring the specification is precise and complete enough to drive accurate task "
    "generation. Do not remove any existing content that remains valid."
)


def _validate_branch_exists(branch: str) -> None:
    """Verify that the given branch exists in the current repo; exit if not."""
    result = subprocess.run(["git", "branch", "--list", branch], capture_output=True, text=True)
    if not result.stdout.strip():
        print(f"[ralph] I can't find branch '{branch}' in this repo. Aborting.", file=sys.stderr)
        sys.exit(1)


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
                "[ralph] I can't find the 'gh' CLI. "
                "Install it from https://cli.github.com and run 'gh auth login'.",
                file=sys.stderr,
            )
            return False
        if result.returncode != 0:
            print(
                "[ralph] The 'gh' CLI isn't authenticated. "
                "Run 'gh auth login' to sign in.",
                file=sys.stderr,
            )
            return False
        return True
    elif provider == "gitlab":
        try:
            result = subprocess.run(["glab", "auth", "status"], capture_output=True)
        except FileNotFoundError:
            print(
                "[ralph] I can't find the 'glab' CLI. "
                "Install it from https://gitlab.com/gitlab-org/cli and run 'glab auth login'.",
                file=sys.stderr,
            )
            return False
        if result.returncode != 0:
            print(
                "[ralph] The 'glab' CLI isn't authenticated. "
                "Run 'glab auth login' to sign in.",
                file=sys.stderr,
            )
            return False
        return True
    else:
        print(f"[ralph] I don't know the provider '{provider}'. Try 'github' or 'gitlab'.", file=sys.stderr)
        return False


def _assert_project_exists(project_name: str) -> None:
    """Assert that the project directory and spec.md exist; exit with an error if not."""
    ralph_dir = os.path.join(".ralph", project_name)
    if not os.path.exists(ralph_dir):
        print(
            f"[ralph] I can't find project '{project_name}'. "
            f"Expected directory '{ralph_dir}' to exist. "
            "Run 'ralph init' first.",
            file=sys.stderr,
        )
        sys.exit(1)
    spec_path = os.path.join(ralph_dir, "spec.md")
    if not os.path.exists(spec_path):
        print(
            f"[ralph] Project '{project_name}' is missing 'spec.md'. "
            f"Expected '{spec_path}' to exist.",
            file=sys.stderr,
        )
        sys.exit(1)


def cmd_init(args: argparse.Namespace) -> None:
    project_name = args.project_name
    ralph_dir = os.path.join(".ralph", project_name)

    if os.path.exists(ralph_dir):
        print(f"[ralph] Project '{project_name}' already exists at '{ralph_dir}'. Aborting.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(ralph_dir)
    print(f"[ralph] Created project directory '{ralph_dir}'.")

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

    ensure_defaults()

    # Branch mismatch check: compare current branch with the persisted base branch.
    branch_result = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
    if branch_result.returncode == 0 and branch_result.stdout.strip():
        current_branch = branch_result.stdout.strip()
        base_branch = get_base()
        if current_branch != base_branch:
            print(
                f"[ralph] Heads up — you're on branch '{current_branch}' but your base branch is set to '{base_branch}'."
            )
            while True:
                answer = input(f"Update base branch to '{current_branch}'? (y/n): ").strip().lower()
                if answer in ("y", "yes"):
                    set_base(current_branch)
                    print(f"[ralph] Base branch updated to '{current_branch}'.")
                    break
                elif answer in ("n", "no"):
                    break

    print(f"[ralph] Project '{project_name}' is all set up in '{ralph_dir}'.")


def cmd_interview(args: argparse.Namespace) -> None:
    _assert_project_exists(args.project_name)
    verbose = _resolve_verbose(args)
    # Rounds: use explicit CLI value if provided; only fall back to settings.json if absent.
    rounds = args.rounds if args.rounds is not None else get_rounds()

    question_prompts = [
        parse_questions_md(args.project_name, round_num=i + 1, total_rounds=rounds)
        for i in range(rounds)
    ]

    def make_amend_prompt(round_num: int) -> Callable[[str, str], str]:
        def build(questions: str, answers: str) -> str:
            return parse_generate_tasks_md(
                args.project_name,
                round_num=round_num,
                total_rounds=rounds,
                questions=questions,
                answers=answers,
            )
        return build

    amend_fns = [make_amend_prompt(i + 1) for i in range(rounds)]
    Runner(args.project_name, verbose=verbose).run_interview_loop(question_prompts, amend_fns)


def cmd_comment(args: argparse.Namespace) -> None:
    _assert_project_exists(args.project_name)
    prompt = parse_generate_tasks_md(args.project_name, user_comment=args.comment)
    Runner(args.project_name, verbose=_resolve_verbose(args)).run_comment(prompt)


def cmd_execute(args: argparse.Namespace) -> None:
    _assert_project_exists(args.project_name)
    verbose = _resolve_verbose(args)
    asynchronous = _resolve_asynchronous(args)
    limit = args.limit if args.limit is not None else get_limit()
    base = args.base if args.base is not None else get_base()
    if args.base is not None:
        _validate_branch_exists(args.base)

    project_name = args.project_name
    
    if args.resume:
        # Ensure that the project branch already exists; abort if not found.
        branch_check = subprocess.run(["git", "branch", "--list", project_name], capture_output=True, text=True)
        if not branch_check.stdout.strip():
            print(f"[ralph] I can't find branch '{project_name}'. Aborting.", file=sys.stderr)
            sys.exit(1)

        # checkout to the existing project branch
        checkout_branch = subprocess.run(["git", "checkout", project_name], capture_output=True, text=True)
        if checkout_branch.returncode != 0:
            print(f"[ralph] I couldn't check out branch '{project_name}': {create_branch.stderr.strip()}", file=sys.stderr)
            sys.exit(1)
    else:
        # Check whether the project branch already exists; abort if it does.
        branch_check = subprocess.run(["git", "branch", "--list", project_name], capture_output=True, text=True)
        if branch_check.stdout.strip():
            print(f"[ralph] Branch '{project_name}' already exists. Aborting.", file=sys.stderr)
            sys.exit(1)

        # Checkout the base branch.
        checkout_base = subprocess.run(["git", "checkout", base], capture_output=True, text=True)
        if checkout_base.returncode != 0:
            print(f"[ralph] I couldn't check out base branch '{base}': {checkout_base.stderr.strip()}", file=sys.stderr)
            sys.exit(1)

        # Create and checkout the project branch.
        create_branch = subprocess.run(["git", "checkout", "-b", project_name], capture_output=True, text=True)
        if create_branch.returncode != 0:
            print(f"[ralph] I couldn't create branch '{project_name}': {create_branch.stderr.strip()}", file=sys.stderr)
            sys.exit(1)

    # Pre-render all prompts; each references its iteration number
    prompts = [
        parse_execute_md(project_name, iteration_num=i + 1, max_iterations=limit)
        for i in range(limit)
    ]
    Runner(project_name, verbose=verbose).run_execute_loop(prompts, limit, asynchronous=asynchronous)


def cmd_oneshot(args: argparse.Namespace) -> None:
    _assert_project_exists(args.project_name)

    # Uncommitted changes check.
    status_check = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if status_check.stdout:
        print(
            "[ralph] There are uncommitted changes in the working tree. "
            "Please commit or stash them before running 'ralph oneshot'.",
            file=sys.stderr,
        )
        sys.exit(1)

    verbose = _resolve_verbose(args)
    limit = args.limit if args.limit is not None else get_limit()
    base = args.base if args.base is not None else get_base()
    if args.base is not None:
        _validate_branch_exists(args.base)

    project_name = args.project_name

    # Branch existence check.
    branch_check = subprocess.run(["git", "branch", "--list", project_name], capture_output=True, text=True)
    if branch_check.stdout.strip():
        print(f"[ralph] Branch '{project_name}' already exists. Aborting.", file=sys.stderr)
        sys.exit(1)

    # Checkout base branch.
    checkout_base = subprocess.run(["git", "checkout", base], capture_output=True, text=True)
    if checkout_base.returncode != 0:
        print(f"[ralph] I couldn't check out base branch '{base}': {checkout_base.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    # Create project branch.
    create_branch = subprocess.run(["git", "checkout", "-b", project_name], capture_output=True, text=True)
    if create_branch.returncode != 0:
        print(f"[ralph] I couldn't create branch '{project_name}': {create_branch.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    # Comment step: spec enrichment + task generation.
    prompt = parse_generate_tasks_md(project_name, user_comment=_ENRICH_COMMENT)
    Runner(project_name, verbose=verbose).run_comment(prompt)
    tasks_path = os.path.join(".ralph", project_name, "tasks.json")
    if not os.path.exists(tasks_path):
        print(
            f"[ralph] Task generation didn't produce a tasks.json file. "
            f"To retry from here, run: ralph execute {project_name}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Execute step.
    prompts = [
        parse_execute_md(project_name, iteration_num=i + 1, max_iterations=limit)
        for i in range(limit)
    ]
    Runner(project_name, verbose=verbose).run_execute_loop(prompts, limit)
    with open(tasks_path) as f:
        data = json.load(f)
    if not all(task["status"] == "completed" for task in data["tasks"]):
        print(
            f"[ralph] Not all tasks were completed. "
            f"To keep going, run: ralph execute {project_name}",
            file=sys.stderr,
        )
        sys.exit(1)

    # PR step.
    fake_args = argparse.Namespace(project_name=project_name, provider=None)
    try:
        cmd_pr(fake_args)
    except SystemExit as exc:
        if exc.code:
            print(f"[ralph] To create the PR manually, run: ralph pr {project_name}", file=sys.stderr)
            sys.exit(exc.code)


def cmd_pr(args: argparse.Namespace) -> None:
    _assert_project_exists(args.project_name)

    provider = _resolve_provider(args)

    if provider == "github":
        # Check gh CLI is installed.
        gh_check = subprocess.run(["gh", "--version"], capture_output=True)
        if gh_check.returncode != 0:
            print(
                "[ralph] I can't find the 'gh' CLI. Please install it from https://cli.github.com/",
                file=sys.stderr,
            )
            sys.exit(1)

        # Check current branch matches project name.
        branch_result = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
        current_branch = branch_result.stdout.strip()
        if current_branch != args.project_name:
            print(
                f"[ralph] Current branch '{current_branch}' does not match project '{args.project_name}'. "
                "Please check out the correct branch.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Check working tree is clean.
        status_result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status_result.stdout:
            print(
                "[ralph] There are uncommitted changes in the working tree. Please commit or stash them before creating a PR.",
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
                f"[ralph] I couldn't determine the merge base between HEAD and '{base_branch}'. "
                "Make sure the base branch exists and shares history with the current branch.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Check pr-description.md exists.
        pr_desc_path = os.path.join(".ralph", args.project_name, "pr-description.md")
        if not os.path.exists(pr_desc_path):
            print(
                f"[ralph] I can't find 'pr-description.md' at '{pr_desc_path}'. "
                "Run 'ralph execute' first to generate the PR description.",
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

        print("[ralph] Pull request created successfully.")
        print(result.stdout)

    elif provider == "gitlab":
        # Check glab CLI is installed.
        glab_check = subprocess.run(["glab", "--version"], capture_output=True)
        if glab_check.returncode != 0:
            print(
                "[ralph] I can't find the 'glab' CLI. Please install it from https://gitlab.com/gitlab-org/cli",
                file=sys.stderr,
            )
            sys.exit(1)

        # Check current branch matches project name.
        branch_result = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
        current_branch = branch_result.stdout.strip()
        if current_branch != args.project_name:
            print(
                f"[ralph] Current branch '{current_branch}' does not match project '{args.project_name}'. "
                "Please check out the correct branch.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Check working tree is clean.
        status_result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status_result.stdout:
            print(
                "[ralph] There are uncommitted changes in the working tree. Please commit or stash them before creating a MR.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Detect base branch.
        base_branch = get_base()

        # Check pr-description.md exists.
        pr_desc_path = os.path.join(".ralph", args.project_name, "pr-description.md")
        if not os.path.exists(pr_desc_path):
            print(
                f"[ralph] I can't find 'pr-description.md' at '{pr_desc_path}'. "
                "Run 'ralph execute' first to generate the PR description.",
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

        print("[ralph] Merge request created successfully.")
        print(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ralph",
        description="Ralph Wiggum — CLI-driven agentic coding framework",
    )
    # Top-level flags: when provided (without or before a subcommand), persist to settings.json.
    parser.add_argument(
        "--verbose", "-v",
        choices=["true", "false"],
        default=None,
        dest="global_verbose",
        metavar="BOOL",
        help="Persist verbose setting to .ralph/settings.json (true/false)",
    )
    parser.add_argument(
        "--rounds", "-r",
        type=int,
        default=None,
        dest="global_rounds",
        metavar="N",
        help="Persist rounds setting to .ralph/settings.json",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=None,
        dest="global_limit",
        metavar="N",
        help="Persist limit setting to .ralph/settings.json",
    )
    parser.add_argument(
        "--base", "-b",
        type=str,
        default=None,
        dest="global_base",
        metavar="BRANCH",
        help="Persist base branch setting to .ralph/settings.json",
    )
    parser.add_argument(
        "--provider", "-p",
        type=str,
        default=None,
        dest="global_provider",
        metavar="PROVIDER",
        help="Persist provider setting to .ralph/settings.json (github/gitlab)",
    )
    parser.add_argument(
        "--asynchronous", "-a",
        choices=["true", "false"],
        default=None,
        dest="global_asynchronous",
        metavar="BOOL",
        help="Persist asynchronous setting to .ralph/settings.json (true/false)",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ralph init <project-name> [--verbose BOOL]
    init_parser = subparsers.add_parser("init", help="Initialize a new project")
    init_parser.add_argument("project_name", metavar="<project-name>")
    init_parser.add_argument(
        "--verbose", "-v",
        choices=["true", "false"],
        default=None,
        metavar="BOOL",
        help="Enable/disable verbose output for this invocation only",
    )
    init_parser.set_defaults(func=cmd_init)

    # ralph interview <project-name> [--rounds N] [--verbose BOOL]
    interview_parser = subparsers.add_parser(
        "interview", help="Run interview agents to refine the spec"
    )
    interview_parser.add_argument("project_name", metavar="<project-name>")
    interview_parser.add_argument(
        "--rounds", "-r",
        type=int,
        default=None,
        metavar="N",
        help="Number of interview rounds (overrides settings.json for this invocation only)",
    )
    interview_parser.add_argument(
        "--verbose", "-v",
        choices=["true", "false"],
        default=None,
        metavar="BOOL",
        help="Enable/disable verbose output for this invocation only",
    )
    interview_parser.set_defaults(func=cmd_interview)

    # ralph comment <project-name> "<comment>" [--verbose BOOL]
    comment_parser = subparsers.add_parser(
        "comment", help='Refine the spec with a quoted amendment description'
    )
    comment_parser.add_argument("project_name", metavar="<project-name>")
    comment_parser.add_argument(
        "comment",
        metavar='"<comment>"',
        help='A quoted description of the amendments to make, e.g. "Add support for OAuth login"',
    )
    comment_parser.add_argument(
        "--verbose", "-v",
        choices=["true", "false"],
        default=None,
        metavar="BOOL",
        help="Enable/disable verbose output for this invocation only",
    )
    comment_parser.set_defaults(func=cmd_comment)

    # ralph execute <project-name> [--limit N] [--verbose BOOL] [--resume]
    execute_parser = subparsers.add_parser(
        "execute", help="Run execute agents to implement the project"
    )
    execute_parser.add_argument("project_name", metavar="<project-name>")
    execute_parser.add_argument(
        "--limit", "-l",
        type=int,
        default=None,
        metavar="N",
        help=f"Maximum number of agent iterations, upper bound (default: {_DEFAULT_LIMIT})",
    )
    execute_parser.add_argument(
        "--base", "-b",
        type=str,
        default=None,
        metavar="BRANCH",
        help="Base branch to branch from when creating the project branch (overrides settings.json for this invocation only)",
    )
    execute_parser.add_argument(
        "--verbose", "-v",
        choices=["true", "false"],
        default=None,
        metavar="BOOL",
        help="Enable/disable verbose output for this invocation only",
    )
    execute_parser.add_argument(
        "--resume", "-r",
        action="store_true",
        help="Allow the agent to resume execution from an existing branch",
    )
    execute_parser.add_argument(
        "--asynchronous", "-a",
        choices=["true", "false"],
        default=None,
        metavar="BOOL",
        help="Enable/disable asynchronous agent execution for this invocation only",
    )
    execute_parser.set_defaults(func=cmd_execute)

    # ralph oneshot <project-name> [--limit N] [--base BRANCH] [--verbose BOOL]
    oneshot_parser = subparsers.add_parser(
        "oneshot", help="Generate tasks, execute, and create a PR in one streamlined call"
    )
    oneshot_parser.add_argument("project_name", metavar="<project-name>")
    oneshot_parser.add_argument(
        "--limit", "-l",
        type=int,
        default=None,
        metavar="N",
        help=f"Maximum number of agent iterations, upper bound (default: {_DEFAULT_LIMIT})",
    )
    oneshot_parser.add_argument(
        "--base", "-b",
        type=str,
        default=None,
        metavar="BRANCH",
        help="Base branch to branch from when creating the project branch (overrides settings.json for this invocation only)",
    )
    oneshot_parser.add_argument(
        "--verbose", "-v",
        choices=["true", "false"],
        default=None,
        metavar="BOOL",
        help="Enable/disable verbose output for this invocation only",
    )
    oneshot_parser.set_defaults(func=cmd_oneshot)

    # ralph pr <project-name> [--provider PROVIDER]
    pr_parser = subparsers.add_parser("pr", help="Create a pull request for the project")
    pr_parser.add_argument("project_name", metavar="<project-name>")
    pr_parser.add_argument(
        "--provider", "-p",
        type=str,
        default=None,
        metavar="PROVIDER",
        help="Provider to use for this invocation only (github/gitlab)",
    )
    pr_parser.set_defaults(func=cmd_pr)

    args = parser.parse_args()

    # Handle global-level flags: persist to settings.json.
    if args.global_verbose is not None:
        set_verbose(args.global_verbose == "true")
    if args.global_rounds is not None:
        set_rounds(args.global_rounds)
    if args.global_limit is not None:
        set_limit(args.global_limit)
    if args.global_base is not None:
        _validate_branch_exists(args.global_base)
        set_base(args.global_base)
    if args.global_asynchronous is not None:
        set_asynchronous(args.global_asynchronous == "true")

    # If no subcommand given (e.g. `ralph --verbose true`), we're done after persisting.
    if args.command is None:
        if args.global_verbose is None and args.global_rounds is None and args.global_limit is None and args.global_base is None and args.global_provider is None and args.global_asynchronous is None:
            print()
            print(RALPH_BANNER)
            print()
            print("Author: Zhiyang Lu")
            print("Version: 0.2.0")
            print()
            sys.exit(0)
        # Provider requires validation before global persist.
        if args.global_provider is not None:
            if not _validate_provider_cli(args.global_provider):
                sys.exit(1)
            set_provider(args.global_provider)
        return

    # With a subcommand present, persist global provider if provided.
    if args.global_provider is not None:
        set_provider(args.global_provider)

    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n[ralph] Ok, stopping.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
