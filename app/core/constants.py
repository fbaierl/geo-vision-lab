"""
Constants for GeoVision Lab

Centralized constants to avoid magic strings throughout the codebase.
"""


# =============================================================================
# Agent Graph Node Names
# =============================================================================

NODE_VECTOR_SEARCH = "vector_search"
NODE_AGENT = "agent"
NODE_TOOLS = "tools"
NODE_REVIEWER = "reviewer"
NODE_ONTOLOGY_EXTRACTOR = "ontology_extractor"
NODE_LOCATION_PRIORITIZER = "location_prioritizer"

# RAG Subgraph nodes
NODE_RAG_SUBGRAPH = "rag_subgraph"
NODE_GRADER = "grader"


# =============================================================================
# Event Types for Streaming
# =============================================================================

EVENT_TYPE_STATUS = "status"
EVENT_TYPE_TOOL_RESULT = "tool_result"
EVENT_TYPE_TOKEN = "token"
EVENT_TYPE_DONE = "done"
EVENT_TYPE_ERROR = "error"
EVENT_TYPE_ONTOLOGY_UPDATED = "ontology_updated"

# Thinking/reasoning stream events
EVENT_TYPE_THINKING_START = "thinking_start"
EVENT_TYPE_THINKING_TOKEN = "thinking_token"
EVENT_TYPE_THINKING_END = "thinking_end"


# =============================================================================
# Streaming Phases
# =============================================================================

PHASE_VECTOR_SEARCH = "vector_search"
PHASE_REASONING = "reasoning"
PHASE_REVIEWING = "reviewing"
PHASE_ONLINE_SEARCH = "online_search"
PHASE_EXTRACTING_ONTOLOGY = "extracting_ontology"
PHASE_STREAMING = "streaming"
PHASE_REVISING = "revising"


# =============================================================================
# Tool Names
# =============================================================================

TOOL_VECTOR_SEARCH = "vector_search"
TOOL_WEB_SEARCH = "web_search"
TOOL_DUCKDUCKGO_SEARCH = "duckduckgo_search"
TOOL_NEWS_ARCHIVE_SEARCH = "news_archive_search"
TOOL_REASONING = "reasoning"
TOOL_QA_REVIEWER = "QA Reviewer"


# =============================================================================
# Validation Results
# =============================================================================

VALIDATION_VALID = "VALID"
VALIDATION_INVALID = "INVALID"


# =============================================================================
# State Keys
# =============================================================================

STATE_KEY_MESSAGES = "messages"
STATE_KEY_VALIDATION_ATTEMPTS = "validation_attempts"
STATE_KEY_IS_VALID = "is_valid"
STATE_KEY_VECTOR_SEARCH_RESULTS = "vector_search_results"
STATE_KEY_ONTOLOGY = "ontology"

# RAG Subgraph state keys
STATE_KEY_RAG_QUERY = "rag_query"
STATE_KEY_RAG_QUALITY = "rag_quality"
STATE_KEY_RAG_CONTEXT = "rag_context"
STATE_KEY_RAG_HINT = "rag_hint"
STATE_KEY_RETRIEVED_DOCS = "retrieved_docs"  # For re-ranker candidates
