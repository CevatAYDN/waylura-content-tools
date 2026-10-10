# Contributing to waylura-content-tools

We welcome contributions from the community!

## Development Guidelines

1. **Python Compatibility:** All code must run on Python 3.10+ using the standard library.
2. **Determinism:** Any new audit or repair rule must be 100% deterministic and idempotent.
3. **Safety First:**
   - Never auto-apply fixes that could introduce false information.
   - Ambiguous translations must be classified as `REVIEW_REQUIRED`.
   - Never alter structural metadata like IDs, coordinates, or publication statuses.
4. **Test Coverage:** All new features or bug fixes must include unit tests in `tests/`.

## Running Tests

Before submitting a PR, verify all tests pass:

```bash
python -m unittest discover -s tests -v
```
