"""LangGraph agent for Earth Observation questions."""

from typing import Any

from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from eve_agent.mcp_client import load_mcp_tools
from eve_agent.settings import OLLAMA_MODEL
from eve_agent.tracing import AgentTrace

MAX_HISTORY_TURNS = 6
MAX_TOOL_OUTPUT_CHARS = 8_000
TOOL_OUTPUT_TRUNCATION_MARKER = "\n[Tool output truncated]"

SYSTEM_PROMPT = """\
You are an Earth Observation assistant.
Use the available MCP tools for factual questions about wildfire events and
historical weather. Ground factual claims in tool results, identify the data
source, and preserve units. If a tool fails, returns no relevant data, or does
not support an answer, say so instead of guessing. EONET wildfire-category
events may include prescribed burns; do not describe them as confirmed
uncontrolled fires unless the tool data supports that conclusion.
"""


def _format_tool_error(error: Exception) -> str:
    return f"Tool execution failed ({type(error).__name__}): {error}"


def _prune_history(state: MessagesState) -> dict[str, list[RemoveMessage]]:
    messages = state["messages"]
    user_turns = [
        index for index, message in enumerate(messages) if isinstance(message, HumanMessage)
    ]
    if len(user_turns) <= MAX_HISTORY_TURNS:
        return {}

    remove_before = user_turns[-MAX_HISTORY_TURNS]
    removed_messages = []
    for message in messages[:remove_before]:
        if message.id is None:
            raise ValueError("Cannot prune a conversation message without an ID")
        removed_messages.append(RemoveMessage(id=message.id))
    return {"messages": removed_messages}


def _truncate_tool_outputs(state: MessagesState) -> dict[str, list[ToolMessage]]:
    updated_messages = []
    for message in state["messages"]:
        if not isinstance(message, ToolMessage):
            continue
        content = message.content if isinstance(message.content, str) else str(message.content)
        if len(content) > MAX_TOOL_OUTPUT_CHARS:
            content = (
                content[: MAX_TOOL_OUTPUT_CHARS - len(TOOL_OUTPUT_TRUNCATION_MARKER)]
                + TOOL_OUTPUT_TRUNCATION_MARKER
            )
            updated_messages.append(message.model_copy(update={"content": content}))
    return {"messages": updated_messages}


def _create_agent_graph(
    model: Runnable,
    tools: list[BaseTool],
) -> CompiledStateGraph:
    graph = StateGraph(MessagesState)

    async def call_model(state: MessagesState) -> dict[str, list[AnyMessage]]:
        messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        response = await model.ainvoke(messages)
        return {"messages": [response]}

    graph.add_node("assistant", call_model)
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=_format_tool_error))
    graph.add_node("prune_before_model", _prune_history)
    graph.add_node("truncate_tool_outputs", _truncate_tool_outputs)
    graph.add_node("prune_after_turn", _prune_history)
    graph.add_edge(START, "prune_before_model")
    graph.add_edge("prune_before_model", "assistant")
    graph.add_conditional_edges(
        "assistant",
        tools_condition,
        {"tools": "tools", END: "prune_after_turn"},
    )
    graph.add_edge("tools", "truncate_tool_outputs")
    graph.add_edge("truncate_tool_outputs", "assistant")
    graph.add_edge("prune_after_turn", END)
    return graph.compile(checkpointer=MemorySaver())


async def build_agent() -> CompiledStateGraph:
    """Build the agent and load its tools from the running MCP server."""
    tools = await load_mcp_tools()
    model = ChatOllama(model=OLLAMA_MODEL, temperature=0).bind_tools(tools)
    return _create_agent_graph(model, tools)


async def invoke_agent_turn(
    agent: CompiledStateGraph,
    session_id: str,
    message: str,
) -> dict[str, Any]:
    """Run one turn, preserving history under the given session ID."""
    if not session_id.strip():
        raise ValueError("session_id must not be empty")
    trace = AgentTrace(session_id, message)
    try:
        async for event in agent.astream_events(
            {"messages": [HumanMessage(content=message)]},
            config={"configurable": {"thread_id": session_id}},
            version="v2",
        ):
            trace.observe(event)
        result = trace.result()
        trace.complete(result)
        return result
    except Exception as error:
        trace.fail(error)
        raise
    finally:
        trace.write()
