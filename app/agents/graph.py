from typing import Literal, AsyncGenerator
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
import logging
import re
from datetime import datetime
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from app.agents.state import AgentState
from app.agents.tools import tools
from app.services.llm import get_reasoning_llm, get_reviewer_llm

system_msg = """You are an advanced Geopolitical Intelligence Agent for the GeoVision Lab.
Your objective is to provide concise, accurate, and tactical analysis of conflicts and geopolitical shifts.

You have access to intel feeds:
1. `vector_search`: For historical reports, past wars, and cold war intelligence stored locally.
2. `web_search`: For Wikipedia summaries of background information on active geopolitics.
3. `duckduckgo_search`: For live web search results regarding current events and general queries.

Use the proper tool depending on whether the user asks about deep history or current events. If you don't know the answer, use a tool to find out.

CRITICAL INSTRUCTION: If the user asks about a specific location, city, country, or region, you MUST ALWAYS provide a map for it. 
For a specific city or exact location, include its exact coordinates using EXACTLY this format:
[map: Location Name, latitude, longitude]

For a whole country, use EXACTLY this format instead:
[map-country: Country Name]

Examples:
[map: Kyiv, 50.4501, 30.5234]
[map-country: Taiwan]

Do NOT say "I cannot provide a visual map". The system will intercept the map tags and render it automatically. Simply output the tag.

Respond in a clear, brief, unclassified military-style format, avoiding robotic language. Always summarize the intel you found.

CRITICAL INSTRUCTION: Before you generate any final response or tool call, you MUST wrap your thought process inside <think>...</think> tags. Do not skip this reasoning step.
"""

critic_prompt = """You are a strict QA Reviewer for a Geopolitical Intelligence Agent.
Rule 1: If the user asked about a specific location, city, or region, the agent MUST include exactly one or more [map: Location Name, latitude, longitude] tags. (e.g. [map: Kyiv, 50.4501, 30.5234]). 
Rule 2: If the user asked about a whole country, the agent MUST include exactly one or more [map-country: Country Name] tags. (e.g. [map-country: Taiwan]).
Rule 3: Responses must be concise, unclassified military-style format. 

Original User Query: "{user_query}"
Agent Response: "{assistant_response}"

If the agent properly followed the rules, output exactly the word: VALID
If the agent failed (e.g., missed a map tag for a location, or hallucinated the tag formatting), output: INVALID: <reason and instructions for the agent to fix it>
"""

logger = logging.getLogger("agent_flow")


def should_continue(state: AgentState) -> Literal["tools", "reviewer"]:
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        logger.debug(
            f"[AGENT LOG] Transitioning to 'tools' node. Tools requested: {last_message.tool_calls}"
        )
        return "tools"
    logger.debug("[AGENT LOG] Transitioning to 'reviewer'.")
    return "reviewer"


def call_model(state: AgentState):
    logger.debug("[AGENT LOG] Entering 'call_model' node.")
    llm = get_reasoning_llm()
    llm_with_tools = llm.bind_tools(tools)

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_prompt = f"\n\nCURRENT SYSTEM TIME: {current_time}. Keep this in mind for time-sensitive queries."

    messages = [SystemMessage(content=system_msg + time_prompt)] + list(
        state["messages"]
    )
    logger.debug(f"[AGENT LOG] Invoking LLM with {len(messages)} messages.")
    response = llm_with_tools.invoke(messages)
    logger.debug("[AGENT LOG] LLM responded.")
    return {"messages": [response]}


def review_response(state: AgentState, config: RunnableConfig):
    logger.debug("[AGENT LOG] Entering 'review_response' node.")
    llm = get_reviewer_llm()
    
    user_msgs = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    user_query = user_msgs[0].content if user_msgs else "N/A"
    
    last_message = state["messages"][-1]
    assistant_response = last_message.content if hasattr(last_message, "content") else str(last_message)
    

    formatted_prompt = critic_prompt.format(user_query=user_query, assistant_response=assistant_response)
    response = llm.with_config({"tags": ["reviewer"]}).invoke([SystemMessage(content=formatted_prompt)], config=config)
    content = response.content.strip() if hasattr(response, "content") else str(response).strip()
    
    if content.startswith("VALID"):
        logger.debug("[AGENT LOG] Validation passed.")
        return {"is_valid": True, "validation_attempts": 1}
    else:
        logger.debug(f"[AGENT LOG] Validation failed: {content}")
        return {
            "is_valid": False,
            "validation_attempts": 1,
            "messages": [SystemMessage(content=f"CRITICAL FEEDBACK FROM QA REVIEWER: {content}. You MUST fix this in your next response. NEVER apologize, just output the corrected intelligence report.", additional_kwargs={"role": "system"})]
        }


def check_validation(state: AgentState) -> Literal["agent", "__end__"]:
    # If it's valid, or we've tried too many times, we end to avoid infinite loops
    if state.get("is_valid"):
        logger.debug("[AGENT LOG] Reviewer approved. Transitioning to '__end__'.")
        return "__end__"
    
    attempts = state.get("validation_attempts", 0)
    if attempts >= 3:
        logger.debug(f"[AGENT LOG] Max validation attempts ({attempts}) reached. Forcing '__end__'.")
        return "__end__"
    
    logger.debug("[AGENT LOG] Reviewer rejected. Transitioning back to 'agent'.")
    return "agent"


def get_graph():
    checkpointer = MemorySaver()
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", ToolNode(tools))
    workflow.add_node("reviewer", review_response)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue)
    workflow.add_edge("tools", "agent")
    workflow.add_conditional_edges("reviewer", check_validation)
    return workflow.compile(checkpointer=checkpointer)


app_graph = get_graph()


# External interface
def process_query(user_query: str, thread_id: str = "default") -> str:
    """Process a user query with conversational memory (non-streaming)."""
    logger.info(f"\n[QUERY] New query received (thread={thread_id}): '{user_query}'")
    inputs = {"messages": [HumanMessage(content=user_query)]}
    config = {"configurable": {"thread_id": thread_id}}
    result = app_graph.invoke(inputs, config=config)
    return result["messages"][-1].content


def _format_blocks(text: str) -> list[str]:
    clean_text = re.sub(r"^ARCHIVAL INTELLIGENCE REPORT:\n*", "", text, flags=re.IGNORECASE)
    clean_text = re.sub(r"^LIVE WEB INTELLIGENCE(?: \(.*?\))?:\n*", "", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"^LIVE WEB SEARCH RESULTS:\n*", "", clean_text, flags=re.IGNORECASE)
    
    if "\n\n" in clean_text:
        blocks = [b.strip() for b in clean_text.split("\n\n") if b.strip()]
    else:
        blocks = [b.strip() for b in clean_text.split("\n") if b.strip()]
        
    return blocks if blocks else [text]

def _summarise_tool_output(output) -> str:
    """Create a short summary of tool output for the activity trail."""
    text = output.content if hasattr(output, "content") else str(output)
    if not text or "Error" in text:
        return "No results found"
    
    blocks = _format_blocks(text)
    return f"Retrieved {len(blocks)} text block{'s' if len(blocks) != 1 else ''}"


async def process_query_stream(
    user_query: str, thread_id: str = "default"
) -> AsyncGenerator[dict, None]:
    """Yields dicts with type: 'status'|'tool_result'|'token'|'done'|'error'"""
    logger.info(
        f"\n[QUERY-STREAM] New query received (thread={thread_id}): '{user_query}'"
    )
    inputs = {"messages": [HumanMessage(content=user_query)]}
    config = {"configurable": {"thread_id": thread_id}}
    streaming_started = False
    
    buffer = ""
    in_think = False
    think_buffer = ""

    async for event in app_graph.astream_events(inputs, config=config, version="v2"):
        kind = event.get("event")
        tags = event.get("tags", [])

        if kind == "on_chat_model_start":
            if "reviewer" in tags:
                from app.core.config import settings
                yield {"type": "status", "phase": "reviewing", "model": settings.REVIEWER_LLM_MODEL_NAME}
            else:
                from app.core.config import settings
                if streaming_started:
                    yield {"type": "status", "phase": "revising", "model": settings.REASONING_LLM_MODEL_NAME}
                yield {"type": "status", "phase": "reasoning", "model": settings.REASONING_LLM_MODEL_NAME}

        elif kind == "on_tool_start":
            tool_name = event.get("name", "unknown")
            tool_input = event.get("data", {}).get("input", {})
            query_used = tool_input.get("query", "")
            phase = "vector_search" if tool_name == "vector_search" else "online_search"
            yield {
                "type": "status",
                "phase": phase,
                "tool": tool_name,
                "query": query_used,
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

        elif kind == "on_chat_model_end":
            output = event.get("data", {}).get("output")
            content = getattr(output, "content", "")
            tool_calls = getattr(output, "tool_calls", [])
            
            if "reviewer" in tags:
                yield {
                    "type": "tool_result",
                    "tool": "QA Reviewer",
                    "summary": "Analysis completed",
                    "content": content
                }
            elif tool_calls and content:
                yield {
                    "type": "tool_result",
                    "tool": "reasoning",
                    "summary": "Reasoning steps completed",
                    "content": content.strip()
                }

        elif kind == "on_chat_model_stream":
            if "reviewer" in tags:
                continue

            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                # Process content from ALL chunks, even if they have tool calls.
                # Tool call reasoning is often in chunks that also have tool_call_chunks present!
                content_chunk = chunk.content
                if isinstance(content_chunk, list):
                    # Sometimes content is a list of dicts
                    content_chunk = "".join([c.get("text", "") for c in content_chunk if isinstance(c, dict) and "text" in c])
                elif not isinstance(content_chunk, str):
                    content_chunk = str(content_chunk)

                # Remove tool_code and tool_call tags as they arrive
                content_chunk = content_chunk.replace("<tool_code>", "").replace("</tool_code>", "")
                content_chunk = content_chunk.replace("<tool_call>", "").replace("</tool_call>", "")
                
                if not content_chunk:
                    continue
                    
                buffer += content_chunk
                
                while buffer:
                    if not in_think:
                        if "<think>" in buffer:
                            idx = buffer.find("<think>")
                            before = buffer[:idx]
                            if before:
                                if not streaming_started:
                                    yield {"type": "status", "phase": "streaming"}
                                    streaming_started = True
                                yield {"type": "token", "content": before}
                            buffer = buffer[idx + len("<think>"):]
                            in_think = True
                        else:
                            idx = buffer.rfind("<")
                            if idx == -1:
                                if not streaming_started:
                                    yield {"type": "status", "phase": "streaming"}
                                    streaming_started = True
                                yield {"type": "token", "content": buffer}
                                buffer = ""
                            else:
                                before = buffer[:idx]
                                if before:
                                    if not streaming_started:
                                        yield {"type": "status", "phase": "streaming"}
                                        streaming_started = True
                                    yield {"type": "token", "content": before}
                                buffer = buffer[idx:]
                                if len(buffer) > 15:
                                    if not streaming_started:
                                        yield {"type": "status", "phase": "streaming"}
                                        streaming_started = True
                                    yield {"type": "token", "content": buffer}
                                    buffer = ""
                                break
                    else: # in_think
                        if "</think>" in buffer:
                            idx = buffer.find("</think>")
                            think_buffer += buffer[:idx]
                            yield {
                                "type": "tool_result", 
                                "tool": "reasoning", 
                                "summary": "Reasoning steps completed", 
                                "content": think_buffer.strip()
                            }
                            think_buffer = ""
                            buffer = buffer[idx + len("</think>"):]
                            in_think = False
                        else:
                            idx = buffer.rfind("<")
                            if idx == -1:
                                think_buffer += buffer
                                buffer = ""
                            else:
                                think_buffer += buffer[:idx]
                                buffer = buffer[idx:]
                                if len(buffer) > 15:
                                    think_buffer += buffer
                                    buffer = ""
                                break

    if buffer:
        if in_think:
            think_buffer += buffer
            yield {
                "type": "tool_result", 
                "tool": "reasoning", 
                "summary": "Reasoning steps completed", 
                "content": think_buffer.strip()
            }
        else:
            if not streaming_started:
                yield {"type": "status", "phase": "streaming"}
            yield {"type": "token", "content": buffer}

    yield {"type": "done"}
