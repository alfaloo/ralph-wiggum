"""Ralph Wiggum CLI entry point."""

import argparse
import json
import os
import sys
from typing import Callable

from ralph.config import ensure_defaults, get_limit, get_rounds, get_verbose, set_limit, set_rounds, set_verbose
from ralph.parse import parse_comment, parse_execute, parse_interview, parse_interview_questions
from ralph.run import Runner

_DEFAULT_LIMIT = 20

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


def cmd_init(args: argparse.Namespace) -> None:
    project_name = args.project_name
    artifacts_dir = os.path.join("artifacts", project_name)

    if os.path.exists(artifacts_dir):
        print(f"[ralph] Error: project '{project_name}' already exists at '{artifacts_dir}'. Aborting.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(artifacts_dir)
    print(f"[ralph] Created directory '{artifacts_dir}'.")

    spec_path = os.path.join(artifacts_dir, "spec.md")
    with open(spec_path, "w") as f:
        f.write(_SPEC_MD_TEMPLATE.format(project_name=project_name))

    state_path = os.path.join(artifacts_dir, "state.json")
    with open(state_path, "w") as f:
        json.dump([], f)

    obstacles_path = os.path.join(artifacts_dir, "obstacles.json")
    with open(obstacles_path, "w") as f:
        json.dump({"obstacles": []}, f)

    tasks_path = os.path.join(artifacts_dir, "tasks.json")
    with open(tasks_path, "w") as f:
        json.dump({}, f)

    ensure_defaults()
    print(f"[ralph] Init complete. Project '{project_name}' created in '{artifacts_dir}'.")


def cmd_interview(args: argparse.Namespace) -> None:
    verbose = _resolve_verbose(args)
    # Rounds: use explicit CLI value if provided; only fall back to settings.json if absent.
    rounds = args.rounds if args.rounds is not None else get_rounds()

    question_prompts = [
        parse_interview_questions(args.project_name, round_num=i + 1, total_rounds=rounds)
        for i in range(rounds)
    ]

    def make_amend_prompt(round_num: int) -> Callable[[str, str], str]:
        def build(questions: str, answers: str) -> str:
            return parse_interview(
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
    prompt = parse_comment(args.project_name, args.comment)
    Runner(args.project_name, verbose=_resolve_verbose(args)).run_comment(prompt)


def cmd_execute(args: argparse.Namespace) -> None:
    verbose = _resolve_verbose(args)
    limit = args.limit if args.limit is not None else get_limit()
    # Pre-render all prompts; each references its iteration number
    prompts = [
        parse_execute(args.project_name, iteration_num=i + 1, max_iterations=limit)
        for i in range(limit)
    ]
    Runner(args.project_name, verbose=verbose).run_execute_loop(prompts, limit)


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

    # ralph execute <project-name> [--limit N] [--verbose BOOL]
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
        "--verbose", "-v",
        choices=["true", "false"],
        default=None,
        metavar="BOOL",
        help="Enable/disable verbose output for this invocation only",
    )
    execute_parser.set_defaults(func=cmd_execute)

    args = parser.parse_args()

    # Handle global-level flags: persist to settings.json.
    if args.global_verbose is not None:
        set_verbose(args.global_verbose == "true")
    if args.global_rounds is not None:
        set_rounds(args.global_rounds)
    if args.global_limit is not None:
        set_limit(args.global_limit)

    # If no subcommand given (e.g. `ralph --verbose true`), we're done after persisting.
    if args.command is None:
        if args.global_verbose is None and args.global_rounds is None and args.global_limit is None:
            parser.print_help()
            sys.exit(1)
        return

    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n[ralph] Interrupted.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
