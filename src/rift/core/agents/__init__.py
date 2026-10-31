from rift.core.agents.coder_agent import build_coder_agent
from rift.core.agents.design_agent import build_design_agent
from rift.core.agents.plan_agent import build_plan_agent
from rift.core.agents.review_agent import build_review_agent
from rift.core.ports.sandbox import SandboxProvider
from rift.core.studio.nodes import AgentFactories


def default_agent_factories(sandbox: SandboxProvider) -> AgentFactories:
    return AgentFactories(
        plan=build_plan_agent,
        design=build_design_agent,
        code=build_coder_agent,
        review=lambda sid: build_review_agent(sandbox, sid),
    )


__all__ = [
    "build_coder_agent",
    "build_design_agent",
    "build_plan_agent",
    "build_review_agent",
    "default_agent_factories",
]
