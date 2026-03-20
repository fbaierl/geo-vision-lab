# LangSmith Cloud Setup

LangSmith is a debugging and monitoring platform for LLM applications. It provides:

- **Tracing** - See every LLM call, tool invocation, and reasoning step
- **Debugging** - Inspect prompts, responses, and token usage
- **Testing** - Create test suites and evaluate model performance
- **Analytics** - Track latency, costs, and usage patterns

## Quick Setup

### 1. Get a Free API Key

1. Visit [smith.langchain.com](https://smith.langchain.com)
2. Sign up / log in
3. Click your profile → **Settings** → **API Keys**
4. Click **Create API Key**

### 2. Configure Your Environment

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` and add your API key:

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_...your-key-here
LANGSMITH_PROJECT=geo-vision-lab
```

### 3. Restart the Stack

```bash
docker-compose down
docker-compose up -d
```

### 4. View Your Traces

1. Make a query at [localhost:8000](http://localhost:8000)
2. Visit [smith.langchain.com](https://smith.langchain.com)
3. Select the `geo-vision-lab` project
4. See real-time traces of all LLM operations

## What Gets Traced

- **LLM Calls** - Prompts, completions, token counts, latency
- **Tool Usage** - Vector search, web search, geocoding
- **Agent Reasoning** - Each step of the LangGraph workflow
- **Location Extraction** - NER results and disambiguation
- **Validation** - Reviewer model feedback

## Disable Tracing

To disable (e.g., for offline work):

1. Set `LANGSMITH_TRACING=false` in `.env`
2. Or remove the LangSmith env vars from `docker-compose.yml`

## Privacy Note

When enabled, trace data is sent to LangChain's cloud servers. This includes:
- Prompts sent to LLMs
- LLM responses
- Tool inputs/outputs

**Do not enable** if you're processing sensitive or classified data.

## Pricing

- **Free Tier**: 1,000 traces/month (sufficient for development)
- **Plus**: $100/month for 10,000 traces
- **Pro**: Custom pricing

See [langchain.com/pricing](https://www.langchain.com/pricing) for details.

## Alternative: Open Source

For fully local tracing, consider:
- [LangFuse](https://langfuse.com) - Open source, self-hostable
- [Arize Phoenix](https://arize.com/phoenix) - Local LLM observability

These require additional Docker containers but keep all data local.
