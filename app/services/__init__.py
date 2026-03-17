"""
Services package for GeoVision Lab

All services now use dependency injection via the DI container.
Legacy function wrappers are provided for backward compatibility.
"""

from app.services.vector_store import VectorStoreService, get_vector_store
from app.services.location_extractor import LocationExtractorService, get_location_extractor
from app.services.location_prioritizer import LocationPrioritizerService, get_location_prioritizer

__all__ = [
    "VectorStoreService",
    "get_vector_store",
    "LocationExtractorService",
    "get_location_extractor",
    "LocationPrioritizerService",
    "get_location_prioritizer",
]
