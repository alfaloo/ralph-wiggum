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


def _resolve_questions_block(template: str, has_questions: bool) -> str:
    """Replace {% if QUESTIONS %} ... {% else %} ... {% endif %} blocks."""
    def replacer(match: re.Match) -> str:
        if_block = match.group(1)
        else_block = match.group(2)
        return if_block.strip() if has_questions else else_block.strip()

    return re.sub(
        r"\{%\s*if QUESTIONS\s*%\}(.*?)\{%\s*else\s*%\}(.*?)\{%\s*endif\s*%\}",
        replacer,
        template,
        flags=re.DOTALL,
    )


def parse_questions_md(project_name: str, round_num: int, total_rounds: int) -> str:
    """Render the question-generation prompt (phase 1 of each interview round)."""
    return _render(
        "questions.md",
        PROJECT_NAME=project_name,
        ROUND_NUM=str(round_num),
        TOTAL_ROUNDS=str(total_rounds),
    )


def parse_generate_tasks_md(
    project_name: str,
    *,
    round_num: int = 0,
    total_rounds: int = 0,
    questions: str = "",
    answers: str = "",
    user_comment: str = "",
) -> str:
    """Render the generate_tasks prompt template.

    In interview mode (questions supplied), incorporates Q&A and updates spec.md and tasks.json.
    In comment mode (user_comment supplied), incorporates the comment and updates spec.md and tasks.json.
    """
    template = _load_template("generate_tasks.md")
    template = _resolve_questions_block(template, has_questions=bool(questions))
    if questions:
        return _substitute(
            template,
            PROJECT_NAME=project_name,
            ROUND_NUM=str(round_num),
            TOTAL_ROUNDS=str(total_rounds),
            QUESTIONS=questions,
            ANSWERS=answers,
        )
    return _substitute(template, PROJECT_NAME=project_name, USER_COMMENT=user_comment)


def parse_execute_md(project_name: str, iteration_num: int, max_iterations: int) -> str:
    """Render the execute prompt template."""
    return _render(
        "execute.md",
        PROJECT_NAME=project_name,
        ITERATION_NUM=str(iteration_num),
        MAX_ITERATIONS=str(max_iterations),
    )


def parse_execute_async_md(
    project_name: str, task_id: str, iteration_num: int, max_iterations: int
) -> str:
    """Render the async execute prompt template for a pre-assigned task."""
    return _render(
        "execute_async.md",
        PROJECT_NAME=project_name,
        TASK_ID=task_id,
        ITERATION_NUM=str(iteration_num),
        MAX_ITERATIONS=str(max_iterations),
    )


def parse_summarise_md(project_name: str, ralph_dir: str, exit_reason: str) -> str:
    """Render the results summary prompt template."""
    return _render(
        "summarise.md",
        PROJECT_NAME=project_name,
        ralph_dir=ralph_dir,
        EXIT_REASON=exit_reason,
    )
