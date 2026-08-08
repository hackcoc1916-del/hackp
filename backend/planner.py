"""
AEGIS PoC — Investigation Planner
Uses Gemini to generate an investigation plan from uploaded evidence.
"""

from __future__ import annotations
import json, os, traceback
from google import genai
from google.genai import types
from models import InvestigationPlan, PlanPhase, PlanTask

_client: genai.Client | None = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable not set")
        _client = genai.Client(api_key=api_key)
    return _client


PLANNER_PROMPT = """You are an investigation AI planner for a law enforcement platform called AEGIS.

Given the following evidence items uploaded to an investigation, generate an investigation plan.

Investigation Goal: {goal}

Evidence items:
{evidence_list}

Generate a JSON plan with this exact structure:
{{
  "objective": "Restate the investigation objective clearly",
  "capabilities_selected": ["vision_analysis", "metadata_extraction", "entity_extraction", ...],
  "phases": [
    {{
      "name": "Phase name (e.g., 'Evidence Intake', 'Image Analysis', 'Entity Extraction', 'Intelligence Synthesis')",
      "tasks": [
        {{
          "capability": "capability_name",
          "description": "What this task does",
          "rationale": "Why this capability was selected for this evidence"
        }}
      ]
    }}
  ]
}}

Available capabilities:
- vision_analysis: Analyze images for objects, people, vehicles, text, scenes
- metadata_extraction: Extract EXIF data including GPS, timestamps, camera info
- entity_extraction: Identify and classify entities (people, vehicles, locations, devices)
- relationship_mapping: Determine relationships between extracted entities
- timeline_reconstruction: Build chronological timeline from timestamps and events
- threat_assessment: Assess safety concerns and flag items for review
- report_generation: Generate investigation report from findings

Select only the capabilities that are appropriate for the uploaded evidence types.
Respond ONLY with valid JSON."""


async def generate_plan(
    investigation_id: str,
    goal: str,
    evidence_items: list[dict],
) -> InvestigationPlan:
    """Generate an investigation plan using Gemini."""
    try:
        client = _get_client()

        # Format evidence list
        ev_text = "\n".join([
            f"  - {e['filename']} ({e['mime_type']}, {e['file_size']} bytes)"
            for e in evidence_items
        ]) or "  (no evidence uploaded yet)"

        prompt = PLANNER_PROMPT.format(goal=goal or "General investigation", evidence_list=ev_text)

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

        phases = []
        for p in data.get("phases", []):
            tasks = []
            for t in p.get("tasks", []):
                tasks.append(PlanTask(
                    capability=t.get("capability", ""),
                    description=t.get("description", ""),
                    rationale=t.get("rationale", ""),
                ))
            phases.append(PlanPhase(name=p.get("name", ""), tasks=tasks))

        return InvestigationPlan(
            investigation_id=investigation_id,
            objective=data.get("objective", goal),
            phases=phases,
            capabilities_selected=data.get("capabilities_selected", []),
        )

    except Exception as ex:
        traceback.print_exc()
        # Fallback plan
        return InvestigationPlan(
            investigation_id=investigation_id,
            objective=goal or "Analyze uploaded evidence",
            capabilities_selected=["vision_analysis", "metadata_extraction", "entity_extraction"],
            phases=[
                PlanPhase(name="Evidence Intake", tasks=[
                    PlanTask(capability="metadata_extraction", description="Extract EXIF metadata from all images", rationale="Images may contain GPS, timestamps, and device info"),
                ]),
                PlanPhase(name="Image Analysis", tasks=[
                    PlanTask(capability="vision_analysis", description="Analyze each image for objects, people, text", rationale="Visual evidence requires forensic analysis"),
                ]),
                PlanPhase(name="Intelligence Synthesis", tasks=[
                    PlanTask(capability="entity_extraction", description="Extract and classify all detected entities", rationale="Build entity registry from analysis results"),
                    PlanTask(capability="relationship_mapping", description="Map relationships between entities", rationale="Connect people, vehicles, locations, devices"),
                    PlanTask(capability="timeline_reconstruction", description="Build timeline from timestamps", rationale="Establish chronological sequence of events"),
                ]),
            ],
        )
