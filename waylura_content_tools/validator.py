"""Dataset structural and relational validator."""
from __future__ import annotations

from typing import Any
from .schema import (
    ALLOWED_CATEGORIES,
    CANONICAL_CANDIDATE_ID_PATTERN,
    CITY_ID_PATTERN,
    COUNTRY_ID_PATTERN,
    POI_ID_PATTERN,
    REQUIRED_NAME_FIELDS,
    REQUIRED_POI_FIELDS,
    SCHEMA_FLAT_POI,
    SCHEMA_WAYLURA_C0,
    detect_schema,
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


def validate_dataset(
    data: dict[str, Any],
    *,
    known_sources: set[str] | None = None,
    schema_adapter: str | None = None,
    expected_schema: str | None = None,
    require_sources: bool = False,
) -> list[ValidationFinding]:
    """Validate full content dataset against explicit schema contracts."""
    findings: list[ValidationFinding] = []

    if not isinstance(data, dict):
        return [ValidationFinding("ERROR", "INVALID_ROOT_TYPE", "Dataset root must be a JSON object")]

    detected = detect_schema(data)
    target_schema = expected_schema or (None if schema_adapter == "auto" else schema_adapter)
    if target_schema and target_schema != detected:
        findings.append(
            ValidationFinding(
                "ERROR",
                "SCHEMA_MISMATCH",
                f"Expected explicit schema {target_schema!r}, but detected {detected!r}",
            )
        )
        return findings

    schema_version = data.get("schemaVersion")
    if schema_version != 1:
        findings.append(
            ValidationFinding(
                "ERROR",
                "UNSUPPORTED_SCHEMA_VERSION",
                f"Expected schemaVersion=1, got {schema_version}",
            )
        )

    # 1. Determine Country ID and Country Object based on schema
    country_id: str | None = None
    if detected == SCHEMA_WAYLURA_C0:
        country_obj = data.get("country")
        if not isinstance(country_obj, dict):
            findings.append(
                ValidationFinding("ERROR", "MISSING_COUNTRY_BLOCK", "Schema waylura-c0 requires 'country' object")
            )
        else:
            country_id = country_obj.get("id")
            if not isinstance(country_id, str) or not COUNTRY_ID_PATTERN.match(country_id):
                findings.append(
                    ValidationFinding(
                        "ERROR",
                        "INVALID_COUNTRY_ID",
                        f"country.id has invalid format: {country_id!r}",
                        field="country.id",
                    )
                )
            if known_sources is not None and "sourceId" in country_obj:
                c_src = country_obj["sourceId"]
                if c_src not in known_sources:
                    findings.append(
                        ValidationFinding(
                            "ERROR" if require_sources else "WARNING",
                            "ORPHAN_SOURCE_ID",
                            f"country.sourceId {c_src!r} not found in registered sources",
                            field="country.sourceId",
                        )
                    )

    elif detected == SCHEMA_FLAT_POI:
        country_id = data.get("countryId")
        if not isinstance(country_id, str) or not COUNTRY_ID_PATTERN.match(country_id):
            findings.append(
                ValidationFinding(
                    "ERROR",
                    "INVALID_COUNTRY_ID",
                    f"countryId has invalid format: {country_id!r}",
                    field="countryId",
                )
            )
    else:
        findings.append(
            ValidationFinding(
                "ERROR",
                "UNKNOWN_SCHEMA",
                "Dataset matches neither 'waylura-c0' (country object) nor 'flat-poi' (countryId string)",
            )
        )

    # 2. Check Cities if present (Waylura C0)
    city_ids: set[str] = set()
    cities = data.get("cities")
    if isinstance(cities, list):
        for idx, city in enumerate(cities):
            if not isinstance(city, dict):
                findings.append(ValidationFinding("ERROR", "INVALID_CITY_OBJECT", f"City at index {idx} is not object"))
                continue
            c_id = city.get("id")
            if not isinstance(c_id, str) or not CITY_ID_PATTERN.match(c_id):
                findings.append(ValidationFinding("ERROR", "INVALID_CITY_ID", f"City id invalid: {c_id!r}"))
            else:
                city_ids.add(c_id)
            if country_id and city.get("countryId") != country_id:
                findings.append(
                    ValidationFinding(
                        "ERROR",
                        "CITY_COUNTRY_MISMATCH",
                        f"City {c_id} countryId {city.get('countryId')!r} does not match country {country_id!r}",
                    )
                )
            if known_sources is not None and "sourceId" in city:
                city_src = city["sourceId"]
                if city_src not in known_sources:
                    findings.append(
                        ValidationFinding(
                            "ERROR" if require_sources else "WARNING",
                            "ORPHAN_SOURCE_ID",
                            f"City {c_id} sourceId {city_src!r} not in registered sources",
                        )
                    )

    # 3. Source Inventory contract enforcement
    if known_sources is None:
        findings.append(
            ValidationFinding(
                "ERROR" if require_sources else "WARNING",
                "SOURCES_UNCHECKED",
                "Sources inventory is required in strict publication mode, but was not provided"
                if require_sources
                else "No registered sources inventory provided; sourceId relationships are unverified (not marked as pass)",
            )
        )

    # 4. Check Places
    places = data.get("places")
    if not isinstance(places, list):
        findings.append(
            ValidationFinding("ERROR", "MISSING_PLACES_LIST", "Field 'places' must be a list of POI objects")
        )
        return findings

    seen_poi_ids: set[str] = set()
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

        # Check country relationship
        if country_id and place.get("countryId") != country_id:
            findings.append(
                ValidationFinding(
                    "ERROR",
                    "POI_COUNTRY_MISMATCH",
                    f"POI countryId {place.get('countryId')!r} does not match dataset country {country_id!r}",
                    poi_id=poi_id,
                    field="countryId",
                )
            )

        # Check city relationship
        city_id = place.get("cityId")
        if not isinstance(city_id, str) or not city_id:
            findings.append(
                ValidationFinding(
                    "ERROR", "MISSING_CITY_ID", f"Place at index {idx} is missing cityId", poi_id=poi_id, field="cityId"
                )
            )
        elif city_ids and city_id not in city_ids:
            findings.append(
                ValidationFinding(
                    "ERROR",
                    "UNKNOWN_CITY_REFERENCE",
                    f"POI references cityId {city_id!r} not defined in dataset cities list",
                    poi_id=poi_id,
                    field="cityId",
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

        # Source verification against known_sources inventory
        source_id = place.get("sourceId")
        if known_sources is not None and isinstance(source_id, str):
            if source_id not in known_sources:
                findings.append(
                    ValidationFinding(
                        "ERROR" if require_sources else "WARNING",
                        "ORPHAN_SOURCE_ID",
                        f"Referenced sourceId {source_id!r} not found in registered sources inventory",
                        poi_id=poi_id,
                        field="sourceId",
                    )
                )

        # canonicalNowCandidateId validation (validate format; NEVER resolve against places[].id)
        candidate_id = place.get("canonicalNowCandidateId")
        if candidate_id is not None:
            if not isinstance(candidate_id, str) or not CANONICAL_CANDIDATE_ID_PATTERN.match(candidate_id):
                findings.append(
                    ValidationFinding(
                        "WARNING",
                        "INVALID_CANDIDATE_ID_FORMAT",
                        f"canonicalNowCandidateId {candidate_id!r} has invalid upstream candidate format",
                        poi_id=poi_id,
                        field="canonicalNowCandidateId",
                    )
                )

    return findings
