# Dependency Injection in GeoVision Lab

## Overview

GeoVision Lab now uses a **simple dependency injection (DI) container** to manage service dependencies. This replaces the previous singleton-based approach, providing better testability, clearer dependencies, and more flexibility.

## Why Dependency Injection?

### Before (Singleton Pattern - Problems)

```python
# app/services/vector_store.py - OLD APPROACH
_client = None
_db = None

def get_mongo_client():
    global _client
    if _client is None:
        _client = MongoClient(settings.DATABASE_URL)
    return _client

def similarity_search(query: str, k: int = 3):
    # Hidden dependency - not obvious from signature
    collection = get_collection()  # Uses global _client
    ...
```

**Problems:**
- ❌ Hidden dependencies (not visible in function signature)
- ❌ Hard to test (must patch global variables)
- ❌ Tight coupling (functions import specific implementations)
- ❌ Stateful globals (race conditions in async code)

### After (Dependency Injection - Benefits)

```python
# app/services/vector_store.py - NEW APPROACH
class VectorStoreService:
    def __init__(self, embeddings, client, collection):
        # Explicit dependencies
        self.embeddings = embeddings
        self.client = client
        self.collection = collection
    
    def similarity_search(self, query: str, k: int = 3):
        # Uses injected dependencies
        query_embedding = self.embeddings.embed_query(query)
        ...
```

**Benefits:**
- ✅ Explicit dependencies (clear from constructor)
- ✅ Easy to test (inject mocks)
- ✅ Loose coupling (swap implementations easily)
- ✅ No global state (thread-safe)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DI Container (app/core/di.py)            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  get_mongo_client()     → MongoClient                │   │
│  │  get_embeddings()       → HuggingFaceEmbeddings      │   │
│  │  get_reasoning_llm()    → ChatOllama                 │   │
│  │  get_reviewer_llm()     → ChatOllama                 │   │
│  │  get_ner_pipeline()     → HuggingFace NER Pipeline   │   │
│  │  get_vector_store()     → VectorStoreService         │   │
│  │  get_location_extractor() → LocationExtractorService │   │
│  │  get_location_prioritizer() → LocationPrioritizer... │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↓ uses
┌─────────────────────────────────────────────────────────────┐
│                    Service Classes                          │
│  ┌──────────────────┐  ┌──────────────────────┐            │
│  │ VectorStore      │  │ LocationExtractor    │            │
│  │ Service          │  │ Service              │            │
│  │ - embeddings     │  │ - ner_pipeline       │            │
│  │ - client         │  │ - reviewer_llm       │            │
│  │ - collection     │  │ - geocode_cache      │            │
│  └──────────────────┘  └──────────────────────┘            │
│  ┌──────────────────┐                                      │
│  │ LocationPrior....│                                      │
│  │ Service          │                                      │
│  │ - reviewer_llm   │                                      │
│  └──────────────────┘                                      │
└─────────────────────────────────────────────────────────────┘
```

## Usage

### In Application Code

```python
# Option 1: Get service from DI container (recommended)
from app.core.di import get_vector_store

def my_function():
    vector_store = get_vector_store()
    results = vector_store.similarity_search("query")
```

```python
# Option 2: Use legacy wrapper functions (backward compatible)
from app.services.vector_store import similarity_search

def my_function():
    results = similarity_search("query")  # Uses DI internally
```

### In Tests

```python
# tests/test_my_feature.py
from unittest.mock import MagicMock
from app.core.di import container, get_vector_store, get_embeddings

def test_vector_search():
    # Create mock
    mock_embeddings = MagicMock()
    mock_embeddings.embed_query.return_value = [0.1] * 384
    
    # Override dependency
    container.override(get_embeddings, lambda: mock_embeddings)
    
    # Run test - will use mock
    service = get_vector_store()
    results = service.similarity_search("test")
    
    # Verify
    mock_embeddings.embed_query.assert_called_once_with("test")
    
    # Cleanup
    container.reset_overrides()
```

Or use the pytest fixtures from `conftest.py`:

```python
def test_with_fixtures(override_embeddings, override_mongo_client):
    # Fixtures already set up mocks
    service = get_vector_store()
    # ... test code
    # Cleanup automatic via fixture
```

## Service Classes

### VectorStoreService

```python
from app.services.vector_store import VectorStoreService, get_vector_store

# Get from DI
service = get_vector_store()

# Or create manually
service = VectorStoreService(
    embeddings=embeddings,
    client=mongo_client,
    collection=collection
)

# Use
results = service.similarity_search("query", k=3)
service.insert_documents(docs)
```

### LocationExtractorService

```python
from app.services.location_extractor import LocationExtractorService, get_location_extractor

# Get from DI
service = get_location_extractor()

# Or create manually
service = LocationExtractorService(
    ner_pipeline=ner_model,
    reviewer_llm=llm,
    geocode_cache={}
)

# Use
locations = service.extract_and_geocode_locations(
    text="Paris is beautiful",
    query="Tell me about Paris",
    response_text="..."
)
```

### LocationPrioritizerService

```python
from app.services.location_prioritizer import LocationPrioritizerService, get_location_prioritizer

# Get from DI
service = get_location_prioritizer()

# Or create manually
service = LocationPrioritizerService(reviewer_llm=llm)

# Use
prioritized = service.prioritize_locations(
    query="Paris travel",
    locations=[...],
    response_text="..."
)
```

## Testing with DI Overrides

### Example: Testing a Service

```python
def test_vector_store_similarity_search():
    # Create mocks
    mock_embeddings = MagicMock()
    mock_client = MagicMock()
    mock_collection = MagicMock()
    
    # Setup mock behavior
    mock_embeddings.embed_query.return_value = [0.1] * 384
    mock_collection.aggregate.return_value = [
        {"page_content": "Result 1", "metadata": {}}
    ]
    
    # Create service with injected dependencies
    service = VectorStoreService(
        embeddings=mock_embeddings,
        client=mock_client,
        collection=mock_collection
    )
    
    # Call method
    results = service.similarity_search("test query", k=1)
    
    # Verify
    assert len(results) == 1
    mock_embeddings.embed_query.assert_called_once()
```

### Example: Testing with DI Container

```python
from app.core.di import container, get_vector_store, get_embeddings

def test_with_di_override():
    mock_embeddings = MagicMock()
    container.override(get_embeddings, lambda: mock_embeddings)
    
    try:
        service = get_vector_store()
        # Test will use mock
    finally:
        container.reset_overrides()
```

### Example: Using Pytest Fixtures

```python
# tests/test_feature.py

def test_feature(override_reasoning_llm, override_vector_store):
    # Fixtures from conftest.py provide mocked dependencies
    # Test code here
    pass
```

## Migration Guide

### For New Code

1. **Use service classes** instead of standalone functions
2. **Get services from DI** using `get_*()` functions
3. **Make dependencies explicit** in function signatures when needed

### For Existing Code

1. **Legacy wrappers** are provided for backward compatibility
2. **Gradually refactor** to use service classes
3. **Update tests** to use DI overrides instead of `@patch`

## Files Changed

| File | Change |
|------|--------|
| `app/core/di.py` | **NEW** - DI container and providers |
| `app/services/vector_store.py` | Refactored to use DI, added `VectorStoreService` class |
| `app/services/location_extractor.py` | Refactored to use DI, added `LocationExtractorService` class |
| `app/services/location_prioritizer.py` | Refactored to use DI, added `LocationPrioritizerService` class |
| `app/services/llm.py` | Now delegates to DI container |
| `app/agents/graph.py` | Updated to use DI for all services |
| `app/agents/tools.py` | Updated to use DI for vector search |
| `tests/conftest.py` | **NEW** - Pytest fixtures for DI |
| `tests/test_di_container.py` | **NEW** - Tests for DI container |
| `tests/test_services_with_di.py` | **NEW** - Tests for services with DI |

## Best Practices

1. **Prefer constructor injection** - Pass dependencies via `__init__`
2. **Use the DI container** - Get services via `get_*()` functions
3. **Make dependencies explicit** - Clear from function/class signatures
4. **Test with overrides** - Use `container.override()` in tests
5. **Avoid globals** - No module-level state
6. **Keep services focused** - Single responsibility per service class

## Future Improvements

Potential enhancements for the DI system:

1. **Request-scoped dependencies** - For per-request caching
2. **Async support** - For async factories
3. **Auto-wiring** - Automatic dependency resolution
4. **Lifecycle management** - Proper cleanup/shutdown hooks
