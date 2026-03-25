"""
Ontology Extractor Pipeline

Extracts full Entities (People, Orgs, Locations, Events) and their Links.
"""
import logging
from typing import Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
import json

from app.models.ontology import OntologyDelta

logger = logging.getLogger("agent_flow")

class OntologyExtractorService:
    def __init__(self, llm: ChatOllama):
        self.llm = llm
        
        # We use a structured system prompt rather than relying purely on function calling
        # since some smaller local models struggle with strict JSON schema adherence.
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", 
             "You are an expert Intelligence Analyst extracting Entities and Relationships into a strict JSON Knowledge Graph.\n"
             "You must extract the following Entity types: Location, Person, Organization, Event, Asset, Document, Concept.\n"
             "You must extract Links between them with a descriptive relationship_type (if any exist).\n"
             "Your output MUST be a valid JSON object matching this schema:\n"
             "{{\n"
             '  "entities": [\n'
             '    {{ "name": "...", "type": "Location", "context": "exact text from source" }}\n'
             "  ],\n"
             '  "links": [\n'
             '    {{ "source_entity_name": "...", "target_entity_name": "...", "relationship_type": "LOCATED_IN", "context": "exact text" }}\n'
             "  ]\n"
             "}}\n"
             "IMPORTANT: You MUST extract all relevant entities EVEN IF there are no links between them! It is perfectly fine to return an empty 'links' array, but you must still extract the entities.\n"
             "Do not add markdown formatting or conversational text, only output the JSON."),
            ("human", "User Query Context: {query}\n\nText to analyze:\n{text}")
        ])
        
        # Try to use formal structured output if the model supports it well
        try:
            self.structured_llm = self.llm.with_structured_output(OntologyDelta)
        except NotImplementedError:
            self.structured_llm = None
            logger.warning("Structured output not natively supported by this LLM wrapper. Will fallback to JSON parsing.")

    def extract(self, text: str, query: str = "") -> Optional[OntologyDelta]:
        """ Extracts entities and links from the response text. """
        if not text.strip():
            return None
            
        logger.info("[ONTOLOGY_EXTRACTOR] Starting extraction...")
        
        if self.structured_llm:
            try:
                # Use native structured output
                chain = self.prompt | self.structured_llm
                result = chain.invoke({"query": query, "text": text})
                return result
            except Exception as e:
                logger.error(f"[ONTOLOGY_EXTRACTOR] Structured extraction failed: {e}")
                # Fallback to standard generation
                
        # Fallback manual parsing
        try:
            # Force JSON format if structured_llm failed or isn't available
            fallback_llm = self.llm.bind(format="json")
            chain = self.prompt | fallback_llm
            response = chain.invoke({"query": query, "text": text})
            content = response.content
            
            # Clean possible markdown
            if content.startswith("```json"):
                content = content.split("```json")[1].split("```")[0].strip()
            elif content.startswith("```"):
                content = content.split("```")[1].split("```")[0].strip()
                
            data = json.loads(content)
            return OntologyDelta.model_validate(data)
        except Exception as e:
            logger.error(f"[ONTOLOGY_EXTRACTOR] Fallback extraction failed: {e}")
            return None

def get_ontology_extractor() -> OntologyExtractorService:
    from app.core.di_llm import get_llm
    from app.core.di import container
    return container._get_or_create(
        get_ontology_extractor, 
        lambda: OntologyExtractorService(llm=get_llm())
    )
