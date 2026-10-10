"""Multilingual POI name quality, script leakage, and semantic auditor."""
from __future__ import annotations

import re
from typing import Any
from .unicode_utils import (
    contains_cjk,
    contains_cyrillic,
    contains_latin,
    is_nfc,
    normalize_nfc,
)

# Canonical dictionary for well-known verified monuments and temples
CANONICAL_NAMES: dict[str, dict[str, str]] = {
    "poi-tky-sensoji": {
        "tr": "Sensō-ji Tapınağı",
        "en": "Sensō-ji",
        "local": "金龍山 浅草寺",
    },
    "poi-kyo-kinkakuji": {
        "tr": "Kinkaku-ji (Altın Köşk Tapınağı)",
        "en": "Kinkaku-ji",
        "local": "金閣寺",
    },
    "poi-kyo-ginkakuji": {
        "tr": "Ginkaku-ji (Gümüş Köşk Tapınağı)",
        "en": "Ginkakuji",
        "local": "銀閣寺",
    },
    "poi-kyo-ninnaji": {
        "tr": "Ninna-ji Tapınağı",
        "en": "Ninna temple",
        "local": "仁和寺",
    },
    "poi-kyo-toji": {
        "tr": "Tō-ji Tapınağı",
        "en": "East Temple",
        "local": "東寺",
    },
    "poi-kyo-sanjusangendo": {
        "tr": "Sanjūsangen-dō Tapınağı",
        "en": "Sanjūsangen-dō",
        "local": "三十三間堂",
    },
    "poi-ant-hadrians-gate": {
        "tr": "Hadrian Kapısı (Üçkapılar)",
        "en": "Hadrian's Gate",
        "local": "Hadrian Kapısı (Üçkapılar)",
    },
    "poi-ant-kaleici-museum": {
        "tr": "Suna & İnan Kıraç Kaleiçi Müzesi",
        "en": "Suna & İnan Kıraç Kaleiçi Museum",
        "local": "Suna & İnan Kıraç Kaleiçi Müzesi",
    },
    "poi-ant-archaeology-museum": {
        "tr": "Antalya Arkeoloji Müzesi",
        "en": "Antalya Archaeological Museum",
        "local": "Antalya Arkeoloji Müzesi",
    },
    "poi-ant-ataturk-house": {
        "tr": "Antalya Atatürk Evi Müzesi",
        "en": "Antalya Atatürk House Museum",
        "local": "Antalya Atatürk Evi Müzesi",
    },
}

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
    ):
        self.severity = severity
        self.issue_type = issue_type
        self.message = message
        self.poi_id = poi_id
        self.field = field
        self.current_value = current_value
        self.proposed_value = proposed_value
        self.review_required = review_required

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
        }

    def __repr__(self) -> str:
        return f"<{self.severity}: {self.issue_type} on {self.poi_id}.{self.field} - {self.message}>"


def audit_place_names(places: list[dict[str, Any]]) -> list[NameAuditIssue]:
    """Audit all place name objects and identify quality issues."""
    issues: list[NameAuditIssue] = []

    for place in places:
        poi_id = place.get("id") or "unknown"
        name = place.get("name")
        if not isinstance(name, dict):
            continue

        # Check canonical match
        canonical = CANONICAL_NAMES.get(poi_id)

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

            # 1. Unicode NFC check
            if not is_nfc(val):
                normalized = normalize_nfc(val)
                issues.append(
                    NameAuditIssue(
                        "WARNING",
                        "UNICODE_NFC_DENORMALIZED",
                        f"String in {field_name} is not in Unicode NFC normalization form",
                        poi_id=poi_id,
                        field=field_name,
                        current_value=val,
                        proposed_value=normalized,
                        review_required=False,
                    )
                )

            # 2. Cyrillic script leakage check
            if contains_cyrillic(val):
                proposed = None
                if canonical and lang in canonical:
                    proposed = canonical[lang]
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
                    )
                )

            # 3. CJK leakage check in Turkish or English fields
            if lang in ("tr", "en") and contains_cjk(val):
                proposed = None
                if canonical and lang in canonical:
                    proposed = canonical[lang]
                issues.append(
                    NameAuditIssue(
                        "ERROR",
                        "UNTRANSLATED_CJK_IN_TARGET_LANGUAGE",
                        f"Untranslated CJK characters found in {field_name}: {val!r}",
                        poi_id=poi_id,
                        field=field_name,
                        current_value=val,
                        proposed_value=proposed,
                        review_required=(proposed is None),
                    )
                )

            # 4. Canonical discrepancy check
            if canonical and lang in canonical:
                expected_canonical = canonical[lang]
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
