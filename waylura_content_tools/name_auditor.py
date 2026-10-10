"""Multilingual POI name quality, script leakage, and semantic auditor."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from .unicode_utils import (
    contains_cjk,
    contains_cyrillic,
    is_nfc,
    normalize_nfc,
)

DATA_PATH = Path(__file__).resolve().parent / "data" / "canonical_names_v1.json"


def load_canonical_registry() -> dict[str, dict[str, Any]]:
    """Load canonical dictionary with aliases and source provenance."""
    if not DATA_PATH.is_file():
        return {}
    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        entities = data.get("entities", {})
        registry: dict[str, dict[str, Any]] = {}
        for primary_id, record in entities.items():
            registry[primary_id] = record
            for alias in record.get("aliases", []):
                registry[alias] = record
        return registry
    except Exception:
        return {}


CANONICAL_REGISTRY = load_canonical_registry()

SEMANTIC_KEYWORD_RULES = [
    {
        "id_token": "-station",
        "expected_terms": ["istasyon", "station", "gar", "metro", "durak", "eki"],
        "mismatch_message": "POI ID indicates transit station, but name lacks station/istasyon keyword",
    },
    {
        "id_token": "-museum",
        "expected_terms": ["müze", "museum", "sanat", "art", "galeri", "gallery", "hakubutsukan"],
        "mismatch_message": "POI ID indicates museum, but name lacks museum/müze keyword",
    },
    {
        "id_token": "-airport",
        "expected_terms": ["havalimanı", "havaalanı", "airport", "kūkō"],
        "mismatch_message": "POI ID indicates airport, but name lacks airport/havalimanı keyword",
    },
]


class NameAuditIssue:
    def __init__(
        self,
        severity: str,
        issue_type: str,
        message: str,
        poi_id: str,
        field: str,
        current_value: str,
        proposed_value: str | None = None,
        review_required: bool = False,
        source: str | None = None,
    ):
        self.severity = severity
        self.issue_type = issue_type
        self.message = message
        self.poi_id = poi_id
        self.field = field
        self.current_value = current_value
        self.proposed_value = proposed_value
        self.review_required = review_required
        self.source = source

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "issueType": self.issue_type,
            "message": self.message,
            "poiId": self.poi_id,
            "field": self.field,
            "currentValue": self.current_value,
            "proposedValue": self.proposed_value,
            "reviewRequired": self.review_required,
            "source": self.source,
        }

    def __repr__(self) -> str:
        return f"<{self.severity}: {self.issue_type} on {self.poi_id}.{self.field} - {self.message}>"


def audit_place_names(places: list[dict[str, Any]]) -> list[NameAuditIssue]:
    """Audit all place name objects and identify quality issues."""
    issues: list[NameAuditIssue] = []

    for place in places:
        poi_id = place.get("id") or "unknown"
        city_id = place.get("cityId") or ""
        country_id = place.get("countryId") or ""
        is_japan = "jp" in country_id or city_id.startswith("jp-")

        name = place.get("name")
        if not isinstance(name, dict):
            continue

        canonical_record = CANONICAL_REGISTRY.get(poi_id)
        canonical_names = canonical_record.get("names", {}) if canonical_record else {}
        canonical_source = canonical_record.get("source") if canonical_record else None

        for lang in ("tr", "en", "local"):
            val = name.get(lang)
            field_name = f"name.{lang}"

            if not isinstance(val, str) or not val.strip():
                issues.append(
                    NameAuditIssue(
                        "ERROR",
                        "EMPTY_NAME_FIELD",
                        f"Name field '{lang}' is empty or missing",
                        poi_id=poi_id,
                        field=field_name,
                        current_value=str(val),
                        review_required=True,
                    )
                )
                continue

            # 1. Unicode NFC normalization check
            if not is_nfc(val):
                normalized = normalize_nfc(val)
                issues.append(
                    NameAuditIssue(
                        "WARNING",
                        "UNICODE_NFC_DENORMALIZED",
                        f"String in {field_name} is not in Unicode NFC form",
                        poi_id=poi_id,
                        field=field_name,
                        current_value=val,
                        proposed_value=normalized,
                        review_required=False,
                    )
                )

            # 2. Cyrillic script leakage check
            # Cyrillic in Turkish, English, or Japanese places is an anomaly/scraping artifact
            if contains_cyrillic(val):
                # If city is not in a Cyrillic locale, this is foreign leakage
                is_cyrillic_locale = "ru" in country_id or "ua" in country_id or "bg" in country_id
                if not is_cyrillic_locale or lang in ("tr", "en"):
                    proposed = canonical_names.get(lang)
                    issues.append(
                        NameAuditIssue(
                            "ERROR",
                            "CYRILLIC_SCRIPT_LEAKAGE",
                            f"Unexpected Cyrillic script found in {field_name}: {val!r}",
                            poi_id=poi_id,
                            field=field_name,
                            current_value=val,
                            proposed_value=proposed,
                            review_required=(proposed is None),
                            source=canonical_source,
                        )
                    )

            # 3. CJK script leakage check in target languages
            # CJK is LEGITIMATE in local for Japan, but an error in tr or en
            if lang in ("tr", "en") and contains_cjk(val):
                proposed = canonical_names.get(lang)
                issues.append(
                    NameAuditIssue(
                        "ERROR",
                        "UNTRANSLATED_CJK_IN_TARGET_LANGUAGE",
                        f"Untranslated CJK characters found in target language {field_name}: {val!r}",
                        poi_id=poi_id,
                        field=field_name,
                        current_value=val,
                        proposed_value=proposed,
                        review_required=(proposed is None),
                        source=canonical_source,
                    )
                )

            # 4. Canonical discrepancy check
            if canonical_names and lang in canonical_names:
                expected_canonical = canonical_names[lang]
                if val != expected_canonical:
                    issues.append(
                        NameAuditIssue(
                            "INFO",
                            "CANONICAL_NAME_DISCREPANCY",
                            f"Name {val!r} differs from verified canonical name {expected_canonical!r}",
                            poi_id=poi_id,
                            field=field_name,
                            current_value=val,
                            proposed_value=expected_canonical,
                            review_required=False,
                            source=canonical_source,
                        )
                    )

        # 5. Semantic consistency between POI ID and Name
        combined_names = f"{name.get('tr', '')} {name.get('en', '')} {name.get('local', '')}".lower()
        for rule in SEMANTIC_KEYWORD_RULES:
            if rule["id_token"] in poi_id.lower():
                matches = any(term in combined_names for term in rule["expected_terms"])
                if not matches:
                    issues.append(
                        NameAuditIssue(
                            "WARNING",
                            "POI_ID_NAME_SEMANTIC_MISMATCH",
                            rule["mismatch_message"],
                            poi_id=poi_id,
                            field="name",
                            current_value=f"tr={name.get('tr')}, en={name.get('en')}",
                            proposed_value=None,
                            review_required=True,
                        )
                    )

    return issues
