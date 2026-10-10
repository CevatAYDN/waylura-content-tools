"""Dataset structural and relational validator."""
from __future__ import annotations

from typing import Any
from .schema import (
    ALLOWED_CATEGORIES,
    COUNTRY_ID_PATTERN,
    POI_ID_PATTERN,
    REQUIRED_NAME_FIELDS,
    REQUIRED_POI_FIELDS,
    validate_coordinates,
)


class ValidationFinding:
    def __init__(
        self,
        severity: str,
        issue_type: str,
        message: str,
        poi_id: str | None = None,
        field: str | None = None,
    ):
        self.severity = severity  # 'ERROR', 'WARNING', 'INFO'
        self.issue_type = issue_type
        self.message = message
        self.poi_id = poi_id
        self.field = field

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "issueType": self.issue_type,
            "message": self.message,
            "poiId": self.poi_id,
            "field": self.field,
        }

    def __repr__(self) -> str:
        loc = f" [{self.poi_id} -> {self.field}]" if self.poi_id else ""
        return f"<{self.severity}: {self.issue_type}{loc} - {self.message}>"


def validate_dataset(data: dict[str, Any], known_sources: set[str] | None = None) -> list[ValidationFinding]:
    """Validate a full content dataset."""
    findings: list[ValidationFinding] = []

    if not isinstance(data, dict):
        return [ValidationFinding("ERROR", "INVALID_ROOT_TYPE", "Dataset root must be a JSON object")]

    schema_version = data.get("schemaVersion")
    if schema_version != 1:
        findings.append(
            ValidationFinding(
                "ERROR", "UNSUPPORTED_SCHEMA_VERSION", f"Expected schemaVersion=1, got {schema_version}"
            )
        )

    country_id = data.get("countryId")
    if not isinstance(country_id, str) or not COUNTRY_ID_PATTERN.match(country_id):
        findings.append(
            ValidationFinding(
                "ERROR", "INVALID_COUNTRY_ID", f"Invalid countryId format: {country_id!r}", field="countryId"
            )
        )

    places = data.get("places")
    if not isinstance(places, list):
        findings.append(
            ValidationFinding("ERROR", "MISSING_PLACES_LIST", "Field 'places' must be a list of POI objects")
        )
        return findings

    seen_poi_ids: set[str] = set()
    all_poi_ids: set[str] = set()

    # Pre-scan IDs for duplicate and orphan candidate checking
    for idx, place in enumerate(places):
        if isinstance(place, dict) and isinstance(place.get("id"), str):
            p_id = place["id"]
            if p_id in seen_poi_ids:
                findings.append(
                    ValidationFinding(
                        "ERROR",
                        "DUPLICATE_POI_ID",
                        f"Duplicate POI ID found at index {idx}: {p_id}",
                        poi_id=p_id,
                        field="id",
                    )
                )
            seen_poi_ids.add(p_id)
            all_poi_ids.add(p_id)

    # Validate each place
    for idx, place in enumerate(places):
        if not isinstance(place, dict):
            findings.append(
                ValidationFinding("ERROR", "INVALID_PLACE_OBJECT", f"Item at index {idx} is not an object")
            )
            continue

        poi_id = place.get("id")
        if not isinstance(poi_id, str) or not POI_ID_PATTERN.match(poi_id):
            findings.append(
                ValidationFinding(
                    "ERROR",
                    "INVALID_POI_ID_FORMAT",
                    f"POI ID at index {idx} has invalid format: {poi_id!r}",
                    poi_id=str(poi_id) if poi_id else None,
                    field="id",
                )
            )

        city_id = place.get("cityId")
        if not isinstance(city_id, str) or not city_id:
            findings.append(
                ValidationFinding(
                    "ERROR", "MISSING_CITY_ID", f"Place at index {idx} is missing cityId", poi_id=poi_id, field="cityId"
                )
            )

        # Check required fields
        missing_fields = REQUIRED_POI_FIELDS - set(place.keys())
        if missing_fields:
            findings.append(
                ValidationFinding(
                    "ERROR",
                    "MISSING_REQUIRED_FIELDS",
                    f"POI missing required fields: {sorted(missing_fields)}",
                    poi_id=poi_id,
                )
            )

        # Category check
        category = place.get("category")
        if category not in ALLOWED_CATEGORIES:
            findings.append(
                ValidationFinding(
                    "ERROR",
                    "INVALID_CATEGORY",
                    f"Category {category!r} is not allowed. Must be one of {sorted(ALLOWED_CATEGORIES)}",
                    poi_id=poi_id,
                    field="category",
                )
            )

        # Coordinate checks
        lat_errors = validate_coordinates(place.get("latitude"), place.get("longitude"))
        for err in lat_errors:
            findings.append(ValidationFinding("ERROR", "INVALID_COORDINATES", err, poi_id=poi_id, field="coordinates"))

        # Name structure check
        name = place.get("name")
        if not isinstance(name, dict):
            findings.append(
                ValidationFinding(
                    "ERROR", "INVALID_NAME_BLOCK", "Field 'name' must be an object with tr, en, local", poi_id=poi_id, field="name"
                )
            )
        else:
            missing_names = REQUIRED_NAME_FIELDS - set(name.keys())
            if missing_names:
                findings.append(
                    ValidationFinding(
                        "ERROR",
                        "MISSING_LANGUAGE_FIELDS",
                        f"Name object missing language fields: {sorted(missing_names)}",
                        poi_id=poi_id,
                        field="name",
                    )
                )

        # Orphan sourceId check
        source_id = place.get("sourceId")
        if known_sources is not None and isinstance(source_id, str):
            if source_id not in known_sources:
                findings.append(
                    ValidationFinding(
                        "WARNING",
                        "ORPHAN_SOURCE_ID",
                        f"Referenced sourceId {source_id!r} not found in registered sources",
                        poi_id=poi_id,
                        field="sourceId",
                    )
                )

        # Orphan canonicalNowCandidateId check
        candidate_id = place.get("canonicalNowCandidateId")
        if candidate_id is not None:
            if not isinstance(candidate_id, str) or candidate_id not in all_poi_ids:
                findings.append(
                    ValidationFinding(
                        "WARNING",
                        "ORPHAN_NOW_CANDIDATE_ID",
                        f"canonicalNowCandidateId {candidate_id!r} does not resolve to any known POI",
                        poi_id=poi_id,
                        field="canonicalNowCandidateId",
                    )
                )

    return findings
