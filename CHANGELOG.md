# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Offline unit and deterministic acceptance test suite (24 tests).
