from typing import TypedDict, Annotated, List, Optional, Dict, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
import operator

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    validation_attempts: Annotated[int, operator.add]
    is_valid: bool
    vector_search_results: Optional[str]
    ontology: Optional[Any] # Will store SessionOntology.Dict since TypedDict serializes easier
