"""
AEGIS — Vehicle Forensics Agent
Specialized Gemini-powered agent for vehicle identification and analysis.
"""

from __future__ import annotations
import json, os, traceback
from google import genai
from google.genai import types
from models import VehicleAnalysis, DetectedEntity, EntityType

_client: genai.Client | None = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable not set")
        _client = genai.Client(api_key=api_key)
    return _client


VEHICLE_PROMPT = """You are an expert forensic vehicle analyst for a law enforcement investigation platform called AEGIS.

Analyze this image specifically for VEHICLE intelligence. Focus EXCLUSIVELY on vehicles visible in the image.

Return a JSON response with this exact structure:
{
  "vehicles": [
    {
      "brand": "Manufacturer name (e.g., Toyota, Maruti Suzuki, Hyundai, Honda)",
      "model": "Specific model name (e.g., Innova, Swift, Creta, City)",
      "color": "Exact color description",
      "year_estimate": "Estimated year or year range",
      "registration_plate": "License plate text if visible, or empty string",
      "plate_confidence": 0.0 to 1.0,
      "vehicle_type": "SUV | Sedan | Hatchback | Truck | Motorcycle | Auto-Rickshaw | Bus | Van | Pickup",
      "damage": ["List any visible damage"],
      "modifications": ["List any aftermarket modifications"],
      "direction_of_travel": "Direction if determinable, or empty string",
      "speed_estimate": "Moving fast / slow / stationary / unknown",
      "position_in_image": "Where in the image this vehicle appears"
    }
  ],
  "scene_context": "Brief description of the scene (road type, lighting, weather, time of day)",
  "nearby_landmarks": ["Any identifiable landmarks, signs, buildings near vehicles"],
  "camera_angle": "Angle of the camera relative to the vehicles"
}

Be extremely thorough with registration plates — attempt to read partial plates even if blurry.
For Indian vehicles, look for state codes (MH, DL, KA, TN, etc.).
Identify ALL vehicles in the image, not just the most prominent one.

Respond ONLY with valid JSON. No markdown, no code fences."""


async def analyze_vehicles(file_path: str) -> list[VehicleAnalysis]:
    """Analyze an image for detailed vehicle intelligence."""
    try:
        client = _get_client()

        with open(file_path, "rb") as f:
            image_bytes = f.read()

        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}
        mime = mime_map.get(ext, "image/jpeg")

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime),
                VEHICLE_PROMPT,
            ],
        )

        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)
        results = []

        for v in data.get("vehicles", []):
            results.append(VehicleAnalysis(
                brand=v.get("brand", ""),
                model=v.get("model", ""),
                color=v.get("color", ""),
                year_estimate=v.get("year_estimate", ""),
                registration_plate=v.get("registration_plate", ""),
                plate_confidence=float(v.get("plate_confidence", 0)),
                vehicle_type=v.get("vehicle_type", ""),
                damage=v.get("damage", []),
                modifications=v.get("modifications", []),
                direction_of_travel=v.get("direction_of_travel", ""),
                speed_estimate=v.get("speed_estimate", ""),
            ))

        return results

    except Exception as ex:
        traceback.print_exc()
        return [VehicleAnalysis(
            brand=f"Analysis failed: {str(ex)}",
        )]


def vehicle_to_entities(vehicles: list[VehicleAnalysis]) -> list[DetectedEntity]:
    """Convert vehicle analysis results to graph-compatible entities."""
    entities = []
    for v in vehicles:
        # Vehicle entity
        desc = f"{v.color} {v.brand} {v.model}".strip()
        if v.vehicle_type:
            desc = f"{v.vehicle_type}: {desc}"
        entities.append(DetectedEntity(
            type=EntityType.VEHICLE,
            description=desc,
            confidence=0.8,
            details=f"Year: {v.year_estimate}, Direction: {v.direction_of_travel}, Speed: {v.speed_estimate}",
        ))

        # Number plate entity
        if v.registration_plate:
            entities.append(DetectedEntity(
                type=EntityType.NUMBER_PLATE,
                description=v.registration_plate,
                confidence=v.plate_confidence,
                details=f"Plate from {desc}",
            ))

    return entities
