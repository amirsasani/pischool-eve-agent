"""LangGraph agent for Earth Observation questions."""

from langchain_core.messages import AnyMessage, SystemMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from eve_agent.mcp_client import load_mcp_tools
from eve_agent.settings import OLLAMA_MODEL

SYSTEM_PROMPT = """\
You are an Earth Observation assistant.
Use the available MCP tools for factual questions about wildfire events and
historical weather. Ground factual claims in tool results, identify the data
source, and preserve units. If a tool fails, returns no relevant data, or does
not support an answer, say so instead of guessing. EONET wildfire-category
events may include prescribed burns; do not describe them as confirmed
uncontrolled fires unless the tool data supports that conclusion.
"""


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
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "assistant")
    graph.add_conditional_edges("assistant", tools_condition)
    graph.add_edge("tools", "assistant")
    return graph.compile()


async def build_agent() -> CompiledStateGraph:
    """Build the agent and load its tools from the running MCP server."""
    tools = await load_mcp_tools()
    model = ChatOllama(model=OLLAMA_MODEL, temperature=0).bind_tools(tools)
    return _create_agent_graph(model, tools)
