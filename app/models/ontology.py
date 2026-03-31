from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID, uuid4


class Mention(BaseModel):
    """Represents a mention of an entity or relationship in source text."""

    source_text: str
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    confidence: float = 1.0
    thread_id: Optional[str] = None


class OntologyDeltaEntity(BaseModel):
    """Entity extracted from text (intermediate format)."""

    name: str
    type: str
    context: str


class OntologyDeltaLink(BaseModel):
    """Link extracted from text (intermediate format)."""

    source_entity_name: str
    target_entity_name: str
    relationship_type: str
    context: str


class OntologyDelta(BaseModel):
    """Delta containing extracted entities and links from text."""

    entities: List[OntologyDeltaEntity] = Field(default_factory=list)
    links: List[OntologyDeltaLink] = Field(default_factory=list)


class OntologyEntity(BaseModel):
    """Represents an entity in the ontology (person, location, organization, etc.)."""

    uuid: UUID = Field(default_factory=uuid4)
    name: str
    type: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    mentions: List[Mention] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = Field(default="llm_extractor")


class OntologyLink(BaseModel):
    """Represents a relationship between two entities."""

    uuid: UUID = Field(default_factory=uuid4)
    source_uuid: UUID
    target_uuid: UUID
    type: str
    properties: Dict[str, Any] = Field(default_factory=dict)
    mentions: List[Mention] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SessionOntology(BaseModel):
    """The global graph accumulated during a session."""

    entities: Dict[str, OntologyEntity] = Field(default_factory=dict)
    links: Dict[str, OntologyLink] = Field(default_factory=dict)

    def to_array_format(self) -> dict:
        """Convert to array format for MongoDB storage."""
        return {
            "entities": [e.model_dump() for e in self.entities.values()],
            "links": [link.model_dump() for link in self.links.values()],
        }

    @classmethod
    def from_array_format(cls, data: dict) -> "SessionOntology":
        """Load from array format (MongoDB storage)."""
        entities = {}
        for e in data.get("entities", []):
            entity = OntologyEntity.model_validate(e)
            entities[str(entity.uuid)] = entity

        links = {}
        for link_data in data.get("links", []):
            link = OntologyLink.model_validate(link_data)
            links[str(link.uuid)] = link

        return cls(entities=entities, links=links)

    def to_export_format(self, metadata: dict = None) -> dict:
        """Convert to export format with metadata."""
        return {
            "$schema": "https://geo-vision-lab.dev/ontology-v2.schema.json",
            "version": "2.0",
            "metadata": metadata or {},
            "entities": [e.model_dump() for e in self.entities.values()],
            "links": [link.model_dump() for link in self.links.values()],
        }

    @classmethod
    def from_export_format(cls, data: dict) -> "SessionOntology":
        """Import from export format (ignores metadata and schema)."""
        entities = {}
        for e in data.get("entities", []):
            entity = OntologyEntity.model_validate(e)
            entities[str(entity.uuid)] = entity

        links = {}
        for link_data in data.get("links", []):
            link = OntologyLink.model_validate(link_data)
            links[str(link.uuid)] = link

        return cls(entities=entities, links=links)
