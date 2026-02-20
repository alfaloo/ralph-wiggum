"""Template renderer for Ralph Wiggum prompt templates."""

import os
import re

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")


def _load_template(name: str) -> str:
    path = os.path.join(TEMPLATES_DIR, name)
    with open(path, "r") as f:
        return f.read()


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


def parse_init(project_name: str) -> str:
    """Render the init prompt template."""
    template = _load_template("init.md")
    return template.replace("{{PROJECT_NAME}}", project_name)


def parse_interview_questions(project_name: str, round_num: int, total_rounds: int) -> str:
    """Render the question-generation prompt (phase 1 of each interview round)."""
    template = _load_template("interview_questions.md")
    template = template.replace("{{PROJECT_NAME}}", project_name)
    template = template.replace("{{ROUND_NUM}}", str(round_num))
    template = template.replace("{{TOTAL_ROUNDS}}", str(total_rounds))
    return template


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
    template = template.replace("{{PROJECT_NAME}}", project_name)
    template = template.replace("{{ROUND_NUM}}", str(round_num))
    template = template.replace("{{TOTAL_ROUNDS}}", str(total_rounds))
    template = template.replace("{{QUESTIONS}}", questions)
    template = template.replace("{{ANSWERS}}", answers)
    return template


def parse_execute(project_name: str, iteration_num: int, max_iterations: int) -> str:
    """Render the execute prompt template."""
    template = _load_template("execute.md")
    template = template.replace("{{PROJECT_NAME}}", project_name)
    template = template.replace("{{ITERATION_NUM}}", str(iteration_num))
    template = template.replace("{{MAX_ITERATIONS}}", str(max_iterations))
    return template


def parse_comment(project_name: str, user_comment: str) -> str:
    """Render the comment prompt template."""
    template = _load_template("comment.md")
    template = template.replace("{{PROJECT_NAME}}", project_name)
    template = template.replace("{{USER_COMMENT}}", user_comment)
    return template
