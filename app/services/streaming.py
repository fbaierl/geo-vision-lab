"""
Streaming Service for GeoVision Lab.

This module provides the central logic for processing LLM streams and converting them
into UI-ready events. It decouples the complex streaming event loop from the
LangGraph topology in graph.py.

Key Responsibilities:
1. Parsing raw LLM tokens to handle <think> tags and technical artifacts.
2. Managing the LangGraph astream_events loop.
3. Suppressing internal grader/reviewer outputs from the user-facing stream.
4. Auto-saving sessions and ontologies after query completion.
"""

import logging
import re
from typing import AsyncGenerator, Dict, Any, Generator
from langchain_core.messages import HumanMessage

from app.core.config import settings
from app.core.constants import (
    STATE_KEY_RAG_QUALITY,
    STATE_KEY_RAG_HINT,
    STATE_KEY_ONTOLOGY,
    STATE_KEY_PENDING_ONTOLOGY,
)

logger = logging.getLogger("geovision_app")

_SUPPRESSED_NODES = {"grader", "reviewer", "ontology_extractor"}


def _is_suppressed_event(event: dict) -> bool:
    """Check if an event should be suppressed from the user-facing stream.

    Checks both tags and metadata (langgraph_node) to handle cases where
    wrapped LLMs (e.g., with_structured_output) don't propagate tags correctly.
    """
    tags = event.get("tags", [])
    if any(t in tags for t in _SUPPRESSED_NODES):
        return True

    metadata = event.get("metadata", {})
    langgraph_node = metadata.get("langgraph_node", "")
    if langgraph_node in _SUPPRESSED_NODES:
        return True

    return False


def _get_active_model_name() -> str:
    """Get the currently active model name for display."""
    if settings.USE_ONLINE_LLM and settings.GROQ_API_KEY:
        return settings.ONLINE_LLM_MODEL_NAME
    return settings.REASONING_LLM_MODEL_NAME


def _format_blocks(text: str) -> list[str]:
    clean_text = re.sub(
        r"^ARCHIVAL INTELLIGENCE REPORT:\n*", "", text, flags=re.IGNORECASE
    )
    clean_text = re.sub(
        r"^LIVE WEB INTELLIGENCE(?: \(.*?\))?:\n*", "", clean_text, flags=re.IGNORECASE
    )
    clean_text = re.sub(
        r"^LIVE WEB SEARCH RESULTS:\n*", "", clean_text, flags=re.IGNORECASE
    )

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


class StreamingResponseParser:
    """A stateful parser for LLM streaming output that handles think tags and partial tokens.

    This parser acts as a state machine to:
    1. Identify and extract <think> blocks into separate UI events.
    2. Buffer partial characters to avoid breaking tags like '<think>' across chunks.
    3. Suppress technical tags like <tool_code> from the user chat.
    """

    def __init__(self):
        self.buffer = ""  # Buffer for raw characters
        self.think_buffer = ""  # Accmulated thinking content for tool_result fallback
        self.in_think = False  # State: currently parsing a <think> block
        self.in_tool_code = False  # State: currently suppressing a <tool_code> block
        self.streaming_started = False

    def process_chunk(
        self, content_chunk: str
    ) -> Generator[Dict[str, Any], None, None]:
        """Process a text chunk from the LLM and yield UI-ready events."""
        if not content_chunk:
            return

        self.buffer += content_chunk

        while self.buffer:
            if not self.in_think and not self.in_tool_code:
                # Priority: Check for <think> then <tool_code> then <tool_call>
                think_idx = self.buffer.find("<think>")
                tool_code_idx = self.buffer.find("<tool_code>")
                tool_call_idx = self.buffer.find("<tool_call>")

                # Find the earliest tag
                found_tags = []
                if think_idx != -1:
                    found_tags.append((think_idx, "<think>"))
                if tool_code_idx != -1:
                    found_tags.append((tool_code_idx, "<tool_code>"))
                if tool_call_idx != -1:
                    found_tags.append((tool_call_idx, "<tool_call>"))

                if found_tags:
                    found_tags.sort()
                    idx, tag = found_tags[0]
                    before = self.buffer[:idx]
                    if before:
                        yield from self._yield_token(before)

                    self.buffer = self.buffer[idx + len(tag) :]
                    if tag == "<think>":
                        self.in_think = True
                        yield {"type": "thinking_start"}
                    elif tag == "<tool_code>":
                        self.in_tool_code = True
                else:
                    # Look for potential tag start at the end
                    idx = self.buffer.rfind("<")
                    if idx == -1:
                        yield from self._yield_token(self.buffer)
                        self.buffer = ""
                    else:
                        before = self.buffer[:idx]
                        if before:
                            yield from self._yield_token(before)
                        self.buffer = self.buffer[idx:]
                        if len(self.buffer) > 15:
                            yield from self._yield_token(self.buffer)
                            self.buffer = ""
                    break  # Wait for more chunks
            elif self.in_think:
                if "</think>" in self.buffer:
                    idx = self.buffer.find("</think>")
                    think_content = self.buffer[:idx]
                    if think_content:
                        yield {"type": "thinking_token", "content": think_content}
                        self.think_buffer += think_content

                    yield {"type": "thinking_end"}
                    # Don't send content - thinking already sent via thinking_* events
                    yield {
                        "type": "tool_result",
                        "tool": "reasoning",
                        "summary": "Reasoning steps completed",
                    }
                    self.think_buffer = ""
                    self.buffer = self.buffer[idx + len("</think>") :]
                    self.in_think = False
                else:
                    # Detect potential closing tag </think>
                    idx = self.buffer.rfind("<")
                    if idx == -1:
                        yield from self._yield_think_token(self.buffer)
                        self.buffer = ""
                    else:
                        before = self.buffer[:idx]
                        if before:
                            yield from self._yield_think_token(before)
                        self.buffer = self.buffer[idx:]
                        if len(self.buffer) > 15:
                            yield from self._yield_think_token(self.buffer)
                            self.buffer = ""
                    break
            elif self.in_tool_code:
                if "</tool_code>" in self.buffer:
                    idx = self.buffer.find("</tool_code>")
                    self.buffer = self.buffer[idx + len("</tool_code>") :]
                    self.in_tool_code = False
                else:
                    # Just consume everything until we see </tool_code>
                    idx = self.buffer.rfind("<")
                    if idx == -1:
                        self.buffer = ""
                    else:
                        self.buffer = self.buffer[idx:]
                        if len(self.buffer) > 15:
                            self.buffer = ""
                    break

    def _yield_token(self, content: str) -> Generator[Dict[str, Any], None, None]:
        if not self.streaming_started:
            yield {"type": "status", "phase": "streaming"}
            self.streaming_started = True
        yield {"type": "token", "content": content}

    def _yield_think_token(self, content: str) -> Generator[Dict[str, Any], None, None]:
        self.think_buffer += content
        yield {"type": "thinking_token", "content": content}

    def flush(self) -> Generator[Dict[str, Any], None, None]:
        """Flush any remaining content in the buffer at the end of the stream."""
        if not self.buffer:
            return

        if not self.in_think:
            yield from self._yield_token(self.buffer)
        else:
            yield from self._yield_think_token(self.buffer)
            yield {"type": "thinking_end"}
            # Don't send content - thinking already sent via thinking_* events
            yield {
                "type": "tool_result",
                "tool": "reasoning",
                "summary": "Reasoning steps completed",
            }
        self.buffer = ""


async def process_query_stream(
    user_query: str, thread_id: str = "default", graph_override=None
) -> AsyncGenerator[dict, None]:
    """Process a user query with conversational memory and stream events for UI.

    This is the primary entry point for the chat interface. It:
    1. Invokes the LangGraph agent with astream_events.
    2. Filters internal events (grader/reviewer/subgraphs).
    3. Translates graph events into a standardized UI event format.
    4. Ensures session persistence (auto-save) upon completion.
    """
    # Deferred import to avoid circular dependency with graph.py
    from app.agents.graph import app_graph

    graph = graph_override or app_graph

    logger.info(
        f"\n[QUERY-STREAM] New query received (thread={thread_id}): '{user_query}'"
    )

    # Set processing state
    from app.api.routes.health import set_processing_state

    set_processing_state(True, user_query)

    inputs = {"messages": [HumanMessage(content=user_query)]}
    config = {"configurable": {"thread_id": thread_id}}
    done_sent = False

    parser = StreamingResponseParser()

    try:
        logger.info(f"[QUERY-STREAM] >>> Starting astream_events (thread={thread_id})")
        async for event in graph.astream_events(inputs, config=config, version="v2"):
            kind = event.get("event")
            event_name = event.get("name", "unknown")

            # Check for errors
            if kind in ["on_chain_error", "on_llm_error", "on_chat_model_error"]:
                error_msg = event.get("data", {}).get("error", "Unknown error")
                logger.error(f"[STREAM ERROR] {kind}: {error_msg}")
                yield {"type": "error", "content": f"LLM error: {str(error_msg)}"}
                return

            if kind == "on_chain_start":
                node_name = event.get("name", "")
                if node_name == "rag_subgraph":
                    yield {
                        "type": "status",
                        "phase": "rag_retrieval",
                        "tool": "RAG Subgraph",
                    }
                elif node_name == "grader":
                    yield {"type": "status", "phase": "rag_grading", "tool": "Grader"}

            elif kind == "on_chat_model_start":
                if _is_suppressed_event(event):
                    continue

                active_model = _get_active_model_name()
                if parser.streaming_started:
                    yield {"type": "status", "phase": "revising", "model": active_model}
                else:
                    yield {
                        "type": "status",
                        "phase": "reasoning",
                        "model": active_model,
                    }

            elif kind == "on_tool_start":
                tool_name = event.get("name", "unknown")
                tool_input = event.get("data", {}).get("input", {})
                query_used = tool_input.get("query", "")
                phase = (
                    "vector_search" if tool_name == "vector_search" else "online_search"
                )
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
                if event.get("name") == "rag_subgraph":
                    output = event.get("data", {}).get("output", {})
                    rag_quality = output.get(STATE_KEY_RAG_QUALITY, "IRRELEVANT")
                    rag_hint = output.get(STATE_KEY_RAG_HINT, "")
                    summary = (
                        f"Archival intelligence retrieved (Quality: {rag_quality})"
                        if rag_quality != "IRRELEVANT"
                        else "No relevant archival data found"
                    )
                    yield {
                        "type": "rag_result",
                        "tool": "RAG Subgraph",
                        "summary": summary,
                        "quality": rag_quality,
                        "hint": rag_hint,
                    }

                node_name = event.get("name", "")
                if "review" in node_name.lower():
                    output = event.get("data", {}).get("output", {})
                    reviewer_result = (
                        output.get("reviewer_result", "")
                        if isinstance(output, dict)
                        else ""
                    )
                    if (
                        reviewer_result
                        and isinstance(reviewer_result, str)
                        and reviewer_result.strip()
                    ):
                        is_valid = reviewer_result.startswith("VALID")
                        yield {
                            "type": "validation_result",
                            "tool": "QA Reviewer",
                            "summary": "Analysis validated"
                            if is_valid
                            else "Analysis revised",
                            "content": reviewer_result,
                        }

                if event.get("name") == "ontology_extractor":
                    output = event.get("data", {}).get("output", {})
                    ontology_state = output.get(STATE_KEY_ONTOLOGY, {})
                    pending_state = output.get(STATE_KEY_PENDING_ONTOLOGY, {})

                    def serialize_ontology(ont):
                        if not ont:
                            return {"entities": {}, "links": {}}
                        entities = (
                            getattr(ont, "entities", {})
                            if not isinstance(ont, dict)
                            else ont.get("entities", {})
                        )
                        links = (
                            getattr(ont, "links", {})
                            if not isinstance(ont, dict)
                            else ont.get("links", {})
                        )

                        def serialize_obj(obj):
                            return (
                                obj.model_dump(mode="json")
                                if hasattr(obj, "model_dump")
                                else obj
                            )

                        return {
                            "entities": {
                                str(k): serialize_obj(v)
                                for k, v in entities.items()
                            },
                            "links": {
                                str(k): serialize_obj(v) for k, v in links.items()
                            },
                        }

                    full_ontology = serialize_ontology(ontology_state)
                    pending_ontology = serialize_ontology(pending_state)

                    entities = full_ontology.get("entities", {})
                    links = full_ontology.get("links", {})
                    pending_entities = pending_ontology.get("entities", {})
                    pending_links = pending_ontology.get("links", {})

                    yield {
                        "type": "ontology_updated",
                        "tool": "ontology_subgraph",
                        "summary": f"Graph updated: {len(entities)} entities, {len(links)} relationships",
                        "ontology": full_ontology,
                    }

                    if pending_entities or pending_links:
                        yield {
                            "type": "pending_ontology_updated",
                            "tool": "ontology_subgraph",
                            "summary": f"Pending changes: {len(pending_entities)} entities, {len(pending_links)} relationships",
                            "pending_ontology": pending_ontology,
                        }

            elif kind == "on_chat_model_end":
                if _is_suppressed_event(event):
                    continue
                # Don't send tool_result with content - tokens already streamed
                # The thinking content is sent via thinking_* events

            elif kind == "on_chat_model_stream":
                if _is_suppressed_event(event):
                    logger.debug(f"[STREAM] Suppressed event from: {event.get('name')}, tags: {event.get('tags')}, metadata: {event.get('metadata', {}).get('langgraph_node')}")
                    continue
                if "grader" in event_name.lower():
                    continue

                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    content_chunk = chunk.content
                    if isinstance(content_chunk, list):
                        content_chunk = "".join(
                            [
                                c.get("text", "")
                                for c in content_chunk
                                if isinstance(c, dict) and "text" in c
                            ]
                        )
                    elif not isinstance(content_chunk, str):
                        content_chunk = str(content_chunk)

                    # Debug: log if content looks like JSON
                    if content_chunk.strip().startswith('{') or content_chunk.strip().startswith('['):
                        logger.debug(f"[STREAM] Possible JSON in stream from: {event.get('name')}, tags: {event.get('tags')}, metadata: {event.get('metadata', {}).get('langgraph_node')}")

                    for ui_event in parser.process_chunk(content_chunk):
                        yield ui_event

    except Exception as e:
        logger.error(f"[QUERY-STREAM] Error: {e}", exc_info=True)
        yield {"type": "error", "content": f"Streaming error: {str(e)}"}
    finally:
        if not done_sent:
            for ui_event in parser.flush():
                yield ui_event
            yield {"type": "done"}
            done_sent = True
        set_processing_state(False)

        # Auto-save session
        try:
            # We must import graph's app_graph here to get the state
            from app.agents.graph import app_graph

            final_state = await graph.aget_state(config)
            messages = final_state.values.get("messages", [])

            serializable_messages = []
            for msg in messages:
                msg_dict = (
                    msg.model_dump(mode="json")
                    if hasattr(msg, "model_dump")
                    else {"content": str(msg)}
                )
                msg_type = msg_dict.get("type", None)
                if msg_type == "human":
                    msg_dict["role"] = "user"
                elif msg_type == "ai":
                    msg_dict["role"] = "assistant"
                elif msg_type == "system":
                    msg_dict["role"] = "system"
                elif msg_type == "tool":
                    msg_dict["role"] = "tool"
                serializable_messages.append(msg_dict)

            # Serialize pending_ontology from graph state
            pending_ontology_data = None
            pending_state = final_state.values.get("pending_ontology")
            if pending_state:
                if hasattr(pending_state, "model_dump"):
                    pending_ontology_data = pending_state.model_dump(mode="json")
                elif isinstance(pending_state, dict):
                    pending_ontology_data = pending_state

            import httpx

            async with httpx.AsyncClient() as client:
                save_url = f"http://localhost:8000/api/sessions/{thread_id}/save"
                save_data = {
                    "messages": serializable_messages,
                }
                if pending_ontology_data is not None:
                    save_data["pending_ontology"] = pending_ontology_data
                await client.post(save_url, json=save_data, timeout=10.0)
        except Exception as save_error:
            logger.error(f"[AUTO-SAVE] Error: {save_error}")
