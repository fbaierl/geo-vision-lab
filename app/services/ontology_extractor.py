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
        
        # We use a formal structured system prompt with concrete examples.
        # The model must replace ALL placeholder values with actual extracted data.
        # Note: All JSON curly braces are escaped with double braces {{}} for LangChain template safety.
        self.prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are an expert Intelligence Analyst extracting Entities and Relationships into a strict JSON Knowledge Graph.\n\n"
             "## Entity Types to Extract:\n"
             "- Location: Cities, countries, regions, geographical features\n"
             "- Person: Individual human beings\n"
             "- Organization: Companies, governments, institutions, groups\n"
             "- Event: Historical events, meetings, conflicts, ceremonies\n"
             "- Asset: Equipment, weapons, vehicles, infrastructure\n"
             "- Document: Reports, treaties, laws, articles\n"
             "- Concept: Ideas, ideologies, theories, movements\n\n"
             "## Output Format:\n"
             "Your output MUST be a valid JSON object with this structure:\n"
             "{{\n"
             '  "entities": [\n'
             '    {{"name": "John Smith", "type": "Person", "context": "John Smith works at Microsoft"}},\n'
             '    {{"name": "Microsoft", "type": "Organization", "context": "works at Microsoft in Seattle"}},\n'
             '    {{"name": "Seattle", "type": "Location", "context": "Microsoft in Seattle, Washington"}}\n'
             "  ],\n"
             '  "links": [\n'
             '    {{"source_entity_name": "John Smith", "target_entity_name": "Microsoft", "relationship_type": "AFFILIATED_WITH", "context": "John Smith works at Microsoft"}},\n'
             '    {{"source_entity_name": "Microsoft", "target_entity_name": "Seattle", "relationship_type": "LOCATED_IN", "context": "Microsoft in Seattle"}}\n'
             "  ]\n"
             "}}\n\n"
             "## CRITICAL INSTRUCTIONS:\n"
             "1. Replace ALL example values with actual entities from YOUR text - NEVER output 'John Smith', 'Microsoft', etc. unless they appear in the source text\n"
             "2. NEVER use '...' or placeholder values - extract REAL names from the text\n"
             "3. You MUST extract all relevant entities EVEN IF there are no links between them\n"
             "4. Empty 'links' array is perfectly fine if no relationships exist\n"
             "5. Use exact entity names as they appear in the text\n"
             "6. The 'context' field must contain the exact sentence or phrase where the entity was mentioned\n"
             "7. Do NOT add markdown formatting (no ```json blocks) - output raw JSON only\n\n"
             "## Relationship Types (use snake_case or CAPS_SNAKE_CASE):\n"
             "LOCATED_IN, AFFILIATED_WITH, SUPPORTS, TARGETS, CONFLICT_WITH, LEADS, PART_OF, PARTICIPATED_IN, OWNS, USES, MENTIONED_IN, RELATED_TO"),
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
