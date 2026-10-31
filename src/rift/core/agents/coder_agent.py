from daytona import Daytona, DaytonaConfig
from deepagents import create_deep_agent
from langchain_daytona import DaytonaSandbox

from rift.config import get_settings
from rift.core.llm import make_model
from rift.core.prompts import CODER_AGENT_PROMPT


def build_coder_agent(sandbox_id: str):
    s = get_settings()
    api_key = s.daytona_api_key.get_secret_value() if s.daytona_api_key else None
    client = Daytona(DaytonaConfig(api_key=api_key))
    sandbox = client.get(sandbox_id)
    return create_deep_agent(
        model=make_model("coder"),
        system_prompt=CODER_AGENT_PROMPT,
        backend=DaytonaSandbox(sandbox=sandbox),
        name="coder",
    )
