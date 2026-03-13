# Debugging the GeoVision Lab RAG Chain

> **Related Documentation:**
> - [Agent Workflow](../AGENT_WORKFLOW.md) — Detailed agent orchestration guide
> - [Technology Choices](../TECHNOLOGY.md) — Tech stack rationale
> - [README](../README.md) — Quick start guide

---

The intelligence agent (RAG chain) operates using LangGraph. This involves passing a state object (messages) between reasoning nodes and tool-execution nodes. Here is a guide on how to debug this pipeline end-to-end.

## 1. Running Unit Tests

The reasoning chain has been decoupled and thoroughly unit tested. Run these tests to verify individual behaviors:

```bash
# Test the ingestion logic (document loaders, vector embeddings)
env -u DEBUG pytest tests/test_ingestion.py -v

# Test the individual intelligence tools (vector search, web search)
env -u DEBUG pytest tests/test_reasoning_tools.py -v

# Test the LangGraph transitions (`should_continue`, `call_model`)
env -u DEBUG pytest tests/test_reasoning_graph.py -v

# Run the live Database Integration Test (automatically spins up Ephemeral MongoDB via Docker)
env -u DEBUG pytest tests/test_db_integration.py -v -s
```

> **Note**: The `DEBUG=WARN` environment variable setting causes issues with Pydantic base settings expecting a boolean `DEBUG` value. The `-u DEBUG` flag unsets this during testing.

## 2. End-to-End Debugging with PDB

To debug the graph transitions interactively, you can drop a `pdb.set_trace()` statement in any of the nodes inside `app/agents/graph.py` (for example, inside `call_model` or `should_continue`). 

Then execute a manual script or unit test that triggers the graph:

```python
# Create a quick script test.py in your root directory
from app.agents.graph import process_query

def main():
    print("Testing graph execution...")
    result = process_query("What factors contributed to the end of the Cold War?", "debug-thread")
    print("\nResult:", result)

if __name__ == "__main__":
    main()
```

Run it locally to step through your debugger:
```bash
python test.py
```

## 3. Investigating LangChain Logs
LangChain supports verbose debugging output to show exactly what prompts are being built and what the LLM is responding with exactly.

You can enable this programmatically by modifying `app/main.py` or `app/agents/graph.py`:

```python
import langchain
langchain.debug = True
```

When this is enabled, every LLM call, prompt template mapping, and tool invocation will be printed distinctly in your standard output, making it extremely clear when an issue is caused by the LLM versus the retrieval steps.
