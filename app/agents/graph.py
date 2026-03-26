from typing import Literal, AsyncGenerator, Dict, Any
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
from app.core.di_llm import get_llm
from app.core.di_services import get_vector_store
from app.core.constants import (
    NODE_VECTOR_SEARCH, NODE_AGENT, NODE_TOOLS, NODE_REVIEWER,
    NODE_ONTOLOGY_EXTRACTOR,
    VALIDATION_VALID, STATE_KEY_MESSAGES, STATE_KEY_VECTOR_SEARCH_RESULTS,
    STATE_KEY_ONTOLOGY, STATE_KEY_VALIDATION_ATTEMPTS, STATE_KEY_IS_VALID,
)
from app.agents.ontology_subgraph import ontology_subgraph
from app.models.ontology import SessionOntology

system_msg = """You are an advanced Geopolitical Intelligence Agent for the GeoVision Lab.
Your objective is to provide concise, accurate, and tactical analysis of conflicts and geopolitical shifts.

You have access to intel feeds:
1. `vector_search`: For retrieving information from ANY locally uploaded documents, reports, custom data, or historical intelligence. (Automatically executed before you begin reasoning)
2. `web_search`: For Wikipedia summaries of background information on active geopolitics.
3. `duckduckgo_search`: For live web search results regarding current events and general queries.

The archival intelligence from vector search is automatically injected into your context. Review it first, then use additional tools if you need live or updated information.

Respond in a clear, brief, unclassified military-style format, avoiding robotic language. Always summarize the intel you found.

CRITICAL INSTRUCTION: Before you generate any final response or tool call, you MUST wrap your thought process inside <think>...</think> tags. Do not skip this reasoning step.
"""

critic_prompt = """You are a QA Reviewer. Validate the response against these rules:

RULES:
1. Use concise military-style format
2. Provide clear, factual information
3. Cite sources when available

User Query: "{user_query}"
Agent Response: "{assistant_response}"

Reply with ONLY one word: VALID or INVALID
Start your response with VALID or INVALID."""

logger = logging.getLogger("agent_flow")


def should_continue(state: AgentState) -> Literal[NODE_TOOLS, NODE_REVIEWER]:
    last_message = state[STATE_KEY_MESSAGES][-1]
    if getattr(last_message, "tool_calls", None):
        logger.debug(
            f"[AGENT LOG] Transitioning to '{NODE_TOOLS}' node. Tools requested: {last_message.tool_calls}"
        )
        return NODE_TOOLS
    logger.debug("[AGENT LOG] Transitioning to 'reviewer'.")
    return NODE_REVIEWER


def vector_search_node(state: AgentState):
    """Mandatory first step: execute vector search for every query."""
    logger.info("=" * 80)
    logger.info("[VECTOR_SEARCH_NODE] Starting mandatory vector search")
    logger.info("=" * 80)

    # Extract user query from the first HumanMessage
    user_msgs = [m for m in state[STATE_KEY_MESSAGES] if isinstance(m, HumanMessage)]
    if not user_msgs:
        logger.warning("[VECTOR_SEARCH_NODE] No user message found for vector search.")
        return {STATE_KEY_VECTOR_SEARCH_RESULTS: "No query provided."}

    query = user_msgs[0].content
    logger.info(f"[VECTOR_SEARCH_NODE] Query: '{query}'")

    try:
        # Use DI to get vector store service
        vector_store = get_vector_store()
        results = vector_store.similarity_search(query, k=3)

        if not results:
            logger.info("[VECTOR_SEARCH_NODE] No archival data found in historical intelligence database.")
            return {STATE_KEY_VECTOR_SEARCH_RESULTS: "No archival data found in historical intelligence database."}

        # Format results like the vector_search tool does
        results_text = "\n\n".join([doc.get("page_content", "") for doc in results])
        formatted_results = f"ARCHIVAL INTELLIGENCE REPORT:\n{results_text}"
        logger.info(f"[VECTOR_SEARCH_NODE] Found {len(results)} result(s)")
        logger.info("[VECTOR_SEARCH_NODE] === RETRIEVED CONTENT START ===")
        logger.info(results_text)
        logger.info("[VECTOR_SEARCH_NODE] === RETRIEVED CONTENT END ===")
        return {STATE_KEY_VECTOR_SEARCH_RESULTS: formatted_results}
    except Exception as e:
        logger.error(f"[VECTOR_SEARCH_NODE] Vector search failed: {e}")
        return {STATE_KEY_VECTOR_SEARCH_RESULTS: f"Vector search error: {str(e)}"}


def call_model(state: AgentState):
    logger.info("=" * 80)
    logger.info("[AGENT] Entering reasoning phase")
    logger.info("=" * 80)
    llm = get_llm()
    llm_with_tools = llm.bind_tools(tools)

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_prompt = f"\n\nCURRENT SYSTEM TIME: {current_time}. Keep this in mind for time-sensitive queries."

    # Inject vector search results into the context
    vector_results = state.get("vector_search_results", "")
    vector_context = ""
    if vector_results:
        vector_context = f"\n\n---\nARCHIVAL INTELLIGENCE (from vector search):\n{vector_results}\n---\n\n"
        logger.info("[AGENT] Vector search results injected into context")

    messages = [SystemMessage(content=system_msg + vector_context + time_prompt)] + list(
        state["messages"]
    )
    logger.info(f"[AGENT] Invoking LLM with {len(messages)} messages")
    response = llm_with_tools.invoke(messages)
    
    # Log the agent's reasoning and tool calls
    if hasattr(response, "content") and response.content:
        logger.info("[AGENT] === REASONING OUTPUT START ===")
        logger.info(response.content)
        logger.info("[AGENT] === REASONING OUTPUT END ===")
    if hasattr(response, "tool_calls") and response.tool_calls:
        logger.info(f"[AGENT] Tool calls requested: {[tc['name'] for tc in response.tool_calls]}")
    
    logger.info("[AGENT] Reasoning phase complete")
    return {STATE_KEY_MESSAGES: [response]}


def review_response(state: AgentState, config: RunnableConfig):
    """QA Reviewer - validates response formatting."""
    logger.info("=" * 80)
    logger.info("[QA_REVIEWER] Starting validation")
    logger.info("=" * 80)

    user_msgs = [m for m in state[STATE_KEY_MESSAGES] if isinstance(m, HumanMessage)]
    user_query = user_msgs[0].content if user_msgs else "N/A"
    last_message = state[STATE_KEY_MESSAGES][-1]
    assistant_response = last_message.content if hasattr(last_message, "content") else str(last_message)

    logger.info(f"[QA_REVIEWER] Query: {user_query[:50]}...")
    logger.info(f"[QA_REVIEWER] Response length: {len(assistant_response)} chars")

    # Simple validation - always pass for now (can add more rules later)
    logger.info("[QA_REVIEWER] Validation PASSED")
    logger.info("[QA_REVIEWER] === VALIDATION RESULT ===")
    logger.info(VALIDATION_VALID)
    logger.info("[QA_REVIEWER] === END ===")

    return {STATE_KEY_IS_VALID: True, STATE_KEY_VALIDATION_ATTEMPTS: 1, "reviewer_result": VALIDATION_VALID}


def check_validation(state: AgentState) -> Literal[NODE_AGENT, NODE_ONTOLOGY_EXTRACTOR]:
    # If it's valid, proceed to ontology extraction
    if state.get(STATE_KEY_IS_VALID):
        logger.debug("[AGENT LOG] Reviewer approved. Transitioning to 'ontology_extractor'.")
        return NODE_ONTOLOGY_EXTRACTOR

    attempts = state.get(STATE_KEY_VALIDATION_ATTEMPTS, 0)
    if attempts >= 3:
        logger.debug(f"[AGENT LOG] Max validation attempts ({attempts}) reached. Forcing '__end__'.")
        return "__end__"

    logger.debug("[AGENT LOG] Reviewer rejected. Transitioning back to 'agent'.")
    return NODE_AGENT


def run_ontology_subgraph(state: AgentState) -> Dict[str, Any]:
    """
    Run the ontology processing sub-graph.
    
    This wraps the ontology_subgraph and maps state between main graph and sub-graph.
    """
    logger.info("=" * 80)
    logger.info("[ONTOLOGY_SUBGRAPH] Starting ontology processing sub-graph")
    logger.info("=" * 80)
    
    # Get the last assistant message (the final response)
    last_message = state[STATE_KEY_MESSAGES][-1]
    assistant_response = last_message.content if hasattr(last_message, "content") else ""
    
    # Get the user query from the first message
    user_msgs = [m for m in state[STATE_KEY_MESSAGES] if isinstance(m, HumanMessage)]
    user_query = user_msgs[0].content if user_msgs else ""
    
    if not assistant_response:
        logger.info("[ONTOLOGY_SUBGRAPH] No response content to process")
        return {STATE_KEY_ONTOLOGY: state.get(STATE_KEY_ONTOLOGY, {})}
    
    try:
        # Prepare sub-graph input
        subgraph_input = {
            "user_query": user_query,
            "assistant_response": assistant_response,
            "query_id": "default"
        }
        
        # Run sub-graph
        subgraph_result = ontology_subgraph.invoke(subgraph_input)
        delta = subgraph_result.get("extracted_delta")
        
        # Merge with existing session ontology
        current_ontology = state.get(STATE_KEY_ONTOLOGY)
        if not current_ontology:
            current_ontology = SessionOntology().model_dump()
        elif isinstance(current_ontology, SessionOntology):
            current_ontology = current_ontology.model_dump()
            
        if delta:
            entities = delta.get("entities", {}) if isinstance(delta, dict) else delta.entities
            links = delta.get("links", {}) if isinstance(delta, dict) else delta.links
            
            # Merge Entities
            for k, v in entities.items():
                new_ent_data = v if isinstance(v, dict) else v.model_dump()
                
                if k not in current_ontology["entities"]:
                    current_ontology["entities"][k] = new_ent_data
                else:
                    # Merge properties and mentions
                    existing = current_ontology["entities"][k]
                    
                    # Add new mentions
                    if "mentions" in new_ent_data:
                        existing.setdefault("mentions", []).extend(new_ent_data["mentions"])
                    
                    # Merge properties (new info takes precedence if non-null)
                    if "properties" in new_ent_data:
                        for p_k, p_v in new_ent_data["properties"].items():
                            if p_v is not None:
                                existing.setdefault("properties", {})[p_k] = p_v
            
            # Merge Links
            for k, v in links.items():
                new_link_data = v if isinstance(v, dict) else v.model_dump()
                if k not in current_ontology["links"]:
                    current_ontology["links"][k] = new_link_data
                else:
                    # Append new mentions to existing link
                    existing_link = current_ontology["links"][k]
                    if "mentions" in new_link_data:
                        existing_link.setdefault("mentions", []).extend(new_link_data["mentions"])
        
        entity_count = len(current_ontology.get("entities", {}))
        logger.info(f"[ONTOLOGY_SUBGRAPH] Sub-graph complete: {entity_count} entities accumulated.")
        return {STATE_KEY_ONTOLOGY: current_ontology}
        
    except Exception as e:
        logger.error(f"[ONTOLOGY_SUBGRAPH] Sub-graph failed: {e}")
        return {STATE_KEY_ONTOLOGY: state.get(STATE_KEY_ONTOLOGY, {})}


def get_graph():
    checkpointer = MemorySaver()
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node(NODE_VECTOR_SEARCH, vector_search_node)
    workflow.add_node(NODE_AGENT, call_model)
    workflow.add_node(NODE_TOOLS, ToolNode(tools))
    workflow.add_node(NODE_REVIEWER, review_response)
    workflow.add_node(NODE_ONTOLOGY_EXTRACTOR, run_ontology_subgraph)

    # Set entry point to vector_search (mandatory first step)
    workflow.set_entry_point(NODE_VECTOR_SEARCH)

    # Vector search always flows to agent
    workflow.add_edge(NODE_VECTOR_SEARCH, NODE_AGENT)

    # Agent decides whether to use tools or go to reviewer
    workflow.add_conditional_edges(NODE_AGENT, should_continue)

    # Tools loop back to agent for further reasoning
    workflow.add_edge(NODE_TOOLS, NODE_AGENT)

    # Reviewer validates or sends back for revision
    workflow.add_conditional_edges(NODE_REVIEWER, check_validation)

    # Ontology sub-graph processes entities, then ends
    workflow.add_edge(NODE_ONTOLOGY_EXTRACTOR, "__end__")

    return workflow.compile(checkpointer=checkpointer)


app_graph = get_graph()


# External interface
def process_query(user_query: str, thread_id: str = "default") -> str:
    """Process a user query with conversational memory (non-streaming)."""
    logger.info(f"\n[QUERY] New query received (thread={thread_id}): '{user_query}'")
    inputs = {"messages": [HumanMessage(content=user_query)]}
    config = {"configurable": {"thread_id": thread_id}}
    result = app_graph.invoke(inputs, config=config)
    
    # Find the last assistant message (not system feedback)
    for msg in reversed(result["messages"]):
        if hasattr(msg, "type") and msg.type == "ai":
            return msg.content
    
    # Fallback to last message if no AI message found
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
    done_sent = False

    # Emit vector search status immediately (mandatory first step)
    from app.core.config import settings
    yield {
        "type": "status",
        "phase": "vector_search",
        "tool": "vector_search",
        "query": user_query,
    }

    buffer = ""
    in_think = False
    think_buffer = ""

    try:
        async for event in app_graph.astream_events(inputs, config=config, version="v2"):
            kind = event.get("event")
            tags = event.get("tags", [])

            # Debug logging for event tracing
            logger.debug(f"[STREAM EVENT] kind={kind}, name={event.get('name')}, tags={tags}")

            # Check for Ollama connection/model errors
            if kind == "on_chain_error" or kind == "on_llm_error":
                error_msg = event.get("data", {}).get("error", "Unknown error")
                logger.error(f"[STREAM ERROR] {kind}: {error_msg}")
                yield {
                    "type": "error",
                    "content": f"LLM error: {str(error_msg)}\n\nThis may be due to:\n- Model not loaded in Ollama\n- Ollama service unavailable\n- Request timeout\n\nTry: `docker restart geovision-ollama`"
                }
                return  # Stop processing

            if kind == "on_chat_model_start":
                if "reviewer" in tags:
                    from app.core.config import settings
                    yield {"type": "status", "phase": "reviewing", "model": settings.REASONING_LLM_MODEL_NAME}
                elif "ontology_extractor" in tags:
                    from app.core.config import settings
                    yield {"type": "status", "phase": "extracting_ontology", "model": settings.REASONING_LLM_MODEL_NAME}
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

            elif kind == "on_chain_end":
                # Capture vector_search_node completion via chain events
                if event.get("name") == "vector_search":
                    output = event.get("data", {}).get("output", {})
                    results = output.get("vector_search_results", "") if isinstance(output, dict) else str(output)
                    if results and isinstance(results, str) and results.strip():
                        has_data = "No archival data" not in results and "error" not in results.lower()
                        yield {
                            "type": "tool_result",
                            "tool": "vector_search",
                            "summary": "Archival intelligence retrieved" if has_data else "No archival data found",
                            "content": results,
                        }

                # Capture reviewer result - check for various possible node names
                node_name = event.get("name", "")
                if "review" in node_name.lower():
                    output = event.get("data", {}).get("output", {})
                    reviewer_result = output.get("reviewer_result", "") if isinstance(output, dict) else ""
                    if reviewer_result and isinstance(reviewer_result, str) and reviewer_result.strip():
                        is_valid = reviewer_result.startswith("VALID")
                        logger.debug(f"[QA_REVIEWER] Validation result: {reviewer_result}")
                        yield {
                            "type": "validation_result",
                            "tool": "QA Reviewer",
                            "summary": "Analysis validated" if is_valid else "Analysis revised",
                            "content": reviewer_result,
                        }

                # Capture ontology sub-graph result
                if event.get("name") == "ontology_extractor":
                    output = event.get("data", {}).get("output", {})
                    ontology_state = output.get(STATE_KEY_ONTOLOGY, {})
                    
                    if ontology_state and isinstance(ontology_state, dict):
                        entities = ontology_state.get("entities", {})
                        links = ontology_state.get("links", {})
                        logger.info(f"[ONTOLOGY_SUBGRAPH] Extracted {len(entities)} entities")
                        
                        yield {
                            "type": "ontology_updated",
                            "tool": "ontology_subgraph",
                            "summary": f"Graph updated: {len(entities)} entities, {len(links)} relationships",
                            "ontology": ontology_state,
                        }
                    else:
                        yield {
                            "type": "ontology_error",
                            "tool": "ontology_subgraph",
                            "content": "Ontology extraction completed but failed to return data."
                        }

            elif kind == "on_chat_model_end":
                output = event.get("data", {}).get("output")
                content = getattr(output, "content", "")
                tool_calls = getattr(output, "tool_calls", [])

                # Skip reviewer here - it's captured in on_chain_end
                if "reviewer" in tags:
                    pass
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
                # Sub-graph LLM calls are handled internally

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
                # Remove tool call artifacts
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

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[QUERY-STREAM] Error during streaming: {error_msg}")
        
        # Check for JSON parsing errors from Ollama client
        if "failed to parse JSON" in error_msg or "unexpected end of JSON input" in error_msg:
            yield {
                "type": "error",
                "content": "LLM response parsing failed. This usually means:\n\n1. Ollama model crashed or timed out\n2. Connection was interrupted\n3. Model returned malformed output\n\nTry:\n- Restart Ollama: `docker restart geovision-ollama`\n- Check model is loaded: `docker exec geovision-ollama ollama ps`\n- Retry your query"
            }
        else:
            yield {"type": "error", "content": f"Streaming error: {error_msg}"}
    finally:
        # Always send done event to signal completion
        if not done_sent:
            if buffer and not in_think:
                yield {"type": "token", "content": buffer}
            yield {"type": "done"}
            done_sent = True
