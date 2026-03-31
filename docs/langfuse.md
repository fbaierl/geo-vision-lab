# Langfuse Integration for GeoVision Lab

This document describes the Langfuse integration for LLM observability in GeoVision Lab.

## Overview

Langfuse provides production-grade monitoring for GeoVision Lab agent workflows, including:
- Distributed tracing
- Prompt versioning
- Cost tracking
- Latency breakdown
- Quality feedback

## Configuration

### Environment Variables

Add the following to your `.env` file:

```env
# Langfuse Configuration
LANGFUSE_ENABLED=false
LANGFUSE_PUBLIC_KEY=pk-lf-your-public-key-here
LANGFUSE_SECRET_KEY=sk-lf-your-secret-key-here
LANGFUSE_HOST=https://cloud.langfuse.com
```

### Deployment Options

1. **Development**: Langfuse Cloud (Free tier: 50k observations/month)
   - Sign up at: https://cloud.langfuse.com
   
2. **Production/B2G**: Self-hosted (Full data control)
   - Deploy using Docker: https://langfuse.com/self-hosting

## Features

### 1. LLM Tracing

When enabled, all LLM calls, chain executions, and tool invocations are automatically traced:
- Agent reasoning steps
- RAG retrieval and grading
- Tool executions (web search, vector search)
- QA validation
- Ontology extraction

### 2. Feedback API

A new `/api/feedback` endpoint allows users to submit thumbs up/down feedback:

```bash
curl -X POST http://localhost:8000/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "thread_id": "session-123",
    "rating": "thumbs_up",
    "comment": "Very helpful response!"
  }'
```

**Response:**
```json
{
  "success": true,
  "message": "Feedback 'thumbs_up' recorded successfully",
  "trace_id": "trace-abc123"
}
```

### 3. UI Feedback Buttons

The chat interface now includes 👍/👎 buttons for each assistant response. Clicking a button:
- Submits feedback to the backend
- Sends the feedback to Langfuse (if enabled)
- Shows a confirmation toast message

## Architecture

### Files Modified/Created

| File | Purpose |
|------|---------|
| `requirements.txt` | Added `langfuse` dependency |
| `.env.example` | Added Langfuse environment variables |
| `app/core/config.py` | Added Langfuse settings |
| `app/core/langfuse_config.py` | Langfuse callback configuration |
| `app/core/di_llm.py` | Support for Langfuse callbacks |
| `app/api/routes/feedback.py` | Feedback API endpoint |
| `app/main.py` | Registered feedback router |
| `static/index.html` | Added Langfuse link and feedback buttons |
| `static/style.css` | Feedback button styling |
| `tests/test_langfuse.py` | Integration tests |

### Tracing Priority

The system supports both Langfuse and LangSmith, with the following priority:
1. **Langfuse** (if enabled)
2. **LangSmith** (if Langfuse disabled, LangSmith enabled)
3. **No tracing** (if both disabled)

Only one tracing backend is active at a time.

## Usage

### Enable Langfuse Tracing

1. Set `LANGFUSE_ENABLED=true` in your `.env` file
2. Add your Langfuse credentials
3. Restart the application

### View Traces

Access the Langfuse dashboard at:
- **Cloud**: https://cloud.langfuse.com
- **Self-hosted**: Your configured host URL

### Submit Feedback

**Via UI:**
1. Click the 👍 or 👎 button below any assistant response
2. Optionally add a comment
3. Feedback is sent to Langfuse automatically

**Via API:**
```bash
POST /api/feedback
{
  "thread_id": "session-id",
  "rating": "thumbs_up" | "thumbs_down",
  "comment": "optional comment"
}
```

## Testing

Run the Langfuse integration tests:

```bash
pytest tests/test_langfuse.py -v
```

**Test coverage:**
- Langfuse configuration
- Callback handler initialization
- LLM integration
- Feedback API endpoints
- Graceful degradation (when Langfuse unavailable)

## Success Metrics

| Metric | Target |
|--------|--------|
| Trace Coverage | 100% of queries traced |
| Latency Overhead | <50ms per trace |
| Error Rate | <0.1% tracing failures |

## Troubleshooting

### Langfuse Not Tracing

1. Check `LANGFUSE_ENABLED=true` in `.env`
2. Verify API keys are correct
3. Check application logs for `[LANGFUSE]` messages
4. Ensure network connectivity to Langfuse host

### Feedback API Returns Error

1. Verify Langfuse credentials
2. Check application logs for `[FEEDBACK]` messages
3. Ensure Langfuse service is accessible

### High Latency

1. Check Langfuse host response times
2. Consider self-hosting for lower latency
3. Review network configuration

## Migration from LangSmith

To migrate from LangSmith to Langfuse:

1. Set `LANGSMITH_TRACING=false`
2. Set `LANGFUSE_ENABLED=true`
3. Add Langfuse credentials
4. Restart application

Both can coexist in the codebase, but only one is active at a time.

## Resources

- [Langfuse Documentation](https://langfuse.com/docs)
- [Langfuse LangChain Integration](https://langfuse.com/docs/integrations/langchain)
- [Langfuse Self-Hosting](https://langfuse.com/self-hosting)
- [GeoVision Lab Architecture](../architecture.mermaid)
