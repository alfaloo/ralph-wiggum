"""Ralph Wiggum CLI entry point."""

import argparse
import sys

from ralph.config import (
    set_asynchronous,
    set_base,
    set_limit,
    set_provider,
    set_rounds,
    set_verbose,
)
from ralph.commands import (
    _DEFAULT_LIMIT,
    _validate_branch_exists,
    _validate_provider_cli,
    _assert_project_exists,
    _resolve_verbose,
    _resolve_asynchronous,
    _resolve_provider,
    _ENRICH_COMMENT,
    Command,
    InitCommand,
    InterviewCommand,
    CommentCommand,
    EnrichCommand,
    ExecuteCommand,
    ValidateCommand,
    UndoCommand,
    RetryCommand,
    OneshotCommand,
    PrCommand,
)

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

RALPH_VERSION = "0.2.6"


# ---------------------------------------------------------------------------
# Backward-compatible thin wrappers
#
# These functions preserve the existing public API so that code (and tests)
# that import cmd_<command> from ralph.cli continue to work.  The real logic
# now lives in the corresponding Command subclass in ralph.commands.
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> None:
    InitCommand(args).execute()


def cmd_interview(args: argparse.Namespace) -> None:
    InterviewCommand(args).execute()


def cmd_comment(args: argparse.Namespace) -> None:
    CommentCommand(args).execute()


def cmd_enrich(args: argparse.Namespace) -> None:
    EnrichCommand(args).execute()


def cmd_execute(args: argparse.Namespace) -> None:
    ExecuteCommand(args).execute()


def cmd_validate(args: argparse.Namespace) -> None:
    ValidateCommand(args).execute()


def cmd_undo(args: argparse.Namespace) -> None:
    UndoCommand(args).execute()


def cmd_retry(args: argparse.Namespace) -> None:
    RetryCommand(args).execute()


def cmd_oneshot(args: argparse.Namespace) -> None:
    OneshotCommand(args).execute()


def cmd_pr(args: argparse.Namespace) -> None:
    PrCommand(args).execute()


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
    init_parser.set_defaults(func=InitCommand)

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
    interview_parser.set_defaults(func=InterviewCommand)

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
    comment_parser.set_defaults(func=CommentCommand)

    # ralph enrich <project-name> [--verbose BOOL]
    enrich_parser = subparsers.add_parser(
        "enrich", help="Enrich spec.md and regenerate tasks.json using the codebase"
    )
    enrich_parser.add_argument("project_name", metavar="<project-name>")
    enrich_parser.add_argument(
        "--verbose", "-v",
        choices=["true", "false"],
        default=None,
        metavar="BOOL",
        help="Enable/disable verbose output for this invocation only",
    )
    enrich_parser.set_defaults(func=EnrichCommand)

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
    execute_parser.set_defaults(func=ExecuteCommand)

    # ralph oneshot <project-name> [--limit N] [--base BRANCH] [--verbose BOOL] [--resume] [--asynchronous BOOL] [--provider PROVIDER]
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
    oneshot_parser.add_argument(
        "--resume", "-r",
        action="store_true",
        help="Allow the agent to resume execution from an existing branch",
    )
    oneshot_parser.add_argument(
        "--asynchronous", "-a",
        choices=["true", "false"],
        default=None,
        metavar="BOOL",
        help="Enable/disable asynchronous agent execution for this invocation only",
    )
    oneshot_parser.add_argument(
        "--provider", "-p",
        type=str,
        default=None,
        metavar="PROVIDER",
        help="Provider to use for this invocation only (github/gitlab)",
    )
    oneshot_parser.set_defaults(func=OneshotCommand)

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
    pr_parser.set_defaults(func=PrCommand)

    # ralph validate <project-name> [--verbose BOOL]
    validate_parser = subparsers.add_parser(
        "validate", help="Run a validation agent to assess whether execute correctly solved the project"
    )
    validate_parser.add_argument("project_name", metavar="<project-name>")
    validate_parser.add_argument(
        "--verbose", "-v",
        choices=["true", "false"],
        default=None,
        metavar="BOOL",
        help="Enable/disable verbose output for this invocation only",
    )
    validate_parser.set_defaults(func=ValidateCommand)

    # ralph undo <project-name> [--force]
    undo_parser = subparsers.add_parser("undo", help="Undo code changes from a previous ralph execute")
    undo_parser.add_argument("project_name", metavar="<project-name>")
    undo_parser.add_argument("--force", "-f", action="store_true", default=False)
    undo_parser.set_defaults(func=UndoCommand)

    # ralph retry <project-name> [--force] [--verbose BOOL]
    retry_parser = subparsers.add_parser("retry", help="Spawn an agent to fix issues identified during validation")
    retry_parser.add_argument("project_name", metavar="<project-name>")
    retry_parser.add_argument("--force", "-f", action="store_true", default=False)
    retry_parser.add_argument(
        "--verbose", "-v",
        choices=["true", "false"],
        default=None,
        metavar="BOOL",
        help="Enable/disable verbose output for this invocation only",
    )
    retry_parser.set_defaults(func=RetryCommand)

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
            print(f"Version: {RALPH_VERSION}")
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
        args.func(args).execute()
    except KeyboardInterrupt:
        print("\n[ralph] Ok, stopping.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
