"""Schema specifications and definitions for travel datasets."""
from __future__ import annotations

import re
from typing import Any

POI_ID_PATTERN = re.compile(r"^poi-[a-z0-9]+-[a-z0-9\-]+$")
COUNTRY_ID_PATTERN = re.compile(r"^country-[a-z0-9\-]+$")
CITY_ID_PATTERN = re.compile(r"^[a-z0-9\-]+$")
SOURCE_ID_PATTERN = re.compile(r"^src-[a-z0-9\-]+$")
CANONICAL_CANDIDATE_ID_PATTERN = re.compile(
    r"^[a-z]{2}-[a-z0-9\-]+-(node|way|relation|place|area)-[0-9]+$"
)

SCHEMA_WAYLURA_C0 = "waylura-c0"
SCHEMA_FLAT_POI = "flat-poi"
SUPPORTED_SCHEMAS = {SCHEMA_WAYLURA_C0, SCHEMA_FLAT_POI}

ALLOWED_CATEGORIES = {
    # Waylura C0 production categories
    "history",
    "food",
    "nature",
    "shopping",
    "transit",
    "viewpoint",
    "family",
    "essentials",
    # Extended travel guide categories
    "culture",
    "accommodation",
    "activity",
    "attraction",
}

REQUIRED_POI_FIELDS = {
    "id",
    "cityId",
    "countryId",
    "name",
    "category",
    "latitude",
    "longitude",
    "sourceId",
}

REQUIRED_NAME_FIELDS = {
    "tr",
    "en",
    "local",
}

REQUIRED_COUNTRY_FIELDS = {
    "id",
    "name",
}


def detect_schema(data: dict[str, Any]) -> str:
    """Explicitly detect schema variant without silent conversion."""
    if not isinstance(data, dict):
        return "unknown"
    if "country" in data and isinstance(data["country"], dict):
        return SCHEMA_WAYLURA_C0
    if "countryId" in data and isinstance(data["countryId"], str):
        return SCHEMA_FLAT_POI
    return "unknown"


def validate_coordinates(lat: Any, lon: Any) -> list[str]:
    """Validate latitude and longitude ranges."""
    errors = []
    if not isinstance(lat, (int, float)) or isinstance(lat, bool):
        errors.append(f"Latitude must be a float, got {type(lat).__name__}")
    elif not (-90.0 <= lat <= 90.0):
        errors.append(f"Latitude {lat} out of range [-90.0, 90.0]")

    if not isinstance(lon, (int, float)) or isinstance(lon, bool):
        errors.append(f"Longitude must be a float, got {type(lon).__name__}")
    elif not (-180.0 <= lon <= 180.0):
        errors.append(f"Longitude {lon} out of range [-180.0, 180.0]")

    return errors
