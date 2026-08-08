"""
AEGIS PoC — Metadata Extraction
Extracts EXIF data from images: GPS coordinates, camera info, timestamps.
"""

from __future__ import annotations
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from models import EvidenceMetadata, GPSCoordinate
import os, traceback


def _dms_to_decimal(dms, ref: str) -> float:
    """Convert EXIF GPS DMS (degrees, minutes, seconds) to decimal degrees."""
    try:
        degrees = float(dms[0])
        minutes = float(dms[1])
        seconds = float(dms[2])
        decimal = degrees + minutes / 60 + seconds / 3600
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except Exception:
        return 0.0


def _extract_gps(exif_data: dict) -> GPSCoordinate | None:
    """Extract GPS coordinates from EXIF GPSInfo."""
    gps_info = exif_data.get("GPSInfo")
    if not gps_info:
        return None

    gps_data = {}
    for tag_id, value in gps_info.items():
        tag_name = GPSTAGS.get(tag_id, str(tag_id))
        gps_data[tag_name] = value

    lat = gps_data.get("GPSLatitude")
    lat_ref = gps_data.get("GPSLatitudeRef", "N")
    lng = gps_data.get("GPSLongitude")
    lng_ref = gps_data.get("GPSLongitudeRef", "E")
    alt = gps_data.get("GPSAltitude")

    if lat and lng:
        return GPSCoordinate(
            latitude=_dms_to_decimal(lat, lat_ref),
            longitude=_dms_to_decimal(lng, lng_ref),
            altitude=float(alt) if alt else None,
        )
    return None


def extract_metadata(file_path: str) -> EvidenceMetadata:
    """Extract EXIF metadata from an image file."""
    meta = EvidenceMetadata()

    try:
        img = Image.open(file_path)
        meta.image_width = img.width
        meta.image_height = img.height

        exif_raw = img._getexif()
        if not exif_raw:
            return meta

        # Build readable dict
        exif_data = {}
        for tag_id, value in exif_raw.items():
            tag_name = TAGS.get(tag_id, str(tag_id))
            exif_data[tag_name] = value

        # GPS
        meta.gps = _extract_gps(exif_data)

        # Camera
        meta.camera_make = str(exif_data.get("Make", "")).strip() or None
        meta.camera_model = str(exif_data.get("Model", "")).strip() or None
        meta.software = str(exif_data.get("Software", "")).strip() or None

        # Timestamp
        date_str = exif_data.get("DateTimeOriginal") or exif_data.get("DateTime")
        if date_str:
            meta.timestamp = str(date_str).strip()

        # Orientation
        orient = exif_data.get("Orientation")
        if orient:
            orientations = {
                1: "Normal", 2: "Mirrored", 3: "Rotated 180°",
                4: "Mirrored vertical", 5: "Mirrored + 270°",
                6: "Rotated 270°", 7: "Mirrored + 90°", 8: "Rotated 90°",
            }
            meta.orientation = orientations.get(orient, str(orient))

        # Store safe subset of raw EXIF
        safe_raw = {}
        for k, v in exif_data.items():
            if k == "GPSInfo":
                continue
            try:
                str(v)  # test serializable
                safe_raw[k] = str(v)[:200]
            except Exception:
                pass
        meta.raw = safe_raw

    except Exception:
        traceback.print_exc()

    return meta
