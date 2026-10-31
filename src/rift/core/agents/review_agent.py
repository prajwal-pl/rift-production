from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

from rift.core.domain.gdd import ReviewVerdict
from rift.core.llm import make_model
from rift.core.ports.sandbox import SandboxProvider
from rift.core.prompts import REVIEW_AGENT_PROMPT
from rift.core.toolbox.sandbox_tools import make_readonly_tools


def build_review_agent(sandbox: SandboxProvider, sandbox_id: str):
    return create_agent(
        model=make_model("review"),
        tools=make_readonly_tools(sandbox, sandbox_id),
        system_prompt=REVIEW_AGENT_PROMPT,
        response_format=ToolStrategy(ReviewVerdict),
        name="reviewer",
    )
