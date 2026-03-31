"""
Grader Node for RAG Subgraph

Evaluates whether retrieved context is relevant to the user's query.
Implements the "Corrective RAG" pattern by catching poor retrieval before generation.
"""

from typing import Dict, Any
from langchain_core.messages import SystemMessage
from app.core.di_llm import get_llm
from app.core.constants import STATE_KEY_VECTOR_SEARCH_RESULTS
import logging

logger = logging.getLogger(__name__)

GRADE_PROMPT = """You are an expert evaluator of retrieval quality for geopolitical intelligence.

Your task: Determine if the retrieved context contains relevant information to answer the user's query.

Evaluation Criteria:
- RELEVANT: Context directly addresses the query topic with useful information
- PARTIALLY_RELEVANT: Context has some related information but may be incomplete
- IRRELEVANT: Context does not address the query or contains unrelated information

User Query: {query}

Retrieved Context:
{context}

Reply with ONLY one word: RELEVANT, PARTIALLY_RELEVANT, or IRRELEVANT"""


def grade_context(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate if retrieved context is relevant to the user's query.
    
    This implements the "Corrective RAG" pattern by catching poor
    retrieval before generation and adjusting agent behavior accordingly.
    
    Args:
        state: Current graph state containing query and context
        
    Returns:
        Dict with 'rag_quality' (RELEVANT, PARTIALLY_RELEVANT, IRRELEVANT)
        and 'rag_context' (filtered context or empty string)
    """
    logger.info("=" * 80)
    logger.info("[GRADER] Starting context relevance evaluation")
    logger.info("=" * 80)
    
    # Extract query from state
    query = state.get("rag_query", "")
    context = state.get(STATE_KEY_VECTOR_SEARCH_RESULTS, "")
    
    if not query:
        logger.warning("[GRADER] No query found, defaulting to IRRELEVANT")
        return {"rag_quality": "IRRELEVANT", "rag_context": ""}
    
    if not context or "No archival data found" in context or "error" in context.lower():
        logger.info("[GRADER] No context available, marking as IRRELEVANT")
        return {"rag_quality": "IRRELEVANT", "rag_context": ""}
    
    logger.info(f"[GRADER] Query: {query[:100]}...")
    logger.info(f"[GRADER] Context length: {len(context)} chars")
    
    # Build prompt
    prompt = GRADE_PROMPT.format(query=query, context=context)
    
    # Get LLM judgment
    llm = get_llm()
    messages = [SystemMessage(content=prompt)]
    
    try:
        response = llm.invoke(messages, config={"tags": ["grader"]})
        grade = response.content.strip().upper()
        
        # Extract just the grade word
        if "RELEVANT" in grade:
            if "PARTIALLY" in grade or "PARTIAL" in grade:
                grade = "PARTIALLY_RELEVANT"
            else:
                grade = "RELEVANT"
        elif "IRRELEVANT" in grade:
            grade = "IRRELEVANT"
        else:
            grade = "PARTIALLY_RELEVANT"  # Default to middle ground
        
        logger.info(f"[GRADER] Context grade: {grade}")
        
        # Filter context based on grade
        if grade == "IRRELEVANT":
            logger.info("[GRADER] Context irrelevant - will not inject into agent")
            rag_context = ""
        else:
            # RELEVANT or PARTIALLY_RELEVANT - inject context
            logger.info(f"[GRADER] Context {grade} - will inject into agent")
            rag_context = context
        
        logger.info("[GRADER] === EVALUATION COMPLETE ===")
        
        return {
            "rag_quality": grade,
            "rag_context": rag_context
        }
        
    except Exception as e:
        logger.error(f"[GRADER] Grading failed: {e}")
        # On error, don't inject potentially bad context
        return {"rag_quality": "IRRELEVANT", "rag_context": ""}
