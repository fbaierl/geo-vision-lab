# MongoDB Vector Search Setup

> **Related Documentation:**
> - [Technology Choices](../TECHNOLOGY.md) — Why MongoDB for vector search
> - [Agent Workflow](../AGENT_WORKFLOW.md) — How vector search is used by agents
> - [README](../README.md) — Quick start guide

---

GeoVision Lab uses **MongoDB 8.2+ Vector Search** for semantic document retrieval. This guide explains how the vector search index is created and managed.

## Collections

| Collection | Purpose |
|------------|---------|
| `vector_documents` | Stores document chunks with vector embeddings |
| `_ingestion_state` | Tracks ingestion metadata (hash, timestamp, document count) |

## How it works

- On startup, the app container runs `python -m app.services.setup_mongodb` **before** starting the server. This creates the vector search index if it doesn't exist.
- The vector search index is created using MongoDB's native `$vectorSearch` aggregation stage with cosine similarity.
- Documents are stored with an `embedding` field containing a 384-dimensional vector (from `all-MiniLM-L6-v2`).

## Vector Index Configuration

The vector search index is configured with:

| Parameter | Value | Description |
|-----------|-------|-------------|
| **Index Name** | `vector_index` | Name of the search index |
| **Vector Path** | `embedding` | Field containing the vector |
| **Dimensions** | 384 | Size of embedding vectors |
| **Similarity** | `cosine` | Cosine similarity for nearest neighbor search |
| **numCandidates** | 100 | Number of candidates for approximate nearest neighbor search |

## Manual Index Management

You can manage the vector search index manually using `mongosh`:

```bash
# Connect to MongoDB
docker compose exec mongodb mongosh

# List existing search indexes
db.vector_documents.listSearchIndexes()

# Drop the vector index (if needed)
db.vector_documents.dropSearchIndex("vector_index")

# Recreate the index
db.vector_documents.createSearchIndex({
  name: "vector_index",
  type: "vectorSearch",
  definition: {
    fields: [
      {
        type: "vector",
        numDimensions: 384,
        path: "embedding",
        similarity: "cosine"
      },
      {
        type: "filter",
        path: "metadata.source"
      }
    ]
  }
})
```

## Querying the Vector Index

The vector search uses MongoDB's aggregation pipeline:

```javascript
db.vector_documents.aggregate([
  {
    "$vectorSearch": {
      "index": "vector_index",
      "path": "embedding",
      "queryVector": [0.12, -0.45, 0.78, ...],
      "numCandidates": 100,
      "limit": 3
    }
  },
  {
    "$project": {
      "embedding": 0,
      "_id": 0
    }
  }
])
```

## Ingestion State Tracking

Document ingestion state is stored in MongoDB (not filesystem) to prevent desynchronization:

```javascript
// Collection: _ingestion_state
{
  _id: "current",
  files_hash: "abc123...",
  last_ingested: "2026-03-28T19:13:28.093Z",
  document_count: 418,
  files_processed: ["fantasy.md", "Iran - Wikipedia.pdf"]
}
```

This ensures:
- Hash and vector data share the same lifecycle
- Empty database is detected automatically (re-ingestion triggered)
- No orphaned state across container restarts

## Troubleshooting

### Index not ready

Vector search index creation is asynchronous. The setup script waits up to 30 seconds for the index to become available. Check the logs:

```bash
docker compose logs geovision-app | grep VECTOR
```

### Rebuilding the index

If you need to rebuild the index:

1. Stop the stack: `docker compose down`
2. Clear MongoDB data: `docker volume rm geovision-lab_mongodb_data`
3. Restart: `docker compose up --build`

The index will be recreated automatically on startup.
