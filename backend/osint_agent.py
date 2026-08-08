"""
AEGIS — OSINT Agent
Simulated Open Source Intelligence agent using Gemini reasoning.
Generates realistic OSINT intelligence from extracted entities.
"""

from __future__ import annotations
import json, os, traceback
from google import genai
from models import DetectedEntity, EntityType

_client: genai.Client | None = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable not set")
        _client = genai.Client(api_key=api_key)
    return _client


OSINT_PROMPT = """You are an OSINT (Open Source Intelligence) analyst for a law enforcement investigation platform called AEGIS.

Given the following entities extracted from investigation evidence, generate REALISTIC and PLAUSIBLE OSINT intelligence that would be found through open-source research.

Investigation Goal: {goal}

Entities to investigate:
{entities_list}

For each entity, generate intelligence that an investigator might find through:
- Public records databases
- Social media searches
- News article searches
- Vehicle registration lookups
- Phone number lookups
- Address lookups
- Business registration searches

Return a JSON response with this exact structure:
{{
  "intelligence_reports": [
    {{
      "entity": "The entity being investigated",
      "entity_type": "Person | Vehicle | PhoneNumber | Email | Location | NumberPlate",
      "sources_checked": ["List of sources checked"],
      "findings": [
        {{
          "source": "Where this info was found (e.g., 'Motor Vehicle Registry', 'Social Media', 'News Archive')",
          "information": "What was found",
          "confidence": 0.0 to 1.0,
          "relevance": "high | medium | low",
          "timestamp": "When this information is from (approximate date)"
        }}
      ],
      "connections": [
        {{
          "connected_entity": "Name/identifier of connected entity",
          "connection_type": "OWNS | ASSOCIATED_WITH | RELATED_TO | EMPLOYED_BY | LIVES_AT | CONTACTED",
          "details": "How they are connected"
        }}
      ],
      "risk_indicators": ["Any risk flags or concerns"],
      "suggested_actions": ["What to investigate next based on these findings"]
    }}
  ],
  "cross_entity_connections": [
    {{
      "entity_a": "First entity",
      "entity_b": "Second entity",
      "connection": "How they connect",
      "confidence": 0.0 to 1.0
    }}
  ],
  "investigation_summary": "Brief summary of all OSINT findings and their implications"
}}

IMPORTANT:
- Generate REALISTIC, PLAUSIBLE intelligence — not fictional
- For Indian context: use realistic Indian names, locations, organizations
- Include both positive findings and dead ends (some searches should return limited results)
- Confidence scores should be varied and honest
- Suggested actions should be specific and actionable

Respond ONLY with valid JSON. No markdown, no code fences."""


async def run_osint(investigation_goal: str, entities: list[dict]) -> dict:
    """Run simulated OSINT analysis on extracted entities."""
    try:
        client = _get_client()

        # Format entities list
        entities_text = "\n".join([
            f"  - [{e.get('type', 'Unknown')}] {e.get('description', '')} "
            f"(Confidence: {e.get('confidence', 0):.0%}, Details: {e.get('details', 'N/A')})"
            for e in entities
        ]) or "  (no entities to investigate)"

        prompt = OSINT_PROMPT.format(
            goal=investigation_goal or "General investigation",
            entities_list=entities_text,
        )

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )

        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        return json.loads(text)

    except Exception as ex:
        traceback.print_exc()
        return {
            "intelligence_reports": [],
            "cross_entity_connections": [],
            "investigation_summary": f"OSINT analysis failed: {str(ex)}",
        }
