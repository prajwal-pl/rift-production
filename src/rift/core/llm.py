from typing import Literal

from langchain_openrouter import ChatOpenRouter

from rift.config import get_settings

Role = Literal["plan", "design", "coder", "review"]

MODEL_BY_ROLE: dict[Role, str] = {
    "plan": "nvidia/nemotron-3.5-super-vl:free",
    "design": "nvidia/nemotron-3.5-super-vl:free",
    "coder": "nvidia/nemotron-3.5-super-vl:free",
    "review": "nvidia/nemotron-3.5-super-vl:free",
}

TEMPERATURE: dict[Role, float] = {
    "plan": 0.4,
    "design": 0.5,
    "coder": 0.2,
    "review": 0.0,
}


def make_model(role: Role) -> ChatOpenRouter:
    s = get_settings()
    api_key = s.openrouter_api_key.get_secret_value() if s.openrouter_api_key else None
    return ChatOpenRouter(
        model=MODEL_BY_ROLE[role],
        api_key=api_key,
        temperature=TEMPERATURE[role],
        max_retries=3,
    )
