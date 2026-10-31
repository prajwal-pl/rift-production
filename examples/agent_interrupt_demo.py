import asyncio
from typing import Any, TypedDict

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel

LLM_CALLS = {"n": 0}
SIDE = {"n": 0}


class Brief(BaseModel):
    title: str
    audience: str


class FakeLLM(GenericFakeChatModel):
    def bind_tools(self, tools, **kw):
        return self

    def _generate(self, *a, **k):
        LLM_CALLS["n"] += 1
        return super()._generate(*a, **k)


@tool
def ask_user(question: str) -> str:
    """Ask the human a question."""
    ans = interrupt({"question": question})
    return f"User said: {ans}"


def msgs():
    yield AIMessage(content="", tool_calls=[{"name": "ask_user", "args": {"question": "Audience?"}, "id": "1"}])
    yield AIMessage(content="", tool_calls=[{"name": "Brief", "args": {"title": "Rust", "audience": "Engineers"}, "id": "2"}])


agent = create_agent(model=FakeLLM(messages=msgs()), tools=[ask_user],
                     response_format=ToolStrategy(Brief), name="interviewer")


class S(TypedDict, total=False):
    prompt: str
    brief: dict[str, Any]


async def interviewer(state: S):
    SIDE["n"] += 1                                  # side effect BEFORE agent call (anti-pattern, to prove re-run)
    r = await agent.ainvoke({"messages": [HumanMessage(state["prompt"])]})
    return {"brief": r["structured_response"].model_dump()}


g = StateGraph(S)
g.add_node("interviewer", interviewer)
g.add_edge(START, "interviewer")
g.add_edge("interviewer", END)
graph = g.compile(checkpointer=InMemorySaver())


async def main():
    cfg = {"configurable": {"thread_id": "t"}}
    out = await graph.ainvoke({"prompt": "make a deck"}, cfg)
    print("paused:", out["__interrupt__"][0].value, "llm calls:", LLM_CALLS["n"], "side:", SIDE["n"])
    out = await graph.ainvoke(Command(resume="Engineers"), cfg)
    print("brief:", out["brief"], "llm calls:", LLM_CALLS["n"], "side:", SIDE["n"])

asyncio.run(main())
