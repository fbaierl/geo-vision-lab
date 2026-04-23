from typing import Literal, Dict, Any
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
import logging
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
    NODE_AGENT,
    NODE_TOOLS,
    NODE_REVIEWER,
    NODE_ONTOLOGY_EXTRACTOR,
    NODE_RAG_SUBGRAPH,
    VALIDATION_VALID,
    STATE_KEY_MESSAGES,
    STATE_KEY_VECTOR_SEARCH_RESULTS,
    STATE_KEY_ONTOLOGY,
    STATE_KEY_VALIDATION_ATTEMPTS,
    STATE_KEY_IS_VALID,
    STATE_KEY_RAG_CONTEXT,
    STATE_KEY_RAG_QUALITY,
    STATE_KEY_RAG_HINT,
)
from app.agents.ontology_subgraph import ontology_subgraph
from app.models.ontology import SessionOntology
from app.services.ontology.merge import merge_ontologies
from app.core.di import get_ontology_service

system_msg = """You are an advanced Geopolitical Intelligence Agent for the GeoVision Lab.
Your objective is to provide concise, accurate, and tactical analysis of conflicts and geopolitical shifts.

You have access to intel feeds:
1. `vector_search`: For retrieving information from ANY locally uploaded documents, reports, custom data, or historical intelligence. (Automatically executed before you begin reasoning)
2. `wikipedia_search`: For Wikipedia summaries of background information on active geopolitics.
3. `news_archive_search`: For structured historical and current event timelines — military operations, conflicts, diplomatic events, and breaking news worldwide. Returns chronological results with dates, event categories, source citations, and sentiment scores.
4. `duckduckgo_search`: For general web search to gather supplementary context and nuance.

ARCHIVAL INTELLIGENCE: The archival intelligence from vector search is automatically injected into your context when relevant. Review it first.

NEWS QUERIES: For any query about "what happened", recent events, current affairs, or what took place in a specific country/location, ALWAYS use `news_archive_search` first. It provides structured, date-organized results that are ideal for answering event-based questions. Use `duckduckgo_search` only for additional context after checking the archive.

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
            logger.info(
                "[VECTOR_SEARCH_NODE] No archival data found in historical intelligence database."
            )
            return {
                STATE_KEY_VECTOR_SEARCH_RESULTS: "No archival data found in historical intelligence database."
            }

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

    messages = [
        SystemMessage(content=system_msg + vector_context + time_prompt)
    ] + list(state["messages"])
    logger.info(f"[AGENT] Invoking LLM with {len(messages)} messages")
    response = llm_with_tools.invoke(messages)

    # Log the agent's reasoning and tool calls
    if hasattr(response, "content") and response.content:
        logger.info("[AGENT] === REASONING OUTPUT START ===")
        logger.info(response.content)
        logger.info("[AGENT] === REASONING OUTPUT END ===")
    if hasattr(response, "tool_calls") and response.tool_calls:
        logger.info(
            f"[AGENT] Tool calls requested: {[tc['name'] for tc in response.tool_calls]}"
        )

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
    assistant_response = (
        last_message.content if hasattr(last_message, "content") else str(last_message)
    )

    logger.info(f"[QA_REVIEWER] Query: {user_query[:50]}...")
    logger.info(f"[QA_REVIEWER] Response length: {len(assistant_response)} chars")

    # Simple validation - always pass for now (can add more rules later)
    logger.info("[QA_REVIEWER] Validation PASSED")
    logger.info("[QA_REVIEWER] === VALIDATION RESULT ===")
    logger.info(VALIDATION_VALID)
    logger.info("[QA_REVIEWER] === END ===")

    return {
        STATE_KEY_IS_VALID: True,
        STATE_KEY_VALIDATION_ATTEMPTS: 1,
        "reviewer_result": VALIDATION_VALID,
    }


def check_validation(state: AgentState) -> Literal[NODE_AGENT, NODE_ONTOLOGY_EXTRACTOR]:
    # If it's valid, proceed to ontology extraction
    if state.get(STATE_KEY_IS_VALID):
        logger.debug(
            "[AGENT LOG] Reviewer approved. Transitioning to 'ontology_extractor'."
        )
        return NODE_ONTOLOGY_EXTRACTOR

    attempts = state.get(STATE_KEY_VALIDATION_ATTEMPTS, 0)
    if attempts >= 3:
        logger.debug(
            f"[AGENT LOG] Max validation attempts ({attempts}) reached. Forcing '__end__'."
        )
        return "__end__"

    logger.debug("[AGENT LOG] Reviewer rejected. Transitioning back to 'agent'.")
    return NODE_AGENT


def run_ontology_subgraph(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Run the ontology processing sub-graph.

    Loads existing ontology from Neo4j, merges new extraction, saves back.
    """
    logger.info("=" * 80)
    logger.info("[ONTOLOGY_SUBGRAPH] Starting ontology processing sub-graph")
    logger.info("=" * 80)

    thread_id = config.get("configurable", {}).get("thread_id", "default")
    logger.info(f"[ONTOLOGY_SUBGRAPH] Thread ID: {thread_id}")

    # Get the last assistant message (the final response)
    last_message = state[STATE_KEY_MESSAGES][-1]
    assistant_response = (
        last_message.content if hasattr(last_message, "content") else ""
    )

    # Build full conversation context from ALL messages (not just the first query)
    user_msgs = [m for m in state[STATE_KEY_MESSAGES] if isinstance(m, HumanMessage)]
    assistant_msgs = [
        m
        for m in state[STATE_KEY_MESSAGES]
        if hasattr(m, "content") and not isinstance(m, HumanMessage)
    ]

    # Build conversation history for context
    full_context_parts = []
    for i, (user_msg, assistant_msg) in enumerate(zip(user_msgs, assistant_msgs), 1):
        user_content = (
            user_msg.content if hasattr(user_msg, "content") else str(user_msg)
        )
        assistant_content = (
            assistant_msg.content
            if hasattr(assistant_msg, "content")
            else str(assistant_msg)
        )
        full_context_parts.append(
            f"Turn {i}:\nUser: {user_content}\nAssistant: {assistant_content}"
        )

    # Include any remaining user messages without assistant responses (current query)
    if len(user_msgs) > len(assistant_msgs):
        remaining_user_msg = user_msgs[-1]
        user_content = (
            remaining_user_msg.content
            if hasattr(remaining_user_msg, "content")
            else str(remaining_user_msg)
        )
        full_context_parts.append(f"Current Query:\nUser: {user_content}")

    full_context = "\n\n".join(full_context_parts) if full_context_parts else ""

    if not assistant_response:
        logger.info("[ONTOLOGY_SUBGRAPH] No response content to process")
        return {STATE_KEY_ONTOLOGY: state.get(STATE_KEY_ONTOLOGY, {})}

    try:
        # Load existing ontology from Neo4j (cross-session persistence)
        logger.info(
            f"[ONTOLOGY_SUBGRAPH] Loading existing ontology from Neo4j (thread={thread_id})"
        )
        try:
            ontology_service = get_ontology_service()
            neo4j_ontology = ontology_service.load_ontology(thread_id)
            logger.info(
                f"[ONTOLOGY_SUBGRAPH] Neo4j ontology loaded: {len(neo4j_ontology.entities)} entities, "
                f"{len(neo4j_ontology.links)} links"
            )
        except Exception as load_err:
            logger.warning(f"[ONTOLOGY_SUBGRAPH] Failed to load from Neo4j: {load_err}")
            neo4j_ontology = SessionOntology()

        # Prepare sub-graph input with full conversation context
        subgraph_input = {
            "user_query": full_context,
            "assistant_response": assistant_response,
            "query_id": thread_id,
        }

        logger.debug(
            f"[ONTOLOGY_SUBGRAPH] Invoking sub-graph with {len(assistant_response)} chars of assistant response"
        )

        # Run sub-graph
        subgraph_result = ontology_subgraph.invoke(subgraph_input)
        delta = subgraph_result.get("extracted_delta")

        # Log sub-graph result details
        if delta:
            logger.info(
                f"[ONTOLOGY_SUBGRAPH] Sub-graph returned {len(delta.entities)} entities and {len(delta.links)} links"
            )
        else:
            logger.warning("[ONTOLOGY_SUBGRAPH] Sub-graph returned None or empty delta")

        # Merge: Neo4j ontology + in-memory state + new delta
        current_ontology = state.get(STATE_KEY_ONTOLOGY)
        if not current_ontology:
            current_ontology = SessionOntology()
        elif isinstance(current_ontology, dict):
            current_ontology = SessionOntology.model_validate(current_ontology)

        # First merge Neo4j state with in-memory state
        current_ontology = merge_ontologies(neo4j_ontology, current_ontology)

        # Then merge the new delta
        if delta:
            current_ontology = merge_ontologies(current_ontology, delta)

        # Save merged ontology back to Neo4j
        try:
            logger.info(
                f"[ONTOLOGY_SUBGRAPH] Saving merged ontology to Neo4j: "
                f"{len(current_ontology.entities)} entities, {len(current_ontology.links)} links"
            )
            ontology_service.save_ontology(thread_id, current_ontology)
            logger.info("[ONTOLOGY_SUBGRAPH] Neo4j save complete")
        except Exception as save_err:
            logger.error(f"[ONTOLOGY_SUBGRAPH] Failed to save to Neo4j: {save_err}")

        entity_count = len(current_ontology.entities)
        link_count = len(current_ontology.links)
        logger.info(
            f"[ONTOLOGY_SUBGRAPH] ✓ Sub-graph complete: {entity_count} total entities, {link_count} total links accumulated."
        )
        return {STATE_KEY_ONTOLOGY: current_ontology}

    except Exception as e:
        logger.error(f"[ONTOLOGY_SUBGRAPH] ✗ Sub-graph failed: {e}")
        logger.exception("[ONTOLOGY_SUBGRAPH] Full stack trace:")
        logger.error(
            f"[ONTOLOGY_SUBGRAPH] Assistant response length: {len(assistant_response)} chars"
        )
        logger.debug(
            f"[ONTOLOGY_SUBGRAPH] Assistant response preview: {assistant_response[:500]}..."
        )
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
            STATE_KEY_RAG_HINT: "NOTE: No query provided.",
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
        logger.info(
            f"[RAG_SUBGRAPH_NODE] Context length: {len(rag_context) if rag_context else 0} chars"
        )
        logger.info(f"[RAG_SUBGRAPH_NODE] Hint: {'Yes' if rag_hint else 'No'}")

        return {
            STATE_KEY_RAG_QUALITY: rag_quality,
            STATE_KEY_RAG_CONTEXT: rag_context,
            STATE_KEY_RAG_HINT: rag_hint,
        }

    except Exception as e:
        logger.error(f"[RAG_SUBGRAPH_NODE] RAG subgraph failed: {e}")
        logger.exception("[RAG_SUBGRAPH_NODE] Full stack trace:")
        # Return safe defaults on error
        return {
            STATE_KEY_RAG_QUALITY: "IRRELEVANT",
            STATE_KEY_RAG_CONTEXT: "",
            STATE_KEY_RAG_HINT: "NOTE: Archival search encountered an error. Use web search tools for information.",
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
    workflow.add_conditional_edges(
        NODE_AGENT,
        should_continue,
        {NODE_TOOLS: NODE_TOOLS, NODE_REVIEWER: NODE_REVIEWER},
    )

    # Tools loop back to agent for further reasoning
    workflow.add_edge(NODE_TOOLS, NODE_AGENT)

    # Reviewer validates or sends back for revision
    workflow.add_conditional_edges(
        NODE_REVIEWER,
        check_validation,
        {
            NODE_AGENT: NODE_AGENT,
            NODE_ONTOLOGY_EXTRACTOR: NODE_ONTOLOGY_EXTRACTOR,
            "__end__": "__end__",
        },
    )

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
