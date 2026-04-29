from typing import TypedDict, Annotated, List, Optional, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
import operator


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    validation_attempts: Annotated[int, operator.add]
    is_valid: bool
    vector_search_results: Optional[str]
    ontology: Optional[
        Any
    ]  # Will store SessionOntology.Dict since TypedDict serializes easier
    pending_ontology: Optional[
        Any
    ]  # Unreviewed ontology changes (queued for batch review)

    # RAG Subgraph outputs
    rag_quality: Optional[str]  # RELEVANT, PARTIALLY_RELEVANT, IRRELEVANT
    rag_context: Optional[str]  # Filtered context to inject into agent
    rag_hint: Optional[str]  # Hint for agent when context is irrelevant
