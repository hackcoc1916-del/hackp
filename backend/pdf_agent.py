"""
AEGIS — PDF Document Analysis Agent
Extracts text, entities, and structured data from PDF evidence.
"""

from __future__ import annotations
import json, os, traceback
from google import genai
from models import DocumentAnalysis, DetectedEntity, EntityType

_client: genai.Client | None = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable not set")
        _client = genai.Client(api_key=api_key)
    return _client


PDF_ANALYSIS_PROMPT = """You are a forensic document analyst for a law enforcement platform called AEGIS.

Analyze the following text extracted from a PDF document and extract ALL investigatively relevant information.

Document Text:
---
{text}
---

Return a JSON response with this exact structure:
{{
  "extracted_text_summary": "Brief summary of what this document contains",
  "names": ["All person names found"],
  "dates": ["All dates found in any format"],
  "addresses": ["All physical addresses found"],
  "id_numbers": ["All ID numbers — Aadhaar, PAN, passport, license, etc."],
  "case_numbers": ["Any case/FIR/reference numbers"],
  "phone_numbers": ["All phone numbers found"],
  "emails": ["All email addresses found"],
  "organizations": ["All organizations/companies mentioned"],
  "financial_amounts": ["Any monetary amounts mentioned"],
  "vehicles": ["Any vehicle descriptions or registrations"],
  "key_facts": ["Important facts relevant to investigation"],
  "entities": [
    {{
      "type": "Person | Vehicle | Location | Device | Document | Account | PhoneNumber | Email | Financial | Organization",
      "description": "Entity description",
      "confidence": 0.0 to 1.0,
      "details": "Additional context"
    }}
  ]
}}

Be THOROUGH. Extract EVERY piece of potentially relevant information.
Respond ONLY with valid JSON. No markdown, no code fences."""


async def analyze_pdf(file_path: str) -> DocumentAnalysis:
    """Analyze a PDF document for investigative content."""
    try:
        # Try to extract text from PDF
        text = _extract_pdf_text(file_path)

        if not text.strip():
            # If text extraction fails, try sending the PDF directly to Gemini
            return await _analyze_pdf_with_gemini_direct(file_path)

        client = _get_client()
        prompt = PDF_ANALYSIS_PROMPT.format(text=text[:8000])  # Limit to avoid token overflow

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )

        resp_text = response.text.strip()
        if resp_text.startswith("```"):
            resp_text = resp_text.split("\n", 1)[1] if "\n" in resp_text else resp_text[3:]
            if resp_text.endswith("```"):
                resp_text = resp_text[:-3]
            resp_text = resp_text.strip()

        data = json.loads(resp_text)

        return DocumentAnalysis(
            extracted_text=text[:5000],
            names=data.get("names", []),
            dates=data.get("dates", []),
            addresses=data.get("addresses", []),
            id_numbers=data.get("id_numbers", []),
            case_numbers=data.get("case_numbers", []),
            phone_numbers=data.get("phone_numbers", []),
            emails=data.get("emails", []),
            summary=data.get("extracted_text_summary", ""),
        )

    except Exception as ex:
        traceback.print_exc()
        return DocumentAnalysis(
            extracted_text=f"Analysis failed: {str(ex)}",
            summary=f"PDF analysis error: {str(ex)}",
        )


def _extract_pdf_text(file_path: str) -> str:
    """Extract text from a PDF file using available libraries."""
    try:
        # Try PyPDF2 first
        import PyPDF2
        text = ""
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text
    except ImportError:
        pass

    try:
        # Try pdfplumber
        import pdfplumber
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text
    except ImportError:
        pass

    return ""


async def _analyze_pdf_with_gemini_direct(file_path: str) -> DocumentAnalysis:
    """Send PDF directly to Gemini for analysis (fallback for scanned documents)."""
    try:
        from google.genai import types
        client = _get_client()

        with open(file_path, "rb") as f:
            pdf_bytes = f.read()

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                PDF_ANALYSIS_PROMPT.format(text="[PDF sent directly — extract all text and information]"),
            ],
        )

        resp_text = response.text.strip()
        if resp_text.startswith("```"):
            resp_text = resp_text.split("\n", 1)[1] if "\n" in resp_text else resp_text[3:]
            if resp_text.endswith("```"):
                resp_text = resp_text[:-3]
            resp_text = resp_text.strip()

        data = json.loads(resp_text)

        return DocumentAnalysis(
            extracted_text=data.get("extracted_text_summary", ""),
            names=data.get("names", []),
            dates=data.get("dates", []),
            addresses=data.get("addresses", []),
            id_numbers=data.get("id_numbers", []),
            case_numbers=data.get("case_numbers", []),
            phone_numbers=data.get("phone_numbers", []),
            emails=data.get("emails", []),
            summary=data.get("extracted_text_summary", ""),
        )

    except Exception as ex:
        traceback.print_exc()
        return DocumentAnalysis(summary=f"Direct PDF analysis failed: {str(ex)}")


def document_to_entities(analysis: DocumentAnalysis) -> list[DetectedEntity]:
    """Convert document analysis to graph-compatible entities."""
    entities = []

    for name in analysis.names:
        entities.append(DetectedEntity(
            type=EntityType.PERSON,
            description=name,
            confidence=0.7,
            details="Extracted from document",
        ))

    for phone in analysis.phone_numbers:
        entities.append(DetectedEntity(
            type=EntityType.PHONE_NUMBER,
            description=phone,
            confidence=0.9,
            details="Extracted from document",
        ))

    for email in analysis.emails:
        entities.append(DetectedEntity(
            type=EntityType.EMAIL,
            description=email,
            confidence=0.9,
            details="Extracted from document",
        ))

    for addr in analysis.addresses:
        entities.append(DetectedEntity(
            type=EntityType.LOCATION,
            description=addr,
            confidence=0.7,
            details="Address from document",
        ))

    for id_num in analysis.id_numbers:
        entities.append(DetectedEntity(
            type=EntityType.DOCUMENT,
            description=id_num,
            confidence=0.85,
            details="ID number from document",
        ))

    return entities
