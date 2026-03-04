import json
from typing import Literal, AsyncGenerator
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from app.agents.state import AgentState
from app.agents.tools import tools
from app.services.llm import get_llm

system_msg = """You are an advanced Geopolitical Intelligence Agent for the GeoVision Lab.
Your objective is to provide concise, accurate, and tactical analysis of conflicts and geopolitical shifts.

You have access to two primary intel feeds:
1. `vector_search`: For historical reports, past wars, and cold war intelligence stored locally.
2. `web_search`: For current, up-to-date, live news and background information on active geopolitics.

Use the proper tool depending on whether the user asks about deep history or current events. If you don't know the answer, use a tool to find out.

Respond in a clear, brief, unclassified military-style format, avoiding robotic language. Always summarize the intel you found.
"""

def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return "__end__"

def call_model(state: AgentState):
    llm = get_llm()
    llm_with_tools = llm.bind_tools(tools)
    messages = [SystemMessage(content=system_msg)] + list(state["messages"])
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

def get_graph():
    checkpointer = MemorySaver()
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", ToolNode(tools))
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue)
    workflow.add_edge("tools", "agent")
    return workflow.compile(checkpointer=checkpointer)

app_graph = get_graph()

# External interface
def process_query(user_query: str, thread_id: str = "default") -> str:
    """Process a user query with conversational memory (non-streaming)."""
    print(f"\n[QUERY] New query received (thread={thread_id}): '{user_query}'")
    inputs = {"messages": [HumanMessage(content=user_query)]}
    config = {"configurable": {"thread_id": thread_id}}
    result = app_graph.invoke(inputs, config=config)
    return result["messages"][-1].content

def _summarise_tool_output(output) -> str:
    """Create a short summary of tool output for the activity trail."""
    text = output.content if hasattr(output, "content") else str(output)
    if not text or "Error" in text:
        return "No results found"
    lines = text.strip().split("\n")
    return f"Retrieved {len(lines)} text blocks"

async def process_query_stream(user_query: str, thread_id: str = "default") -> AsyncGenerator[dict, None]:
    """Yields dicts with type: 'status'|'tool_result'|'token'|'done'|'error'"""
    print(f"\n[QUERY-STREAM] New query received (thread={thread_id}): '{user_query}'")
    inputs = {"messages": [HumanMessage(content=user_query)]}
    config = {"configurable": {"thread_id": thread_id}}
    streaming_started = False

    async for event in app_graph.astream_events(inputs, config=config, version="v2"):
        kind = event.get("event")

        if kind == "on_chat_model_start":
            yield {"type": "status", "phase": "reasoning"}

        elif kind == "on_tool_start":
            tool_name = event.get("name", "unknown")
            tool_input = event.get("data", {}).get("input", {})
            query_used = tool_input.get("query", "")
            phase = "local_rag" if tool_name == "vector_search" else "online_rag"
            yield {
                "type": "status",
                "phase": phase,
                "tool": tool_name,
                "query": query_used
            }

        elif kind == "on_tool_end":
            tool_name = event.get("name", "unknown")
            output = event.get("data", {}).get("output", "")
            text = output.content if hasattr(output, "content") else str(output)
            yield {
                "type": "tool_result",
                "tool": tool_name,
                "summary": _summarise_tool_output(output),
                "content": text,
            }

        elif kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                if not getattr(chunk, "tool_calls", None) and not getattr(chunk, "tool_call_chunks", None):
                    if not streaming_started:
                        yield {"type": "status", "phase": "streaming"}
                        streaming_started = True
                        
                    yield {"type": "token", "content": chunk.content}

    yield {"type": "done"}
