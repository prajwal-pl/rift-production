from langchain.tools import tool
from langgraph.types import interrupt

from rift.core.domain.gdd import Question


@tool
def ask_user(questions: list[Question]):
    """Ask the human clarifying questions about the game they want.

    Send ALL your questions in ONE call (max 5). Only ask what would materially change the game.
    Offer sensible `options` so the user can answer with one click.
    """
    answer: dict[str, str] = interrupt(
        {"type": "clarification", "questions": [q.model_dump() for q in questions]}
    )
    lines = [
        f" - {q.id}: {answer.get(q.id, '(no answer - choose a sensible default and list it as an assumption)')}"
        for q in questions
    ]
    return "User answers: \n" + "\n".join(lines)
