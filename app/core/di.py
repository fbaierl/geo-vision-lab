"""
Dependency Injection Container for GeoVision Lab

This module provides the core DI container and re-exports all dependencies
from focused modules. Uses FastAPI's Depends() pattern for clean, testable DI.

Usage:
    from fastapi import Depends
    from app.core.di import get_mongo_client, get_vector_store, get_location_extractor

    @router.post("/search")
    async def search(
        client: MongoClient = Depends(get_mongo_client),
        vector_store: VectorStore = Depends(get_vector_store)
    ):
        ...

Testing:
    from app.core.di import container

    def test_something():
        container.override(get_mongo_client, mock_client)
        # run test
        container.reset_overrides()
"""

from typing import Any, Callable, Dict

# Re-export container and all dependencies from focused modules
# These are intentional re-exports for backward compatibility
from app.core.di_database import (  # noqa: F401
    get_mongo_client,
    get_database,
    get_collection,
)
from app.core.di_nlp import (  # noqa: F401
    get_embeddings,
    get_ner_pipeline,
    get_geocode_cache,
)
from app.core.di_llm import (  # noqa: F401
    get_llm,
)
from app.core.di_services import (  # noqa: F401
    get_vector_store,
    get_location_extractor,
    get_location_prioritizer,
    ensure_vector_index,
)
from app.services.ontology.service import OntologyService  # noqa: F401

# Import ensure_vector_index from database module for internal use
from app.core.di_database import ensure_vector_index as di_ensure_vector_index  # noqa: F401


def get_ontology_service() -> OntologyService:
    """
    Get or create OntologyService instance.

    Returns:
        OntologyService instance
    """

    def factory():
        db = get_database()
        return OntologyService(db)

    return container._get_or_create(get_ontology_service, factory)


class DIContainer:
    """
    Simple dependency injection container with override support for testing.

    Unlike singletons, this container:
    - Makes dependencies explicit
    - Allows easy mocking in tests via override()
    - Supports proper lifecycle management
    """

    def __init__(self):
        self._overrides: Dict[Callable, Any] = {}
        self._instances: Dict[Callable, Any] = {}

    def override(self, dependency: Callable, mock_or_factory: Any) -> None:
        """Override a dependency with a mock or factory (for testing)."""
        self._overrides[dependency] = mock_or_factory

    def reset_overrides(self) -> None:
        """Remove all overrides (call after tests)."""
        self._overrides.clear()

    def _get_or_create(self, dependency: Callable, factory: Callable) -> Any:
        """Get overridden instance or create via factory."""
        if dependency in self._overrides:
            override = self._overrides[dependency]
            return override() if callable(override) else override

        if dependency not in self._instances:
            self._instances[dependency] = factory()

        return self._instances[dependency]


# Global container instance
container = DIContainer()
