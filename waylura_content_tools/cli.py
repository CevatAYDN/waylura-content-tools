"""Command Line Interface for waylura_content_tools."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from .fixer import apply_proposals_safely, atomic_write_dataset
from .name_auditor import audit_place_names
from .proposer import generate_proposals
from .reporter import format_csv_report, format_json_report, format_text_report
from .validator import validate_dataset

# Ensure UTF-8 output on Windows consoles (prevents cp1254/cp1252 crash on CJK and macron characters)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


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


def load_sources_inventory(sources_path_str: str | None) -> set[str] | None:
    """Load set of known registered source IDs from JSON inventory."""
    if not sources_path_str:
        return None
    path = Path(sources_path_str).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Sources file not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    ids: set[str] = set()
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                ids.add(item)
            elif isinstance(item, dict) and "id" in item:
                ids.add(str(item["id"]))
    elif isinstance(raw, dict):
        if "sources" in raw and isinstance(raw["sources"], list):
            for item in raw["sources"]:
                if isinstance(item, str):
                    ids.add(item)
                elif isinstance(item, dict) and "id" in item:
                    ids.add(str(item["id"]))
        elif "id" in raw:
            ids.add(str(raw["id"]))
    return ids


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

    try:
        known_sources = load_sources_inventory(args.sources)
    except Exception as e:
        print(f"ERROR: Cannot load sources inventory: {e}", file=sys.stderr)
        return 1

    findings = validate_dataset(data, known_sources=known_sources, schema_adapter=args.schema)

    fmt = args.format.lower()
    if fmt == "json":
        report = format_json_report(input_file=str(path), sha256_before=sha, validation_findings=findings)
    elif fmt == "csv":
        report = format_csv_report(validation_findings=findings)
    else:
        report = format_text_report(input_file=str(path), validation_findings=findings)

    write_output(report, args.output)

    has_errors = any(f.severity == "ERROR" for f in findings)
    if getattr(args, "strict", True):
        # Strict validation fails on any ERROR or unverified source relation if sources required
        if getattr(args, "require_sources", False):
            has_unverified = any(f.issue_type in ("ORPHAN_SOURCE_ID", "SOURCES_UNCHECKED") for f in findings)
            if has_unverified:
                return 1
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

    try:
        known_sources = load_sources_inventory(args.sources)
    except Exception as e:
        print(f"ERROR: Cannot load sources inventory: {e}", file=sys.stderr)
        return 1

    # =========================================================================
    # 1. MANDATORY PRE-FIX DATA INTEGRITY VALIDATION
    # Safety policy forbids executing fixes on structurally corrupted datasets
    # or datasets with duplicate POI identities.
    # =========================================================================
    validation_findings = validate_dataset(
        data,
        known_sources=known_sources,
        schema_adapter=args.schema,
    )
    duplicate_errors = [f for f in validation_findings if f.issue_type == "DUPLICATE_POI_ID"]
    if duplicate_errors:
        print(f"PRE-FIX ABORT: Duplicate POI ID detected in {path.name}:", file=sys.stderr)
        for d in duplicate_errors:
            print(f"  * {d.message}", file=sys.stderr)
        print("Safety policy forbids modifying datasets with duplicate identity keys. File unchanged.", file=sys.stderr)
        return 1

    structural_errors = [f for f in validation_findings if f.severity == "ERROR"]
    if structural_errors:
        print(f"PRE-FIX ABORT: Found {len(structural_errors)} fatal structural error(s) in {path.name}:", file=sys.stderr)
        for err in structural_errors:
            loc = f" [{err.poi_id}]" if err.poi_id else ""
            print(f"  * [{err.issue_type}]{loc} {err.message}", file=sys.stderr)
        print("Safety policy forbids repairing structurally invalid datasets. File unchanged.", file=sys.stderr)
        return 1

    is_strict = not getattr(args, "lenient", False)
    if is_strict and getattr(args, "require_sources", False):
        unverified_sources = [f for f in validation_findings if f.issue_type in ("ORPHAN_SOURCE_ID", "SOURCES_UNCHECKED")]
        if unverified_sources:
            print(f"PRE-FIX ABORT (STRICT): Source verification required but unverified relations found in {path.name}:", file=sys.stderr)
            for us in unverified_sources:
                print(f"  * [{us.issue_type}] {us.message}", file=sys.stderr)
            return 1

    raw_bytes = path.read_bytes()
    places = data.get("places", [])
    issues = audit_place_names(places)
    proposals = generate_proposals(issues)

    is_dry_run = not args.apply or args.dry_run
    confirm_review = args.confirm_review or args.allow_review_required

    if confirm_review:
        print("[NOTICE] User passed --confirm-review: applying reviewed proposals.")
        print("[NOTICE] (Note: This is a local CLI override and does NOT constitute an editorial signature or publishing approval receipt.)")

    result = apply_proposals_safely(
        data,
        proposals,
        confirm_review=confirm_review,
        allow_review_required=confirm_review,
    )

    if is_dry_run:
        print(f"[DRY-RUN] Checked {len(places)} places in {path.name}")
        print(f"[DRY-RUN] SHA-256 (unchanged): {sha_before}")
        print(f"[DRY-RUN] Proposals that would be applied: {len(result.applied)}")
        print(f"[DRY-RUN] Proposals skipped/review required: {len(result.skipped)}")
        if result.rejections:
            print(f"[DRY-RUN] Rejections/conflicts: {len(result.rejections)}")
        if result.applied:
            print("\nSafe proposals that WOULD be applied with --apply:")
            for p in result.applied:
                print(f"  * {p.poi_id}.{p.field}: {p.current_value!r} -> {p.proposed_value!r}")
        if result.rejections:
            print("\nRejections detail:")
            for r in result.rejections:
                print(f"  ! {r.get('poi_id')}.{r.get('field')}: {r.get('reason')} - {r.get('message')}")
        print("\nPass --apply to safely write changes.")
        return 0

    out_path = Path(args.output).resolve() if args.output else path

    if not result.is_changed:
        # Zero changes required! Original file MUST NOT be rewritten or reformatted.
        # Original SHA-256 and mtime remain completely untouched.
        if out_path != path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(raw_bytes)
        sha_after = file_sha256(out_path)
        print(f"NO CHANGES REQUIRED: {out_path.name} is already canonical.")
        print(f"  SHA-256 (strictly preserved): {sha_after}")
        if result.skipped:
            print(f"  Skipped proposals: {len(result.skipped)}")
        if result.rejections:
            print(f"  Rejected proposals: {len(result.rejections)}")
        return 0

    # Atomic write with rollback protection
    try:
        atomic_write_dataset(
            target_path=out_path,
            modified_data=result.modified_data,
            is_changed=True,
            original_bytes=raw_bytes,
        )
    except Exception as e:
        print(f"ERROR: Failed during atomic write (rolled back): {e}", file=sys.stderr)
        return 1

    sha_after = file_sha256(out_path)
    print(f"SUCCESS: Surgically applied {len(result.applied)} changes to {out_path.name}")
    print(f"  SHA-256 Before: {sha_before}")
    print(f"  SHA-256 After:  {sha_after}")
    if result.skipped:
        print(f"  Skipped (REVIEW REQUIRED or unverified): {len(result.skipped)}")
    if result.rejections:
        print(f"  Rejections: {len(result.rejections)}")

    # Exit code contract: if critical rejections occurred, signal non-zero
    has_critical_rejection = any(r.get("reason") in ("CONFLICTING_PROPOSALS", "STALE_PROPOSAL", "DUPLICATE_POI_ID") for r in result.rejections)
    if has_critical_rejection:
        print("WARNING: One or more proposals were rejected due to data conflicts or stale state.", file=sys.stderr)
        return 1
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
    p_val.add_argument("--sources", "-s", default=None, help="Path to registered sources inventory JSON")
    p_val.add_argument(
        "--schema",
        choices=["auto", "waylura-c0", "flat-poi"],
        default="auto",
        help="Schema adapter type (auto, waylura-c0 with country object, or flat-poi with countryId)",
    )
    p_val.add_argument("--strict", action="store_true", default=True, help="Strict validation (default)")
    p_val.add_argument("--require-sources", action="store_true", help="Fail validation if sources are unverified")
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
    p_fix = subparsers.add_parser("fix", help="Surgically apply safe name fixes with pre-fix validation")
    p_fix.add_argument("--input", "-i", required=True, help="Input JSON file path")
    p_fix.add_argument("--output", "-o", default=None, help="Target output file (defaults to in-place update)")
    p_fix.add_argument("--apply", action="store_true", help="Actually write changes (default is dry-run)")
    p_fix.add_argument("--dry-run", action="store_true", help="Explicitly run in dry-run mode")
    p_fix.add_argument("--sources", "-s", default=None, help="Path to registered sources inventory JSON")
    p_fix.add_argument(
        "--schema",
        choices=["auto", "waylura-c0", "flat-poi"],
        default="auto",
        help="Schema adapter type",
    )
    p_fix.add_argument("--strict", action="store_true", default=True, help="Strict pre-fix validation (default)")
    p_fix.add_argument("--lenient", action="store_true", help="Allow fixing if only non-fatal warnings exist")
    p_fix.add_argument("--require-sources", action="store_true", help="Fail pre-fix check if sources are unverified")
    p_fix.add_argument(
        "--confirm-review",
        action="store_true",
        help="Explicit CLI user override to apply proposals with REVIEW_REQUIRED status",
    )
    p_fix.add_argument(
        "--allow-review-required",
        action="store_true",
        help="Alias for --confirm-review (backwards compatibility)",
    )
    p_fix.set_defaults(handler=handle_fix)

    parsed = parser.parse_args(argv)
    return parsed.handler(parsed)


if __name__ == "__main__":
    sys.exit(main())
