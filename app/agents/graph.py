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
from app.services.llm import get_reasoning_llm
from app.services.vector_store import similarity_search

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

RULES (apply only if relevant):
1. REAL geographic locations (cities, countries) MUST have [map: Name, lat, lon] tags
2. REAL countries MUST have [map-country: Country] tags  
3. Use concise military-style format

IMPORTANT: Fictional entities (DuckyDucks, fantasy locations) do NOT need maps. Only flag REAL locations.

User Query: "{user_query}"
Agent Response: "{assistant_response}"

Reply with ONLY one word: VALID or INVALID
Start your response with VALID or INVALID."""

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


def vector_search_node(state: AgentState):
    """Mandatory first step: execute vector search for every query."""
    logger.info("=" * 80)
    logger.info("[VECTOR_SEARCH_NODE] Starting mandatory vector search")
    logger.info("=" * 80)
    
    # Extract user query from the first HumanMessage
    user_msgs = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    if not user_msgs:
        logger.warning("[VECTOR_SEARCH_NODE] No user message found for vector search.")
        return {"vector_search_results": "No query provided."}
    
    query = user_msgs[0].content
    logger.info(f"[VECTOR_SEARCH_NODE] Query: '{query}'")
    
    try:
        results = similarity_search(query, k=3)
        if not results:
            logger.info("[VECTOR_SEARCH_NODE] No archival data found in historical intelligence database.")
            return {"vector_search_results": "No archival data found in historical intelligence database."}

        # Format results like the vector_search tool does
        results_text = "\n\n".join([doc.get("page_content", "") for doc in results])
        formatted_results = f"ARCHIVAL INTELLIGENCE REPORT:\n{results_text}"
        logger.info(f"[VECTOR_SEARCH_NODE] Found {len(results)} result(s)")
        logger.info("[VECTOR_SEARCH_NODE] === RETRIEVED CONTENT START ===")
        logger.info(results_text)
        logger.info("[VECTOR_SEARCH_NODE] === RETRIEVED CONTENT END ===")
        return {"vector_search_results": formatted_results}
    except Exception as e:
        logger.error(f"[VECTOR_SEARCH_NODE] Vector search failed: {e}")
        return {"vector_search_results": f"Vector search error: {str(e)}"}


def call_model(state: AgentState):
    logger.info("=" * 80)
    logger.info("[AGENT] Entering reasoning phase")
    logger.info("=" * 80)
    llm = get_reasoning_llm()
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
    return {"messages": [response]}


def review_response(state: AgentState, config: RunnableConfig):
    """QA Reviewer - validates response quality and accuracy.
    
    Review checks (in order):
    1. Response answers the user's query (relevance)
    2. No contradictions with vector search results (fact-checking)
    3. Proper military intelligence format
    4. Thinking tags properly closed
    5. Response has substantive content (not empty/generic)
    6. No sensitive data exposure (API keys, internal info)
    
    NOTE: Map tags are NOT checked here - they are added by extract_geo_node AFTER review.
    """
    logger.info("=" * 80)
    logger.info("[QA_REVIEWER] Starting validation")
    logger.info("=" * 80)

    user_msgs = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    user_query = user_msgs[0].content if user_msgs else "N/A"
    last_message = state["messages"][-1]
    assistant_response = last_message.content if hasattr(last_message, "content") else ""
    
    # Get vector search results for fact-checking
    vector_results = state.get("vector_search_results", "")

    logger.info(f"[QA_REVIEWER] Query: {user_query[:50]}...")
    logger.info(f"[QA_REVIEWER] Response length: {len(assistant_response)} chars")

    # Run all validation checks
    is_valid = True
    reviewer_result = "VALID"
    issues = []

    # Check 1: Thinking tags properly closed
    has_unclosed_think = "<think>" in assistant_response and "</think>" not in assistant_response
    if has_unclosed_think:
        issues.append("Unclosed thinking tags")
        is_valid = False

    # Check 2: Response has substantive content
    if not assistant_response or len(assistant_response.strip()) < 20:
        issues.append("Response too short or empty")
        is_valid = False
    
    # Check for generic non-answers
    generic_phrases = ["i can't help", "i don't know", "i'm unable", "not able to"]
    if any(phrase in assistant_response.lower() for phrase in generic_phrases):
        # Only flag if there's no actual content
        if len(assistant_response.strip()) < 100:
            issues.append("Generic non-answer response")
            is_valid = False

    # Check 3: Response addresses the query (basic keyword overlap check)
    query_words = set(user_query.lower().split())
    response_words = set(assistant_response.lower().split())
    # Remove common stop words
    stop_words = {'the', 'a', 'an', 'is', 'are', 'what', 'where', 'when', 'how', 'why', 'tell', 'me', 'about'}
    query_words = query_words - stop_words
    response_words = response_words - stop_words
    
    # Check if any query keywords appear in response
    if query_words and not (query_words & response_words):
        # No keyword overlap - might not be answering the query
        # But don't fail, just note it (LLM can be semantically relevant without exact keywords)
        logger.warning("[QA_REVIEWER] No keyword overlap between query and response")

    # Check 4: No contradictions with vector search results
    if vector_results and "No archival data" not in vector_results:
        # Extract key entities from vector results (simple heuristic)
        vector_lower = vector_results.lower()
        response_lower = assistant_response.lower()
        
        # Check for obvious contradictions (dates, numbers that don't match)
        # This is a simplified check - full fact-checking would require NER
        import re
        vector_years = re.findall(r'\b(19\d{2}|20\d{2})\b', vector_lower)
        response_years = re.findall(r'\b(19\d{2}|20\d{2})\b', response_lower)
        
        # If vector results mention specific years and response mentions completely different ones, flag it
        if vector_years and response_years:
            year_set_v = set(vector_years)
            year_set_r = set(response_years)
            if not (year_set_v & year_set_r) and len(year_set_v) > 0 and len(year_set_r) > 0:
                # Different years mentioned - might be contradiction or different context
                logger.warning(f"[QA_REVIEWER] Year mismatch: vector={year_set_v}, response={year_set_r}")
                # Don't fail on this alone - could be discussing different time periods

    # Check 5: No sensitive data exposure
    sensitive_patterns = [
        r'api[_-]?key\s*[=:]\s*\w+',
        r'password\s*[=:]\s*\w+',
        r'secret\s*[=:]\s*\w+',
        r'token\s*[=:]\s*\w+',
        r'mongodb://\S+',
    ]
    for pattern in sensitive_patterns:
        if re.search(pattern, assistant_response, re.IGNORECASE):
            issues.append("Potential sensitive data exposure")
            is_valid = False
            break

    # Check 6: Proper formatting (markdown headers if long response)
    if len(assistant_response) > 500:
        # Long responses should have some structure
        if not any(marker in assistant_response for marker in ['\n\n', '-', '*', '###', '**']):
            logger.warning("[QA_REVIEWER] Long response lacks formatting/structure")
            # Don't fail, just note it

    # Compile results
    if not is_valid:
        reviewer_result = f"INVALID: {'; '.join(issues)}"
        logger.warning(f"[QA_REVIEWER] {reviewer_result}")
    else:
        logger.info("[QA_REVIEWER] Validation PASSED")

    logger.info("[QA_REVIEWER] === VALIDATION RESULT ===")
    logger.info(reviewer_result)
    logger.info("[QA_REVIEWER] === END ===")

    if is_valid:
        return {"is_valid": True, "validation_attempts": 1, "reviewer_result": reviewer_result}
    else:
        return {
            "is_valid": False,
            "validation_attempts": 1,
            "reviewer_result": reviewer_result,
            "messages": [SystemMessage(content=f"QA FEEDBACK: {reviewer_result}", additional_kwargs={"role": "system"})]
        }


def check_validation(state: AgentState) -> Literal["agent", "extract_geo"]:
    # If it's valid, or we've tried too many times, we end to avoid infinite loops
    if state.get("is_valid"):
        logger.debug("[AGENT LOG] Reviewer approved. Transitioning to 'extract_geo'.")
        return "extract_geo"

    attempts = state.get("validation_attempts", 0)
    if attempts >= 3:
        logger.debug(f"[AGENT LOG] Max validation attempts ({attempts}) reached. Forcing '__end__'.")
        return "__end__"

    logger.debug("[AGENT LOG] Reviewer rejected. Transitioning back to 'agent'.")
    return "agent"


async def extract_geo_node(state: AgentState):
    """Extract geographic locations and connections from the final response.

    Async node — uses ainvoke to call the LLM without blocking the event loop.
    """
    logger.info("=" * 80)
    logger.info("[EXTRACT_GEO] === STARTING GEOGRAPHIC EXTRACTION ===")
    logger.info("=" * 80)

    from app.services.geo_ner import extract_with_coordinates_async

    # Get the final assistant response
    last_message = state["messages"][-1]
    response_text = last_message.content if hasattr(last_message, "content") else ""

    if not response_text:
        logger.warning("[EXTRACT_GEO] No response text to extract from")
        return {"geo_locations": [], "geo_connections": []}

    # Get original user query for context
    user_msgs = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    user_query = user_msgs[0].content if user_msgs else ""

    logger.info(f"[EXTRACT_GEO] Response text length: {len(response_text)} chars")
    logger.info(f"[EXTRACT_GEO] User query context: '{user_query[:80]}'")

    try:
        result = await extract_with_coordinates_async(response_text, user_query)

        locations = result.get("locations", [])
        connections = result.get("connections", [])
        stats = result.get("stats", {})

        logger.info("[EXTRACT_GEO] === EXTRACTION COMPLETE ===")
        logger.info(f"[EXTRACT_GEO] Found {len(locations)} locations, {len(connections)} connections")
        logger.info(f"[EXTRACT_GEO] Stats: {stats}")

        for loc in locations:
            logger.info(f"  LOC: {loc['name']} ({loc['type']}) @ {loc.get('coordinates', 'N/A')}")
        for conn in connections:
            logger.info(f"  CONN: {conn['from_name']} --[{conn['type']}]--> {conn['to_name']}")

        return {
            "geo_locations": locations,
            "geo_connections": connections,
        }

    except Exception as e:
        logger.error(f"[EXTRACT_GEO] Extraction failed: {e}", exc_info=True)
        return {"geo_locations": [], "geo_connections": []}


def get_graph():
    checkpointer = MemorySaver()
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("vector_search", vector_search_node)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", ToolNode(tools))
    workflow.add_node("reviewer", review_response)
    workflow.add_node("extract_geo", extract_geo_node)

    # Set entry point to vector_search (mandatory first step)
    workflow.set_entry_point("vector_search")

    # Vector search always flows to agent
    workflow.add_edge("vector_search", "agent")

    # Agent decides whether to use tools or go to reviewer
    workflow.add_conditional_edges("agent", should_continue)

    # Tools loop back to agent for further reasoning
    workflow.add_edge("tools", "agent")

    # Reviewer validates or sends back for revision
    workflow.add_conditional_edges("reviewer", check_validation)
    
    # Geo extraction flows to end
    workflow.add_edge("extract_geo", "__end__")

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

        elif kind == "on_chain_start":
            node_name = event.get("name", "")
            if node_name == "extract_geo":
                yield {"type": "status", "phase": "extracting"}

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
                    yield {
                        "type": "tool_result",
                        "tool": "QA Reviewer",
                        "summary": "Analysis validated" if is_valid else "Analysis revised",
                        "content": reviewer_result,
                    }
            
            # Capture geo extraction result
            node_name = event.get("name", "")
            if node_name == "extract_geo":
                try:
                    output = event.get("data", {}).get("output", {})
                    # Use .get() safely and double-check structure
                    locations = output.get("geo_locations", []) if isinstance(output, dict) else []
                    connections = output.get("geo_connections", []) if isinstance(output, dict) else []
                    
                    if (locations and len(locations) > 0) or (connections and len(connections) > 0):
                        logger.info(f"[STREAM] Yielding {len(locations)} locs / {len(connections)} conns")
                        yield {
                            "type": "geo_locations",
                            "locations": locations,
                            "connections": connections,
                        }
                    else:
                        logger.debug("[STREAM] Geo extraction returned empty results")
                except Exception as e:
                    logger.warning(f"[STREAM] Failed to extract geo data from event: {e}")
                    # Don't fail the stream - just skip geo event

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

    # Always yield done to complete the stream
    # Geo extraction events will be captured separately via on_chain_end
    yield {"type": "done"}
