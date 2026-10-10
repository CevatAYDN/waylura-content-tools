"""Safe, idempotent, surgical dataset fixer with conflict and stale proposal protection."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any
from .proposer import ProposalRecord

ALLOWED_FIX_FIELDS = {"name.tr", "name.en", "name.local"}


class FixResult:
    def __init__(
        self,
        applied: list[ProposalRecord],
        skipped: list[ProposalRecord],
        rejections: list[dict[str, Any]],
        modified_data: dict[str, Any],
        is_changed: bool,
    ):
        self.applied = applied
        self.skipped = skipped
        self.rejections = rejections
        self.modified_data = modified_data
        self.is_changed = is_changed

    def to_dict(self) -> dict[str, Any]:
        return {
            "appliedCount": len(self.applied),
            "skippedCount": len(self.skipped),
            "rejectionsCount": len(self.rejections),
            "isChanged": self.is_changed,
            "applied": [p.to_dict() for p in self.applied],
            "skipped": [p.to_dict() for p in self.skipped],
            "rejections": self.rejections,
        }


def apply_proposals_safely(
    data: dict[str, Any],
    proposals: list[ProposalRecord],
    *,
    confirm_review: bool = False,
    allow_review_required: bool = False,  # backwards compatibility alias
) -> FixResult:
    """Surgically and idempotently apply safe proposals to dataset in memory.
    
    Strict safety invariants:
    - Rejects datasets containing duplicate POI IDs.
    - Rejects modifications to any field outside ALLOWED_FIX_FIELDS ({'name.tr', 'name.en', 'name.local'}).
    - Rejects stale proposals where proposal.current_value != current_field_value.
    - Rejects conflicting proposals targeting the same POI and field.
    - Rejects non-AUTO_SAFE proposals without explicit, traceable human review confirmation (confirm_review=True).
    - Never touch place 'id', 'category', 'latitude', 'longitude', 'sourceId', 'cityId', 'countryId', 'provenance'.
    - Never alter publicationStatus, editorialReview, or approval flags.
    - Maintains zero change if applied count is 0.
    """
    allow_manual = confirm_review or allow_review_required
    updated_data = copy.deepcopy(data)
    places = updated_data.get("places", [])
    if not isinstance(places, list):
        return FixResult([], proposals, [{"reason": "INVALID_PLACES", "message": "places must be a JSON array"}], data, False)

    # 1. Identity & Duplicate Key Pre-check
    seen_ids: set[str] = set()
    for place in places:
        if isinstance(place, dict) and "id" in place:
            p_id = place["id"]
            if p_id in seen_ids:
                return FixResult(
                    [],
                    proposals,
                    [{
                        "reason": "DUPLICATE_POI_ID",
                        "poi_id": p_id,
                        "message": f"Duplicate POI ID detected in dataset: {p_id!r}. Fix aborted.",
                    }],
                    data,
                    False,
                )
            seen_ids.add(p_id)

    # 2. Conflict detection pre-scan across proposals
    target_proposals: dict[tuple[str, str], list[ProposalRecord]] = {}
    for p in proposals:
        target_proposals.setdefault((p.poi_id, p.field), []).append(p)

    conflicting_keys: set[tuple[str, str]] = set()
    for key, p_list in target_proposals.items():
        if len(p_list) > 1:
            unique_proposed = {p.proposed_value for p in p_list}
            if len(unique_proposed) > 1:
                conflicting_keys.add(key)
        for p in p_list:
            if "CONFLICT" in p.status:
                conflicting_keys.add(key)

    # Build lookup by POI ID
    poi_lookup: dict[str, dict[str, Any]] = {}
    for place in places:
        if isinstance(place, dict) and "id" in place:
            poi_lookup[place["id"]] = place

    applied: list[ProposalRecord] = []
    skipped: list[ProposalRecord] = []
    rejections: list[dict[str, Any]] = []

    # Process proposals deterministically
    for prop in proposals:
        key = (prop.poi_id, prop.field)

        # A. Check for conflicting proposals
        if key in conflicting_keys:
            reason = f"CONFLICT: Conflicting proposals exist for {prop.poi_id}.{prop.field}"
            skipped.append(prop)
            rejections.append({
                "poi_id": prop.poi_id,
                "field": prop.field,
                "reason": "CONFLICTING_PROPOSALS",
                "message": reason,
            })
            continue

        # B. Check for target POI existence
        target_poi = poi_lookup.get(prop.poi_id)
        if target_poi is None:
            reason = f"NOT_FOUND: POI '{prop.poi_id}' not found in dataset"
            skipped.append(prop)
            rejections.append({
                "poi_id": prop.poi_id,
                "field": prop.field,
                "reason": "POI_NOT_FOUND",
                "message": reason,
            })
            continue

        # C. Check allowed field constraint: ONLY ALLOWED_FIX_FIELDS are permitted
        if prop.field not in ALLOWED_FIX_FIELDS:
            reason = f"FORBIDDEN_FIELD: Only fields in {sorted(ALLOWED_FIX_FIELDS)} may be modified (attempted {prop.field})"
            skipped.append(prop)
            rejections.append({
                "poi_id": prop.poi_id,
                "field": prop.field,
                "reason": "FORBIDDEN_FIELD",
                "message": reason,
            })
            continue

        lang = prop.field.split(".", 1)[1]
        name_obj = target_poi.get("name")
        if not isinstance(name_obj, dict):
            reason = f"INVALID_NAME_OBJECT: POI '{prop.poi_id}' has non-dict name field"
            skipped.append(prop)
            rejections.append({
                "poi_id": prop.poi_id,
                "field": prop.field,
                "reason": "INVALID_NAME_OBJECT",
                "message": reason,
            })
            continue

        current_val = name_obj.get(lang)

        # D. Stale proposal protection: current value must match prop.current_value exactly
        if current_val != prop.current_value:
            reason = (
                f"STALE_PROPOSAL: Current value {current_val!r} does not match proposal "
                f"current_value {prop.current_value!r} for {prop.poi_id}.{prop.field}"
            )
            skipped.append(prop)
            rejections.append({
                "poi_id": prop.poi_id,
                "field": prop.field,
                "reason": "STALE_PROPOSAL",
                "message": reason,
                "expected": prop.current_value,
                "actual": current_val,
            })
            continue

        # E. Review required protection: non-AUTO_SAFE proposals require explicit human confirmation
        if prop.status != "AUTO_SAFE" and not allow_manual:
            reason = f"REVIEW_REQUIRED: Proposal status '{prop.status}' requires explicit human confirmation (--confirm-review)"
            skipped.append(prop)
            rejections.append({
                "poi_id": prop.poi_id,
                "field": prop.field,
                "reason": "REVIEW_REQUIRED",
                "message": reason,
            })
            continue

        # F. Idempotency: already has proposed value
        if current_val == prop.proposed_value:
            skipped.append(prop)
            continue

        # G. Apply surgical edit
        name_obj[lang] = prop.proposed_value
        applied.append(prop)

    # 3. Post-verification of safety invariants
    for orig_p in data.get("places", []):
        p_id = orig_p.get("id")
        mod_p = poi_lookup.get(p_id)
        if mod_p:
            for protected in ("id", "category", "latitude", "longitude", "sourceId", "cityId", "countryId"):
                if orig_p.get(protected) != mod_p.get(protected):
                    raise ValueError(
                        f"SAFETY INVARIANT VIOLATION: Protected field '{protected}' on '{p_id}' "
                        f"was altered from {orig_p.get(protected)!r} to {mod_p.get(protected)!r}."
                    )
    if data.get("publicationStatus") != updated_data.get("publicationStatus"):
        raise ValueError("SAFETY INVARIANT VIOLATION: publicationStatus was altered.")

    is_changed = len(applied) > 0
    return FixResult(applied, skipped, rejections, updated_data, is_changed)


def atomic_write_dataset(
    target_path: Path,
    modified_data: dict[str, Any],
    is_changed: bool,
    *,
    original_bytes: bytes | None = None,
) -> bool:
    """Atomically write modified_data to target_path using temp file replacement.
    
    Guarantees:
    - If is_changed is False, does NOT rewrite or touch target_path if it exists.
      Original SHA-256 and mtime are strictly preserved.
    - If is_changed is True, writes to a temp file in target_path.parent, flushes, fsyncs,
      and atomically replaces target_path with os.replace.
    - If an error occurs during write/flush/replace, the temporary file is removed and
      the original file remains untouched (rollback).
    
    Returns True if target_path was written/replaced, False if untouched.
    """
    if not is_changed:
        if target_path.exists():
            return False
        if original_bytes is not None:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(original_bytes)
            return True

    target_path = target_path.resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    temp_file = target_path.with_name(f".{target_path.name}.tmp.{os.getpid()}")
    try:
        content = json.dumps(modified_data, indent=2, ensure_ascii=False) + "\n"
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_file, target_path)
        return True
    except Exception:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass
        raise
