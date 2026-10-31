from langchain.agents import create_agent
from langchain_openrouter import ChatOpenRouter

from rift.core.llm import make_model
from rift.core.prompts import REVIEW_AGENT_PROMPT


def build_review_agent(sandbox_id: str):
    return create_agent(
        model=make_model("review"),
        system_prompt=REVIEW_AGENT_PROMPT,
        name="reviewer",
    )
