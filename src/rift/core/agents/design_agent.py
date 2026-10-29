from langchain.agents import create_agent
from langchain_openrouter import ChatOpenRouter

from rift.core.prompts import DESIGN_AGENT_PROMPT

design_agent = create_agent(
    model=ChatOpenRouter(model="nvidia/nemotron-3.5-super-vl:free"),
    system_prompt=DESIGN_AGENT_PROMPT,
)
