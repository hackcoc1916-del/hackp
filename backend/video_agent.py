"""
AEGIS — Video Analysis Agent
Extracts key frames from video and analyzes them using Gemini Vision.
"""

from __future__ import annotations
import json, os, traceback, tempfile
from google import genai
from google.genai import types
from models import VisionAnalysis, DetectedEntity, EntityType

_client: genai.Client | None = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable not set")
        _client = genai.Client(api_key=api_key)
    return _client


VIDEO_PROMPT = """You are a forensic video analyst for a law enforcement platform called AEGIS.

Analyze this video evidence thoroughly. Focus on:

1. **People**: Identify all persons visible — physical descriptions, clothing, behavior, distinguishing features
2. **Vehicles**: All vehicles — make, model, color, registration plates, direction of movement
3. **Objects**: Weapons, bags, devices, tools, anything unusual
4. **Locations**: Scene identification — indoor/outdoor, landmarks, street signs, business names
5. **Actions**: What is happening — movements, interactions, suspicious activities
6. **Timeline**: Sequence of events observed in the video

Return a JSON response with this exact structure:
{
  "description": "Overall scene description",
  "duration_estimate": "Estimated video duration",
  "key_moments": [
    {
      "timestamp": "Approximate time in video",
      "description": "What happens",
      "entities_visible": ["List of entities visible at this moment"]
    }
  ],
  "entities": [
    {
      "type": "Person | Vehicle | Object | Text | Location | Device",
      "description": "Detailed description",
      "confidence": 0.0 to 1.0,
      "details": "Identifying features, colors, text content",
      "first_appearance": "When first seen in the video",
      "last_appearance": "When last seen"
    }
  ],
  "movement_patterns": [
    {
      "entity": "Who/what is moving",
      "direction": "Direction of movement",
      "speed": "fast | walking | slow | stationary",
      "path": "Description of movement path"
    }
  ],
  "safety_flags": ["Any concerning content"],
  "requires_review": true or false,
  "review_reason": "Why review is recommended",
  "reasoning": "Step-by-step analysis process",
  "scene_context": {
    "lighting": "Daylight / Night / Artificial",
    "weather": "If outdoors",
    "location_type": "Street / Building / Park / etc.",
    "camera_type": "CCTV / Dashcam / Phone / etc."
  }
}

Respond ONLY with valid JSON. No markdown, no code fences."""


async def analyze_video(file_path: str) -> VisionAnalysis:
    """Analyze a video file using Gemini multimodal."""
    try:
        client = _get_client()

        with open(file_path, "rb") as f:
            video_bytes = f.read()

        # Determine mime type
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {
            ".mp4": "video/mp4", ".avi": "video/x-msvideo", ".mov": "video/quicktime",
            ".mkv": "video/x-matroska", ".webm": "video/webm", ".flv": "video/x-flv",
            ".wmv": "video/x-ms-wmv", ".3gp": "video/3gpp",
        }
        mime = mime_map.get(ext, "video/mp4")

        # Send video directly to Gemini (supports up to ~20MB)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Part.from_bytes(data=video_bytes, mime_type=mime),
                VIDEO_PROMPT,
            ],
        )

        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)

        # Map to VisionAnalysis model (reuse existing model for compatibility)
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

    except Exception as ex:
        traceback.print_exc()
        return VisionAnalysis(
            description=f"Video analysis failed: {str(ex)}",
            requires_review=True,
            review_reason=f"Error: {str(ex)}",
        )
