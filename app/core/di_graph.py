"""
Graph Database Dependencies for GeoVision Lab

This module provides Neo4j-related dependency providers.
Uses the DI container for clean, testable dependency injection.

Usage:
    from fastapi import Depends
    from app.core.di_graph import get_neo4j_driver, get_graph_store

    def some_operation(driver = Depends(get_neo4j_driver)):
        ...

Testing:
    from app.core.di import container
    container.override(get_neo4j_driver, mock_driver)
    # run test
    container.reset_overrides()
"""

from neo4j import GraphDatabase, Driver
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_container():
    """Lazy import to avoid circular dependency."""
    from app.core.di import container

    return container


def _create_neo4j_driver() -> Driver:
    """Factory function to create Neo4j driver."""
    logger.info("[DI] Creating Neo4j driver...")
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )
    # Verify connectivity
    try:
        driver.verify_connectivity()
        logger.info("[DI] Neo4j connection verified")
    except Exception as e:
        logger.error(f"[DI] Neo4j connection failed: {e}")
        raise
    return driver


def get_neo4j_driver() -> Driver:
    """Get Neo4j driver (managed by DI container)."""
    return _get_container()._get_or_create(get_neo4j_driver, _create_neo4j_driver)


def get_graph_store():
    """Get or create GraphStoreService instance."""
    from app.services.graph_store import GraphStoreService

    def factory():
        driver = get_neo4j_driver()
        return GraphStoreService(driver)

    return _get_container()._get_or_create(get_graph_store, factory)


def close_neo4j_driver() -> None:
    """Close Neo4j driver on shutdown."""
    container = _get_container()
    if get_neo4j_driver in container._instances:
        driver = container._instances[get_neo4j_driver]
        driver.close()
        logger.info("[DI] Neo4j driver closed")
        del container._instances[get_neo4j_driver]
