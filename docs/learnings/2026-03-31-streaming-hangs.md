# Case Study: Resolving Persistent Streaming Hangs (2026-03-31)

## Problem Statement
The GeoVision Lab agent experienced a consistent system hang immediately after a `web_search` tool call was requested. The agent would complete its reasoning phase, log that tool calls were requested, and then stop responding entirely without any error messages.

## Root Causes Identified

### 1. The Python `while...else` Indentation Trap
**Issue**: During a refactor in PR #76, an `if...else` block inside a `while buffer:` loop was accidentally re-indented.

```python
# Intended Logic (if/else inside while)
while buffer:
    if not in_think:
        ...
    else:  # Correct: pairs with if
        ...

# Buggy Logic (while/else)
while buffer:
    if not in_think:
        ...
    # else:  <-- Wrong: pairs with while loop itself!
```

**Consequence**: In Python, a `while...else` block executes only when the `while` loop terminates naturally (buffer becomes empty). If `in_think` was `True`, the `if not in_think:` branch was skipped, and there was no alternative branch. The loop would re-check `buffer` (which was still full), leading to an **infinite CPU-spinning loop** that blocked the async event stream.

### 2. Sync Wrapper Deadlock in LangGraph `astream_events`
**Issue**: A custom synchronous node `execute_tools_with_logging` was used to wrap the `ToolNode`.

```python
def execute_tools_with_logging(state: AgentState):
    # This is a synchronous function
    tool_node = ToolNode(tools)
    return tool_node.invoke(state)
```

**Consequence**: LangGraph's `astream_events` requires that nodes properly propagate the `RunnableConfig` to downstream components to maintain the async context. When `ToolNode` is invoked inside a standard sync `def` without this context, it loses its connection to the parent stream. In some configurations, this causes the underlying `ToolNode` to deadlock while trying to emit its own internal events to a stream that is no longer accessible from its thread context.

### 3. ThreadPoolExecutor `wait=True` Deadlock
**Issue**: A timeout wrapper for external tools used a `with` context manager for `ThreadPoolExecutor`.

```python
with ThreadPoolExecutor() as executor:
    future = executor.submit(func)
    return future.result(timeout=10)
```

**Consequence**: The `with` statement in Python calls `.shutdown(wait=True)` by default. If the underlying thread (e.g., a hanging Wikipedia request) continues to block beyond the 10-second timeout, the `future.result()` raises an exception, but the `with` block **cannot exit** until the hanging thread completes. This caused the main execution thread to hang at the end of the context block.

## Lessons Learned & Best Practices

1.  **Indentation Consistency**: Use strict linting (e.g., Ruff or Black) and be extremely cautious when re-indenting complex control structures.
2.  **Native LangGraph Nodes**: Avoid wrapping standard LangGraph components (like `ToolNode`) in simple sync functions if using `astream_events`. Use them directly via `workflow.add_node(NODE_NAME, ToolNode(tools))`.
3.  **Non-Blocking Shutdowns**: When using `ThreadPoolExecutor` for timeouts, always use `executor.shutdown(wait=False)` in a `finally` block to ensure the main thread can proceed even if a child thread remains blocked.
4.  **Logging as Breadcrumbs**: The fact that the hang occurred *exactly* between agent output and tool execution was the key to identifying the `ToolNode` and streaming loop as the primary suspects.
