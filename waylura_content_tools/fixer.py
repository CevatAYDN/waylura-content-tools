"""Transactional, safe, idempotent dataset fixer with all-or-nothing rollback."""
from __future__ import annotations

import copy
import hashlib
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
        transaction_aborted: bool = False,
        abort_reason: str | None = None,
    ):
        self.applied = applied
        self.skipped = skipped
        self.rejections = rejections
        self.modified_data = modified_data
        self.is_changed = is_changed
        self.transaction_aborted = transaction_aborted
        self.abort_reason = abort_reason

    @property
    def has_fatal_rejection(self) -> bool:
        """True if any rejection was a fatal safety abort (stale, conflict, duplicate, etc.)."""
        return self.transaction_aborted or any(r.get("is_fatal", True) for r in self.rejections)

    def to_dict(self) -> dict[str, Any]:
        return {
            "appliedCount": len(self.applied),
            "skippedCount": len(self.skipped),
            "rejectionsCount": len(self.rejections),
            "isChanged": self.is_changed,
            "transactionAborted": self.transaction_aborted,
            "abortReason": self.abort_reason,
            "hasFatalRejection": self.has_fatal_rejection,
            "applied": [p.to_dict() for p in self.applied],
            "skipped": [p.to_dict() for p in self.skipped],
            "rejections": self.rejections,
        }


def apply_proposals_safely(
    data: dict[str, Any],
    proposals: list[ProposalRecord],
    *,
    confirm_review: bool = False,
    allow_review_required: bool = False,
) -> FixResult:
    """Transactionally and surgically evaluate and apply proposals in memory.
    
    Transactional Invariants:
    1. Pre-evaluates ALL proposals in memory before applying ANY changes.
    2. If ANY fatal rejection is encountered (STALE_PROPOSAL, CONFLICTING_PROPOSALS,
       DUPLICATE_POI_ID, FORBIDDEN_FIELD, etc.), the ENTIRE transaction is ABORTED.
       Zero partial modifications are performed; modified_data is identical to input data.
    3. Only non-fatal skips (REVIEW_REQUIRED when unconfirmed, or idempotent no-ops)
       are permitted alongside safe proposals.
    4. Applies modifications only when zero fatal rejections exist across the batch.
    5. Preserves all protected metadata (ids, categories, coordinates, source IDs, statuses).
    """
    allow_manual = confirm_review or allow_review_required
    places = data.get("places")
    if not isinstance(places, list):
        return FixResult(
            applied=[],
            skipped=proposals,
            rejections=[{"reason": "INVALID_PLACES", "message": "Field 'places' must be a list", "is_fatal": True}],
            modified_data=data,
            is_changed=False,
            transaction_aborted=True,
            abort_reason="Field 'places' must be a list",
        )

    # 1. Identity & Duplicate Key Pre-check
    seen_ids: set[str] = set()
    for place in places:
        if isinstance(place, dict) and "id" in place:
            p_id = place["id"]
            if p_id in seen_ids:
                return FixResult(
                    applied=[],
                    skipped=proposals,
                    rejections=[{
                        "reason": "DUPLICATE_POI_ID",
                        "poi_id": p_id,
                        "message": f"Duplicate POI ID detected in dataset: {p_id!r}. Transaction aborted.",
                        "is_fatal": True,
                    }],
                    modified_data=data,
                    is_changed=False,
                    transaction_aborted=True,
                    abort_reason=f"Duplicate POI ID detected: {p_id}",
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

    # Build lookup by POI ID on pristine data
    poi_lookup: dict[str, dict[str, Any]] = {}
    for place in places:
        if isinstance(place, dict) and "id" in place:
            poi_lookup[place["id"]] = place

    # 3. Pre-evaluation pass: evaluate every proposal against strict rules
    fatal_rejections: list[dict[str, Any]] = []
    non_fatal_rejections: list[dict[str, Any]] = []
    skipped_proposals: list[ProposalRecord] = []
    valid_candidates: list[tuple[ProposalRecord, dict[str, Any], str]] = []

    for prop in proposals:
        key = (prop.poi_id, prop.field)

        # Rule A: Conflict detection
        if key in conflicting_keys:
            fatal_rejections.append({
                "poi_id": prop.poi_id,
                "field": prop.field,
                "reason": "CONFLICTING_PROPOSALS",
                "message": f"Conflicting proposals exist targeting {prop.poi_id}.{prop.field}",
                "is_fatal": True,
            })
            continue

        # Rule B: Target POI existence
        target_poi = poi_lookup.get(prop.poi_id)
        if target_poi is None:
            fatal_rejections.append({
                "poi_id": prop.poi_id,
                "field": prop.field,
                "reason": "POI_NOT_FOUND",
                "message": f"Target POI '{prop.poi_id}' not found in dataset",
                "is_fatal": True,
            })
            continue

        # Rule C: Allowed field constraint
        if prop.field not in ALLOWED_FIX_FIELDS:
            fatal_rejections.append({
                "poi_id": prop.poi_id,
                "field": prop.field,
                "reason": "FORBIDDEN_FIELD",
                "message": f"Field '{prop.field}' is forbidden. Only {sorted(ALLOWED_FIX_FIELDS)} may be patched.",
                "is_fatal": True,
            })
            continue

        lang = prop.field.split(".", 1)[1]
        name_obj = target_poi.get("name")
        if not isinstance(name_obj, dict):
            fatal_rejections.append({
                "poi_id": prop.poi_id,
                "field": prop.field,
                "reason": "INVALID_NAME_OBJECT",
                "message": f"POI '{prop.poi_id}' has non-dict name object",
                "is_fatal": True,
            })
            continue

        current_val = name_obj.get(lang)

        # Rule D: Stale proposal protection
        if current_val != prop.current_value:
            fatal_rejections.append({
                "poi_id": prop.poi_id,
                "field": prop.field,
                "reason": "STALE_PROPOSAL",
                "message": (
                    f"Current value {current_val!r} does not match proposal current_value "
                    f"{prop.current_value!r} for {prop.poi_id}.{prop.field}"
                ),
                "expected": prop.current_value,
                "actual": current_val,
                "is_fatal": True,
            })
            continue

        # Rule E: Review required check (Non-fatal skip if not confirmed)
        if prop.status != "AUTO_SAFE" and not allow_manual:
            reason = f"REVIEW_REQUIRED: Proposal status '{prop.status}' requires explicit human confirmation (--confirm-review)"
            skipped_proposals.append(prop)
            non_fatal_rejections.append({
                "poi_id": prop.poi_id,
                "field": prop.field,
                "reason": "REVIEW_REQUIRED",
                "message": reason,
                "is_fatal": False,
            })
            continue

        # Rule F: Idempotency (Already matches proposed value, non-fatal skip)
        if current_val == prop.proposed_value:
            skipped_proposals.append(prop)
            continue

        # Candidate passed all checks!
        valid_candidates.append((prop, name_obj, lang))

    # 4. TRANSACTIONAL ABORT: If ANY fatal rejection exists, abort ALL changes!
    if fatal_rejections:
        return FixResult(
            applied=[],
            skipped=proposals,
            rejections=fatal_rejections + non_fatal_rejections,
            modified_data=data,  # Untouched pristine data
            is_changed=False,
            transaction_aborted=True,
            abort_reason=(
                f"Transactional fix aborted: {len(fatal_rejections)} fatal rejection(s) detected. "
                f"Zero partial modifications applied."
            ),
        )

    # 5. Apply validated candidates to a deep copy of dataset
    updated_data = copy.deepcopy(data)
    updated_places = updated_data.get("places", [])
    updated_lookup = {p["id"]: p for p in updated_places if isinstance(p, dict) and "id" in p}

    applied: list[ProposalRecord] = []
    for prop, _, lang in valid_candidates:
        target_poi = updated_lookup[prop.poi_id]
        target_poi["name"][lang] = prop.proposed_value
        applied.append(prop)

    # 6. Post-verification of safety invariants
    for orig_p in places:
        p_id = orig_p.get("id")
        mod_p = updated_lookup.get(p_id)
        if mod_p:
            for protected in ("id", "category", "latitude", "longitude", "sourceId", "cityId", "countryId"):
                if orig_p.get(protected) != mod_p.get(protected):
                    raise ValueError(
                        f"SAFETY INVARIANT VIOLATION: Protected field '{protected}' on '{p_id}' was altered."
                    )
    if data.get("publicationStatus") != updated_data.get("publicationStatus"):
        raise ValueError("SAFETY INVARIANT VIOLATION: publicationStatus was altered.")

    is_changed = len(applied) > 0
    return FixResult(
        applied=applied,
        skipped=skipped_proposals,
        rejections=non_fatal_rejections,
        modified_data=updated_data,
        is_changed=is_changed,
        transaction_aborted=False,
        abort_reason=None,
    )


def atomic_write_dataset(
    target_path: Path,
    modified_data: dict[str, Any],
    is_changed: bool,
    *,
    original_bytes: bytes | None = None,
    expected_sha256: str | None = None,
) -> bool:
    """Atomically write modified_data to target_path using temp file replacement.
    
    Guarantees:
    - If is_changed is False, does NOT rewrite or touch target_path if it exists.
      Original SHA-256 and mtime are strictly preserved.
    - If expected_sha256 is provided, verifies that target_path on disk still matches
      expected_sha256 before commit. If an external process modified target_path,
      aborts to prevent TOCTOU race conditions.
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

    # TOCTOU Race Condition Check
    if expected_sha256 is not None and target_path.exists():
        current_sha = hashlib.sha256(target_path.read_bytes()).hexdigest()
        if current_sha != expected_sha256:
            raise RuntimeError(
                f"EXTERNAL_MODIFICATION_DETECTED: {target_path.name} was modified on disk "
                f"during processing (disk sha {current_sha} != expected {expected_sha256}). "
                f"Write aborted to prevent overwriting external changes."
            )

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
