"""
AEGIS — Lead Generator Agent
Proactively generates investigation leads and next-action suggestions.
"""

from __future__ import annotations
import json, os, traceback
from google import genai
from models import InvestigationLead, LeadPriority

_client: genai.Client | None = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable not set")
        _client = genai.Client(api_key=api_key)
    return _client


LEAD_PROMPT = """You are an expert criminal investigator AI for a law enforcement platform called AEGIS.

Based on the following investigation data, generate ACTIONABLE investigation leads — specific next steps the investigator should take.

Investigation:
- Name: {inv_name}
- Goal: {inv_goal}
- Priority: {inv_priority}

Evidence Analyzed:
{evidence_summary}

Entities Discovered:
{entities_summary}

Current Findings:
{findings_summary}

OSINT Intelligence:
{osint_summary}

Return a JSON response with this exact structure:
{{
  "leads": [
    {{
      "title": "Short, actionable title",
      "description": "Detailed description of what to investigate and why",
      "priority": "critical | high | medium | low",
      "confidence": 0.0 to 1.0,
      "suggested_action": "Specific action the investigator should take RIGHT NOW",
      "category": "vehicle_trace | cctv_review | witness_interview | document_request | financial_trace | phone_trace | location_search | identity_verification | forensic_analysis | surveillance | coordination",
      "reasoning": "Why this lead is important and how it connects to the investigation"
    }}
  ],
  "investigation_gaps": [
    {{
      "gap": "What information is missing",
      "impact": "How filling this gap would help the investigation",
      "suggested_source": "Where to get this information"
    }}
  ],
  "priority_sequence": ["Ordered list of lead titles showing recommended investigation sequence"]
}}

RULES:
- Generate 5-10 leads minimum
- Leads must be SPECIFIC and ACTIONABLE (not vague like "investigate further")
- Consider Indian law enforcement context (RTO, CCTV networks, toll plazas, petrol pumps)
- Think about what an experienced investigator would do next
- Consider time-sensitivity (CCTV footage may be overwritten)
- Include both obvious and non-obvious leads
- Prioritize leads that could produce results quickly

Respond ONLY with valid JSON. No markdown, no code fences."""


async def generate_leads(
    investigation_context: dict,
    evidence_items: list[dict],
    entities: list[dict],
    findings: list[dict],
    osint_data: dict | None = None,
) -> list[InvestigationLead]:
    """Generate investigation leads based on all available data."""
    try:
        client = _get_client()

        # Format summaries
        evidence_text = "\n".join([
            f"  - {e.get('filename', 'Unknown')} ({e.get('mime_type', '')}) — "
            f"GPS: {e.get('gps', 'N/A')}, Time: {e.get('timestamp', 'N/A')}"
            for e in evidence_items
        ]) or "  (no evidence)"

        entities_text = "\n".join([
            f"  - [{e.get('type', 'Unknown')}] {e.get('description', '')} "
            f"(Confidence: {e.get('confidence', 0):.0%})"
            for e in entities
        ]) or "  (no entities)"

        findings_text = "\n".join([
            f"  - {f.get('title', 'Finding')}: {f.get('description', '')[:150]}"
            for f in findings
        ]) or "  (no findings yet)"

        osint_text = "Not available"
        if osint_data:
            reports = osint_data.get("intelligence_reports", [])
            if reports:
                osint_text = "\n".join([
                    f"  - {r.get('entity', 'Unknown')}: "
                    + ", ".join([f.get('information', '')[:100] for f in r.get('findings', [])[:3]])
                    for r in reports
                ])

        prompt = LEAD_PROMPT.format(
            inv_name=investigation_context.get('name', 'Unknown'),
            inv_goal=investigation_context.get('goal', 'General investigation'),
            inv_priority=investigation_context.get('priority', 'medium'),
            evidence_summary=evidence_text,
            entities_summary=entities_text,
            findings_summary=findings_text,
            osint_summary=osint_text,
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
        leads = []

        for lead_data in data.get("leads", []):
            priority_map = {
                "critical": LeadPriority.CRITICAL,
                "high": LeadPriority.HIGH,
                "medium": LeadPriority.MEDIUM,
                "low": LeadPriority.LOW,
            }
            leads.append(InvestigationLead(
                investigation_id=investigation_context.get('id', ''),
                title=lead_data.get("title", ""),
                description=lead_data.get("description", ""),
                priority=priority_map.get(lead_data.get("priority", "medium"), LeadPriority.MEDIUM),
                confidence=float(lead_data.get("confidence", 0.5)),
                suggested_action=lead_data.get("suggested_action", ""),
                category=lead_data.get("category", ""),
            ))

        return leads

    except Exception as ex:
        traceback.print_exc()
        return [InvestigationLead(
            investigation_id=investigation_context.get('id', ''),
            title="Lead generation failed",
            description=f"Error: {str(ex)}",
            priority=LeadPriority.LOW,
            confidence=0.0,
            suggested_action="Retry lead generation or manually assess evidence",
            category="error",
        )]
