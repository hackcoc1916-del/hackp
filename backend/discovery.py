"""
AEGIS — Discovery Engine
Sits between Correlation and Lead Generation.

Correlation connects data.
Discovery creates investigative intelligence.
Lead Generation turns intelligence into actionable next steps.

The Discovery Engine finds what the investigator didn't think to ask.
"""

from __future__ import annotations
import json, os, traceback
from google import genai
from models import SharedInvestigationContext

_client: genai.Client | None = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable not set")
        _client = genai.Client(api_key=api_key)
    return _client


DISCOVERY_PROMPT = """You are the Discovery Engine of AEGIS, a law enforcement investigation platform.

Your job is NOT to summarize what was found.
Your job is to find what the INVESTIGATOR DIDN'T THINK TO ASK.

You receive the complete Shared Investigation Context — everything the investigation knows so far.

Investigation Goal: {goal}
Goal Type: {goal_type}

═══ EVIDENCE INTELLIGENCE ═══

Entities Discovered ({entity_count}):
{entities}

Vehicle Intelligence:
{vehicles}

Person Intelligence:
{persons}

Location Intelligence:
{locations}

Temporal Data:
{temporal}

Document Intelligence:
{documents}

Audio Intelligence:
{audio}

═══ CORRELATION RESULTS ═══
{correlations}

═══ GAPS IN THE INVESTIGATION ═══
{gaps}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Now perform DISCOVERY. Find insights the investigator hasn't explicitly asked about.

Think about:
1. **Pattern Detection**: Travel patterns, repeated locations, time sequences that reveal behavior
2. **Anomaly Detection**: Metadata inconsistencies, impossible timelines, suspicious absences
3. **Missing Link Identification**: Expected entities that are ABSENT (no owner for a vehicle, no phone for a person)
4. **Risk Escalation**: Combinations of evidence that suggest higher threat than individual pieces
5. **Connection Expansion**: How entities connect to broader networks beyond this evidence
6. **Temporal Intelligence**: Time-based patterns — when did things happen relative to each other?
7. **Geographic Intelligence**: Spatial patterns — proximity, routes, jurisdictions
8. **Behavioral Intelligence**: What does the evidence suggest about the subject's behavior, planning, or intent?

Return a JSON response:
{{
  "discoveries": [
    {{
      "title": "Brief discovery title",
      "category": "pattern | anomaly | missing_link | risk_escalation | connection | temporal | geographic | behavioral",
      "description": "Detailed description of what was discovered",
      "evidence_basis": "What evidence supports this discovery",
      "confidence": 0.0 to 1.0,
      "significance": "critical | high | medium | low",
      "investigative_implication": "What this means for the investigation",
      "questions_raised": ["Questions the investigator should now consider"]
    }}
  ],
  "patterns": [
    {{
      "name": "Pattern name",
      "description": "What the pattern reveals",
      "entities_involved": ["Which entities form this pattern"],
      "confidence": 0.0 to 1.0
    }}
  ],
  "risk_assessment": {{
    "overall_threat_level": "critical | high | medium | low",
    "escalation_recommended": true or false,
    "reasoning": "Why this threat level"
  }},
  "investigation_gaps": [
    {{
      "gap": "What information is missing",
      "impact": "How filling this gap would change the investigation",
      "priority": "critical | high | medium | low",
      "suggested_source": "Where to get this information"
    }}
  ],
  "unexpected_connections": [
    {{
      "description": "A connection the investigator likely didn't anticipate",
      "entities": ["connected entities"],
      "reasoning": "Why this connection matters"
    }}
  ]
}}

RULES:
- Generate AT LEAST 5 discoveries
- Focus on NON-OBVIOUS insights — things a busy investigator would miss
- Every discovery must have a clear investigative implication
- Think like a senior detective with 20 years of experience reviewing a case file
- Indian law enforcement context (RTO, CCTV networks, toll plazas, petrol pumps)
- Be specific, not generic

Respond ONLY with valid JSON. No markdown, no code fences."""


async def run_discovery_engine(context: SharedInvestigationContext) -> dict:
    """Run the Discovery Engine on the Shared Investigation Context.
    
    This is the component that finds what the investigator didn't think to ask.
    It reads the full context and produces investigative intelligence.
    """
    try:
        client = _get_client()

        # Format context for the prompt
        entities_text = "\n".join([
            f"  - [{e.get('type', '?')}] {e.get('description', '')} "
            f"(conf: {e.get('confidence', 0):.0%}, details: {e.get('details', 'N/A')})"
            for e in context.entities[:30]
        ]) or "  (none)"

        vehicles_text = "\n".join([
            f"  - {v.get('brand', '')} {v.get('model', '')} {v.get('color', '')} "
            f"Plate: {v.get('registration_plate', 'N/A')}"
            for v in context.vehicle_intelligence
        ]) or "  (none)"

        persons_text = "\n".join([
            f"  - {p.get('description', 'Unknown person')} ({p.get('details', '')})"
            for p in context.person_intelligence
        ]) or "  (none)"

        locations_text = "\n".join([
            f"  - {l.get('description', '')} (GPS: {l.get('gps', 'N/A')})"
            for l in context.locations
        ]) or "  (none)"

        temporal_text = "\n".join([
            f"  - [{t.get('timestamp', '?')}] {t.get('description', '')}"
            for t in context.temporal_data
        ]) or "  (none)"

        docs_text = "\n".join([
            f"  - {d.get('summary', d.get('description', 'Document'))}"
            for d in context.document_intelligence
        ]) or "  (none)"

        audio_text = "\n".join([
            f"  - {a.get('summary', a.get('transcript', 'Audio')[:200])}"
            for a in context.audio_intelligence
        ]) or "  (none)"

        corr_text = "\n".join([
            f"  - {c.get('entity_a_label', '?')} —[{c.get('relationship', '?')}]→ "
            f"{c.get('entity_b_label', '?')} (conf: {c.get('confidence', 0):.0%})"
            for c in context.correlations
        ]) or "  (none)"

        gaps_text = "\n".join([f"  - {g}" for g in context.gaps]) or "  (none identified yet)"

        prompt = DISCOVERY_PROMPT.format(
            goal=context.goal or "General investigation",
            goal_type=context.goal_type,
            entity_count=len(context.entities),
            entities=entities_text,
            vehicles=vehicles_text,
            persons=persons_text,
            locations=locations_text,
            temporal=temporal_text,
            documents=docs_text,
            audio=audio_text,
            correlations=corr_text,
            gaps=gaps_text,
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

        result = json.loads(text)

        # Write discoveries back into the shared context
        context.discoveries = result.get("discoveries", [])
        context.gaps = [
            g.get("gap", "") for g in result.get("investigation_gaps", [])
        ]

        return result

    except Exception as ex:
        traceback.print_exc()
        return {
            "discoveries": [],
            "patterns": [],
            "risk_assessment": {"overall_threat_level": "unknown", "reasoning": f"Discovery failed: {str(ex)}"},
            "investigation_gaps": [],
            "unexpected_connections": [],
        }
