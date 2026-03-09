# Enhanced Logging for Dozzle

## Overview

The logging has been enhanced to provide real-time visibility into the agent's reasoning process, tool usage, and response streaming in Dozzle.

---

## What You'll See Now

### When a Query Arrives

```
2026-03-09 12:34:56 | geovision_main | INFO | ▸ GeoVision Lab starting...
2026-03-09 12:35:10 | geovision_api | INFO | ▸ QUERY RECEIVED: 'What happened in Ukraine in 2024?' [thread=abc-123-def]
2026-03-09 12:35:10 | agent_flow | INFO | 
============================================================
2026-03-09 12:35:10 | agent_flow | INFO | ▸ NEW QUERY: 'What happened in Ukraine in 2024?' [thread=abc-123-def]
2026-03-09 12:35:10 | agent_flow | INFO | ============================================================
```

### During Agent Processing

```
2026-03-09 12:35:11 | agent_flow | INFO |   ┝━ [AGENT DECISION] Using tools: web_search
2026-03-09 12:35:12 | geovision_api | INFO |   ┝━ [REASONING] LLM: qwen3.5:4b
2026-03-09 12:35:13 | geovision_api | INFO |   ┝━ [ONLINE_SEARCH] Tool: web_search | Query: 'Ukraine 2024 conflict'
2026-03-09 12:35:15 | geovision_api | INFO |   ┝━ [TOOL RESULT] web_search: Retrieved 1 text block | Citations: 1
2026-03-09 12:35:16 | agent_flow | INFO |   ┝━ [AGENT DECISION] Generating final response
2026-03-09 12:35:17 | geovision_api | INFO |   ┝━ [REVIEWING] LLM: qwen2.5:0.5b
2026-03-09 12:35:18 | agent_flow | INFO |   ┝━ [QA REVIEW] ✓ Response validated successfully
2026-03-09 12:35:19 | geovision_api | INFO | ▸ RESPONSE COMPLETE [thread=abc-123-def]
```

### When QA Review Fails (Retry Loop)

```
2026-03-09 12:40:22 | agent_flow | INFO |   ┝━ [REVIEWING] LLM: qwen2.5:0.5b
2026-03-09 12:40:25 | agent_flow | INFO |   ┝━ [QA REVIEW] ✗ Response rejected: INVALID: Missing map tag for location query...
2026-03-09 12:40:26 | geovision_api | INFO |   ┝━ [REVISING] LLM: qwen3.5:4b
2026-03-09 12:40:30 | agent_flow | INFO |   ┝━ [QA REVIEW] ✓ Response validated successfully
```

### When Using Vector Search with Citations

```
2026-03-09 12:45:00 | geovision_api | INFO | ▸ QUERY RECEIVED: 'Show me reports about Cold War espionage' [thread=xyz-789]
2026-03-09 12:45:01 | agent_flow | INFO |   ┝━ [AGENT DECISION] Using tools: vector_search
2026-03-09 12:45:02 | geovision_api | INFO |   ┝━ [VECTOR_SEARCH] Tool: vector_search | Query: 'Cold War espionage'
2026-03-09 12:45:04 | geovision_api | INFO |   ┝━ [TOOL RESULT] vector_search: Retrieved 3 text blocks | Citations: 3
```

---

## Log Legend

| Symbol | Meaning |
|--------|---------|
| `▸` | Major event (query received, complete) |
| `┝━` | Sub-step in processing |
| `✓` | Success (QA passed) |
| `✗` | Failure (QA rejected) |

---

## Log Levels

| Level | What It Shows |
|-------|---------------|
| **INFO** | All major processing steps, tool usage, QA results |
| **DEBUG** | Detailed agent state transitions (hidden by default) |
| **WARNING** | Non-critical issues |
| **ERROR** | Stream failures, database errors, LLM errors |

---

## Configuration

Logging is configured in `app/main.py`:

```python
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Uvicorn access logs are suppressed to reduce noise
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
```

---

## Benefits

1. **Real-time debugging**: Watch the agent think and choose tools
2. **QA visibility**: See when responses are rejected and why
3. **Citation tracking**: Know when citations are attached
4. **Performance monitoring**: Identify slow steps in the pipeline
5. **User support**: Debug user issues by reviewing query logs

---

## Accessing Logs

| Service | URL | What You See |
|---------|-----|--------------|
| **Dozzle** | http://localhost:9999 | Real-time container logs with filtering |
| **Grafana** | http://localhost:3000 | Aggregated logs with Loki queries |
| **Docker CLI** | `docker logs -f geovision-app` | Raw terminal logs |
