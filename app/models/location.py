"""
Location Value Object

Defines the Location value object for type-safe geographic location handling.
"""

from dataclasses import dataclass


@dataclass(frozen=False)
class Location:
    """
    Geographic location value object.

    Attributes:
        name: Location name (e.g., "Paris", "Iran")
        lat: Latitude coordinate
        lon: Longitude coordinate
        type: Location type (country, city, region, landmark, etc.)
        country: Country name
        display_name: Full display name from geocoding
        state: State/region (optional)
        city: City name (optional)
        relevance: Relevance score (0.0-1.0) for prioritization
    """

    name: str
    lat: float
    lon: float
    type: str
    country: str = "Unknown"
    display_name: str = ""
    state: str = ""
    city: str = ""
    relevance: float = 1.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "type": self.type,
            "country": self.country,
            "display_name": self.display_name,
            "state": self.state,
            "city": self.city,
            "relevance": self.relevance,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Location":
        """Create Location from dictionary."""
        return cls(
            name=data.get("name", ""),
            lat=float(data.get("lat", 0)),
            lon=float(data.get("lon", 0)),
            type=data.get("type", "landmark"),
            country=data.get("country", "Unknown"),
            display_name=data.get("display_name", ""),
            state=data.get("state", ""),
            city=data.get("city", ""),
            relevance=float(data.get("relevance", 1.0)),
        )

    def __post_init__(self):
        """Validate location data after initialization."""
        if not -90 <= self.lat <= 90:
            raise ValueError(f"Latitude must be between -90 and 90, got {self.lat}")
        if not -180 <= self.lon <= 180:
            raise ValueError(f"Longitude must be between -180 and 180, got {self.lon}")


@dataclass(frozen=True)
class LocationType:
    """Enumeration of location types as frozen dataclass for immutability."""

    COUNTRY = "country"
    REGION = "region"
    CITY = "city"
    TOWN = "town"
    VILLAGE = "village"
    NEIGHBOURHOOD = "neighbourhood"
    LANDMARK = "landmark"
    OTHER = "other"
