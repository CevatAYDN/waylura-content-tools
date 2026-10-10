# waylura-content-tools

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](pyproject.toml)

An open-source, deterministic Python CLI tool for **validating**, **auditing**, and **safely repairing** structured multilingual travel content datasets (JSON).

Developed to ensure data integrity across multilingual travel guides (Turkish, English, and local scripts such as Japanese CJK) without accidental data corruption, script contamination, stale overwrites, or unauthorized mutations.

---

## Key Features

1. **Explicit Schema Adapter & Structural Validation (`validate`)**:
   - Supports both `waylura-c0` (production schema with root `country` object and `cities` array) and `flat-poi` schemas.
   - Enforces coordinate boundaries (`-90 <= lat <= 90`, `-180 <= lon <= 180`).
   - Supports full category inventory: `history`, `food`, `transit`, `shopping`, `nature`, `culture`, `viewpoint`, `essentials`, `family`, `accommodation`, `activity`, `attraction`.
   - Validates Country-City-POI hierarchy and references.
   - Verifies `canonicalNowCandidateId` format (`<cc>-<city>-<node|way|rel>-<id>`) without confusing it with `places[].id`.
   - Explicit `--sources` contract: Validates `sourceId` against registered sources inventory. When sources are omitted, reports unverified status honestly (`SOURCES_UNCHECKED`) instead of marking uninspected links as passing.
2. **Multilingual Script & Quality Audit (`audit-names`)**:
   - Backed by versioned, sourced canonical reference dictionary (`waylura_content_tools/data/canonical_names_v1.json`).
   - Rigorous citation contract: entries require authoritative URLs, proof excerpts, and explicit verification status (`OFFICIAL_VERIFIED`). Incomplete entries are flagged as `REVIEW_REQUIRED`.
   - Separates mechanical string normalization (`UNICODE_NFC_DENORMALIZED`) from semantic name changes (`CANONICAL_NAME_DISCREPANCY`).
   - Distinguishes legitimate local script usage (e.g. CJK in Japanese `local`) from script leakage in target language fields (`tr`, `en`).
   - Flags Cyrillic and foreign script scraping residue.
3. **Deterministic Proposals & Conflict Resolution (`propose`)**:
   - Emits structured diff proposals (`AUTO_SAFE` vs `REVIEW_REQUIRED`).
   - Detects conflicting proposals targeting the same POI and field.
4. **Safe, Surgical, Idempotent Fixer with Pre-Fix Validation (`fix`)**:
   - **Mandatory Pre-Fix Validation:** Aborts immediately if duplicate POI IDs or fatal structural corruptions are present. File remains untouched.
   - **Strict Patch Boundary:** Modifies ONLY `name.tr`, `name.en`, `name.local`. Any attempt to alter other fields is rejected with `FORBIDDEN_FIELD`.
   - **Dry-run by default:** No files are touched without `--apply`.
   - **Stale proposal protection:** Rejects modifications if active field value does not match `proposal.current_value`.
   - **Conflict rejection:** Automatically rejects conflicting proposals for the same POI/field.
   - **Human review guard:** Requires `--confirm-review` for ambiguous proposals. (Note: this is a local CLI override and does not constitute an editorial approval receipt).
   - **Zero-change preservation:** If 0 changes are applied, the file is never touched or rewritten, strictly preserving SHA-256 and mtime.
   - **Atomic write & rollback:** Uses temporary file, fsync, and atomic `os.replace` to guarantee write durability.
   - **Invariant guarantee:** Never modifies `id`, `category`, `latitude`, `longitude`, `cityId`, `sourceId`, or C0/C1/C2 approval statuses.

---

## Quickstart

### Installation

Requires Python 3.10+ (standard library only; no external dependencies required):

```bash
# Clone the repository
git clone https://github.com/CevatAYDN/waylura-content-tools.git
cd waylura-content-tools

# Optional: install locally in editable mode
pip install -e .
```

---

## CLI Usage

### 1. Validate Structure & Schema
```powershell
# Validate Waylura C0 production schema with sources inventory
python -m waylura_content_tools validate `
  --input examples/valid_waylura_c0_turkey.json `
  --sources examples/sources.json `
  --schema waylura-c0

# Validate flat-poi schema
python -m waylura_content_tools validate --input examples/valid_japan.json
```
Returns exit code `0` on success, or `1` if structural errors are encountered.

### 2. Audit Multilingual Names & Scripts
```powershell
python -m waylura_content_tools audit-names --input examples/fixable_sample.json --format text
```
Exports structured reports in `text`, `json`, or `csv`.

### 3. Generate Fix Proposals
```powershell
python -m waylura_content_tools propose --input examples/fixable_sample.json --output report.json
```

### 4. Safe Dry-Run & Fix
```powershell
# Dry-run (default: validates pre-fix integrity and reports what WOULD change without touching disk)
python -m waylura_content_tools fix --input examples/fixable_sample.json --dry-run

# Apply safe changes in-place with mandatory pre-fix validation and atomic replace
python -m waylura_content_tools fix --input examples/fixable_sample.json --apply

# Explicit CLI user override to apply reviewed proposals (local flag only; not an editorial receipt)
python -m waylura_content_tools fix --input examples/fixable_sample.json --apply --confirm-review

# Or write repaired output to a new file
python -m waylura_content_tools fix --input examples/fixable_sample.json --apply --output fixed.json
```

### Exit Code Contracts
- `0`: Success (all checks passed, fixes applied cleanly, or zero changes required).
- `1`: Validation error, pre-fix integrity abort (duplicate POI IDs or corrupted schema), unresolvable proposal conflicts, or invalid input.

---

## Running Tests

Run the full offline test suite:
```bash
python -m unittest discover -s tests -v
```

All 40 unit, acceptance, and negative tests run in milliseconds without network or external dependencies.

---

## Safety & Governance Principles

- **SOURCE AVAILABLE, TESTED, REPRODUCIBLE, RELEASE READY:** Evaluated independently.
- **Fail-Closed on Unknowns:** Ambiguous translations or missing data are flagged as `REVIEW_REQUIRED` and are NEVER automatically overwritten.
- **Pre-Fix Fail-Closed:** Datasets containing duplicate identities or schema corruption are aborted prior to fix execution.
- **No Private Data:** Synthetic, anonymous datasets are provided in `examples/`. The core Waylura mobile application codebase remains private.

---

## License

This project is licensed under the [MIT License](LICENSE).
