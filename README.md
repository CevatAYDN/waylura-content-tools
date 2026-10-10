# waylura-content-tools

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](pyproject.toml)

An open-source, deterministic Python CLI tool for **validating**, **auditing**, and **safely repairing** structured multilingual travel content datasets (JSON).

Developed to ensure data integrity across multilingual travel guides (Turkish, English, and local scripts such as Japanese CJK) without accidental data corruption, script contamination, or unauthorized changes.

---

## Key Features

1. **JSON Schema & Structural Validation (`validate`)**:
   - Verifies schema version, country IDs, and place structure.
   - Enforces coordinate boundaries (`-90 <= lat <= 90`, `-180 <= lon <= 180`).
   - Detects duplicate POI IDs and duplicate source records.
   - Flags orphan `sourceId` and `canonicalNowCandidateId` references.
2. **Multilingual Script & Quality Audit (`audit-names`)**:
   - Detects foreign script scraping contamination (e.g., Cyrillic characters in Turkish/English/Japanese fields).
   - Detects untranslated CJK characters in `tr` or `en` target language fields.
   - Enforces Unicode NFC normalization.
   - Flags semantic mismatches between POI IDs and names (e.g., transit station ID without station designation in name).
3. **Deterministic Proposals & Diffs (`propose`)**:
   - Emits structured diff proposals (`AUTO_SAFE` vs `REVIEW_REQUIRED`).
   - Never alters files during proposal generation.
4. **Safe, Surgical, Idempotent Fixer (`fix`)**:
   - **Dry-run by default:** No files are touched without `--apply`.
   - **Surgical updates:** Updates ONLY specific target string fields (`name.tr`, `name.en`, `name.local`).
   - **Data preservation:** Never modifies `id`, `category`, `latitude`, `longitude`, `cityId`, `sourceId`, or C0/C1/C2 approval statuses.
   - **Idempotency:** Executing the tool repeatedly produces identical output and 0 further diffs.

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
# Windows PowerShell
python -m waylura_content_tools validate --input examples/valid_japan.json

# Linux / macOS
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
# Dry-run (default: reports what WOULD change without touching disk)
python -m waylura_content_tools fix --input examples/fixable_sample.json --dry-run

# Apply safe changes in-place
python -m waylura_content_tools fix --input examples/fixable_sample.json --apply

# Or write repaired output to a new file
python -m waylura_content_tools fix --input examples/fixable_sample.json --apply --output fixed.json
```

---

## Running Tests

Run the full offline test suite:
```bash
python -m unittest discover -s tests -v
```

All 24 unit and deterministic acceptance tests run in milliseconds without network or external dependencies.

---

## Safety & Governance Principles

- **SOURCE AVAILABLE, TESTED, REPRODUCIBLE, RELEASE READY:** These statuses are evaluated independently.
- **Fail-Closed on Unknowns:** Ambiguous translations or missing data are flagged as `REVIEW REQUIRED` and are NEVER automatically overwritten.
- **No Private Data:** Synthetic, anonymous datasets are provided in `examples/`. The core Waylura mobile application codebase remains private.

---

## License

This project is licensed under the [MIT License](LICENSE).
