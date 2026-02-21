"""Template renderer for Ralph Wiggum prompt templates."""

import os
import re

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")


def _load_template(name: str) -> str:
    path = os.path.join(TEMPLATES_DIR, name)
    with open(path, "r") as f:
        return f.read()


def _substitute(template: str, **vars: str) -> str:
    """Replace {{KEY}} placeholders with values in a template string."""
    for key, value in vars.items():
        template = template.replace(f"{{{{{key}}}}}", value)
    return template


def _render(name: str, **vars: str) -> str:
    """Load a template file and substitute {{KEY}} placeholders."""
    return _substitute(_load_template(name), **vars)


def _resolve_final_round(template: str, is_final: bool) -> str:
    """Replace {% if IS_FINAL_ROUND %} ... {% endif %} blocks."""
    def replacer(match: re.Match) -> str:
        return match.group(1).strip() if is_final else ""

    return re.sub(
        r"\{%\s*if IS_FINAL_ROUND\s*%\}(.*?)\{%\s*endif\s*%\}",
        replacer,
        template,
        flags=re.DOTALL,
    )


def parse_interview_questions(project_name: str, round_num: int, total_rounds: int) -> str:
    """Render the question-generation prompt (phase 1 of each interview round)."""
    return _render(
        "questions.md",
        PROJECT_NAME=project_name,
        ROUND_NUM=str(round_num),
        TOTAL_ROUNDS=str(total_rounds),
    )


def parse_interview(
    project_name: str,
    round_num: int,
    total_rounds: int,
    questions: str,
    answers: str,
) -> str:
    """Render the spec-amendment prompt (phase 2 of each interview round).

    Injects the questions Claude generated and the user's answers so the agent
    can amend spec.md (and, on the final round, generate tasks.json).
    """
    template = _load_template("interview.md")
    template = _resolve_final_round(template, is_final=(round_num == total_rounds))
    return _substitute(
        template,
        PROJECT_NAME=project_name,
        ROUND_NUM=str(round_num),
        TOTAL_ROUNDS=str(total_rounds),
        QUESTIONS=questions,
        ANSWERS=answers,
    )


def parse_execute(project_name: str, iteration_num: int, max_iterations: int) -> str:
    """Render the execute prompt template."""
    return _render(
        "execute.md",
        PROJECT_NAME=project_name,
        ITERATION_NUM=str(iteration_num),
        MAX_ITERATIONS=str(max_iterations),
    )


def parse_comment(project_name: str, user_comment: str) -> str:
    """Render the comment prompt template."""
    return _render("comment.md", PROJECT_NAME=project_name, USER_COMMENT=user_comment)


def parse_results_summary(project_name: str, ralph_dir: str, exit_reason: str) -> str:
    """Render the results summary prompt template."""
    return _render(
        "summarise.md",
        PROJECT_NAME=project_name,
        ralph_dir=ralph_dir,
        EXIT_REASON=exit_reason,
    )
