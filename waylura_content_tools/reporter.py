"""Report formatting utilities (JSON, CSV, and Human CLI)."""
from __future__ import annotations

import csv
import io
import json
from typing import Any
from .name_auditor import NameAuditIssue
from .proposer import ProposalRecord
from .validator import ValidationFinding


def format_text_report(
    *,
    input_file: str,
    validation_findings: list[ValidationFinding] | None = None,
    name_issues: list[NameAuditIssue] | None = None,
    proposals: list[ProposalRecord] | None = None,
) -> str:
    """Format a human-readable text report."""
    lines = [
        "=" * 70,
        f" WAYLURA CONTENT TOOLS AUDIT REPORT: {input_file}",
        "=" * 70,
    ]

    if validation_findings:
        lines.append(f"\n[STRUCTURAL VALIDATION] ({len(validation_findings)} findings)")
        for vf in validation_findings:
            loc = f" [{vf.poi_id}]" if vf.poi_id else ""
            lines.append(f"  [{vf.severity:<7}] {vf.issue_type:<28}{loc} -> {vf.message}")

    if name_issues:
        lines.append(f"\n[MULTILINGUAL NAME AUDIT] ({len(name_issues)} issues)")
        for ni in name_issues:
            prop_str = f" => proposed: {ni.proposed_value!r}" if ni.proposed_value else ""
            lines.append(f"  [{ni.severity:<7}] {ni.poi_id}.{ni.field:<8} ({ni.issue_type}){prop_str}")

    if proposals:
        lines.append(f"\n[PROPOSED CHANGES] ({len(proposals)} proposals)")
        for p in proposals:
            lines.append(f"  [{p.status:<15}] {p.poi_id}.{p.field}")
            lines.append(f"      Current:  {p.current_value!r}")
            lines.append(f"      Proposed: {p.proposed_value!r}")
            lines.append(f"      Reason:   {p.reason}")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def format_json_report(
    *,
    input_file: str,
    sha256_before: str | None = None,
    sha256_after: str | None = None,
    validation_findings: list[ValidationFinding] | None = None,
    name_issues: list[NameAuditIssue] | None = None,
    proposals: list[ProposalRecord] | None = None,
) -> str:
    """Format report as JSON."""
    report = {
        "inputFile": input_file,
        "sha256Before": sha256_before,
        "sha256After": sha256_after,
        "summary": {
            "validationCount": len(validation_findings or []),
            "nameIssuesCount": len(name_issues or []),
            "proposalsCount": len(proposals or []),
        },
        "validationFindings": [vf.to_dict() for vf in (validation_findings or [])],
        "nameIssues": [ni.to_dict() for ni in (name_issues or [])],
        "proposals": [p.to_dict() for p in (proposals or [])],
    }
    return json.dumps(report, indent=2, ensure_ascii=False)


def format_csv_report(
    *,
    validation_findings: list[ValidationFinding] | None = None,
    name_issues: list[NameAuditIssue] | None = None,
    proposals: list[ProposalRecord] | None = None,
) -> str:
    """Format report as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "poi_id",
        "field",
        "severity",
        "issue_type",
        "current_value",
        "proposed_value",
        "status",
        "message",
    ])

    if validation_findings:
        for vf in validation_findings:
            writer.writerow([
                vf.poi_id or "",
                vf.field or "",
                vf.severity,
                vf.issue_type,
                "",
                "",
                "",
                vf.message,
            ])

    if name_issues:
        for ni in name_issues:
            writer.writerow([
                ni.poi_id,
                ni.field,
                ni.severity,
                ni.issue_type,
                ni.current_value,
                ni.proposed_value or "",
                "REVIEW_REQUIRED" if ni.review_required else "AUTO_SAFE",
                ni.message,
            ])

    if proposals:
        for p in proposals:
            writer.writerow([
                p.poi_id,
                p.field,
                "PROPOSAL",
                "FIX_PROPOSAL",
                p.current_value,
                p.proposed_value,
                p.status,
                p.reason,
            ])

    return output.getvalue()
