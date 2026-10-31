from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

from rift.core.domain.gdd import GameDesignDoc
from rift.core.llm import make_model
from rift.core.prompts import DESIGN_AGENT_PROMPT


def build_design_agent():
    return create_agent(
        model=make_model("design"),
        system_prompt=DESIGN_AGENT_PROMPT,
        response_format=ToolStrategy(GameDesignDoc),
        name="designer",
    )
