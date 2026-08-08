"""
AEGIS PoC — Report Generation
Uses Gemini to generate a professional investigation report.
"""

from __future__ import annotations
import json, os, traceback
from google import genai
from models import Report, Finding, EvidenceItem, TimelineEvent, GraphNode, GraphEdge
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


REPORT_PROMPT = """You are generating an investigation report for a law enforcement intelligence platform called AEGIS.

Write a professional forensic investigation report in Markdown format based on the following data.

## Investigation
- Name: {inv_name}
- ID: {inv_id}
- Goal: {inv_goal}
- Lead Investigator: {inv_lead}
- Classification: {inv_class}

## Evidence Analyzed ({ev_count} items)
{evidence_list}

## Entities Discovered ({entity_count})
{entities_list}

## Relationships ({edge_count})
{relationships_list}

## Timeline Events ({timeline_count})
{timeline_list}

## AI Findings ({finding_count})
{findings_list}

---

Write the report with these sections:
1. **Executive Summary** — concise overview of the investigation and key conclusions
2. **Evidence Inventory** — table of all evidence items with integrity status
3. **Key Findings** — each finding with confidence, evidence citations, and reasoning
4. **Entity Analysis** — all discovered entities and their relationships
5. **Timeline of Events** — chronological sequence of key events
6. **Recommendations** — actionable next steps for the investigation
7. **Appendix: AI Methodology** — brief explanation of capabilities used

Rules:
- Every claim MUST cite specific evidence (e.g., [EV-xxxx: filename.jpg])
- Include confidence scores for all AI-generated findings
- Be professional and suitable for law enforcement review
- Use Markdown formatting with headers, tables, and bullet points"""


async def generate_report(investigation_id: str) -> Report:
    """Generate a complete investigation report."""
    inv = state.investigations.get(investigation_id)
    if not inv:
        return Report(investigation_id=investigation_id, title="Error", content="Investigation not found")

    evidence_items = state.get_evidence_for_investigation(investigation_id)
    findings_list = state.get_findings_for_investigation(investigation_id)
    timeline = state.get_timeline_for_investigation(investigation_id)
    nodes = list(state.graph_nodes.values())
    edges = list(state.graph_edges.values())

    # Format evidence
    ev_text = "\n".join([
        f"- [{e.id}: {e.filename}] ({e.mime_type}, SHA-256: {e.sha256[:16]}...)"
        for e in evidence_items
    ]) or "No evidence"

    # Format entities
    ent_text = "\n".join([
        f"- {n.label} (Type: {n.type.value}, Confidence: {n.confidence:.0%})"
        for n in nodes
    ]) or "No entities"

    # Format relationships
    rel_text = "\n".join([
        f"- {_node_label(e.source_id)} → [{e.relationship}] → {_node_label(e.target_id)} (Confidence: {e.confidence:.0%})"
        for e in edges
    ]) or "No relationships"

    # Format timeline
    tl_text = "\n".join([
        f"- [{t.timestamp}] {t.title}: {t.description}"
        for t in timeline
    ]) or "No timeline events"

    # Format findings
    fnd_text = "\n".join([
        f"- [{f.id}] {f.title} (Confidence: {f.confidence:.0%}, Status: {f.status.value})\n  Reasoning: {f.reasoning[:200]}"
        for f in findings_list
    ]) or "No findings"

    prompt = REPORT_PROMPT.format(
        inv_name=inv.name, inv_id=inv.id, inv_goal=inv.goal,
        inv_lead=inv.lead_investigator, inv_class=inv.classification,
        ev_count=len(evidence_items), evidence_list=ev_text,
        entity_count=len(nodes), entities_list=ent_text,
        edge_count=len(edges), relationships_list=rel_text,
        timeline_count=len(timeline), timeline_list=tl_text,
        finding_count=len(findings_list), findings_list=fnd_text,
    )

    try:
        client = _get_client()
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )

        report = Report(
            investigation_id=investigation_id,
            title=f"Investigation Report — {inv.name}",
            content=response.text,
        )
        state.reports[report.id] = report
        return report

    except Exception as ex:
        traceback.print_exc()
        report = Report(
            investigation_id=investigation_id,
            title=f"Investigation Report — {inv.name}",
            content=f"# Report Generation Failed\n\nError: {str(ex)}\n\nPlease retry report generation.",
        )
        state.reports[report.id] = report
        return report


def _node_label(node_id: str) -> str:
    """Get label for a node by ID."""
    node = state.graph_nodes.get(node_id)
    return node.label if node else node_id
