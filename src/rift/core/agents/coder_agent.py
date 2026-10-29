from daytona import Daytona
from deepagents import create_deep_agent
from langchain_daytona import DaytonaSandbox
from langchain_openrouter import ChatOpenRouter

from rift.core.prompts import CODER_AGENT_PROMPT

sandbox = Daytona().create()
backend = DaytonaSandbox(sandbox=sandbox)

coder_agent = create_deep_agent(
    model=ChatOpenRouter(model="nvidia/nemotron-3.5-super-vl:free"),
    system_prompt=CODER_AGENT_PROMPT,
    backend=backend,
)

# result = coder_agent.ainvoke({"messages": [{"role": "user", "content": ""}]})
