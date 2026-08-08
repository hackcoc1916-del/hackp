"""
AEGIS — Correlation Engine
Cross-evidence entity resolution and intelligence chain detection.
The most critical analytical component — connects the dots across all evidence.
"""

from __future__ import annotations
import json, os, traceback
from google import genai
from models import Correlation, GraphNode, GraphEdge, EntityType
import state

_client: genai.Client | None = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable not set")
        _client = genai.Client(api_key=api_key)
    return _client


CORRELATION_PROMPT = """You are an expert intelligence analyst for a law enforcement platform called AEGIS.

Your job is to find CONNECTIONS between entities discovered across different pieces of evidence.

Investigation Goal: {goal}

All entities discovered (from different evidence items):
{entities_list}

OSINT intelligence (if available):
{osint_data}

Analyze these entities and find:
1. **Same-entity matches**: entities that likely refer to the same person/vehicle/location across different evidence
2. **Ownership chains**: Vehicle → Owner → Phone → Transactions
3. **Location correlations**: entities seen at the same or nearby locations
4. **Temporal correlations**: entities appearing in a time sequence that suggests movement or connection
5. **Association networks**: groups of connected entities

Return a JSON response with this exact structure:
{{
  "correlations": [
    {{
      "entity_a": "First entity description",
      "entity_a_type": "Person | Vehicle | Location | NumberPlate | etc.",
      "entity_b": "Second entity description",
      "entity_b_type": "Person | Vehicle | Location | NumberPlate | etc.",
      "relationship": "SAME_AS | OWNS | DRIVES | CONTACTED | TRANSACTED_WITH | ASSOCIATED_WITH | LOCATED_NEAR | TRAVELED_TO | WITNESSED_BY | EMPLOYED_BY",
      "confidence": 0.0 to 1.0,
      "reasoning": "Why you believe this connection exists",
      "evidence_support": "Which evidence items support this connection"
    }}
  ],
  "chains": [
    {{
      "name": "Chain name (e.g., 'Vehicle Ownership Chain')",
      "description": "What this chain reveals",
      "links": ["Entity A → relationship → Entity B → relationship → Entity C"],
      "confidence": 0.0 to 1.0,
      "investigative_value": "high | medium | low"
    }}
  ],
  "clusters": [
    {{
      "name": "Cluster name (e.g., 'Suspect Network')",
      "entities": ["List of connected entities"],
      "connections": ["How they connect"],
      "threat_level": "high | medium | low"
    }}
  ],
  "timeline_sequence": [
    {{
      "timestamp": "Approximate time",
      "entity": "Who/what",
      "location": "Where",
      "action": "What happened"
    }}
  ]
}}

RULES:
- Only propose correlations you have genuine reasoning for
- Confidence must reflect actual evidence strength
- Don't hallucinate connections — if uncertain, use low confidence
- Think like an experienced detective connecting dots
- Indian law enforcement context (state police, RTO, toll plazas)

Respond ONLY with valid JSON. No markdown, no code fences."""


async def run_correlation_engine(
    investigation_id: str,
    investigation_goal: str,
    osint_data: dict | None = None,
) -> list[Correlation]:
    """Run cross-evidence correlation analysis on all entities in the investigation."""
    try:
        client = _get_client()

        # Gather all nodes from the knowledge graph for this investigation
        nodes = [n for n in state.graph_nodes.values() if n.investigation_id == investigation_id]

        if len(nodes) < 2:
            return []  # Need at least 2 entities to correlate

        # Format entities with their evidence sources
        entities_text = "\n".join([
            f"  - [{n.type.value}] \"{n.label}\" "
            f"(Confidence: {n.confidence:.0%}, Evidence: {', '.join(n.evidence_ids)}, "
            f"Properties: {json.dumps(n.properties)})"
            for n in nodes
        ])

        osint_text = "Not available"
        if osint_data:
            osint_text = json.dumps(osint_data, indent=2)[:2000]

        prompt = CORRELATION_PROMPT.format(
            goal=investigation_goal,
            entities_list=entities_text,
            osint_data=osint_text,
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

        data = json.loads(text)
        correlations = []

        for cor in data.get("correlations", []):
            # Find matching nodes
            entity_a_node = _find_best_node_match(cor.get("entity_a", ""), nodes)
            entity_b_node = _find_best_node_match(cor.get("entity_b", ""), nodes)

            correlation = Correlation(
                investigation_id=investigation_id,
                entity_a_id=entity_a_node.id if entity_a_node else "",
                entity_a_label=cor.get("entity_a", ""),
                entity_b_id=entity_b_node.id if entity_b_node else "",
                entity_b_label=cor.get("entity_b", ""),
                relationship=cor.get("relationship", "ASSOCIATED_WITH"),
                confidence=float(cor.get("confidence", 0.5)),
                reasoning=cor.get("reasoning", ""),
                evidence_chain=entity_a_node.evidence_ids + entity_b_node.evidence_ids if entity_a_node and entity_b_node else [],
            )
            correlations.append(correlation)

            # Also add as graph edges for visualization
            if entity_a_node and entity_b_node:
                from graph import add_edge
                add_edge(
                    entity_a_node.id,
                    entity_b_node.id,
                    cor.get("relationship", "CORRELATED"),
                    investigation_id,
                    float(cor.get("confidence", 0.5)),
                    {"reasoning": cor.get("reasoning", ""), "source": "correlation_engine"},
                )

        # Process chains → add as graph edges too
        for chain in data.get("chains", []):
            # Store chain info as a special correlation
            correlations.append(Correlation(
                investigation_id=investigation_id,
                entity_a_label=chain.get("name", ""),
                entity_b_label="Chain",
                relationship="CHAIN",
                confidence=float(chain.get("confidence", 0.5)),
                reasoning=chain.get("description", "") + " | Links: " + " → ".join(chain.get("links", [])),
            ))

        return correlations

    except Exception as ex:
        traceback.print_exc()
        return []


def _find_best_node_match(entity_text: str, nodes: list[GraphNode]) -> GraphNode | None:
    """Find the best matching node for an entity description."""
    if not entity_text:
        return None

    entity_lower = entity_text.lower().strip()

    # Exact match
    for node in nodes:
        if node.label.lower().strip() == entity_lower:
            return node

    # Substring match
    for node in nodes:
        if entity_lower in node.label.lower() or node.label.lower() in entity_lower:
            return node

    # Word overlap match
    entity_words = set(entity_lower.split())
    best_match = None
    best_overlap = 0
    for node in nodes:
        node_words = set(node.label.lower().split())
        overlap = len(entity_words & node_words)
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = node

    return best_match if best_overlap > 0 else None
