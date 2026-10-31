"""Wires and compiles the Rift `StudioState` graph."""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from rift.core.ports.sandbox import SandboxProvider
from rift.core.ports.storage import StorageProvider
from rift.core.studio.nodes import AgentFactories, StudioNodes
from rift.core.studio.routing import route_after_verify, route_from_start
from rift.core.studio.state import StudioState


def build_studio_graph(
    *,
    sandbox: SandboxProvider,
    storage: StorageProvider,
    agents: AgentFactories,
    checkpointer: BaseCheckpointSaver | None = None,
):
    n = StudioNodes(sandbox=sandbox, storage=storage, agents=agents)
    g = StateGraph(StudioState)

    g.add_node("planner", n.planner)
    g.add_node("designer", n.designer)
    g.add_node("provision", n.provision)
    g.add_node("coder", n.coder)
    g.add_node("verify", n.verify)
    g.add_node("reviewer", n.reviewer)  # returns Command[Literal["coder", "publish", "fail"]]
    g.add_node("publish", n.publish)
    g.add_node("fail", n.fail)
    g.add_node("cleanup", n.cleanup)

    g.add_conditional_edges(START, route_from_start, ["planner", "provision"])
    g.add_edge("planner", "designer")
    g.add_edge("designer", "provision")
    g.add_edge("provision", "coder")
    g.add_edge("coder", "verify")
    g.add_conditional_edges("verify", route_after_verify, ["reviewer", "coder", "fail"])
    # reviewer -> coder | publish | fail is handled atomically via Command(goto=...)
    g.add_edge("publish", "cleanup")
    g.add_edge("fail", "cleanup")
    g.add_edge("cleanup", END)

    return g.compile(checkpointer=checkpointer)
