"""Generates deterministic, structured fix proposals."""
from __future__ import annotations

import difflib
from typing import Any
from .name_auditor import NameAuditIssue


class ProposalRecord:
    def __init__(
        self,
        poi_id: str,
        field: str,
        current_value: str,
        proposed_value: str,
        reason: str,
        status: str,  # 'AUTO_SAFE' or 'REVIEW_REQUIRED'
    ):
        self.poi_id = poi_id
        self.field = field
        self.current_value = current_value
        self.proposed_value = proposed_value
        self.reason = reason
        self.status = status

    @property
    def diff(self) -> str:
        diff_lines = list(
            difflib.unified_diff(
                [self.current_value + "\n"],
                [self.proposed_value + "\n"],
                fromfile=f"{self.poi_id}.{self.field} (current)",
                tofile=f"{self.poi_id}.{self.field} (proposed)",
            )
        )
        return "".join(diff_lines).strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "poiId": self.poi_id,
            "field": self.field,
            "currentValue": self.current_value,
            "proposedValue": self.proposed_value,
            "reason": self.reason,
            "status": self.status,
            "diff": self.diff,
        }


def generate_proposals(issues: list[NameAuditIssue]) -> list[ProposalRecord]:
    """Generate deterministic proposals from name audit issues."""
    proposals: list[ProposalRecord] = []
    seen: set[tuple[str, str]] = set()

    for issue in issues:
        if issue.proposed_value is None or issue.proposed_value == issue.current_value:
            continue

        key = (issue.poi_id, issue.field)
        if key in seen:
            continue
        seen.add(key)

        status = "REVIEW_REQUIRED" if issue.review_required else "AUTO_SAFE"
        proposals.append(
            ProposalRecord(
                poi_id=issue.poi_id,
                field=issue.field,
                current_value=issue.current_value,
                proposed_value=issue.proposed_value,
                reason=issue.message,
                status=status,
            )
        )

    # Sort deterministically
    proposals.sort(key=lambda p: (p.poi_id, p.field))
    return proposals
