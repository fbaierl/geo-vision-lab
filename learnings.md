# Geopolitical Intelligence Agent: Technical Learnings

## Agent Graph Decision Logic

In the GeoVision Lab agent, the decision of whether to continue with tool calls or move to the review phase is handled by a **directed acyclic graph (DAG)** implemented using `LangGraph`.

### The Core Mechanism: Conditional Edges

The heart of the decision-making process is the `should_continue` function, which acts as a router on a **conditional edge**.

```python
def should_continue(state: AgentState) -> Literal["tools", "reviewer"]:
    # 1. Get the last message from the assistant
    last_message = state["messages"][-1]
    
    # 2. Check if the LLM requested any tool calls
    if getattr(last_message, "tool_calls", None):
        return "tools"
        
    # 3. If no tools are requested, the LLM is done with its work
    return "reviewer"
```

### How the Workflow Operates

1.  **Model Binding**: The reasoning LLM is "bound" to a set of specific tools (`vector_search`, `duckduckgo_search`, etc.). This tells the LLM that these functions are available for it to call if it needs more information.
2.  **The Reasoning Loop**:
    *   The `agent` node invokes the LLM.
    *   The LLM generates a response. If it realizes it needs data (e.g., "I need to check current events in Iran"), it outputs a specialized `tool_call` payload instead of a final text answer.
    *   The `should_continue` edge intercepts this. If `tool_calls` are present, it sends the state to the `tools` node.
3.  **Tool Execution**:
    *   The `tools` node (standard LangGraph `ToolNode`) executes the actual Python functions associated with the requested tools.
    *   The results of these tools are appended to the message history as `ToolMessage` objects.
    *   The graph loops back to the `agent` node.
4.  **Completion**:
    *   The LLM now sees the tool results in its context and decides if it has enough info.
    *   If it produces a normal text response (no `tool_calls`), `should_continue` routes the flow to the `reviewer` node for final QA before ending the process.

### Why this approach?
- **Autonomy**: The LLM autonomously decides *when* it needs help.
- **Stateful**: The `AgentState` ensures that the entire "conversation" with tools is recorded, so the LLM doesn't repeat itself.
- **Validation**: By routing to a `reviewer` node only *after* the tool loop finishes, we ensure that the final result (even if based on tool data) still meets our strict GeoVision formatting rules (like mandatory map tags).

## Reasoning vs. Standard LLMs

### What is a "Reasoning LLM"?

In the context of this project, a **Reasoning LLM** is the primary model (Worker) that follows a "Chain-of-Thought" (CoT) pattern. Instead of jumping straight to the final answer, it breaks down its logic into steps:
1.  **Analyze** the user intent.
2.  **Determine** which tools are needed (e.g., "Do I need local history or live news?").
3.  **Synthesize** the tool outputs into a coherent military-style report.

### How it differs from other LLMs

| Feature | Reasoning LLM (Worker) | Standard/Reviewer LLM |
| :--- | :--- | :--- |
| **Primary Goal** | Complex problem solving & Tool use | Narrow validation or direct response |
| **Output Style** | Detailed, multi-step, structured logic | Direct, concise, "Yes/No" or fixed format |
| **Constraint** | Forced to use `<think>` tags | No reasoning tags (usually) |
| **Model Size** | Typically larger (4B - 9B) | Typically smaller (0.5B) for speed |

### Do all LLMs here have "Reasoning"?

Technically, **any** Instruction-tuned LLM can "reason" if prompted correctly, but they fall into two categories:

1.  **Native Reasoning**: Models like *DeepSeek-R1* or *OpenAI o1* are specifically trained to reason internally. They might output reasoning even without being asked.
2.  **Prompted Reasoning**: Models like our `qwen3.5` variants (Instruct models). They have the *capability* to reason, but we explicitly trigger it using the **System Prompt** in `graph.py` (Rule 40):
    > *"you MUST wrap your thought process inside <think>...</think> tags."*

### How can I check if a model is "reasoning"?

1.  **The "Think" Test**: Look at the stream output in the UI. If you see the "Reasoning steps completed" indicator (which hides the text between `<think>` tags), the model is following the protocol.
2.  **Response Latency**: A model performing reasoning will take longer to "start" its final answer because it's busy generating the "thought" tokens first.
3.  **Log Inspection**: Check the `app_flow` logs. If the model output contains a logical breakdown of its search strategy before the actual tool call, it's effectively reasoning.
4.  **Hardware Check**: In our `docker-compose.yml`, the `geovision-ollama` container logs will show the VRAM usage. Larger reasoning models (9B) will consume significantly more VRAM than the tiny reviewer model (0.5B).
