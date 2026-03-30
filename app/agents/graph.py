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
from app.agents.rag_subgraph import run_rag_subgraph
from app.core.di_llm import get_llm
from app.core.di_services import get_vector_store
from app.core.constants import (
    NODE_AGENT, NODE_TOOLS, NODE_REVIEWER,
    NODE_ONTOLOGY_EXTRACTOR, NODE_RAG_SUBGRAPH,
    VALIDATION_VALID, STATE_KEY_MESSAGES, STATE_KEY_VECTOR_SEARCH_RESULTS,
    STATE_KEY_ONTOLOGY, STATE_KEY_VALIDATION_ATTEMPTS, STATE_KEY_IS_VALID,
    STATE_KEY_RAG_CONTEXT, STATE_KEY_RAG_QUALITY, STATE_KEY_RAG_HINT,
)
from app.agents.ontology_subgraph import ontology_subgraph
from app.models.ontology import SessionOntology
from app.services.ontology.merge import merge_ontologies
from app.core.config import settings


def _get_active_model_name() -> str:
    """Get the currently active model name for display.
    
    Returns the online model name if USE_ONLINE_LLM is enabled, otherwise the local reasoning model.
    """
    if settings.USE_ONLINE_LLM and settings.GROQ_API_KEY:
        return settings.ONLINE_LLM_MODEL_NAME
    return settings.REASONING_LLM_MODEL_NAME

system_msg = """You are an advanced Geopolitical Intelligence Agent for the GeoVision Lab.
Your objective is to provide concise, accurate, and tactical analysis of conflicts and geopolitical shifts.

You have access to intel feeds:
1. `vector_search`: For retrieving information from ANY locally uploaded documents, reports, custom data, or historical intelligence. (Automatically executed before you begin reasoning)
2. `web_search`: For Wikipedia summaries of background information on active geopolitics.
3. `duckduckgo_search`: For live web search results regarding current events and general queries.

The archival intelligence from vector search is automatically injected into your context when relevant. Review it first, then use additional tools if you need live or updated information.

If archival search found no relevant information, you will see a NOTE telling you to use web search tools.

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

    # Inject RAG context (from RAG subgraph) into the agent prompt
    rag_context = state.get(STATE_KEY_RAG_CONTEXT, "")
    rag_hint = state.get(STATE_KEY_RAG_HINT, "")
    
    vector_context = ""
    if rag_context:
        vector_context = f"\n\n---\nARCHIVAL INTELLIGENCE (from vector search):\n{rag_context}\n---\n\n"
        logger.info("[AGENT] RAG context injected (RELEVANT or PARTIALLY_RELEVANT)")
    elif rag_hint:
        # Context was irrelevant, add hint to prompt
        vector_context = f"\n\n---\n{rag_hint}\n---\n\n"
        logger.info("[AGENT] RAG hint injected (context was IRRELEVANT)")
    else:
        logger.info("[AGENT] No RAG context or hint available")

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

    # Build full conversation context from ALL messages (not just the first query)
    user_msgs = [m for m in state[STATE_KEY_MESSAGES] if isinstance(m, HumanMessage)]
    assistant_msgs = [m for m in state[STATE_KEY_MESSAGES] if hasattr(m, "content") and not isinstance(m, HumanMessage)]

    # Build conversation history for context
    full_context_parts = []
    for i, (user_msg, assistant_msg) in enumerate(zip(user_msgs, assistant_msgs), 1):
        user_content = user_msg.content if hasattr(user_msg, "content") else str(user_msg)
        assistant_content = assistant_msg.content if hasattr(assistant_msg, "content") else str(assistant_msg)
        full_context_parts.append(f"Turn {i}:\nUser: {user_content}\nAssistant: {assistant_content}")

    # Include any remaining user messages without assistant responses (current query)
    if len(user_msgs) > len(assistant_msgs):
        remaining_user_msg = user_msgs[-1]
        user_content = remaining_user_msg.content if hasattr(remaining_user_msg, "content") else str(remaining_user_msg)
        full_context_parts.append(f"Current Query:\nUser: {user_content}")

    full_context = "\n\n".join(full_context_parts) if full_context_parts else ""

    if not assistant_response:
        logger.info("[ONTOLOGY_SUBGRAPH] No response content to process")
        return {STATE_KEY_ONTOLOGY: state.get(STATE_KEY_ONTOLOGY, {})}

    try:
        # Prepare sub-graph input with full conversation context
        subgraph_input = {
            "user_query": full_context,
            "assistant_response": assistant_response,
            "query_id": "default"
        }

        logger.debug(f"[ONTOLOGY_SUBGRAPH] Invoking sub-graph with {len(assistant_response)} chars of assistant response")

        # Run sub-graph
        subgraph_result = ontology_subgraph.invoke(subgraph_input)
        delta = subgraph_result.get("extracted_delta")

        # Log sub-graph result details
        if delta:
            logger.info(f"[ONTOLOGY_SUBGRAPH] Sub-graph returned {len(delta.entities)} entities and {len(delta.links)} links")
        else:
            logger.warning("[ONTOLOGY_SUBGRAPH] Sub-graph returned None or empty delta")

        # Merge with existing session ontology
        current_ontology = state.get(STATE_KEY_ONTOLOGY)
        if not current_ontology:
            current_ontology = SessionOntology()
        elif isinstance(current_ontology, dict):
            current_ontology = SessionOntology.model_validate(current_ontology)

        if delta:
            # Use the new merge function
            current_ontology = merge_ontologies(current_ontology, delta)

        entity_count = len(current_ontology.entities)
        link_count = len(current_ontology.links)
        logger.info(f"[ONTOLOGY_SUBGRAPH] ✓ Sub-graph complete: {entity_count} total entities, {link_count} total links accumulated.")
        return {STATE_KEY_ONTOLOGY: current_ontology}

    except Exception as e:
        logger.error(f"[ONTOLOGY_SUBGRAPH] ✗ Sub-graph failed: {e}")
        logger.exception("[ONTOLOGY_SUBGRAPH] Full stack trace:")
        logger.error(f"[ONTOLOGY_SUBGRAPH] Assistant response length: {len(assistant_response)} chars")
        logger.debug(f"[ONTOLOGY_SUBGRAPH] Assistant response preview: {assistant_response[:500]}...")
        return {STATE_KEY_ONTOLOGY: state.get(STATE_KEY_ONTOLOGY, {})}


def run_rag_subgraph_node(state: AgentState) -> Dict[str, Any]:
    """
    Run the RAG subgraph to retrieve and grade context.
    
    This wraps the RAG subgraph and maps state between main graph and sub-graph.
    """
    logger.info("=" * 80)
    logger.info("[RAG_SUBGRAPH_NODE] Starting RAG subgraph")
    logger.info("=" * 80)
    
    # Extract user query from the first HumanMessage
    user_msgs = [m for m in state[STATE_KEY_MESSAGES] if isinstance(m, HumanMessage)]
    if not user_msgs:
        logger.warning("[RAG_SUBGRAPH_NODE] No user message found")
        return {
            STATE_KEY_RAG_QUALITY: "IRRELEVANT",
            STATE_KEY_RAG_CONTEXT: "",
            STATE_KEY_RAG_HINT: "NOTE: No query provided."
        }
    
    query = user_msgs[0].content
    logger.info(f"[RAG_SUBGRAPH_NODE] Query: '{query}'")
    
    try:
        # Run the RAG subgraph
        rag_result = run_rag_subgraph(query)
        
        rag_quality = rag_result.get("rag_quality", "IRRELEVANT")
        rag_context = rag_result.get("rag_context", "")
        rag_hint = rag_result.get("rag_hint", "")
        
        logger.info(f"[RAG_SUBGRAPH_NODE] RAG quality: {rag_quality}")
        logger.info(f"[RAG_SUBGRAPH_NODE] Context length: {len(rag_context) if rag_context else 0} chars")
        logger.info(f"[RAG_SUBGRAPH_NODE] Hint: {'Yes' if rag_hint else 'No'}")
        
        return {
            STATE_KEY_RAG_QUALITY: rag_quality,
            STATE_KEY_RAG_CONTEXT: rag_context,
            STATE_KEY_RAG_HINT: rag_hint
        }
        
    except Exception as e:
        logger.error(f"[RAG_SUBGRAPH_NODE] RAG subgraph failed: {e}")
        logger.exception("[RAG_SUBGRAPH_NODE] Full stack trace:")
        # Return safe defaults on error
        return {
            STATE_KEY_RAG_QUALITY: "IRRELEVANT",
            STATE_KEY_RAG_CONTEXT: "",
            STATE_KEY_RAG_HINT: "NOTE: Archival search encountered an error. Use web search tools for information."
        }


def get_graph():
    checkpointer = MemorySaver()
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node(NODE_RAG_SUBGRAPH, run_rag_subgraph_node)
    workflow.add_node(NODE_AGENT, call_model)
    workflow.add_node(NODE_TOOLS, ToolNode(tools))
    workflow.add_node(NODE_REVIEWER, review_response)
    workflow.add_node(NODE_ONTOLOGY_EXTRACTOR, run_ontology_subgraph)

    # Set entry point to RAG subgraph (mandatory first step)
    workflow.set_entry_point(NODE_RAG_SUBGRAPH)

    # RAG subgraph always flows to agent (with context or hint)
    workflow.add_edge(NODE_RAG_SUBGRAPH, NODE_AGENT)

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
    
    # Set processing state
    from app.api.routes.health import set_processing_state
    set_processing_state(True, user_query)
    
    inputs = {"messages": [HumanMessage(content=user_query)]}
    config = {"configurable": {"thread_id": thread_id}}
    streaming_started = False
    done_sent = False

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
                logger.exception("[STREAM ERROR] Full error event data:")
                yield {
                    "type": "error",
                    "content": f"LLM error: {str(error_msg)}\n\nThis may be due to:\n- Model not loaded in Ollama\n- Ollama service unavailable\n- Request timeout\n\nTry: `docker restart geovision-ollama`"
                }
                return  # Stop processing
            
            # Check for Groq-specific errors in stream events
            if kind == "on_chat_model_error":
                error_msg = event.get("data", {}).get("error", "Unknown error")
                logger.error(f"[STREAM ERROR] on_chat_model_error: {error_msg}")
                logger.exception("[STREAM ERROR] Full error event data:")
                yield {
                    "type": "error",
                    "content": f"Chat model error: {str(error_msg)}"
                }
                return  # Stop processing

            if kind == "on_chain_start":
                # Capture RAG subgraph and grader phases
                node_name = event.get("name", "")
                if node_name == "rag_subgraph":
                    yield {"type": "status", "phase": "rag_retrieval", "tool": "RAG Subgraph"}
                elif node_name == "grader":
                    yield {"type": "status", "phase": "rag_grading", "tool": "Grader"}

            if kind == "on_chat_model_start":
                # Skip grader, reviewer, ontology - only stream agent tokens
                if "grader" in tags or "reviewer" in tags or "ontology_extractor" in tags:
                    continue
                    
                active_model = _get_active_model_name()
                if "reviewer" in tags:
                    yield {"type": "status", "phase": "reviewing", "model": active_model}
                elif "ontology_extractor" in tags:
                    yield {"type": "status", "phase": "extracting_ontology", "model": active_model}
                else:
                    if streaming_started:
                        yield {"type": "status", "phase": "revising", "model": active_model}
                    yield {"type": "status", "phase": "reasoning", "model": active_model}

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
                # Capture RAG subgraph completion
                if event.get("name") == "rag_subgraph":
                    output = event.get("data", {}).get("output", {})
                    rag_quality = output.get(STATE_KEY_RAG_QUALITY, "IRRELEVANT")
                    _ = output.get(STATE_KEY_RAG_CONTEXT, "")  # Used internally
                    rag_hint = output.get(STATE_KEY_RAG_HINT, "")
                    
                    if rag_quality == "IRRELEVANT":
                        summary = "No relevant archival data found"
                    else:
                        summary = f"Archival intelligence retrieved (Quality: {rag_quality})"
                    
                    yield {
                        "type": "rag_result",
                        "tool": "RAG Subgraph",
                        "summary": summary,
                        "quality": rag_quality,
                        "hint": rag_hint,
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

                    # Handle both SessionOntology objects and dicts
                    entities = {}
                    links = {}
                    
                    if ontology_state:
                        if isinstance(ontology_state, dict):
                            entities = ontology_state.get("entities", {})
                            links = ontology_state.get("links", {})
                        else:
                            # It's a SessionOntology object
                            entities = getattr(ontology_state, "entities", {})
                            links = getattr(ontology_state, "links", {})
                        
                        # Count entities and links (handle both dict and object formats)
                        if isinstance(entities, dict):
                            entity_count = len(entities)
                        elif hasattr(entities, "__len__"):
                            entity_count = len(entities)
                        else:
                            entity_count = 0
                            
                        if isinstance(links, dict):
                            link_count = len(links)
                        elif hasattr(links, "__len__"):
                            link_count = len(links)
                        else:
                            link_count = 0
                            
                        logger.info(f"[STREAM] Ontology extracted: {entity_count} entities, {link_count} links")

                        # Convert to JSON-serializable format
                        def serialize_entity(e):
                            if hasattr(e, "model_dump"):
                                return e.model_dump(mode='json')
                            return e
                            
                        def serialize_link(link_obj):
                            if hasattr(link_obj, "model_dump"):
                                return link_obj.model_dump(mode='json')
                            return link_obj

                        yield {
                            "type": "ontology_updated",
                            "tool": "ontology_subgraph",
                            "summary": f"Graph updated: {entity_count} entities, {link_count} relationships",
                            "ontology": ontology_state if isinstance(ontology_state, dict) else {
                                "entities": {str(k): serialize_entity(v) for k, v in entities.items()},
                                "links": {str(k): serialize_link(v) for k, v in links.items()}
                            },
                        }
                    else:
                        logger.warning("[STREAM] Ontology extraction returned empty or invalid result")
                        yield {
                            "type": "ontology_error",
                            "tool": "ontology_subgraph",
                            "summary": "No ontology data extracted",
                            "content": "Ontology extraction completed but returned no data. Check backend logs for detailed error information."
                        }

            elif kind == "on_chat_model_end":
                # Skip grader, reviewer, ontology - already handled
                if "grader" in tags or "reviewer" in tags or "ontology_extractor" in tags:
                    continue
                    
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
                # Note: Final response without tool calls is already streamed via on_chat_model_stream
                # Don't yield here to avoid duplicates

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
                            # Emit thinking_start event
                            yield {"type": "thinking_start"}
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
                            think_content = buffer[:idx]
                            
                            # Stream the remaining think content as tokens
                            if think_content:
                                yield {"type": "thinking_token", "content": think_content}
                            
                            yield {
                                "type": "thinking_end"
                            }
                            
                            # Also emit as tool_result for backward compatibility
                            yield {
                                "type": "tool_result",
                                "tool": "reasoning",
                                "summary": "Reasoning steps completed",
                                "content": (think_buffer + think_content).strip()
                            }
                            
                            think_buffer = ""
                            buffer = buffer[idx + len("</think>"):]
                            in_think = False
                        else:
                            idx = buffer.rfind("<")
                            if idx == -1:
                                # Stream this chunk of thinking content
                                think_buffer += buffer
                                yield {"type": "thinking_token", "content": buffer}
                                buffer = ""
                            else:
                                # Stream partial thinking content
                                partial = buffer[:idx]
                                if partial:
                                    think_buffer += partial
                                    yield {"type": "thinking_token", "content": partial}
                                buffer = buffer[idx:]
                                if len(buffer) > 15:
                                    think_buffer += buffer
                                    yield {"type": "thinking_token", "content": buffer}
                                    buffer = ""
                                break

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[QUERY-STREAM] Error during streaming: {error_msg}")
        logger.exception("[QUERY-STREAM] Full stack trace:")
        logger.error(f"[QUERY-STREAM] Error type: {type(e).__name__}")
        logger.error(f"[QUERY-STREAM] Buffer state: in_think={in_think}, buffer_len={len(buffer)}, think_buffer_len={len(think_buffer)}")

        # Check for JSON parsing errors from Ollama client
        if "failed to parse JSON" in error_msg or "unexpected end of JSON input" in error_msg:
            yield {
                "type": "error",
                "content": "LLM response parsing failed. This usually means:\n\n1. Ollama model crashed or timed out\n2. Connection was interrupted\n3. Model returned malformed output\n\nTry:\n- Restart Ollama: `docker restart geovision-ollama`\n- Check model is loaded: `docker exec geovision-ollama ollama ps`\n- Retry your query"
            }
        # Check for Groq function calling errors
        elif "Failed to call a function" in error_msg:
            yield {
                "type": "error",
                "content": f"Groq API error: {error_msg}\n\nThis typically means:\n1. The model tried to use a tool/function that Groq doesn't support\n2. Prompt instructions conflict with Groq's capabilities\n\nTry:\n- Simplify your query\n- Switch to a local Ollama model\n- Check that tool usage is properly disabled for Groq"
            }
        else:
            yield {"type": "error", "content": f"Streaming error: {error_msg}"}
    finally:
        # Always send done event to signal completion
        if not done_sent:
            if buffer and not in_think:
                yield {"type": "token", "content": buffer}
            elif buffer and in_think:
                # Flush remaining think buffer
                if buffer:
                    yield {"type": "thinking_token", "content": buffer}
                    think_buffer += buffer
                yield {"type": "thinking_end"}
                # Also emit as tool_result for backward compatibility
                yield {
                    "type": "tool_result",
                    "tool": "reasoning",
                    "summary": "Reasoning steps completed",
                    "content": think_buffer.strip()
                }
            yield {"type": "done"}
            done_sent = True
        
        # Clear processing state
        set_processing_state(False)

        # Auto-save session to MongoDB after query completes
        try:
            # Get final state from the graph
            final_state = await app_graph.aget_state(config)
            messages = final_state.values.get("messages", [])
            ontology_state = final_state.values.get("ontology", {})
            
            # Convert messages to serializable format
            serializable_messages = []
            for msg in messages:
                msg_dict = {}
                if hasattr(msg, "model_dump"):
                    msg_dict = msg.model_dump()
                elif hasattr(msg, "dict"):
                    msg_dict = msg.dict()
                else:
                    msg_dict = {"content": str(msg)}
                
                # Map LangChain 'type' field to 'role' field for session storage
                msg_type = msg_dict.get("type", None)
                if msg_type == "human":
                    msg_dict["role"] = "user"
                elif msg_type == "ai":
                    msg_dict["role"] = "assistant"
                elif msg_type == "system":
                    msg_dict["role"] = "system"
                elif msg_type == "tool":
                    msg_dict["role"] = "tool"
                elif "role" not in msg_dict:
                    # Fallback: check class name
                    class_name = msg.__class__.__name__.lower()
                    if "human" in class_name or "user" in class_name:
                        msg_dict["role"] = "user"
                    elif "ai" in class_name or "assistant" in class_name:
                        msg_dict["role"] = "assistant"
                    else:
                        msg_dict["role"] = "unknown"
                
                serializable_messages.append(msg_dict)
            
            # Convert ontology to serializable format
            serializable_ontology = {"entities": {}, "links": {}}
            if ontology_state:
                if hasattr(ontology_state, "model_dump"):
                    serializable_ontology = ontology_state.model_dump(mode='json')
                elif hasattr(ontology_state, "entities") and hasattr(ontology_state, "links"):
                    serializable_ontology["entities"] = {
                        str(k): v.model_dump(mode='json') if hasattr(v, "model_dump") else str(v)
                        for k, v in ontology_state.entities.items()
                    }
                    serializable_ontology["links"] = {
                        str(k): v.model_dump(mode='json') if hasattr(v, "model_dump") else str(v)
                        for k, v in ontology_state.links.items()
                    }
            
            # Save to MongoDB via sessions endpoint
            import httpx
            
            async with httpx.AsyncClient() as client:
                save_url = f"http://localhost:8000/api/sessions/{thread_id}/save"
                save_data = {
                    "messages": serializable_messages,
                    "ontology": serializable_ontology
                }
                response = await client.post(save_url, json=save_data, timeout=10.0)
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"[AUTO-SAVE] Session saved: {result.get('message_count')} messages, {result.get('entity_count')} entities, {result.get('link_count')} links")
                else:
                    logger.error(f"[AUTO-SAVE] Failed to save session: {response.status_code} - {response.text}")
        except Exception as save_error:
            logger.error(f"[AUTO-SAVE] Error saving session: {save_error}")
            # Don't propagate error - auto-save is best effort
