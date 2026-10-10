"""Schema specifications and definitions for travel datasets."""
from __future__ import annotations

import re
from typing import Any

POI_ID_PATTERN = re.compile(r"^poi-[a-z0-9]+-[a-z0-9\-]+$")
COUNTRY_ID_PATTERN = re.compile(r"^country-[a-z0-9\-]+$")
CITY_ID_PATTERN = re.compile(r"^[a-z0-9\-]+$")
SOURCE_ID_PATTERN = re.compile(r"^src-[a-z0-9\-]+$")

ALLOWED_CATEGORIES = {
    "history",
    "food",
    "culture",
    "transit",
    "nature",
    "shopping",
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
