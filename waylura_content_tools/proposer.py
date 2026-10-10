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
        source: str | None = None,
        source_url: str | None = None,
        evidence: str | None = None,
        classification: str = "SEMANTIC_NAME_CHANGE",
    ):
        self.poi_id = poi_id
        self.field = field
        self.current_value = current_value
        self.proposed_value = proposed_value
        self.reason = reason
        self.status = status
        self.source = source
        self.source_url = source_url
        self.evidence = evidence
        self.classification = classification

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
            "source": self.source,
            "sourceUrl": self.source_url,
            "evidence": self.evidence,
            "classification": self.classification,
            "diff": self.diff,
        }


def generate_proposals(issues: list[NameAuditIssue]) -> list[ProposalRecord]:
    """Generate deterministic proposals from name audit issues with conflict detection."""
    proposals_by_key: dict[tuple[str, str], list[ProposalRecord]] = {}

    for issue in issues:
        if issue.proposed_value is None or issue.proposed_value == issue.current_value:
            continue

        key = (issue.poi_id, issue.field)
        status = "REVIEW_REQUIRED" if issue.review_required else "AUTO_SAFE"

        prop = ProposalRecord(
            poi_id=issue.poi_id,
            field=issue.field,
            current_value=issue.current_value,
            proposed_value=issue.proposed_value,
            reason=issue.message,
            status=status,
            source=issue.source,
            source_url=issue.source_url,
            evidence=issue.evidence,
            classification=issue.classification,
        )
        proposals_by_key.setdefault(key, []).append(prop)

    result: list[ProposalRecord] = []
    for key, props in proposals_by_key.items():
        if len(props) == 1:
            result.append(props[0])
        else:
            # Check if all proposed values are identical
            unique_proposed = {p.proposed_value for p in props}
            if len(unique_proposed) == 1:
                # Merge reasons
                combined_reason = "; ".join(p.reason for p in props)
                p = props[0]
                p.reason = combined_reason
                result.append(p)
            else:
                # Conflict detected! Mark as CONFLICTING and force REVIEW_REQUIRED
                for p in props:
                    p.status = "CONFLICTING_REVIEW_REQUIRED"
                    p.reason = f"Conflicting proposals exist for {p.poi_id}.{p.field}: {unique_proposed}"
                    result.append(p)

    # Sort deterministically
    result.sort(key=lambda p: (p.poi_id, p.field, p.proposed_value))
    return result
