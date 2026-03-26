from typing import List, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime

class Mention(BaseModel):
    source_text: str                       # The exact snippet or summary it was extracted from
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    confidence: float = 1.0                # Model's confidence returning this

class OntologyEntity(BaseModel):
    id: str                                # Normalized name (e.g., "sudan", "united_nations")
    type: str                              # "Location", "Person", "Organization", "Event", "Asset", "Document", "Concept"
    name: str                              # Display name
    properties: Dict[str, Any] = Field(default_factory=dict) # Type-specific fields (e.g., lat, lon for locations)
    mentions: List[Mention] = Field(default_factory=list)

class OntologyLink(BaseModel):
    id: str                                # Unique hash/id
    source_id: str                         # ID of Source Entity
    target_id: str                         # ID of Target Entity
    type: str                              # Relation type (e.g., "LOCATED_IN", "CONFLICT_WITH")
    properties: Dict[str, Any] = Field(default_factory=dict)
    mentions: List[Mention] = Field(default_factory=list)

class SessionOntology(BaseModel):
    """ The global graph accumulated during the session. """
    entities: Dict[str, OntologyEntity] = Field(default_factory=dict)
    links: Dict[str, OntologyLink] = Field(default_factory=dict)

# Models for the LLM Extraction
class ExtractedEntity(BaseModel):
    name: str = Field(description="The formal name of the entity.")
    type: Literal["Location", "Person", "Organization", "Event", "Asset", "Document", "Concept"] = Field(description="The type of the entity.")
    context: str = Field(description="The original sentence where this was mentioned.")

class ExtractedLink(BaseModel):
    source_entity_name: str = Field(description="The name of the source entity.")
    target_entity_name: str = Field(description="The name of the target entity.")
    relationship_type: str = Field(description="The type of relationship (e.g., LOCATED_IN, AFFILIATED_WITH, SUPPORTS, TARGETS). Should be snake_case or CAPS_SNAKE_CASE.")
    context: str = Field(description="The original sentence where this relationship was described.")

class OntologyDelta(BaseModel):
    """ Used by the LLM to output newly discovered entities and links. """
    entities: List[ExtractedEntity] = Field(description="List of entities found in the text.")
    links: List[ExtractedLink] = Field(description="List of relationships connecting the extracted entities.")
