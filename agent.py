import os
from typing import TypedDict, Annotated, List, Literal
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_ollama import ChatOllama
from langchain_core.tools import tool
from langchain_postgres import PGVector
import wikipedia
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

# Environment properties
POSTGRES_URI = os.getenv(
    "POSTGRES_URI",
    "postgresql+psycopg://geovision:geovision@geovision-postgres:5432/geovision",
)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://geovision-ollama:11434")
COLLECTION_NAME = "historical_reports"

# Shared embedding model (loaded once at startup)
_embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")


def _get_vector_store() -> PGVector:
    return PGVector(
        embeddings=_embeddings,
        connection=POSTGRES_URI,
        collection_name=COLLECTION_NAME,
    )


# --- Tool Definitions ---

@tool
def vector_search(query: str) -> str:
    """Searches the local archival intelligence database for historical conflict reports or past war events."""
    print(f"  [AGENT] Using vector_search for: {query}")
    try:
        store = _get_vector_store()
        docs = store.similarity_search(query, k=3)
        if not docs:
            return "No archival data found in historical intelligence database."
        results = "\n\n".join([doc.page_content for doc in docs])
        return f"ARCHIVAL INTELLIGENCE REPORT:\n{results}"
    except Exception as e:
        return f"Error accessing vector database: {str(e)}"


@tool
def web_search(query: str) -> str:
    """Searches Wikipedia to get live, up-to-date news and background on CURRENT events and recent geopolitical shifts."""
    print(f"  [AGENT] Using web_search for: {query}")
    try:
        results = wikipedia.summary(query, sentences=4)
        return f"LIVE WEB INTELLIGENCE:\n{results}"
    except Exception as e:
        return f"Failed to retrieve web information on '{query}'. Error: {e}"


tools = [vector_search, web_search]

# --- LangGraph Setup ---

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]


# Setup the LLM
llm = ChatOllama(model="qwen2.5:7b", base_url=OLLAMA_HOST)
llm_with_tools = llm.bind_tools(tools)

system_msg = """You are an advanced Geopolitical Intelligence Agent for the GeoVision Lab.
Your objective is to provide concise, accurate, and tactical analysis of conflicts and geopolitical shifts.

You have access to two primary intel feeds:
1. `vector_search`: For historical reports, past wars, and cold war intelligence stored locally.
2. `web_search`: For current, up-to-date, live news and background information on active geopolitics.

Use the proper tool depending on whether the user asks about deep history or current events. If you don't know the answer, use a tool to find out.

Respond in a clear, brief, unclassified military-style format, avoiding robotic language. Always summarize the intel you found.
"""


def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return "__end__"


def call_model(state: AgentState):
    messages = [SystemMessage(content=system_msg)] + list(state["messages"])
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


# Build the Graph with short-term conversational memory
checkpointer = MemorySaver()
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", ToolNode(tools))
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")
app_graph = workflow.compile(checkpointer=checkpointer)


# External interface
def process_query(user_query: str, thread_id: str = "default") -> str:
    """Process a user query with conversational memory.

    Args:
        user_query: The user's question or command.
        thread_id: A unique session identifier so the agent can maintain
                   context across follow-up questions within the same thread.
    """
    print(f"\n[QUERY] New query received (thread={thread_id}): '{user_query}'")
    inputs = {"messages": [HumanMessage(content=user_query)]}
    config = {"configurable": {"thread_id": thread_id}}
    result = app_graph.invoke(inputs, config=config)
    return result["messages"][-1].content
