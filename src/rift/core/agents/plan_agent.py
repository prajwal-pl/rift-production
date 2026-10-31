from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain.agents.structured_output import ToolStrategy

from rift.core.domain.gdd import GameBrief
from rift.core.llm import make_model
from rift.core.prompts import PLAN_AGENT_PROMPT
from rift.core.toolbox.interactive_tools import ask_user


def build_plan_agent():
    return create_agent(
        model=make_model("plan"),
        system_prompt=PLAN_AGENT_PROMPT,
        tools=[ask_user],
        response_format=ToolStrategy(GameBrief),
        middleware=[
            ToolCallLimitMiddleware(
                tool_name="ask_user", run_limit=3, exit_behavior="continue"
            )
        ],
        name="planner",
    )
