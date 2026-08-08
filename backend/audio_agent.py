"""
AEGIS — Audio Analysis Agent
Analyzes audio evidence using Gemini multimodal capabilities.
"""

from __future__ import annotations
import json, os, traceback
from google import genai
from google.genai import types
from models import AudioAnalysis, DetectedEntity, EntityType

_client: genai.Client | None = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable not set")
        _client = genai.Client(api_key=api_key)
    return _client


AUDIO_PROMPT = """You are a forensic audio analyst for a law enforcement platform called AEGIS.

Analyze this audio recording and extract ALL investigatively relevant information.

Return a JSON response with this exact structure:
{
  "transcript": "Full transcription of any speech",
  "speaker_count": 0,
  "keywords": ["Important words and phrases"],
  "emotion": "Overall emotional tone (calm, agitated, threatening, distressed, etc.)",
  "language": "Primary language spoken",
  "background_sounds": ["Identifiable background sounds (traffic, crowd, machinery, etc.)"],
  "entities_mentioned": [
    {
      "type": "Person | Location | Vehicle | PhoneNumber | Organization",
      "description": "What was mentioned",
      "confidence": 0.0 to 1.0,
      "details": "Context of the mention"
    }
  ],
  "summary": "Brief investigative summary of the audio content",
  "timestamps_of_interest": [
    {
      "time": "Approximate timestamp",
      "event": "What happens at this time"
    }
  ]
}

Respond ONLY with valid JSON. No markdown, no code fences."""


async def analyze_audio(file_path: str) -> AudioAnalysis:
    """Analyze an audio file using Gemini multimodal."""
    try:
        client = _get_client()

        with open(file_path, "rb") as f:
            audio_bytes = f.read()

        # Determine mime type
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {
            ".mp3": "audio/mp3", ".wav": "audio/wav", ".ogg": "audio/ogg",
            ".m4a": "audio/mp4", ".flac": "audio/flac", ".aac": "audio/aac",
            ".wma": "audio/x-ms-wma",
        }
        mime = mime_map.get(ext, "audio/mpeg")

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Part.from_bytes(data=audio_bytes, mime_type=mime),
                AUDIO_PROMPT,
            ],
        )

        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)

        return AudioAnalysis(
            transcript=data.get("transcript", ""),
            speaker_count=int(data.get("speaker_count", 0)),
            keywords=data.get("keywords", []),
            emotion=data.get("emotion", ""),
            language=data.get("language", ""),
            duration_seconds=0.0,  # Would need ffprobe for accurate duration
            background_sounds=data.get("background_sounds", []),
        )

    except Exception as ex:
        traceback.print_exc()
        return AudioAnalysis(
            transcript=f"Audio analysis failed: {str(ex)}",
        )


def audio_to_entities(analysis: AudioAnalysis) -> list[DetectedEntity]:
    """Convert audio analysis to graph-compatible entities."""
    entities = []

    # Add keywords as text entities
    for keyword in analysis.keywords[:10]:
        entities.append(DetectedEntity(
            type=EntityType.TEXT,
            description=keyword,
            confidence=0.6,
            details=f"Keyword from audio transcript (language: {analysis.language})",
        ))

    return entities
