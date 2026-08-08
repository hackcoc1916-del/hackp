"""
AEGIS PoC — Vision Analysis Module
Uses Google Gemini multimodal to analyze evidence images.
"""

from __future__ import annotations
import json, os, traceback
from google import genai
from google.genai import types
from models import VisionAnalysis, DetectedEntity, EntityType

# Initialize client (API key from environment)
_client: genai.Client | None = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable not set")
        _client = genai.Client(api_key=api_key)
    return _client


VISION_PROMPT = """You are a forensic image analyst for a law enforcement investigation intelligence platform called AEGIS.

Analyze this image thoroughly and return a structured JSON response with these exact fields:

{
  "description": "Detailed scene description — what you see, the environment, lighting, notable features",
  "entities": [
    {
      "type": "Person | Vehicle | Object | Text | Location | Device | Document",
      "description": "What you observed",
      "confidence": 0.0 to 1.0,
      "details": "Any identifying details — colors, text content, distinguishing features"
    }
  ],
  "safety_flags": ["List any concerning content types detected, or empty array"],
  "requires_review": true or false,
  "review_reason": "Why human review is recommended (if applicable), or empty string",
  "reasoning": "Step-by-step explanation of your analysis process"
}

Be thorough. Identify ALL entities — people, vehicles (make, model, color if possible), readable text, devices, documents, locations. Rate confidence honestly. Flag anything that warrants human investigator attention.

Respond ONLY with valid JSON. No markdown, no code fences, no commentary."""


async def analyze_image(file_path: str) -> VisionAnalysis:
    """Send an image to Gemini for forensic analysis."""
    try:
        client = _get_client()

        # Read image bytes
        with open(file_path, "rb") as f:
            image_bytes = f.read()

        # Determine mime type
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}
        mime = mime_map.get(ext, "image/jpeg")

        # Call Gemini
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime),
                VISION_PROMPT,
            ],
        )

        # Parse JSON response
        text = response.text.strip()
        # Strip code fences if Gemini wraps in ```json ... ```
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)

        # Map to model
        entities = []
        for e in data.get("entities", []):
            entity_type = EntityType.OBJECT
            raw_type = e.get("type", "Object").strip()
            for et in EntityType:
                if et.value.lower() == raw_type.lower():
                    entity_type = et
                    break
            entities.append(DetectedEntity(
                type=entity_type,
                description=e.get("description", ""),
                confidence=float(e.get("confidence", 0)),
                details=e.get("details", ""),
            ))

        return VisionAnalysis(
            description=data.get("description", ""),
            entities=entities,
            safety_flags=data.get("safety_flags", []),
            requires_review=data.get("requires_review", False),
            review_reason=data.get("review_reason", ""),
            reasoning=data.get("reasoning", ""),
        )

    except json.JSONDecodeError:
        # If Gemini returns non-JSON, wrap raw text
        return VisionAnalysis(
            description=f"Raw AI response (non-JSON): {response.text[:500] if response else 'No response'}",
            requires_review=True,
            review_reason="AI returned unstructured response",
        )
    except Exception as ex:
        traceback.print_exc()
        return VisionAnalysis(
            description=f"Analysis failed: {str(ex)}",
            requires_review=True,
            review_reason=f"Error during analysis: {str(ex)}",
        )
