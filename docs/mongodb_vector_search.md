# MongoDB Vector Search Setup

GeoVision Lab uses **MongoDB 8.2+ Vector Search** for semantic document retrieval. This guide explains how the vector search index is created and managed.

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
docker compose exec mongodb mongosh -u geovision -p geovision

# List existing search indexes
db.historical_reports.listSearchIndexes()

# Drop the vector index (if needed)
db.historical_reports.dropSearchIndex("vector_index")

# Recreate the index
db.historical_reports.createSearchIndex({
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
db.historical_reports.aggregate([
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
