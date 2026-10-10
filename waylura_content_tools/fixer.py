"""Safe, idempotent, surgical dataset fixer."""
from __future__ import annotations

import copy
from typing import Any
from .proposer import ProposalRecord


class FixResult:
    def __init__(
        self,
        applied: list[ProposalRecord],
        skipped: list[ProposalRecord],
        modified_data: dict[str, Any],
        is_changed: bool,
    ):
        self.applied = applied
        self.skipped = skipped
        self.modified_data = modified_data
        self.is_changed = is_changed

    def to_dict(self) -> dict[str, Any]:
        return {
            "appliedCount": len(self.applied),
            "skippedCount": len(self.skipped),
            "isChanged": self.is_changed,
            "applied": [p.to_dict() for p in self.applied],
            "skipped": [p.to_dict() for p in self.skipped],
        }


def apply_proposals_safely(
    data: dict[str, Any],
    proposals: list[ProposalRecord],
    *,
    allow_review_required: bool = False,
) -> FixResult:
    """Surgically and idempotently apply safe proposals to dataset in memory.
    
    Strict constraints:
    - Never touch place 'id', 'category', 'latitude', 'longitude', 'sourceId'.
    - Never alter publicationStatus or approval flags.
    - Only modify target string fields in place['name'][subfield].
    - Skip proposals marked REVIEW_REQUIRED unless allow_review_required=True.
    """
    updated_data = copy.deepcopy(data)
    places = updated_data.get("places", [])
    if not isinstance(places, list):
        return FixResult([], proposals, data, False)

    # Build lookup by POI ID
    poi_lookup: dict[str, dict[str, Any]] = {}
    for place in places:
        if isinstance(place, dict) and "id" in place:
            poi_lookup[place["id"]] = place

    applied: list[ProposalRecord] = []
    skipped: list[ProposalRecord] = []

    for prop in proposals:
        if prop.status == "REVIEW_REQUIRED" and not allow_review_required:
            skipped.append(prop)
            continue

        target_poi = poi_lookup.get(prop.poi_id)
        if target_poi is None:
            skipped.append(prop)
            continue

        # Surgical update in name field
        if prop.field.startswith("name."):
            lang = prop.field.split(".", 1)[1]
            name_obj = target_poi.get("name")
            if isinstance(name_obj, dict):
                current_val = name_obj.get(lang)
                if current_val != prop.proposed_value:
                    # Update ONLY the specific language string
                    name_obj[lang] = prop.proposed_value
                    applied.append(prop)
                else:
                    # Already up to date (idempotent)
                    skipped.append(prop)
            else:
                skipped.append(prop)
        else:
            # Any non-name field proposal is rejected by safety policy
            skipped.append(prop)

    is_changed = len(applied) > 0
    return FixResult(applied, skipped, updated_data, is_changed)
