"""Ralph Wiggum CLI entry point."""

import argparse
import sys
from typing import Callable

from ralph.parse import parse_comment, parse_execute, parse_init, parse_interview, parse_interview_questions
from ralph.run import run_comment, run_execute_loop, run_init, run_interview_loop

DEFAULT_ROUNDS = 3
DEFAULT_ITERATIONS = 20


def cmd_init(args: argparse.Namespace) -> None:
    prompt = parse_init(args.project_name)
    run_init(args.project_name, prompt)


def cmd_interview(args: argparse.Namespace) -> None:
    rounds = args.rounds
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

    run_interview_loop(args.project_name, question_prompts, amend_fns)


def cmd_comment(args: argparse.Namespace) -> None:
    prompt = parse_comment(args.project_name, args.comment)
    run_comment(args.project_name, prompt)


def cmd_execute(args: argparse.Namespace) -> None:
    iterations = args.iterations
    # Pre-render all prompts; each references its iteration number
    prompts = [
        parse_execute(args.project_name, iteration_num=i + 1, max_iterations=iterations)
        for i in range(iterations)
    ]
    run_execute_loop(args.project_name, prompts, iterations)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ralph",
        description="Ralph Wiggum — CLI-driven agentic coding framework",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    # ralph init <project-name>
    init_parser = subparsers.add_parser("init", help="Initialize a new project")
    init_parser.add_argument("project_name", metavar="<project-name>")
    init_parser.set_defaults(func=cmd_init)

    # ralph interview <project-name> [--rounds N]
    interview_parser = subparsers.add_parser(
        "interview", help="Run interview agents to refine the spec"
    )
    interview_parser.add_argument("project_name", metavar="<project-name>")
    interview_parser.add_argument(
        "--rounds",
        type=int,
        default=DEFAULT_ROUNDS,
        metavar="N",
        help=f"Number of interview rounds (default: {DEFAULT_ROUNDS})",
    )
    interview_parser.set_defaults(func=cmd_interview)

    # ralph comment <project-name> <comment>
    comment_parser = subparsers.add_parser(
        "comment", help="Refine the spec with a user comment"
    )
    comment_parser.add_argument("project_name", metavar="<project-name>")
    comment_parser.add_argument("comment", metavar="<comment>")
    comment_parser.set_defaults(func=cmd_comment)

    # ralph execute <project-name> [--iterations N]
    execute_parser = subparsers.add_parser(
        "execute", help="Run execute agents to implement the project"
    )
    execute_parser.add_argument("project_name", metavar="<project-name>")
    execute_parser.add_argument(
        "--iterations",
        type=int,
        default=DEFAULT_ITERATIONS,
        metavar="N",
        help=f"Maximum number of agent iterations (default: {DEFAULT_ITERATIONS})",
    )
    execute_parser.set_defaults(func=cmd_execute)

    args = parser.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n[ralph] Interrupted.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
