from langchain.agents import create_agent
from langchain_openrouter import ChatOpenRouter

from rift.core.prompts import REVIEW_AGENT_PROMPT

review_agent = create_agent(
    model=ChatOpenRouter(model="nvidia/nemotron-3.5-super-vl:free"),
    system_prompt=REVIEW_AGENT_PROMPT,
)
