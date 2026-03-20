# LangSmith Self-Hosted Setup

This project includes a fully self-hosted LangSmith instance for tracing and debugging all LLM operations.

## Architecture

The LangSmith stack consists of:

- **langsmith-redis** (port 6379) - Message queue and caching
- **langsmith-postgres** (port 5432) - Primary data storage
- **langsmith-clickhouse** (ports 8123, 9000) - Analytics and tracing data
- **langsmith-backend** (port 1984) - API server
- **langsmith-frontend** (port 3030) - Web UI

## Quick Start

### 1. Start the Full Stack

```bash
docker-compose up -d
```

Wait ~2 minutes for all LangSmith services to become healthy.

### 2. Access the LangSmith UI

Open your browser: **http://localhost:3030**

- No authentication required for local development
- All traces are automatically sent from the app

### 3. View Your Traces

1. Make a request to the API: `http://localhost:8000`
2. Refresh the LangSmith UI
3. See real-time traces of:
   - LLM calls (prompts, completions, token usage)
   - Tool invocations (vector search, web search)
   - Agent reasoning steps
   - Location extraction & prioritization
   - Full execution graphs

## Configuration

LangSmith is configured in `app/core/config.py`:

```python
LANGSMITH_TRACING: bool = True
LANGSMITH_API_KEY: str = "langsmith"  # Self-hosted doesn't require real key
LANGSMITH_PROJECT: str = "geo-vision-lab"
LANGSMITH_ENDPOINT: str = "http://geovision-langsmith-backend:1984"
```

## Disabling LangSmith

To disable tracing (e.g., for faster local testing):

1. Set `LANGSMITH_TRACING=false` in environment variables
2. Or remove the LangSmith services from `docker-compose.yml`

## Troubleshooting

### Backend not starting
```bash
docker logs geovision-langsmith-backend
```

### Frontend not connecting to backend
Check that the backend is healthy:
```bash
docker inspect geovision-langsmith-backend | grep Health
```

### No traces appearing
1. Verify the app service has LangSmith env vars
2. Check app logs: `docker logs geovision-app`
3. Ensure `langsmith` package is installed: `pip show langsmith`

## Resource Usage

The LangSmith stack requires:
- ~2-4 GB RAM
- ~1 GB disk space (grows with traces)

To clean up trace data:
```bash
docker-compose down -v  # Removes all volumes
```

## Comparison: Self-Hosted vs Cloud

| Feature | Self-Hosted | Cloud |
|---------|-------------|-------|
| Setup | 5 containers | Env vars only |
| Data | Local | LangChain servers |
| Cost | Free | Free tier available |
| Internet | Not required | Required |
| Maintenance | You maintain | Managed |

**For most local development**, self-hosted is great because:
- No data leaves your machine
- Works offline
- Full control over retention
- No API key needed
