from langchain.agents import create_agent

from rift.core.prompts import PLAN_AGENT_PROMPT

plan_agent = create_agent(
    model="nvidia/nemotron-3.5-super-vl:free", system_prompt=PLAN_AGENT_PROMPT
)

# result = plan_agent.invoke()
