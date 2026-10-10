"""Command Line Interface for waylura_content_tools."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from .fixer import apply_proposals_safely
from .name_auditor import audit_place_names
from .proposer import generate_proposals
from .reporter import format_csv_report, format_json_report, format_text_report
from .validator import validate_dataset


def file_sha256(path: Path) -> str:
    """Compute sha256 of file bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path_str: str) -> tuple[dict[str, Any], Path, str]:
    path = Path(path_str).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")
    raw_bytes = path.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()
    data = json.loads(raw_bytes.decode("utf-8"))
    return data, path, sha


def write_output(content: str, output_path: str | None) -> None:
    if output_path:
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(content, encoding="utf-8")
        print(f"Report written to: {out_p}")
    else:
        print(content)


def handle_validate(args: argparse.Namespace) -> int:
    try:
        data, path, sha = load_json(args.input)
    except Exception as e:
        print(f"ERROR: Cannot load input: {e}", file=sys.stderr)
        return 1

    findings = validate_dataset(data)

    fmt = args.format.lower()
    if fmt == "json":
        report = format_json_report(input_file=str(path), sha256_before=sha, validation_findings=findings)
    elif fmt == "csv":
        report = format_csv_report(validation_findings=findings)
    else:
        report = format_text_report(input_file=str(path), validation_findings=findings)

    write_output(report, args.output)

    has_errors = any(f.severity == "ERROR" for f in findings)
    return 1 if has_errors else 0


def handle_audit_names(args: argparse.Namespace) -> int:
    try:
        data, path, sha = load_json(args.input)
    except Exception as e:
        print(f"ERROR: Cannot load input: {e}", file=sys.stderr)
        return 1

    places = data.get("places", [])
    issues = audit_place_names(places)

    fmt = args.format.lower()
    if fmt == "json":
        report = format_json_report(input_file=str(path), sha256_before=sha, name_issues=issues)
    elif fmt == "csv":
        report = format_csv_report(name_issues=issues)
    else:
        report = format_text_report(input_file=str(path), name_issues=issues)

    write_output(report, args.output)

    has_errors = any(i.severity == "ERROR" for i in issues)
    return 1 if has_errors else 0


def handle_propose(args: argparse.Namespace) -> int:
    try:
        data, path, sha = load_json(args.input)
    except Exception as e:
        print(f"ERROR: Cannot load input: {e}", file=sys.stderr)
        return 1

    places = data.get("places", [])
    issues = audit_place_names(places)
    proposals = generate_proposals(issues)

    fmt = args.format.lower() if args.format else ("json" if args.output else "text")
    if fmt == "json":
        report = format_json_report(
            input_file=str(path),
            sha256_before=sha,
            name_issues=issues,
            proposals=proposals,
        )
    elif fmt == "csv":
        report = format_csv_report(name_issues=issues, proposals=proposals)
    else:
        report = format_text_report(input_file=str(path), proposals=proposals)

    write_output(report, args.output)
    return 0


def handle_fix(args: argparse.Namespace) -> int:
    try:
        data, path, sha_before = load_json(args.input)
    except Exception as e:
        print(f"ERROR: Cannot load input: {e}", file=sys.stderr)
        return 1

    places = data.get("places", [])
    issues = audit_place_names(places)
    proposals = generate_proposals(issues)

    is_dry_run = not args.apply or args.dry_run

    result = apply_proposals_safely(
        data,
        proposals,
        allow_review_required=args.allow_review_required,
    )

    if is_dry_run:
        print(f"[DRY-RUN] Checked {len(places)} places in {path.name}")
        print(f"[DRY-RUN] SHA-256 (unchanged): {sha_before}")
        print(f"[DRY-RUN] Proposals that would be applied: {len(result.applied)}")
        print(f"[DRY-RUN] Proposals skipped/review required: {len(result.skipped)}")
        if result.applied:
            print("\nSafe proposals that WOULD be applied with --apply:")
            for p in result.applied:
                print(f"  * {p.poi_id}.{p.field}: {p.current_value!r} -> {p.proposed_value!r}")
        print("\nPass --apply to safely write these changes.")
        return 0

    # Apply changes
    out_path = Path(args.output).resolve() if args.output else path
    out_bytes = json.dumps(result.modified_data, indent=2, ensure_ascii=False) + "\n"
    out_path.write_text(out_bytes, encoding="utf-8")
    sha_after = file_sha256(out_path)

    print(f"SUCCESS: Applied {len(result.applied)} changes to {out_path.name}")
    print(f"  SHA-256 Before: {sha_before}")
    print(f"  SHA-256 After:  {sha_after}")
    if result.skipped:
        print(f"  Skipped (REVIEW REQUIRED): {len(result.skipped)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="waylura_content_tools",
        description="Multilingual travel content dataset validator, auditor, and safe patcher.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # 1. validate
    p_val = subparsers.add_parser("validate", help="Validate JSON schema, coordinates, IDs, and relations")
    p_val.add_argument("--input", "-i", required=True, help="Input JSON file path")
    p_val.add_argument("--format", "-f", choices=["text", "json", "csv"], default="text", help="Output format")
    p_val.add_argument("--output", "-o", default=None, help="Save report to file")
    p_val.set_defaults(handler=handle_validate)

    # 2. audit-names
    p_aud = subparsers.add_parser("audit-names", help="Audit multilingual names, scripts, and Unicode NFC")
    p_aud.add_argument("--input", "-i", required=True, help="Input JSON file path")
    p_aud.add_argument("--format", "-f", choices=["text", "json", "csv"], default="text", help="Output format")
    p_aud.add_argument("--output", "-o", default=None, help="Save report to file")
    p_aud.set_defaults(handler=handle_audit_names)

    # 3. propose
    p_prop = subparsers.add_parser("propose", help="Generate deterministic fix proposals")
    p_prop.add_argument("--input", "-i", required=True, help="Input JSON file path")
    p_prop.add_argument("--format", "-f", choices=["text", "json", "csv"], default=None, help="Output format")
    p_prop.add_argument("--output", "-o", default=None, help="Save proposals to file")
    p_prop.set_defaults(handler=handle_propose)

    # 4. fix
    p_fix = subparsers.add_parser("fix", help="Surgically apply safe name fixes (dry-run by default)")
    p_fix.add_argument("--input", "-i", required=True, help="Input JSON file path")
    p_fix.add_argument("--output", "-o", default=None, help="Target output file (defaults to in-place update)")
    p_fix.add_argument("--apply", action="store_true", help="Actually write changes (default is dry-run)")
    p_fix.add_argument("--dry-run", action="store_true", help="Explicitly run in dry-run mode")
    p_fix.add_argument("--allow-review-required", action="store_true", help="Also apply ambiguous changes")
    p_fix.set_defaults(handler=handle_fix)

    parsed = parser.parse_args(argv)
    return parsed.handler(parsed)


if __name__ == "__main__":
    sys.exit(main())
