# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-10-10

### Security & Robustness Hardening
- **Explicit Schema Adapters**: Added support for production `waylura-c0` (root `country` object, `cities` array, and hierarchy verification) alongside `flat-poi` schema.
- **Extended Categories**: Added `viewpoint`, `essentials`, and `family` to allowed category definitions.
- **Sourced Reference Data**: Separated canonical names into `waylura_content_tools/data/canonical_names_v1.json` with official citations (UNESCO, JNTO, Turkish Ministry of Culture).
- **Sources Inventory Verification**: Added `--sources` parameter; when omitted, uninspected source relations are explicitly reported as unverified (`SOURCES_UNCHECKED`) instead of falsely passing.
- **Candidate ID Handling**: Decoupled `canonicalNowCandidateId` from `places[].id`, validating raw upstream candidate format (`<country>-<city>-<type>-<id>`).
- **Stale Proposal Protection**: Rejected fix proposals where active value does not match `proposal.current_value`.
- **Conflict Resolution**: Rejected conflicting proposals targeting the same POI and field.
- **Human Review Enforcement**: Protected non-`AUTO_SAFE` proposals behind explicit `--confirm-review` confirmation.
- **Zero-Change Preservation**: Preserved file SHA-256 and mtime untouched when zero changes are required.
- **Atomic Replacement**: Implemented atomic file writes via temporary files, fsync, and `os.replace` with automatic rollback on error.
- **Test Expansion**: Expanded test suite to 34 unit, acceptance, and negative tests.

## [1.0.0] - 2026-10-10

### Added
- Initial public open-source release.
- Structural schema and coordinate validation (`validate`).
- Multilingual name quality and script leakage auditor (`audit-names`).
- Cyrillic contamination and untranslated CJK detection in target fields.
- Unicode NFC normalization verification.
- Deterministic diff proposal engine (`propose`).
- Safe, surgical, idempotent in-place fixer (`fix`) with dry-run default.
- Export formats in human text, JSON, and CSV.
- Offline unit and deterministic acceptance test suite.
