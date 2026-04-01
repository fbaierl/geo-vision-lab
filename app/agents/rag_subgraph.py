"""
RAG Subgraph for GeoVision Lab

Encapsulates the retrieval + grading flow as a reusable subgraph.
This subgraph is called by the main agent graph to retrieve and validate context.

Architecture (configurable):
    All disabled: Vector Search (k=3) → Agent
    Grader only:  Vector Search (k=3) → Grader → Agent
    Re-ranker only: Vector Search (k=20) → Re-rank → Top 3 → Agent
    Both enabled: Vector Search (k=20) → Re-rank → Grader → Agent
"""

from typing import TypedDict, Dict, Any, Literal
from langgraph.graph import StateGraph
import logging

from app.agents.grader import grade_context
from app.core.di_services import get_vector_store
from app.core.constants import STATE_KEY_VECTOR_SEARCH_RESULTS, STATE_KEY_RETRIEVED_DOCS
from app.core.config import settings

logger = logging.getLogger(__name__)


class RAGState(TypedDict):
    """State for the RAG subgraph."""

    rag_query: str  # The query to search for
    vector_search_results: str  # Output from vector search (final formatted results)
    retrieved_docs: list  # Raw retrieved documents (for re-ranker)
    rag_quality: str  # RELEVANT, PARTIALLY_RELEVANT, IRRELEVANT
    rag_context: str  # Filtered context to inject into agent
    rag_hint: str  # Optional hint for the agent
    ontology_context: str  # Graph-based context from Neo4j ontology


def vector_search_node(state: RAGState) -> Dict[str, Any]:
    """
    Execute vector search for the given query.

    Retrieves more candidates if re-ranker is enabled.
    """
    logger.info("=" * 80)
    logger.info("[RAG_SUBGRAPH] Starting vector search")
    logger.info("=" * 80)

    query = state.get("rag_query", "")
    logger.info(f"[RAG_SUBGRAPH] Query: '{query}'")

    # Determine how many candidates to retrieve
    if settings.RAG_RERANKER_ENABLED:
        k = settings.RAG_RERANKER_CANDIDATES_K
        logger.info(f"[RAG_SUBGRAPH] Re-ranker enabled, retrieving {k} candidates")
    else:
        k = settings.SEARCH_K
        logger.info(f"[RAG_SUBGRAPH] Re-ranker disabled, retrieving {k} results")

    try:
        vector_store = get_vector_store()
        results = vector_store.similarity_search(query, k=k)

        if not results:
            logger.info(
                "[RAG_SUBGRAPH] No archival data found in historical intelligence database."
            )
            return {
                STATE_KEY_VECTOR_SEARCH_RESULTS: "No archival data found in historical intelligence database.",
                STATE_KEY_RETRIEVED_DOCS: [],
            }

        # Store raw documents for potential re-ranking
        logger.info(f"[RAG_SUBGRAPH] Found {len(results)} result(s)")

        return {
            STATE_KEY_VECTOR_SEARCH_RESULTS: "",  # Will be set by re-ranker or formatter
            STATE_KEY_RETRIEVED_DOCS: results,
        }

    except Exception as e:
        logger.error(f"[RAG_SUBGRAPH] Vector search failed: {e}")
        return {
            STATE_KEY_VECTOR_SEARCH_RESULTS: f"Vector search error: {str(e)}",
            STATE_KEY_RETRIEVED_DOCS: [],
        }


def rerank_node(state: RAGState) -> Dict[str, Any]:
    """
    Re-rank retrieved documents using BGE cross-encoder.

    Only runs if RAG_RERANKER_ENABLED is true.
    """
    logger.info("=" * 80)
    logger.info("[RAG_SUBGRAPH] Starting re-ranking")
    logger.info("=" * 80)

    retrieved_docs = state.get(STATE_KEY_RETRIEVED_DOCS, [])
    query = state.get("rag_query", "")

    if not retrieved_docs:
        logger.info("[RAG_SUBGRAPH] No documents to re-rank")
        return {STATE_KEY_VECTOR_SEARCH_RESULTS: "No archival data found."}

    # Check if re-ranker is enabled
    if not settings.RAG_RERANKER_ENABLED:
        logger.info(
            "[RAG_SUBGRAPH] Re-ranker disabled, using raw vector search results"
        )
        # Format raw results
        results_text = "\n\n".join(
            [doc.get("page_content", "") for doc in retrieved_docs[: settings.SEARCH_K]]
        )
        return {
            STATE_KEY_VECTOR_SEARCH_RESULTS: f"ARCHIVAL INTELLIGENCE REPORT:\n{results_text}"
        }

    try:
        from app.services.reranker import get_reranker_service

        reranker = get_reranker_service()

        if not reranker.is_available():
            logger.warning(
                "[RAG_SUBGRAPH] Re-ranker model not available, falling back to vector search"
            )
            # Fallback to vector search results
            results_text = "\n\n".join(
                [
                    doc.get("page_content", "")
                    for doc in retrieved_docs[: settings.SEARCH_K]
                ]
            )
            return {
                STATE_KEY_VECTOR_SEARCH_RESULTS: f"ARCHIVAL INTELLIGENCE REPORT:\n{results_text}"
            }

        # Re-rank documents
        reranked = reranker.rerank(
            query=query, documents=retrieved_docs, top_k=settings.SEARCH_K
        )

        # Format reranked results
        results_text = "\n\n".join([doc.get("page_content", "") for doc in reranked])

        logger.info(
            f"[RAG_SUBGRAPH] Re-ranking complete: {len(retrieved_docs)} -> {len(reranked)} results"
        )

        return {
            STATE_KEY_VECTOR_SEARCH_RESULTS: f"ARCHIVAL INTELLIGENCE REPORT:\n{results_text}",
            STATE_KEY_RETRIEVED_DOCS: reranked,  # Store reranked docs for grader
        }

    except Exception as e:
        logger.error(f"[RAG_SUBGRAPH] Re-ranking failed: {e}")
        logger.exception("[RAG_SUBGRAPH] Full stack trace:")
        # Fallback to vector search results
        results_text = "\n\n".join(
            [doc.get("page_content", "") for doc in retrieved_docs[: settings.SEARCH_K]]
        )
        return {
            STATE_KEY_VECTOR_SEARCH_RESULTS: f"ARCHIVAL INTELLIGENCE REPORT:\n{results_text}"
        }


def ontology_context_node(state: RAGState) -> Dict[str, Any]:
    """
    Retrieve graph-based context from the Neo4j ontology.

    Extracts entity names from the query and fetches related entities
    and relationships from the knowledge graph. This augments document
    retrieval with structured relationship context.
    """
    logger.info("[RAG_SUBGRAPH] Starting ontology context retrieval")

    query = state.get("rag_query", "")
    if not query or len(query.strip()) < 3:
        return {"ontology_context": ""}

    try:
        from app.core.di import get_ontology_service

        ontology_service = get_ontology_service()

        # Use the query itself as entity names - the graph store will
        # match partial names and find related entities
        entity_names = [query.strip()]

        context = ontology_service.get_context_for_query(
            entity_names=entity_names,
            thread_id=None,  # Cross-session context
        )

        if context:
            logger.info(
                f"[RAG_SUBGRAPH] Ontology context retrieved: {len(context)} chars"
            )
        else:
            logger.info("[RAG_SUBGRAPH] No ontology context found for query")

        return {"ontology_context": context or ""}

    except Exception as e:
        logger.error(f"[RAG_SUBGRAPH] Ontology context retrieval failed: {e}")
        return {"ontology_context": ""}


def merge_context_node(state: RAGState) -> Dict[str, Any]:
    """
    Merge document context and ontology context into final rag_context.

    Combines vector search results with graph-based relationship context.
    """
    vector_context = state.get(STATE_KEY_VECTOR_SEARCH_RESULTS, "")
    ontology_context = state.get("ontology_context", "")

    context_parts = []

    if ontology_context:
        context_parts.append(ontology_context)

    if vector_context and "No archival data found" not in vector_context:
        context_parts.append(vector_context)

    if not context_parts:
        return {
            "rag_quality": "IRRELEVANT",
            "rag_context": "",
            "rag_hint": "NOTE: No relevant information found in documents or knowledge graph.",
        }

    merged_context = "\n\n---\n\n".join(context_parts)

    logger.info(
        f"[RAG_SUBGRAPH] Context merged: {len(merged_context)} chars "
        f"(vector: {len(vector_context)}, ontology: {len(ontology_context)})"
    )

    return {
        "rag_quality": "RELEVANT",
        "rag_context": merged_context,
        "rag_hint": "",
    }


def check_grader_result(state: RAGState) -> Literal["__end__"]:
    """
    Check grader result and prepare final output.

    This is the final step - always ends the subgraph.
    """
    rag_quality = state.get("rag_quality", "IRRELEVANT")
    rag_context = state.get("rag_context", "")
    ontology_context = state.get("ontology_context", "")

    # If grader marked context as irrelevant but ontology has context,
    # still provide the ontology context
    if rag_quality == "IRRELEVANT" and ontology_context:
        logger.info(
            "[RAG_SUBGRAPH] Grader marked context irrelevant but ontology context available"
        )
        return {
            "rag_quality": "PARTIALLY_RELEVANT",
            "rag_context": ontology_context,
            "rag_hint": "NOTE: Document search found no relevant information, but knowledge graph context is available.",
        }

    # Add hint for agent if context was irrelevant
    if rag_quality == "IRRELEVANT" or not rag_context:
        hint = "NOTE: Archival search found no relevant information. Use web search tools for current information."
    else:
        hint = ""

    logger.info(
        f"[RAG_SUBGRAPH] Final quality: {rag_quality}, hint: {'Yes' if hint else 'No'}"
    )

    return {"rag_quality": rag_quality, "rag_context": rag_context, "rag_hint": hint}


def should_use_grader(state: RAGState) -> Literal["grader", "check_result"]:
    """Decide whether to use grader based on settings."""
    if settings.RAG_GRADER_ENABLED:
        logger.info("[RAG_SUBGRAPH] Grader enabled, proceeding to grade context")
        return "grader"
    else:
        logger.info("[RAG_SUBGRAPH] Grader disabled, skipping grading")
        # When grader is disabled, inject all context
        return "check_result"


def prepare_context_no_grader(state: RAGState) -> Dict[str, Any]:
    """
    Prepare context without grading (grader disabled).

    Injects all retrieved context directly, including ontology context.
    """
    rag_context = state.get(STATE_KEY_VECTOR_SEARCH_RESULTS, "")
    ontology_context = state.get("ontology_context", "")

    context_parts = []

    if ontology_context:
        context_parts.append(ontology_context)

    if rag_context and "No archival data found" not in rag_context:
        context_parts.append(rag_context)

    if not context_parts:
        return {
            "rag_quality": "IRRELEVANT",
            "rag_context": "",
            "rag_hint": "NOTE: Archival search found no relevant information. Use web search tools for current information.",
        }

    merged_context = "\n\n---\n\n".join(context_parts)

    # Inject all context when grader is disabled
    return {
        "rag_quality": "RELEVANT",  # Assume relevant when grader is off
        "rag_context": merged_context,
        "rag_hint": "",
    }


def get_rag_subgraph() -> StateGraph:
    """
    Build and return the RAG subgraph.

    The subgraph consists of:
    1. Vector Search Node - retrieves context from vector store
    2. Re-ranker Node (optional) - re-ranks documents if enabled
    3. Ontology Context Node - retrieves graph context from Neo4j
    4. Merge Context Node - combines document + graph context
    5. Grader Node (optional) - evaluates context relevance if enabled
    6. Check Result - prepares final output with optional hint

    Returns:
        Compiled StateGraph ready to invoke
    """
    from langgraph.graph import END

    workflow = StateGraph(RAGState)

    # Add nodes
    workflow.add_node("vector_search", vector_search_node)
    workflow.add_node("reranker", rerank_node)
    workflow.add_node("ontology_context", ontology_context_node)
    workflow.add_node("merge_context", merge_context_node)
    workflow.add_node("grader", grade_context)
    workflow.add_node("check_result", check_grader_result)
    workflow.add_node("prepare_context_no_grader", prepare_context_no_grader)

    # Set entry point
    workflow.set_entry_point("vector_search")

    # Define edges
    workflow.add_edge("vector_search", "reranker")
    workflow.add_edge("reranker", "ontology_context")
    workflow.add_edge("ontology_context", "merge_context")

    # After merging context, decide whether to use grader
    workflow.add_conditional_edges("merge_context", should_use_grader)

    # Grader flows to check_result
    workflow.add_edge("grader", "check_result")

    # No-grader path flows to check_result
    workflow.add_edge("prepare_context_no_grader", "check_result")

    # Check result ends the subgraph
    workflow.add_edge("check_result", END)

    logger.info("[RAG_SUBGRAPH] Subgraph compiled successfully")
    logger.info(
        f"[RAG_SUBGRAPH] Configuration: grader={settings.RAG_GRADER_ENABLED}, reranker={settings.RAG_RERANKER_ENABLED}"
    )

    return workflow.compile()


# Compiled subgraph instance (singleton)
rag_subgraph = get_rag_subgraph()


def run_rag_subgraph(query: str) -> Dict[str, Any]:
    """
    Run the RAG subgraph for a given query.

    This is the main entry point for the main agent graph to use.

    Args:
        query: The user query to search for

    Returns:
        Dict with:
        - rag_quality: RELEVANT, PARTIALLY_RELEVANT, or IRRELEVANT
        - rag_context: Filtered context to inject (empty if irrelevant)
        - rag_hint: Optional hint for the agent
    """
    logger.info("[RAG_SUBGRAPH] Invoking RAG subgraph")
    logger.info(
        f"[RAG_SUBGRAPH] Configuration: grader={settings.RAG_GRADER_ENABLED}, reranker={settings.RAG_RERANKER_ENABLED}"
    )

    initial_state = {
        "rag_query": query,
        "vector_search_results": "",
        "retrieved_docs": [],
        "rag_quality": "",
        "rag_context": "",
        "rag_hint": "",
        "ontology_context": "",
    }

    try:
        result = rag_subgraph.invoke(initial_state)

        logger.info(
            f"[RAG_SUBGRAPH] Subgraph complete: quality={result.get('rag_quality')}"
        )

        return result

    except Exception as e:
        logger.error(f"[RAG_SUBGRAPH] Subgraph failed: {e}")
        logger.exception("[RAG_SUBGRAPH] Full stack trace:")

        # Return safe defaults on error
        return {
            "rag_quality": "IRRELEVANT",
            "rag_context": "",
            "rag_hint": "NOTE: Archival search encountered an error. Use web search tools for information.",
        }
