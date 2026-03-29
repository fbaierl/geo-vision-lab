"""
Ontology Extractor Pipeline

Extracts full Entities (People, Orgs, Locations, Events) and their Links.
"""
import logging
from typing import Optional, List
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
import json

from app.models.ontology import OntologyDelta, OntologyDeltaEntity

logger = logging.getLogger("agent_flow")

class OntologyExtractorService:
    def __init__(self, llm):
        self.llm = llm
        self.is_groq = isinstance(llm, ChatGroq)

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
             "Predefined types: LOCATED_IN, AFFILIATED_WITH, SUPPORTS, TARGETS, CONFLICT_WITH, LEADS, PART_OF, PARTICIPATED_IN, OWNS, USES, MENTIONED_IN, RELATED_TO, ATTACKED, DEFENDS, VISITED, MET_WITH, NEGOTIATES_WITH, FUNDS, TRAINS, ARMS, SANCTIONS, EMBARGOES, DEPLOYS_TO, STATIONED_IN, ORIGINATES_FROM, OPERATES_IN, CONTROLS, OCCUPIES, LIBERATES, BOMBS, STRIKES, INFILTRATES, ESCALATES, DE-ESCALATES, MEDIATES, ARBITRATES, CONDEMNS, PRAISES, THREATENS, SURRENDERS_TO, CEASEFIRE_WITH, ALLIES_WITH, HOSTILE_TO, COMPETES_WITH, MERGES_WITH, ACQUIRES, PARTNERS_WITH, SPONSORS, BOYCOTTS, SANCTIONED_BY, DESIGNATES_AS_TERRORIST, REMOVES_SANCTIONS, ESTABLISHED, DISSOLVED, FOUNDED, HEADQUARTERED_IN, BRANCH_IN, REPRESENTS, SPEAKS_FOR, ADVISES, REPORTS_TO, COMMANDS, SUBORDINATE_TO, COLLABORATES_WITH, COORDINATES_WITH, SHARES_INTELLIGENCE_WITH, PROVIDES_ASYLUM_TO, EXTRADITES_TO, DEPORTS, DETAINS, ARRESTS, RELEASES, TRIALS, CONVICTS, ACQUITS, PARDONS, EXCHANGES_PRISONERS_WITH, DEPLOYS_TROOPS_TO, WITHDRAWS_TROOPS_FROM, CONDUCTS_AIRSTRIKE_ON, LAUNCHES_MISSILE_AT, DEPLOYS_MISSILES_IN, DESTROYS, CAPTURES, SEIZES, RECAPTURES, OVERRUNS, FORTIFIES, MINES, BLOCKADES, EMBARGOES_SANCTIONS, IMPOSES_TARIFFS_ON, REMOVES_TARIFFS_FROM, GRANTS_AID_TO, RECEIVES_AID_FROM, PROVIDES_HUMANITARIAN_AID_TO, ACCEPTS_HUMANITARIAN_AID_FROM, BLOCKS_AID_TO, ALLOWS_AID_THROUGH, SIGNATORY_TO, RATIFIES, VIOLATES, WITHDRAWS_FROM, REJOINS, PROPOSES, REJECTS, AMENDS, VETOES, UPHOLDS, OVERTURNS, CHALLENGES, COMPLIES_WITH, IGNORES, DEFIES, ACCEDES_TO, PROTESTS_AGAINST, DEMONSTRATES_AGAINST, PETITIONS, LOBBIES, CAMPAIGNS_FOR, CAMPAIGNS_AGAINST, ENDORSES, OPPOSES, CRITICIZES, DENOUNCES, APPLAUDS, ACKNOWLEDGES, DENIES, ADMITS, CONFIRMS, REFUTES, CLAIMS, ASSERTS, ALLEGES, ACCUSES_OF, BLAMES_FOR, HOLDS_RESPONSIBLE, EXONERATES, INVESTIGATES, INDICTS, CHARGES, PROSECUTES, SUED_BY, SETTLES_WITH, COMPENSATES, REIMBURSES, RESTITUTES, REPARATIONS_TO, REPARATIONS_FROM\n\n"
             "IMPORTANT: You are NOT limited to the predefined types above. Feel free to discover and use additional relationship types that accurately capture the semantic connections between entities in the text. Use clear, descriptive relationship names in CAPS_SNAKE_CASE format (e.g., MARRIED_TO, SIBLING_OF, STUDIED_AT, WORKED_ON, INFLUENCED_BY, INSPIRED_BY, DERIVED_FROM, EVOLVED_INTO, PRECEDED_BY, SUCCEEDED_BY, etc.). The goal is to accurately represent the relationships found in the text, even if they don't match the predefined list."),
            ("human", "User Query Context: {query}\n\nText to analyze:\n{text}")
        ])

        # Try to use formal structured output if the model supports it well
        # Skip structured output for Groq as it doesn't support it well
        self.structured_llm = None
        if not self.is_groq:
            try:
                self.structured_llm = self.llm.with_structured_output(OntologyDelta)
            except NotImplementedError:
                logger.warning("Structured output not natively supported by this LLM wrapper. Will fallback to JSON parsing.")

        # Gap extraction prompt - specialized for extracting only missing entities
        self.gap_prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are repairing a knowledge graph extraction.\n\n"
             "## Task\n"
             "The following entities were referenced in relationships but were NOT extracted:\n"
             "{missing_entities}\n\n"
             "Your task: Extract ONLY these missing entities from the text below.\n"
             "For each missing entity:\n"
             "1. Find where it appears in the text\n"
             "2. Determine its correct type (Organization, Concept, Event, Location, Person, Asset, Document)\n"
             "3. Extract the context where it's mentioned\n\n"
             "## Output Format\n"
             "Your output MUST be a valid JSON object with this structure:\n"
             "{{\n"
             '  "entities": [\n'
             '    {{"name": "Allies", "type": "Organization", "context": "The Allies and Axis powers were the two main opposing military alliances"}},\n'
             '    {{"name": "Axis powers", "type": "Organization", "context": "the Allies and Axis powers were the two main opposing military alliances"}}\n'
             "  ],\n"
             '  "links": []\n'
             "}}\n\n"
             "## CRITICAL INSTRUCTIONS:\n"
             "1. Extract ONLY the missing entities listed above - do NOT extract other entities\n"
             "2. Do NOT extract links - leave the links array empty\n"
             "3. Use exact entity names as they appear in the text\n"
             "4. The 'context' field must contain the exact sentence or phrase where the entity was mentioned\n"
             "5. Do NOT add markdown formatting (no ```json blocks) - output raw JSON only\n"
             "6. If a missing entity cannot be found in the text, omit it from the output\n"
             "7. Determine the appropriate type based on context (e.g., military alliances → Organization, ideologies → Concept)"),
            ("human", "User Query Context: {query}\n\nText to analyze:\n{text}")
        ])

    def extract(self, text: str, query: str = "") -> Optional[OntologyDelta]:
        """ Extracts entities and links from the response text. """
        if not text.strip():
            logger.warning("[ONTOLOGY_EXTRACTOR] Empty text provided - cannot extract")
            return None

        logger.info("[ONTOLOGY_EXTRACTOR] Starting extraction...")

        # Use native structured output only for Ollama (Groq doesn't support it well)
        if self.structured_llm and not self.is_groq:
            try:
                # Use native structured output
                chain = self.prompt | self.structured_llm
                logger.debug("[ONTOLOGY_EXTRACTOR] Invoking structured LLM...")
                result = chain.invoke({"query": query, "text": text})
                logger.info(f"[ONTOLOGY_EXTRACTOR] ✓ Structured extraction successful: {len(result.entities)} entities, {len(result.links)} links")
                return result
            except Exception as e:
                logger.error(f"[ONTOLOGY_EXTRACTOR] ✗ Structured extraction failed: {e}")
                logger.exception("[ONTOLOGY_EXTRACTOR] Structured extraction stack trace:")
                # Fallback to standard generation

        # Fallback manual parsing (used for Groq or when structured output fails)
        try:
            logger.info("[ONTOLOGY_EXTRACTOR] Attempting fallback JSON parsing...")
            # For Ollama, we can use format="json", but Groq doesn't support it
            if self.is_groq:
                # Groq: use regular LLM with strong JSON instruction in prompt
                fallback_llm = self.llm
            else:
                # Ollama: use format="json" for better JSON compliance
                fallback_llm = self.llm.bind(format="json")
            
            chain = self.prompt | fallback_llm
            response = chain.invoke({"query": query, "text": text})
            content = response.content

            # Log raw response for debugging
            logger.debug(f"[ONTOLOGY_EXTRACTOR] Raw LLM response ({len(content)} chars): {content[:500]}...")

            # Clean possible markdown
            if content.startswith("```json"):
                logger.debug("[ONTOLOGY_EXTRACTOR] Stripping markdown json code block")
                content = content.split("```json")[1].split("```")[0].strip()
            elif content.startswith("```"):
                logger.debug("[ONTOLOGY_EXTRACTOR] Stripping markdown code block")
                content = content.split("```")[1].split("```")[0].strip()

            data = json.loads(content)
            logger.debug(f"[ONTOLOGY_EXTRACTOR] Parsed JSON: {len(data.get('entities', []))} entities, {len(data.get('links', []))} links")

            result = OntologyDelta.model_validate(data)
            logger.info(f"[ONTOLOGY_EXTRACTOR] ✓ Fallback extraction successful: {len(result.entities)} entities, {len(result.links)} links")
            return result
        except json.JSONDecodeError as json_err:
            logger.error(f"[ONTOLOGY_EXTRACTOR] ✗ JSON parsing failed: {json_err}")
            logger.exception("[ONTOLOGY_EXTRACTOR] JSON decode stack trace:")
            logger.error(f"[ONTOLOGY_EXTRACTOR] Invalid JSON content: {content[:1000] if 'content' in locals() else 'N/A'}...")
            return None
        except Exception as e:
            logger.error(f"[ONTOLOGY_EXTRACTOR] ✗ Fallback extraction failed: {e}")
            logger.exception("[ONTOLOGY_EXTRACTOR] Fallback extraction stack trace:")
            if 'data' in locals():
                logger.debug(f"[ONTOLOGY_EXTRACTOR] Parsed data that failed validation: {data}")
            return None

    def extract_missing_entities(self, text: str, missing_names: List[str], query: str = "") -> List[OntologyDeltaEntity]:
        """
        Extract only the specified missing entities from text.

        Use case: Links reference entities that weren't extracted in pass 1.
        This method performs targeted extraction to recover gap entities.

        Args:
            text: The source text to analyze
            missing_names: List of entity names that need to be extracted
            query: Optional user query context

        Returns:
            List of extracted entities (only the missing ones)
        """
        if not text.strip() or not missing_names:
            logger.warning("[ONTOLOGY_EXTRACTOR] Empty text or missing names for gap extraction")
            return []

        logger.info(f"[ONTOLOGY_EXTRACTOR] Starting gap extraction for {len(missing_names)} entities: {missing_names}")

        # Format missing entities as a bulleted list for the prompt
        missing_entities_str = "\n".join(f"- \"{name}\"" for name in missing_names)

        try:
            # For Ollama, we can use format="json", but Groq doesn't support it
            if self.is_groq:
                # Groq: use regular LLM with strong JSON instruction in prompt
                gap_llm = self.llm
            else:
                # Ollama: use format="json" for better JSON compliance
                gap_llm = self.llm.bind(format="json")
            
            chain = self.gap_prompt | gap_llm
            response = chain.invoke({
                "query": query,
                "text": text,
                "missing_entities": missing_entities_str
            })
            content = response.content

            # Log raw response for debugging
            logger.debug(f"[ONTOLOGY_EXTRACTOR] Raw gap extraction response ({len(content)} chars): {content[:500]}...")

            # Clean possible markdown
            if content.startswith("```json"):
                logger.debug("[ONTOLOGY_EXTRACTOR] Stripping markdown json code block")
                content = content.split("```json")[1].split("```")[0].strip()
            elif content.startswith("```"):
                logger.debug("[ONTOLOGY_EXTRACTOR] Stripping markdown code block")
                content = content.split("```")[1].split("```")[0].strip()

            data = json.loads(content)
            entities_data = data.get("entities", [])
            logger.debug(f"[ONTOLOGY_EXTRACTOR] Parsed gap JSON: {len(entities_data)} entities")

            # Validate and return entities
            result = OntologyDelta.model_validate(data)
            logger.info(f"[ONTOLOGY_EXTRACTOR] ✓ Gap extraction successful: {len(result.entities)} entities recovered")

            # Log which missing entities were found
            found_names = [e.name for e in result.entities]
            not_found = set(n.lower() for n in missing_names) - set(n.lower() for n in found_names)
            if not_found:
                logger.warning(f"[ONTOLOGY_EXTRACTOR] Could not find these entities in text: {not_found}")

            return result.entities

        except json.JSONDecodeError as json_err:
            logger.error(f"[ONTOLOGY_EXTRACTOR] ✗ Gap extraction JSON parsing failed: {json_err}")
            logger.exception("[ONTOLOGY_EXTRACTOR] JSON decode stack trace:")
            logger.error(f"[ONTOLOGY_EXTRACTOR] Invalid JSON content: {content[:1000] if 'content' in locals() else 'N/A'}...")
            return []
        except Exception as e:
            logger.error(f"[ONTOLOGY_EXTRACTOR] ✗ Gap extraction failed: {e}")
            logger.exception("[ONTOLOGY_EXTRACTOR] Gap extraction stack trace:")
            return []


def get_ontology_extractor() -> OntologyExtractorService:
    from app.core.di_llm import get_llm
    from app.core.di import container
    return container._get_or_create(
        get_ontology_extractor, 
        lambda: OntologyExtractorService(llm=get_llm())
    )
