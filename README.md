<h1 align="center">GeoVision Lab</h1>

<p align="center">
  <em>Local-first RAG platform for geopolitical analysis — fully containerized, privacy-first</em>
</p>

<p align="center">
  <strong>📝 This is a demo / learning project</strong>
</p>

<p align="center">
  <img src="static/demo_presentation.gif" alt="GeoVision Lab Demo" width="900" />
</p>


## Overview

GeoVision Lab is a local-first RAG (Retrieval-Augmented Generation) platform for geopolitical intelligence analysis. It ingests documents (PDF, Markdown), vectorizes them using semantic embeddings, and lets you query them through an AI-powered chat interface — all running entirely within Docker without cloud dependencies.

### Key Features

- **Multi-Agent AI** — Worker + Critic + Location Extractor architecture with autonomous tool selection
- **Hybrid Search** — Vector search (archival) + Web search (live events)
- **Automatic Map Rendering** — Hugging Face NER + Multi-candidate geocoding + LLM disambiguation
- **3-Panel UI** — Reasoning Chain | Text Result | Maps Result with resizable panels
- **Conversational Memory** — Context-aware follow-up questions via LangGraph MemorySaver
- **Privacy-First** — All inference runs locally — no data leaves your machine
- **Observability** — Grafana + Loki logging, Dozzle real-time monitoring
- **Model Switching** — Dynamic Qwen 3.5 selection (9B/4B) at runtime
- **GPU Status Indicator** — Real-time display of GPU acceleration status

### Test Data Included

The platform ships with sample fantasy lore about the **DuckyDucks and FrogyFrogs** of Quackswamp — a rich test dataset for validating vector search capabilities.

---

## Architecture

### Main Agent Graph

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           GEO-VISION-LAB AGENT FLOW                          │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────────┐
                              │   USER QUERY     │
                              └────────┬─────────┘
                                       │
                                       ▼
                         ┌─────────────────────────┐
                         │   VECTOR_SEARCH_NODE    │
                         │   (Archival RAG Lookup) │
                         └────────────┬────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────┐
                    │      AGENT_NODE (Worker)        │
                    │  - Receives vector search results│
                    │  - Can call tools iteratively   │
                    │  - Builds response with reasoning│
                    └────────────┬────────────────────┘
                                 │
               ┌─────────────────┴─────────────────┐
               │                                   │
               ▼                                   ▼
    ┌─────────────────────┐           ┌─────────────────────┐
    │   TOOL_NODE         │           │  REVIEWER_NODE      │
    │  - DuckDuckGo       │           │  (QA Critic LLM)    │
    │  - Wikipedia        │           │  - Validates output │
    │  - Time lookup      │           │  - Checks constraints│
    └─────────┬───────────┘           └──────────┬──────────┘
              │                                  │
              │         ┌────────────────────────┤
              │         │                        │
              │         │ (if invalid, <3 tries) │
              │         │                        │
              │         ▼                        ▼
              │   ┌─────────────┐      ┌─────────────────────┐
              │   │   Retry     │      │ LOCATION_EXTRACTOR  │
              │   │   Agent     │      │   (Sub-Graph)       │
              │   └─────────────┘      └──────────┬──────────┘
              │                                   │
              └───────────────────────────────────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │  FINAL OUTPUT │
                              │  + Locations  │
                              └───────────────┘
```

### Location Processing Sub-Graph (Phase 1 - Current)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      LOCATION_SUBGRAPH (Internal Flow)                       │
└─────────────────────────────────────────────────────────────────────────────┘

    ┌──────────────────────┐
    │  user_query          │
    │  assistant_response  │
    └──────────┬───────────┘
               │
               ▼
    ┌─────────────────────────┐
    │  PARSE_QUERY_LOCS       │◄─── Future: Extract target locations from query
    │  (Placeholder)          │
    └──────────┬──────────────┘
               │
               ▼
    ┌─────────────────────────┐
    │  EXTRACT_NER_LOCS       │
    │  - Hugging Face NER     │
    │  - Nominatim Geocoding  │
    │  - Multi-candidate fetch│
    └──────────┬──────────────┘
               │
               ▼
    ┌─────────────────────────┐
    │  GEOCODE_WITH_CTX       │◄─── Future: Bias geocoding with query context
    │  (Passthrough)          │
    └──────────┬──────────────┘
               │
               ▼
    ┌─────────────────────────┐
    │  FILTER_RELEVANCE       │
    │  - LLM prioritization   │
    │  - Relevance scoring    │
    │  - Exclusion reasoning  │
    └──────────┬──────────────┘
               │
               ▼
    ┌─────────────────────────┐
    │  final_locations        │
    │  (sorted by relevance)  │
    └─────────────────────────┘
```

### Location Prioritization Detail

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FILTER_RELEVANCE (LLM Decision Process)                   │
└─────────────────────────────────────────────────────────────────────────────┘

    Input: All geocoded candidates (may have multiple per location name)

    ┌─────────────────────────────────────────────────────────────────────┐
    │  For EACH location group:                                           │
    │  1. Select BEST candidate (or mark excluded with candidate_index=-1)│
    │  2. Assign relevance score (0.0 to 1.0)                             │
    │  3. Provide reason (REQUIRED for debugging)                         │
    └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │  Relevance Criteria:                                                │
    │  - PRIMARY (1.0):   Main subject of query/response                  │
    │  - SECONDARY (0.7): Important related (capitals, major cities)      │
    │  - TERTIARY (0.4):  Mentioned but not central                       │
    │  - EXCLUDED (0.0):  Wrong country, ambiguous, incidental            │
    └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    Output: All locations with relevance + reason (sorted desc, max 5)
            - Included: relevance > 0.0
            - Excluded: relevance = 0.0, excluded: true, reason provided
```

### System Architecture

```mermaid
%%{init: {'theme': 'dark'}}%%
graph TB
    subgraph User["User Interface"]
        UI["Web Interface<br/>(3-Panel UI + Leaflet)"]
    end

    subgraph Backend["Backend Services"]
        API["FastAPI<br/>(REST + Streaming)"]
        AGENT["LangGraph Agent<br/>(Worker + Critic)"]
        LOC["Location Sub-Graph<br/>(NER + Geocode + Filter)"]
    end

    subgraph Data["Data Layer"]
        MDB[("MongoDB 8.2+<br/>(Vector Search)")]
        OL["Ollama<br/>(Qwen 3.5 LLM)"]
    end

    subgraph Tools["External Tools"]
        WEB["DuckDuckGo<br/>(Live Search)"]
        WIKI["Wikipedia API"]
        NOM["Nominatim<br/>(Geocoding)"]
    end

    UI --> API
    API --> AGENT
    AGENT --> MDB
    AGENT --> OL
    AGENT --> WEB
    AGENT --> WIKI
    AGENT --> LOC
    LOC --> NOM
```

For detailed technology decisions, see [Technology Choices](TECHNOLOGY.md).

For agent orchestration details, see [Agent Workflow](AGENT_WORKFLOW.md).

---

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Optional: NVIDIA GPU + Container Toolkit for accelerated inference

#### GPU Acceleration (Recommended)

```bash
# Install NVIDIA drivers and Container Toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Verify GPU visibility
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### 1. Add Your Documents

Place PDF files into `./documents/pdf/` for the RAG archival pipeline.

### 2. Launch the Stack

```bash
docker compose up --build
```

This orchestrates:
- MongoDB with vector search index
- Ollama pulling the Qwen 3.5 LLM
- Document ingestion and chunking
- FastAPI backend with streaming
- Grafana + Loki observability stack

### 3. Access the Dashboards

| Service | URL | Credentials |
|---------|-----|-------------|
| Web Interface | [localhost:8000](http://localhost:8000) | — |
| MongoDB Browser | [localhost:8081](http://localhost:8081) | `admin` / `geovision` |
| Container Logs | [localhost:9999](http://localhost:9999) | — |
| Grafana Dashboards | [localhost:3000](http://localhost:3000) | `admin` / `geovision` |

**Optional: LangSmith Tracing** - See [docs/langsmith.md](docs/langsmith.md) for setup.

---

## Model Switching

GeoVision Lab supports **dynamic switching between different Qwen 3.5 LLM models**:

| Model | Size | Speed | Quality | Best For |
|-------|------|-------|---------|----------|
| **Qwen 3.5 9B** | 9B | Slower | Highest | Complex analysis, detailed reports |
| **Qwen 3.5 4B** | 4B | Balanced | High | Default — general purpose |

**To switch models:**
1. Open the Web Interface at [localhost:8000](http://localhost:8000)
2. Use the model selector dropdown above the chat input
3. Selection takes effect immediately

The QA/Reviewer model remains fixed at `Qwen 2.5:0.5b` for consistent constraint checking.

---

## Testing & Validation

### Quick Test with Included Fantasy Data

The platform includes a sample document (`documents/fantasy.md`) about the **DuckyDucks and FrogyFrogs** of Quackswamp. Use these test queries:

| Test Query | Expected Behavior |
|------------|-------------------|
| *"Where is the secret base of the DuckyDucks located?"* | Should retrieve Antarctica reference |
| *"Tell me about the War of Ripples"* | Should return details about the 6-year war (1247-1253) |
| *"What are the characteristics of FrogyFrogs?"* | Should list emerald skin, leaping ability, water magic |
| *"Who signed the Treaty of Ripples?"* | Should mention the peace treaty on a lily pad |
| *"What is the Prophecy of the Golden Tadpole?"* | Should retrieve the unity prophecy |

### Validation Checklist

1. **Ingestion** — Check Dozzle logs for `geovision-ingest` document loading
2. **Vector Search** — Ask about DuckyDucks; watch `vector_search` tool trigger
3. **Live Search** — Ask about breaking news; verify `duckduckgo_search` execution
4. **Time Awareness** — Ask "What exact date and time is it right now?"
5. **Map Rendering** — Ask about any real location (e.g., "Tell me about Paris"); verify automatic map appears in Maps panel
6. **Model Switching** — Switch between Qwen variants; observe quality/speed differences
7. **3-Panel UI** — Verify Reasoning Chain shows workflow steps, Text Result shows response, Maps Result shows geocoded locations
8. **Resizable Panels** — Drag the vertical handles between panels to adjust widths
9. **GPU Status** — Check the top panel shows correct GPU status (Active/Standby/CPU Only)

---

## Project Structure

```
geo-vision-lab/
├── app/                    # Core application package
│   ├── agents/             # LangGraph architecture & tools
│   ├── api/routes/         # FastAPI REST endpoints
│   ├── core/               # Global settings & config
│   ├── ingestion/          # RAG data processing pipeline
│   └── services/           # LLM & MongoDB connectors
├── static/                 # Vanilla JS / CSS Web Interface
├── documents/
│   ├── pdf/                # Your source PDFs
│   └── fantasy.md          # Sample test data
├── monitoring/             # Grafana, Loki, Promtail config
├── docs/                   # Additional documentation
├── migrations/             # Database migration scripts
├── docker-compose.yml      # Full stack orchestration
├── Dockerfile              # Application container
└── requirements.txt        # Python dependencies
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [Technology Choices](docs/technology.md) | Detailed rationale for each technology decision |
| [Agent Workflow](docs/agent_workflow.md) | Deep dive into multi-agent orchestration |
| [Agent Learnings](docs/learnings.md) | Technical insights on reasoning LLMs |
| [Debugging Guide](docs/debugging.md) | Troubleshooting common issues |
| [MongoDB Vector Search](docs/mongodb_vector_search.md) | Vector search implementation details |

---

## Tech Stack Summary

| Layer | Technology |
|-------|------------|
| **LLM Inference** | Ollama + Qwen 3.5 (9B/4B) |
| **QA/Review LLM** | Ollama + Qwen 2.5:0.5b |
| **NER/Location** | Hugging Face (dslim/bert-base-NER) + LLM disambiguation |
| **Embeddings** | all-MiniLM-L6-v2 (384 dims) |
| **Vector Database** | MongoDB 8.2+ Vector Search |
| **Agent Framework** | LangGraph + MemorySaver |
| **Backend API** | FastAPI + uvicorn |
| **Frontend UI** | Vanilla JS + Leaflet.js (3-Lane) |
| **Testing** | PyTest + Testcontainers |
| **CI/CD** | GitHub Actions |
| **Observability** | Grafana + Loki + Dozzle |
| **Tracing & Debugging** | LangSmith (self-hosted) |
| **Containerization** | Docker + Docker Compose |

---