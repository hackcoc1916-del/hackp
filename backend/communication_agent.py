"""
AEGIS — Communication Agent
Auto-generates official investigation documents using Gemini.
Drafts emails, court orders, FIRs, BOLO notices, and internal reports.
"""

from __future__ import annotations
import json, os, traceback
from google import genai
from models import DraftDocument, DocumentType

_client: genai.Client | None = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable not set")
        _client = genai.Client(api_key=api_key)
    return _client


DOCUMENT_PROMPTS = {
    DocumentType.EMAIL_MVD: """Generate a formal email to the Motor Vehicle Department requesting vehicle registration information.

Investigation Details:
{context}

Vehicle Information:
{vehicle_info}

The email should:
- Be addressed to "The Regional Transport Officer"
- Reference the investigation case number
- Request complete registration details for the vehicle(s) identified
- Include legal basis for the request (Section 134 of Motor Vehicles Act, 1988)
- Be professional and concise
- Include sender as "Investigation Officer, {lead_investigator}"

Return the email in markdown format with proper headers (To, From, Subject, Date, Body).""",

    DocumentType.COURT_ORDER: """Draft a court order application for obtaining digital records.

Investigation Details:
{context}

Required Records:
{records_needed}

The application should:
- Be addressed to the appropriate Magistrate
- Reference relevant sections of CrPC and IT Act
- Clearly specify what records are needed and from whom
- Justify the necessity for the investigation
- Be formatted as a formal legal document

Return in markdown format.""",

    DocumentType.FIR_DRAFT: """Draft a First Information Report (FIR) based on the investigation findings.

Investigation Details:
{context}

Key Findings:
{findings}

The FIR should:
- Follow standard Indian police FIR format
- Include sections for: Complainant details, Incident details, Property involved, Suspect details
- Reference applicable IPC sections based on the evidence
- Be professional and factual

Return in markdown format.""",

    DocumentType.BOLO: """Generate a Be On the Lookout (BOLO) notice for law enforcement circulation.

Investigation Details:
{context}

Subject Information:
{subject_info}

The BOLO should:
- Be concise and immediately actionable
- Include physical descriptions (person/vehicle)
- Include last known location and direction of travel
- Include any identifying features (tattoos, scars, modifications)
- Include contact information for the investigating officer
- Use URGENT formatting

Return in markdown format.""",

    DocumentType.INTERNAL_REPORT: """Generate an internal investigation status report.

Investigation Details:
{context}

Current Findings:
{findings}

Timeline:
{timeline}

The report should:
- Summarize current investigation status
- List key findings and their confidence levels
- Identify gaps in the investigation
- Recommend next steps
- Be suitable for briefing senior officers

Return in markdown format.""",

    DocumentType.EVIDENCE_LOG: """Generate a formal evidence log document.

Investigation Details:
{context}

Evidence Items:
{evidence_list}

The log should:
- List all evidence with chain of custody information
- Include integrity verification (SHA-256 hashes)
- Note any GPS/timestamp metadata
- Categorize evidence by type
- Be suitable for court submission

Return in markdown format.""",
}


async def generate_document(
    doc_type: DocumentType,
    investigation_context: dict,
    specific_data: dict,
) -> DraftDocument:
    """Generate an official document based on investigation data."""
    try:
        client = _get_client()

        # Get the appropriate prompt template
        prompt_template = DOCUMENT_PROMPTS.get(
            doc_type,
            DOCUMENT_PROMPTS[DocumentType.INTERNAL_REPORT]
        )

        # Build context string
        context = (
            f"Case: {investigation_context.get('name', 'Unknown')}\n"
            f"ID: {investigation_context.get('id', 'N/A')}\n"
            f"Goal: {investigation_context.get('goal', 'General investigation')}\n"
            f"Lead Investigator: {investigation_context.get('lead_investigator', 'SSA Sarah Chen')}\n"
            f"Classification: {investigation_context.get('classification', 'Law Enforcement Sensitive')}\n"
            f"Priority: {investigation_context.get('priority', 'Medium')}"
        )

        # Format the prompt with available data
        prompt = prompt_template.format(
            context=context,
            lead_investigator=investigation_context.get('lead_investigator', 'Investigation Officer'),
            vehicle_info=specific_data.get('vehicle_info', 'Not available'),
            records_needed=specific_data.get('records_needed', 'Not specified'),
            findings=specific_data.get('findings', 'No findings yet'),
            subject_info=specific_data.get('subject_info', 'Not available'),
            timeline=specific_data.get('timeline', 'No timeline data'),
            evidence_list=specific_data.get('evidence_list', 'No evidence logged'),
        )

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )

        # Determine title and recipient
        titles = {
            DocumentType.EMAIL_MVD: "Request for Vehicle Registration Details",
            DocumentType.COURT_ORDER: "Application for Court Order — Digital Records",
            DocumentType.FIR_DRAFT: "First Information Report (Draft)",
            DocumentType.BOLO: "BOLO Notice — Active Investigation",
            DocumentType.INTERNAL_REPORT: f"Investigation Status Report — {investigation_context.get('name', 'Case')}",
            DocumentType.EVIDENCE_LOG: "Evidence Chain of Custody Log",
            DocumentType.EMAIL_INFO_REQUEST: "Information Request",
            DocumentType.WITNESS_NOTICE: "Witness Summons Notice",
        }

        recipients = {
            DocumentType.EMAIL_MVD: "Regional Transport Officer",
            DocumentType.COURT_ORDER: "Magistrate Court",
            DocumentType.FIR_DRAFT: "Station House Officer",
            DocumentType.BOLO: "All Units",
            DocumentType.INTERNAL_REPORT: "Supervising Officer",
            DocumentType.EVIDENCE_LOG: "Evidence Custodian",
            DocumentType.EMAIL_INFO_REQUEST: "Relevant Authority",
            DocumentType.WITNESS_NOTICE: "Witness",
        }

        return DraftDocument(
            investigation_id=investigation_context.get('id', ''),
            doc_type=doc_type,
            title=titles.get(doc_type, "Investigation Document"),
            recipient=recipients.get(doc_type, ""),
            content=response.text,
        )

    except Exception as ex:
        traceback.print_exc()
        return DraftDocument(
            investigation_id=investigation_context.get('id', ''),
            doc_type=doc_type,
            title=f"Document Generation Failed",
            content=f"# Error\n\nFailed to generate document: {str(ex)}",
        )


async def auto_generate_documents(
    investigation_context: dict,
    entities: list[dict],
    findings: list[dict],
    evidence_items: list[dict],
    timeline: list[dict],
) -> list[DraftDocument]:
    """Automatically determine which documents to generate based on investigation data."""
    documents = []

    # Check for vehicles → generate MVD email
    vehicle_entities = [e for e in entities if e.get('type') in ('Vehicle', 'NumberPlate')]
    if vehicle_entities:
        vehicle_info = "\n".join([
            f"- {e.get('description', 'Unknown')} (Confidence: {e.get('confidence', 0):.0%})"
            for e in vehicle_entities
        ])
        doc = await generate_document(
            DocumentType.EMAIL_MVD,
            investigation_context,
            {"vehicle_info": vehicle_info},
        )
        documents.append(doc)

    # Check for persons/suspects → generate BOLO
    person_entities = [e for e in entities if e.get('type') == 'Person']
    if person_entities:
        subject_info = "\n".join([
            f"- {e.get('description', 'Unknown')} — {e.get('details', 'No details')}"
            for e in person_entities
        ])
        doc = await generate_document(
            DocumentType.BOLO,
            investigation_context,
            {"subject_info": subject_info},
        )
        documents.append(doc)

    # Always generate internal report
    findings_text = "\n".join([
        f"- {f.get('title', 'Finding')}: {f.get('description', '')[:200]}"
        for f in findings
    ]) or "No findings yet"
    timeline_text = "\n".join([
        f"- [{t.get('timestamp', '')}] {t.get('title', '')}"
        for t in timeline
    ]) or "No timeline events"

    doc = await generate_document(
        DocumentType.INTERNAL_REPORT,
        investigation_context,
        {"findings": findings_text, "timeline": timeline_text},
    )
    documents.append(doc)

    # Always generate evidence log
    evidence_text = "\n".join([
        f"- {e.get('filename', 'Unknown')} ({e.get('mime_type', '')}, SHA-256: {e.get('sha256', 'N/A')[:16]}...)"
        for e in evidence_items
    ]) or "No evidence"
    doc = await generate_document(
        DocumentType.EVIDENCE_LOG,
        investigation_context,
        {"evidence_list": evidence_text},
    )
    documents.append(doc)

    return documents
