# Hosting GeoVision Lab on Google Cloud Platform (GCP)

**Document Purpose:** Architecture guide for deploying GeoVision Lab to GCP

**Date:** March 23, 2026

---

## Executive Summary

The GeoVision Lab application can be deployed to GCP using a **containerized serverless architecture** with Cloud Run as the primary compute platform. This document outlines four production-ready deployment patterns, recommended GCP services, and implementation strategies.

**Recommended Approach:** Start with **Cloud Run + Artifact Registry + Cloud SQL** for simplicity, then evolve to **Vertex AI + Pub/Sub** for advanced agent workflows.

---

## Deployment Architecture Options

### Option 1: Simple Serverless (Recommended for MVP)

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   GeoVision     │────▶│    FastAPI       │────▶│  GCP Cloud Run  │
│   LangGraph     │     │    (LangServe)   │     │  (Serverless)   │
│   Application   │     │                  │     │                 │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                    ┌─────────────────────────────────────┼─────────────────────────────────────┐
                    │                                     │                                     │
                    ▼                                     ▼                                     ▼
           ┌─────────────────┐                  ┌─────────────────┐                  ┌─────────────────┐
           │  Cloud SQL      │                  │  Artifact       │                  │  Secret         │
           │  (PostgreSQL)   │                  │  Registry       │                  │  Manager        │
           │  - Sessions     │                  │  - Docker Image │                  │  - API Keys     │
           │  - Checkpoints  │                  │                 │                  │  - Config       │
           └─────────────────┘                  └─────────────────┘                  └─────────────────┘
```

**Best For:** MVP, small-scale deployments, cost-conscious projects

**GCP Services:**
| Service | Purpose | Pricing Model |
|---------|---------|---------------|
| **Cloud Run** | Application hosting | Pay-per-request ($0.0000025/vCPU-second) |
| **Artifact Registry** | Docker image storage | $0.10/GB/month |
| **Cloud SQL (PostgreSQL)** | Persistent storage | $0.055/hour + storage |
| **Secret Manager** | API key management | $0.06/secret/month |
| **Cloud Logging** | Application logs | Free tier: 50GB/month |

**Estimated Monthly Cost (Low Traffic):** $50-150/month

---

### Option 2: Multi-Agent with Human-in-the-Loop (Production)

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    USER INTERFACE                                        │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              CLOUD RUN (FastAPI + LangGraph)                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                    │
│  │   Vector    │→ │  Reasoning  │→ │  Reviewer   │→ │  Location   │                    │
│  │   Search    │  │   Agent     │  │   Node      │  │  Subgraph   │                    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘                    │
└─────────────────────────────────────────────────────────────────────────────────────────┘
         │                    │                    │                    │
         │                    │                    ▼                    │
         │                    │         ┌─────────────────────┐        │
         │                    │         │   HUMAN REVIEW      │        │
         │                    │         │   (Approval Node)   │        │
         │                    │         └──────────┬──────────┘        │
         │                    │                    │                    │
         ▼                    ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Vertex AI      │  │  Cloud SQL      │  │  Pub/Sub        │  │  Cloud          │
│  Search         │  │  - Sessions     │  │  - Notifications│  │  Functions      │
│  - RAG          │  │  - Checkpoints  │  │  - Events       │  │  - Slack/Email  │
│  - Documents    │  └─────────────────┘  └────────┬────────┘  │     Triggers    │
└─────────────────┘                                │         └─────────────────┘
                                                   │
                                                   ▼
                                          ┌─────────────────┐
                                          │  Human Analyst  │
                                          │  (Approval UI)  │
                                          └─────────────────┘
```

**Best For:** Production deployments requiring human oversight, enterprise use

**Additional GCP Services:**
| Service | Purpose | Pricing |
|---------|---------|---------|
| **Vertex AI Search** | RAG-based document retrieval | $0.05/1000 queries |
| **Pub/Sub** | Event-driven notifications | $0.04/100K messages |
| **Cloud Functions** | Notification triggers | $0.40/1M invocations |
| **Firebase Auth** | User authentication | Free tier: 10K/month |

**Estimated Monthly Cost (Medium Traffic):** $300-800/month

---

### Option 3: Advanced Agentic with Vertex AI (Enterprise)

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           VERTEX AI AGENT ECOSYSTEM                                  │
│                                                                                     │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐              │
│  │  Vertex AI       │    │  Vertex AI       │    │  Vertex AI       │              │
│  │  Agent Engine    │◀──▶│  Reasoning       │◀──▶│  Model Garden    │              │
│  │  (Orchestration) │    │  Engine          │    │  - Gemini Flash  │              │
│  │                  │    │  (Long-running)  │    │  - Gemini Pro    │              │
│  └────────┬─────────┘    └──────────────────┘    └──────────────────┘              │
│           │                                                                          │
│           ▼                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐        │
│  │                    LangGraph Multi-Agent Workflow                       │        │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐               │        │
│  │  │Researcher│→ │  Writer  │→ │Verifier  │→ │(loop back)│              │        │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘               │        │
│  └─────────────────────────────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  BigQuery       │  │  Cloud Storage  │  │  Cloud Trace    │  │  Cloud SQL      │
│  - Analytics    │  │  - Documents    │  │  - Tracing      │  │  - State        │
│  - Financial    │  │  - Media        │  │  - Debugging    │  │  - Sessions     │
└─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘
```

**Best For:** Enterprise-scale, complex multi-agent workflows, long-running reasoning

**Additional GCP Services:**
| Service | Purpose | Pricing |
|---------|---------|---------|
| **Vertex AI Agent Engine** | Managed agent orchestration | Custom pricing |
| **Vertex AI Reasoning Engine** | Long-running reasoning loops | Custom pricing |
| **Vertex AI Model Garden** | Model selection (Gemini Flash/Pro) | Per-token pricing |
| **BigQuery** | Large-scale data processing | $5/TB queried |
| **Cloud Trace** | Distributed tracing | $0.50/100K spans |
| **Cloud Storage** | Document/media storage | $0.02/GB/month |

**Estimated Monthly Cost (High Traffic):** $1,000-5,000+/month

---

### Option 4: Event-Driven Multimodal (Advanced)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                           EVENT-DRIVEN ARCHITECTURE                               │
│                                                                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                     │
│  │  Cloud       │     │  Cloud       │     │  Cloud       │                     │
│  │  Storage     │────▶│  Functions   │────▶│  Run         │                     │
│  │  (GCS)       │     │  (Trigger)   │     │  (Process)   │                     │
│  │  - Images    │     │              │     │              │                     │
│  │  - Videos    │     │              │     │              │                     │
│  └──────────────┘     └──────────────┘     └──────┬───────┘                     │
│                                                   │                               │
│                                                   ▼                               │
│                                          ┌─────────────────┐                     │
│                                          │  Pub/Sub        │                     │
│                                          │  - Events       │                     │
│                                          │  - Topics       │                     │
│                                          └────────┬────────┘                     │
│                                                   │                               │
│                    ┌──────────────────────────────┼──────────────────────────┐   │
│                    │                              │                          │   │
│                    ▼                              ▼                          ▼   │
│           ┌─────────────────┐          ┌─────────────────┐         ┌──────────────┐│
│           │  Cloud Run      │          │  Cloud Run      │         │  Cloud       ││
│           │  (Vision Agent) │          │  (Text Agent)   │         │  Functions   ││
│           │  - Image        │          │  - NLP          │         │  (Notify)    ││
│           │    Analysis     │          │  - Reasoning    │         │              ││
│           └─────────────────┘          └─────────────────┘         └──────────────┘│
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Best For:** Multimodal processing (images + text), supply chain intelligence, automated analysis

---

## Recommended GCP Services for GeoVision Lab

### Core Infrastructure (Required)

| Service | Purpose | Configuration |
|---------|---------|---------------|
| **Cloud Run** | Primary compute | 2 vCPU, 4GB RAM, 300s timeout |
| **Artifact Registry** | Container storage | Regional (us-central1) |
| **Cloud SQL** | PostgreSQL for sessions | db-custom-2-4096, 25GB SSD |
| **Secret Manager** | API credentials | Standard tier |
| **Cloud Logging** | Application logs | Default |
| **Cloud Monitoring** | Metrics/alerting | Default |

### Enhanced Features (Recommended)

| Service | Purpose | When to Add |
|---------|---------|-------------|
| **Vertex AI Search** | RAG for document retrieval | When vector search needs scaling |
| **Pub/Sub** | Event notifications | Human-in-the-loop workflows |
| **Cloud Functions** | Notification triggers | Slack/email alerts |
| **Firebase Auth** | User authentication | Multi-user deployment |
| **Cloud Trace** | Distributed tracing | Production debugging |
| **LangSmith** | Agent observability | Development + production |

### Advanced Capabilities (Future)

| Service | Purpose | When to Add |
|---------|---------|-------------|
| **Vertex AI Agent Engine** | Managed orchestration | Enterprise scale |
| **BigQuery** | Analytics processing | Large-scale data analysis |
| **Cloud Storage** | Media file storage | Image/video analysis |
| **Vertex AI Model Garden** | Model selection | Multi-model workflows |

---

## Implementation Guide

### Phase 1: Basic Cloud Run Deployment

#### Step 1: Prepare Dockerfile

```dockerfile
# Dockerfile (already exists - verify configuration)
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port (Cloud Run requires PORT environment variable)
ENV PORT=8080
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# Run with uvicorn
CMD exec uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
```

#### Step 2: Configure Environment Variables

```bash
# .env.gcp (add to .gitignore)
# GCP Configuration
GCP_PROJECT_ID=your-project-id
GCP_REGION=us-central1

# Database
DATABASE_URL=postgresql+psycopg://user:password@/geo-vision-lab?host=/cloudsql/project:region:instance

# Secret Manager (reference by secret name)
OPENAI_API_KEY=projects/PROJECT_ID/secrets/openai-api-key/versions/latest
MONGODB_URI=projects/PROJECT_ID/secrets/mongodb-uri/versions/latest

# Application
ENVIRONMENT=production
LOG_LEVEL=INFO
```

#### Step 3: Build and Push Docker Image

```bash
# Set variables
PROJECT_ID="your-project-id"
REGION="us-central1"
REPO_NAME="geo-vision-lab"
IMAGE_NAME="app"
IMAGE_TAG="latest"

# Create Artifact Registry (one-time)
gcloud artifacts repositories create $REPO_NAME \
  --repository-format=docker \
  --location=$REGION \
  --description="GeoVision Lab Docker images"

# Authenticate Docker
gcloud auth configure-docker $REGION-docker.pkg.dev

# Build and push
docker build -t $REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME:$IMAGE_TAG .
docker push $REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME:$IMAGE_TAG
```

#### Step 4: Deploy to Cloud Run

```bash
# Deploy to Cloud Run
gcloud run deploy geo-vision-lab \
  --image $REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME:$IMAGE_TAG \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --memory 4Gi \
  --cpu 2 \
  --timeout 300 \
  --min-instances 0 \
  --max-instances 10 \
  --set-env-vars ENVIRONMENT=production,LOG_LEVEL=INFO \
  --set-secrets OPENAI_API_KEY=openai-api-key:latest,MONGODB_URI=mongodb-uri:latest \
  --add-cloudsql-instances $PROJECT_ID:$REGION:geo-vision-lab-db
```

#### Step 5: Set Up Cloud SQL

```bash
# Create Cloud SQL instance
gcloud sql instances create geo-vision-lab-db \
  --database-version=POSTGRES_15 \
  --tier=db-custom-2-4096 \
  --region=$REGION \
  --storage-size=25GB \
  --storage-type=SSD \
  --root-password=secure-root-password

# Create database
gcloud sql databases create geo_vision_lab \
  --instance=geo-vision-lab-db

# Create user
gcloud sql users create app_user \
  --instance=geo-vision-lab-db \
  --password=secure-password
```

#### Step 6: Configure Checkpointer

```python
# app/core/di_database.py (update for production)
from langgraph.checkpoint.postgres import PostgresSaver

def get_checkpointer():
    """Get production checkpointer (PostgreSQL)."""
    if settings.ENVIRONMENT == "production":
        return PostgresSaver.from_conn_string(settings.DATABASE_URL)
    else:
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()
```

---

### Phase 2: Add Observability

#### Step 1: Enable LangSmith

```bash
# Add to Secret Manager
gcloud secrets create langchain-api-key \
  --replication-policy="automatic"
  
echo -n "your-langsmith-api-key" | \
  gcloud secrets versions add langchain-api-key --data-file=-
```

```python
# app/core/langsmith_config.py (already exists - verify)
import os
from langchain_core.callbacks import CallbackManager
from langchain_community.callbacks.manager import LangChainTracer

def get_langsmith_tracer():
    """Configure LangSmith tracing."""
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
    os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY")
    os.environ["LANGCHAIN_PROJECT"] = "geo-vision-lab"
    
    tracer = LangChainTracer()
    return CallbackManager([tracer])
```

#### Step 2: Enable Cloud Trace

```python
# Add to requirements.txt
google-cloud-trace==2.15.0
opentelemetry-exporter-gcp-trace==1.6.0

# app/main.py
from opentelemetry import trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

def setup_cloud_trace():
    """Configure Google Cloud Trace."""
    provider = TracerProvider()
    processor = BatchSpanProcessor(CloudTraceSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
```

---

### Phase 3: Human-in-the-Loop with Pub/Sub

#### Step 1: Create Pub/Sub Topics

```bash
# Create topic for human review
gcloud pubsub topics create human-review-topic

# Create subscription for notification service
gcloud pubsub subscriptions create human-review-sub \
  --topic=human-review-topic
```

#### Step 2: Update Graph with Interrupts

```python
# app/agents/graph.py (add interrupt)
from langgraph.graph import StateGraph, Interrupt

def get_graph():
    checkpointer = get_checkpointer()
    workflow = StateGraph(AgentState)
    
    # ... add nodes ...
    
    # Add interrupt before location extraction for human review
    workflow.add_node(NODE_LOCATION_EXTRACTOR, run_location_subgraph)
    workflow.add_edge(NODE_REVIEWER, NODE_LOCATION_EXTRACTOR)
    
    # Compile with interrupt
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=[NODE_LOCATION_EXTRACTOR]
    )

# API endpoint to resume with approval
@app.post("/api/chat/{thread_id}/approve")
async def approve_location(thread_id: str, locations: List[Location]):
    """Approve extracted locations and continue execution."""
    graph = get_graph()
    
    # Update state with approved locations
    config = {"configurable": {"thread_id": thread_id}}
    
    # Resume from interrupt
    result = await graph.ainvoke(
        {"extracted_locations": locations},
        config=config
    )
    
    return result
```

#### Step 3: Create Cloud Function for Notifications

```python
# functions/notify_review/main.py
import functions_framework
from google.cloud import pubsub_v1
import requests

@functions_framework.cloud_event
def notify_review(cloud_event):
    """Send notification when human review is needed."""
    message = cloud_event.data["message"]
    data = message.get("data", {})
    
    thread_id = data.get("thread_id")
    query = data.get("query")
    
    # Send Slack notification
    slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
    payload = {
        "text": f"🔍 GeoVision Lab Review Required\n"
                f"Query: {query}\n"
                f"Thread: {thread_id}\n"
                f"Review URL: https://your-app.run.app/review/{thread_id}"
    }
    
    requests.post(slack_webhook, json=payload)
```

```bash
# Deploy Cloud Function
gcloud functions deploy notify-review \
  --gen2 \
  --runtime=python311 \
  --region=$REGION \
  --source=functions/notify_review \
  --entry-point=notify_review \
  --trigger-topic=human-review-topic \
  --set-env-vars SLACK_WEBHOOK_URL=your-webhook-url
```

---

## Production Checklist

### Security
- [ ] Enable HTTPS-only traffic
- [ ] Configure Cloud Armor for DDoS protection
- [ ] Set up VPC Service Controls
- [ ] Enable Identity-Aware Proxy (IAP) for admin endpoints
- [ ] Rotate secrets regularly (90-day rotation)
- [ ] Configure CORS properly
- [ ] Implement rate limiting

### Monitoring
- [ ] Set up Cloud Monitoring dashboards
- [ ] Configure alerting policies (error rate, latency, CPU)
- [ ] Enable Cloud Logging with structured logs
- [ ] Set up LangSmith for agent tracing
- [ ] Monitor Cloud SQL connections

### Reliability
- [ ] Configure Cloud SQL high availability
- [ ] Set up automated backups (daily)
- [ ] Implement retry logic for API calls
- [ ] Add health check endpoints
- [ ] Configure dead letter queues for Pub/Sub

### Cost Optimization
- [ ] Set Cloud Run max instances
- [ ] Use committed use discounts for Cloud SQL
- [ ] Enable Cloud SQL auto-scaling
- [ ] Monitor BigQuery query costs
- [ ] Set up billing alerts

---

## Migration Path

### Current → Phase 1 (Week 1-2)
1. Update Dockerfile for Cloud Run
2. Create GCP project and enable APIs
3. Set up Cloud SQL
4. Deploy to Cloud Run
5. Test with production traffic

### Phase 1 → Phase 2 (Week 3-4)
1. Enable LangSmith tracing
2. Add Cloud Trace integration
3. Switch to PostgreSQL checkpointer
4. Set up monitoring dashboards

### Phase 2 → Phase 3 (Week 5-8)
1. Design human-in-the-loop workflow
2. Set up Pub/Sub topics
3. Create Cloud Functions for notifications
4. Add interrupt logic to graph
5. Build review UI

### Phase 3 → Phase 4 (Month 3+)
1. Evaluate Vertex AI migration
2. Implement multi-agent architecture
3. Add BigQuery analytics
4. Enable multimodal processing

---

## Cost Estimation

### Scenario 1: Low Traffic (MVP)
- **Users:** 100/day
- **Queries:** 500/day
- **Avg Response Time:** 5 seconds

| Service | Monthly Cost |
|---------|-------------|
| Cloud Run (2 vCPU, 4GB) | $45 |
| Cloud SQL (db-custom-2-4096) | $40 |
| Artifact Registry | $1 |
| Secret Manager | $3 |
| Cloud Logging | Free |
| **Total** | **~$90/month** |

### Scenario 2: Medium Traffic (Production)
- **Users:** 1,000/day
- **Queries:** 5,000/day
- **Avg Response Time:** 5 seconds

| Service | Monthly Cost |
|---------|-------------|
| Cloud Run (auto-scale 0-10 instances) | $450 |
| Cloud SQL (db-custom-4-8192 HA) | $150 |
| Vertex AI Search | $50 |
| Pub/Sub | $10 |
| Cloud Functions | $5 |
| Cloud Trace | $25 |
| **Total** | **~$690/month** |

### Scenario 3: High Traffic (Enterprise)
- **Users:** 10,000/day
- **Queries:** 50,000/day
- **Multi-agent workflows**

| Service | Monthly Cost |
|---------|-------------|
| Cloud Run (auto-scale 0-50 instances) | $2,250 |
| Cloud SQL (db-custom-8-16384 HA) | $400 |
| Vertex AI Agent Engine | $1,500 |
| Vertex AI Search | $500 |
| BigQuery | $200 |
| Cloud Storage | $50 |
| **Total** | **~$4,900/month** |

---

## Troubleshooting

### Common Issues

#### 1. Cloud Run Timeout
**Problem:** Requests timeout after 300 seconds  
**Solution:** 
- Increase timeout: `--timeout 600`
- Optimize LLM calls (reduce model calls, use streaming)
- Add progress indicators for long operations

#### 2. Cold Start Latency
**Problem:** First request takes 10+ seconds  
**Solution:**
- Set `--min-instances 1` (costs ~$20/month)
- Use Cloud Run requests for keep-alive
- Optimize container size (multi-stage builds)

#### 3. Database Connection Errors
**Problem:** Can't connect to Cloud SQL  
**Solution:**
- Verify Cloud SQL Proxy sidecar
- Check IAM permissions
- Validate connection string format

#### 4. Memory Issues
**Problem:** OOM kills  
**Solution:**
- Increase memory: `--memory 8Gi`
- Profile memory usage
- Optimize vector store loading

---

## References

- [Deploying LangGraph on GCP Cloud Run](https://smarttechnotes.com/langgraph-cloudrun/)
- [Mastering Orchestration: LangGraph + LangChain on Google Cloud](https://www.linkedin.com/pulse/mastering-orchestration-langgraph-langchain-google-cloud-ben-hultin-amcuc)
- [GCP Architecture Patterns for AI Agents](https://cloud.google.com/architecture/ai-agents)
- [LangGraph Documentation](https://docs.langchain.com/oss/python/langgraph/overview)
- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Vertex AI Agent Engine](https://cloud.google.com/vertex-ai/docs/agent-engine)

---

## Next Steps

1. **Immediate (This Week):**
   - Create GCP project
   - Enable required APIs
   - Test basic Cloud Run deployment

2. **Short-term (2-4 Weeks):**
   - Set up Cloud SQL
   - Enable LangSmith
   - Configure monitoring

3. **Medium-term (1-2 Months):**
   - Implement human-in-the-loop
   - Add Pub/Sub notifications
   - Build review UI

4. **Long-term (3+ Months):**
   - Evaluate Vertex AI migration
   - Implement multi-agent architecture
   - Add advanced analytics
