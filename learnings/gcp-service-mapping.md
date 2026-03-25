# GeoVision Lab → GCP Service Mapping

**Document Purpose:** Direct translation of current GeoVision Lab components to GCP services

**Date:** March 23, 2026

---

## Current Architecture → GCP Mapping

### Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CURRENT → GCP TRANSLATION                             │
├────────────────────────────────┬────────────────────────────────────────────┤
│  Current Component             │  GCP Equivalent                            │
├────────────────────────────────┼────────────────────────────────────────────┤
│  LangGraph (orchestration)     │  Vertex AI Agent Engine OR Keep LangGraph  │
│  Ollama (LLM hosting)          │  Vertex AI Model Garden                    │
│  HuggingFace Embeddings        │  Vertex AI Embeddings API                  │
│  MongoDB (vector store)        │  Vertex AI Vector Search                   │
│  MongoDB (sessions)            │  Cloud SQL (PostgreSQL)                    │
│  FastAPI (API layer)           │  Cloud Run                                 │
│  LangSmith (observability)     │  Cloud Trace + LangSmith (keep)            │
│  DuckDuckGo/Wikipedia (tools)  │  Keep as-is (external APIs)                │
│  Geopy/Nominatim (geocoding)   │  Google Maps Geocoding API                 │
└────────────────────────────────┴────────────────────────────────────────────┘
```

---

## Component-by-Component Mapping

### 1. LLM Models

| Current | GCP Equivalent | Notes |
|---------|----------------|-------|
| **Ollama (local Llama)** | **Vertex AI Model Garden** | Access Gemini, Claude, Llama via managed API |
| **HuggingFace Transformers** | **Vertex AI Model Garden** | Deploy custom models or use pre-built |

#### Vertex AI Model Garden Options

```python
# Current (Ollama)
from langchain_ollama import ChatOllama
llm = ChatOllama(model="llama3.1:8b")

# GCP Equivalent (Vertex AI - Gemini)
from langchain_google_vertexai import ChatVertexAI
llm = ChatVertexAI(model="gemini-2.0-flash-001")

# OR (Vertex AI - Llama via Model Garden)
from langchain_google_vertexai import VertexAIModelGarden
llm = VertexAIModelGarden(
    model_id="meta/llama-3.1-8b-instruct",
    endpoint_id="your-endpoint-id"
)
```

#### Model Comparison

| Model | Use Case | GCP Service | Cost (per 1K tokens) |
|-------|----------|-------------|---------------------|
| Gemini 2.0 Flash | Fast reasoning, agent calls | Vertex AI | $0.075 input / $0.30 output |
| Gemini 2.0 Pro | Complex analysis | Vertex AI | $0.125 input / $0.50 output |
| Claude 3.5 Sonnet | Advanced reasoning | Vertex AI (Model Garden) | $0.30 input / $1.50 output |
| Llama 3.1 70B | Cost-effective | Vertex AI (Model Garden) | ~$0.02 input / $0.08 output |

---

### 2. Embeddings

| Current | GCP Equivalent | Notes |
|---------|----------------|-------|
| **HuggingFaceEmbeddings** | **Vertex AI Embeddings API** | Managed, scalable, no infrastructure |

```python
# Current (HuggingFace)
from langchain_huggingface import HuggingFaceEmbeddings
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

# GCP Equivalent (Vertex AI)
from langchain_google_vertexai import VertexAIEmbeddings
embeddings = VertexAIEmbeddings(
    model_name="text-embedding-004",  # or "text-multilingual-embedding-002"
    project="your-gcp-project"
)
```

#### Embedding Model Comparison

| Model | Dimensions | Max Tokens | Cost |
|-------|-----------|------------|------|
| HuggingFace (MiniLM) | 384 | 512 | Free (self-hosted) |
| Vertex AI Text Embedding | 768 | 2,048 | $0.02 / 1K tokens |
| Vertex AI Multilingual | 768 | 2,048 | $0.02 / 1K tokens |

---

### 3. Vector Store

| Current | GCP Equivalent | Notes |
|---------|----------------|-------|
| **MongoDB Atlas Vector Search** | **Vertex AI Vector Search** | Native GCP, high performance |
| | **Cloud SQL (pgvector)** | PostgreSQL with vector extension |

#### Option A: Vertex AI Vector Search (Recommended for Scale)

```python
# Current (MongoDB)
from langchain_mongodb import MongoDBAtlasVectorSearch

vector_store = MongoDBAtlasVectorSearch.from_connection_string(
    connection_string=settings.MONGODB_URI,
    namespace="geo_vision_lab.documents",
    embedding=embeddings,
    index_name="vector_index"
)

# GCP Equivalent (gem)
from langchain_google_vertexai.vectorstores import VectorSearchVectorStore

vector_store = VectorSearchVectorStore.from_components(
    project_id="your-gcp-project",
    region="us-central1",
    gcs_bucket_name="your-bucket-name",
    endpoint_id="your-vector-search-endpoint-id",
    index_id="your-vector-search-index-id",
    embedding=embeddings
)
```

#### Option B: Cloud SQL with pgvector (Recommended for Simplicity)

```python
# GCP Equivalent (Cloud SQL + pgvector)
from langchain_postgres import PGVector
from sqlalchemy import create_engine

engine = create_engine(
    "postgresql+psycopg://user:pass@/geo_vision_lab?host=/cloudsql/project:region:instance"
)

vector_store = PGVector(
    connection_string="postgresql+psycopg://user:pass@/geo_vision_lab?host=/cloudsql/project:region:instance",
    embedding_function=embeddings,
    collection_name="documents"
)
```

#### Vector Store Comparison

| Feature | MongoDB Atlas | Vertex AI Vector Search | Cloud SQL (pgvector) |
|---------|--------------|------------------------|---------------------|
| Performance | High | **Very High** (10K+ QPS) | Medium |
| Scalability | High | **Very High** (billions) | Medium |
| Cost | $0.17/GB + ops | $0.072/hour + storage | $0.055/hour + storage |
| Setup Complexity | Medium | High | **Low** |
| Best For | General purpose | Large-scale production | MVP/SMB |

---

### 4. Orchestration (LangGraph)

| Current | GCP Equivalent | Notes |
|---------|----------------|-------|
| **LangGraph** | **Keep LangGraph on Cloud Run** OR **Vertex AI Agent Engine** | Both viable |

#### Option A: Keep LangGraph (Recommended)

**Why:** LangGraph is framework-agnostic and works perfectly on GCP. No need to rewrite.

```yaml
# Deploy LangGraph app on Cloud Run (serverless)
gcloud run deploy geo-vision-lab \
  --image us-central1-docker.pkg.dev/project/app/app:latest \
  --platform managed \
  --region us-central1 \
  --memory 4Gi \
  --cpu 2 \
  --timeout 300
```

**Pros:**
- ✅ No code changes required
- ✅ Full LangGraph feature set
- ✅ Serverless scaling
- ✅ Cost-effective

**Cons:**
- ❌ You manage the infrastructure
- ❌ No native GCP agent features

#### Option B: Vertex AI Agent Engine (For Enterprise)

**What it is:** Managed environment for deploying, scaling, and managing AI agents.

```python
# Vertex AI Agent Engine (conceptual - requires migration)
from google.cloud import aiplatform

# Initialize agent
agent_client = aiplatform.AgentClient(
    project="your-project",
    location="us-central1"
)

# Define agent tools (similar to LangGraph tools)
tools = [
    aiplatform.Tool(name="vector_search", function=search_vector_store),
    aiplatform.Tool(name="web_search", function=search_web),
]

# Deploy agent
agent = agent_client.create_agent(
    display_name="geo-vision-agent",
    tools=tools
)
```

**Pros:**
- ✅ Managed infrastructure
- ✅ Native GCP integration
- ✅ Built-in monitoring
- ✅ Enterprise features

**Cons:**
- ❌ Requires significant code rewrite
- ❌ Less flexible than LangGraph
- ❌ Higher cost
- ❌ Vendor lock-in

#### Recommendation: **Keep LangGraph on Cloud Run**

```
┌─────────────────────────────────────────────────────────────┐
│                    RECOMMENDED ARCHITECTURE                  │
│                                                             │
│  Cloud Run (LangGraph)                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Vector    │→ │  Reasoning  │→ │  Reviewer   │        │
│  │   Search    │  │   Agent     │  │   Node      │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│         │                │                │                │
│         ▼                ▼                ▼                │
│  Vertex AI         Vertex AI        Vertex AI             │
│  Vector Search     Model Garden     Model Garden          │
│  (embeddings)      (Gemini/Llama)   (Gemini/Llama)        │
└─────────────────────────────────────────────────────────────┘
```

---

### 5. Database (Sessions & Checkpointing)

| Current | GCP Equivalent | Notes |
|---------|----------------|-------|
| **MongoDB (sessions)** | **Cloud SQL (PostgreSQL)** | For LangGraph checkpointing |
| **MemorySaver** | **PostgresSaver** | Persistent checkpointing |

```python
# Current (MemorySaver - volatile)
from langgraph.checkpoint.memory import MemorySaver
checkpointer = MemorySaver()

# GCP Equivalent (PostgresSaver - persistent)
from langgraph.checkpoint.postgres import PostgresSaver

checkpointer = PostgresSaver.from_conn_string(
    "postgresql+psycopg://user:pass@/geo_vision_lab?host=/cloudsql/project:region:instance"
)
```

---

### 6. Geocoding

| Current | GCP Equivalent | Notes |
|---------|----------------|-------|
| **Geopy/Nominatim** | **Google Maps Geocoding API** | More accurate, rate-limited |

```python
# Current (Geopy - free, rate-limited)
from geopy.geocoders import Nominatim
geolocator = Nominatim(user_agent="geo_vision_lab")
location = geolocator.geocode("Tehran, Iran")

# GCP Equivalent (Google Maps API - paid, higher limits)
from googlemaps import Client
gmaps = Client(key="your-api-key")
geocode_result = gmaps.geocode("Tehran, Iran")
```

#### Cost Comparison

| Service | Rate Limit | Cost |
|---------|-----------|------|
| Nominatim | 1 req/sec | Free |
| Google Maps Geocoding | 50 req/sec | $5 per 1,000 requests |

---

### 7. Search Tools

| Current | GCP Equivalent | Notes |
|---------|----------------|-------|
| **DuckDuckGo** | **Keep as-is** | External API, no GCP equivalent needed |
| **Wikipedia** | **Keep as-is** | External API, no GCP equivalent needed |
| **Vector Search (custom)** | **Vertex AI Search** | For enterprise RAG |

#### Vertex AI Search (Enterprise RAG)

```python
# Current (custom vector search)
vector_store.similarity_search(query, k=3)

# GCP Equivalent (Vertex AI Search - managed RAG)
from google.cloud import discoveryengine

search_client = discoveryengine.SearchServiceClient()
response = search_client.search(
    request={
        "serving_config": "projects/project/locations/global/collections/default_collection/engines/engine-id/servingConfigs/default",
        "query": query,
        "page_size": 3
    }
)
```

---

### 8. Observability

| Current | GCP Equivalent | Notes |
|---------|----------------|-------|
| **LangSmith** | **Keep LangSmith** + **Cloud Trace** | LangSmith for agents, Cloud Trace for infra |

**Recommendation:** Keep LangSmith (already integrated) + add Cloud Trace for infrastructure monitoring.

```python
# Add Cloud Trace alongside LangSmith
from opentelemetry import trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Configure Cloud Trace
provider = trace.TracerProvider()
processor = BatchSpanProcessor(CloudTraceSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
```

---

## Complete GCP Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           GEOVISION LAB ON GCP                                   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                         CLOUD RUN (LangGraph)                           │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │   │
│  │  │   Vector     │→ │  Reasoning   │→ │  Reviewer    │→ │ Location   │ │   │
│  │  │   Search     │  │   Agent      │  │   Node       │  │ Subgraph   │ │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│           │                │                │                     │             │
│           │                │                │                     │             │
│           ▼                ▼                ▼                     ▼             │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌──────────────┐ │
│  │  Vertex AI      │ │  Vertex AI      │ │  Vertex AI      │ │  Google Maps │ │
│  │  Vector Search  │ │  Model Garden   │ │  Model Garden   │ │  Geocoding   │ │
│  │  (embeddings +  │ │  (Gemini 2.0    │ │  (Gemini 2.0    │ │  API         │ │
│  │   documents)    │ │   Flash)        │ │   Pro)          │ │              │ │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘ └──────────────┘ │
│                                                                                 │
│  ┌─────────────────┐ ┌─────────────────┐                                       │
│  │  Cloud SQL      │ │  Cloud Trace    │                                       │
│  │  (PostgreSQL)   │ │  + LangSmith    │                                       │
│  │  - Sessions     │ │  (Observability)│                                       │
│  │  - Checkpoints  │ │                 │                                       │
│  └─────────────────┘ └─────────────────┘                                       │
│                                                                                 │
│  External APIs: DuckDuckGo, Wikipedia (unchanged)                               │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Migration Priority

### Phase 1: Infrastructure (Week 1-2)

| Component | Action | Effort |
|-----------|--------|--------|
| **Cloud Run** | Deploy existing LangGraph app | 2-4 hours |
| **Cloud SQL** | Set up PostgreSQL, migrate checkpointing | 4-6 hours |
| **Secret Manager** | Move API keys from .env | 1-2 hours |

### Phase 2: AI Services (Week 3-4)

| Component | Action | Effort |
|-----------|--------|--------|
| **Vertex AI Model Garden** | Switch from Ollama to Gemini | 2-4 hours |
| **Vertex AI Embeddings** | Replace HuggingFace embeddings | 1-2 hours |
| **Vertex AI Vector Search** OR **Cloud SQL (pgvector)** | Migrate from MongoDB | 8-16 hours |

### Phase 3: Optimization (Week 5+)

| Component | Action | Effort |
|-----------|--------|--------|
| **Google Maps Geocoding** | Replace Geopy for production | 2-4 hours |
| **Cloud Trace** | Add infrastructure tracing | 2-4 hours |
| **Vertex AI Search** | Evaluate for enterprise RAG | 8-16 hours |

---

## Cost Comparison

### Current (Self-Hosted)

| Component | Monthly Cost |
|-----------|-------------|
| Ollama (self-hosted) | $0 (your hardware) |
| HuggingFace (self-hosted) | $0 |
| MongoDB Atlas | $25-100 (M10-M30) |
| **Total** | **$25-100** |

### GCP (Recommended Setup)

| Component | Monthly Cost (Low) | Monthly Cost (Medium) |
|-----------|-------------------|----------------------|
| Cloud Run (2 vCPU, 4GB) | $45 | $450 |
| Cloud SQL (db-custom-2-4096) | $40 | $150 |
| Vertex AI Model Garden (Gemini) | $50 | $500 |
| Vertex AI Embeddings | $10 | $100 |
| Vertex AI Vector Search | $50 | $200 |
| Google Maps Geocoding | $5 | $50 |
| **Total** | **~$200/month** | **~$1,450/month** |

### GCP (Enterprise Setup)

| Component | Monthly Cost |
|-----------|-------------|
| Cloud Run (auto-scale) | $2,000 |
| Cloud SQL (HA, db-custom-8) | $800 |
| Vertex AI Model Garden (Gemini Pro) | $3,000 |
| Vertex AI Vector Search | $1,000 |
| Vertex AI Search (RAG) | $500 |
| **Total** | **~$7,300/month** |

---

## Code Changes Required

### Minimal Changes (Keep LangGraph, Switch to GCP Services)

```python
# app/core/di_nlp.py (update embeddings)
from langchain_google_vertexai import VertexAIEmbeddings

def get_embeddings():
    return VertexAIEmbeddings(
        model_name="text-embedding-004",
        project=settings.GCP_PROJECT_ID
    )

# app/core/di_llm.py (update LLM)
from langchain_google_vertexai import ChatVertexAI

def get_llm():
    return ChatVertexAI(
        model="gemini-2.0-flash-001",
        project=settings.GCP_PROJECT_ID,
        location="us-central1"
    )

# app/services/vector_store.py (update vector store)
from langchain_google_vertexai.vectorstores import VectorSearchVectorStore

def get_vector_store():
    return VectorSearchVectorStore.from_components(
        project_id=settings.GCP_PROJECT_ID,
        region="us-central1",
        gcs_bucket_name=settings.GCP_VECTOR_SEARCH_BUCKET,
        endpoint_id=settings.GCP_VECTOR_SEARCH_ENDPOINT_ID,
        index_id=settings.GCP_VECTOR_SEARCH_INDEX_ID,
        embedding=get_embeddings()
    )
```

---

## Decision Matrix

| Decision | Keep Current | Migrate to GCP | Recommendation |
|----------|-------------|----------------|----------------|
| **LangGraph** | ✅ Self-hosted | ❌ Vertex AI Agent Engine | **Keep LangGraph on Cloud Run** |
| **LLM** | Ollama (local) | Vertex AI Model Garden | **Migrate for production** |
| **Embeddings** | HuggingFace | Vertex AI Embeddings | **Migrate for scale** |
| **Vector Store** | MongoDB | Vertex AI Vector Search / Cloud SQL | **Cloud SQL for MVP, Vertex AI for scale** |
| **Geocoding** | Geopy/Nominatim | Google Maps API | **Migrate for production reliability** |
| **Observability** | LangSmith | LangSmith + Cloud Trace | **Keep LangSmith, add Cloud Trace** |

---

## Summary

### What to Keep
- ✅ **LangGraph** - Deploy on Cloud Run (no rewrite needed)
- ✅ **LangSmith** - Already integrated, works with GCP
- ✅ **DuckDuckGo/Wikipedia** - External APIs, no GCP equivalent needed

### What to Migrate
- 🔄 **Ollama → Vertex AI Model Garden** (Gemini 2.0 Flash/Pro)
- 🔄 **HuggingFace → Vertex AI Embeddings**
- 🔄 **MongoDB → Cloud SQL (pgvector) or Vertex AI Vector Search**
- 🔄 **Geopy → Google Maps Geocoding API** (for production)

### Migration Effort
- **Minimal (Keep LangGraph, switch services):** 20-40 hours
- **Full (Vertex AI Agent Engine):** 80-120 hours (not recommended)

---

## References

- [Vertex AI Model Garden](https://cloud.google.com/vertex-ai/docs/model-garden/overview)
- [Vertex AI Vector Search](https://cloud.google.com/vertex-ai/docs/vector-search/overview)
- [Vertex AI Embeddings](https://cloud.google.com/vertex-ai/docs/generative-ai/embeddings/get-text-embeddings)
- [LangChain Google Vertex AI](https://python.langchain.com/docs/integrations/platforms/google/)
- [Cloud Run Documentation](https://cloud.google.com/run/docs)
