"""Tests for CLI entrypoints and commands."""
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from waylura_content_tools.cli import main

EXAMPLES_DIR = pathlib.Path(__file__).resolve().parents[1] / "examples"


class CliTests(unittest.TestCase):
    def test_cli_validate_success(self):
        exit_code = main(["validate", "--input", str(EXAMPLES_DIR / "valid_japan.json")])
        self.assertEqual(exit_code, 0)

    def test_cli_validate_with_sources_inventory(self):
        exit_code = main([
            "validate",
            "--input", str(EXAMPLES_DIR / "valid_waylura_c0_turkey.json"),
            "--sources", str(EXAMPLES_DIR / "sources.json"),
            "--schema", "waylura-c0",
        ])
        self.assertEqual(exit_code, 0)

    def test_cli_validate_failure(self):
        exit_code = main(["validate", "--input", str(EXAMPLES_DIR / "invalid_corrupted.json")])
        self.assertEqual(exit_code, 1)

    def test_cli_audit_names_json_format(self):
        captured = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = captured
            exit_code = main([
                "audit-names",
                "--input", str(EXAMPLES_DIR / "fixable_sample.json"),
                "--format", "json"
            ])
        finally:
            sys.stdout = old_stdout

        output_str = captured.getvalue()
        data = json.loads(output_str)
        self.assertIn("nameIssues", data)
        self.assertGreater(len(data["nameIssues"]), 0)

    def test_cli_propose_text(self):
        captured = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = captured
            exit_code = main([
                "propose",
                "--input", str(EXAMPLES_DIR / "fixable_sample.json")
            ])
        finally:
            sys.stdout = old_stdout

        self.assertEqual(exit_code, 0)
        self.assertIn("PROPOSED CHANGES", captured.getvalue())

    def test_cli_fix_dry_run_leaves_file_unmodified(self):
        sample_path = EXAMPLES_DIR / "fixable_sample.json"
        orig_bytes = sample_path.read_bytes()

        captured = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = captured
            exit_code = main([
                "fix",
                "--input", str(sample_path),
                "--dry-run"
            ])
        finally:
            sys.stdout = old_stdout

        self.assertEqual(exit_code, 0)
        self.assertIn("[DRY-RUN]", captured.getvalue())
        self.assertEqual(sample_path.read_bytes(), orig_bytes)

    def test_cli_fix_zero_changes_preserves_file_sha256(self):
        """When dataset has 0 changes, --apply must NOT rewrite file or change SHA-256."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "clean_data.json"
            orig_bytes = (EXAMPLES_DIR / "valid_japan.json").read_bytes()
            test_file.write_bytes(orig_bytes)
            sha_before = hashlib.sha256(orig_bytes).hexdigest()

            captured = io.StringIO()
            old_stdout = sys.stdout
            try:
                sys.stdout = captured
                exit_code = main([
                    "fix",
                    "--input", str(test_file),
                    "--apply"
                ])
            finally:
                sys.stdout = old_stdout

            self.assertEqual(exit_code, 0)
            self.assertIn("NO CHANGES REQUIRED", captured.getvalue())
            sha_after = hashlib.sha256(test_file.read_bytes()).hexdigest()
            self.assertEqual(sha_before, sha_after)

    def test_cli_fix_aborts_on_duplicate_poi_id(self):
        """Pre-fix validation must abort if duplicate POI IDs exist."""
        corrupted_data = {
            "schemaVersion": 1,
            "countryId": "country-tr-turkey",
            "places": [
                {
                    "id": "poi-ist-hagia-sophia",
                    "cityId": "tr-istanbul",
                    "countryId": "country-tr-turkey",
                    "name": {"tr": "Ayasofya", "en": "Hagia Sophia", "local": "Ayasofya"},
                    "category": "history",
                    "latitude": 41.0085,
                    "longitude": 28.9802,
                },
                {
                    "id": "poi-ist-hagia-sophia",  # Duplicate ID
                    "cityId": "tr-istanbul",
                    "countryId": "country-tr-turkey",
                    "name": {"tr": "Ayasofya Camii", "en": "Hagia Sophia Mosque", "local": "Ayasofya"},
                    "category": "history",
                    "latitude": 41.0085,
                    "longitude": 28.9802,
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "dup_data.json"
            orig_bytes = json.dumps(corrupted_data, indent=2).encode("utf-8")
            test_file.write_bytes(orig_bytes)

            captured_err = io.StringIO()
            old_stderr = sys.stderr
            try:
                sys.stderr = captured_err
                exit_code = main([
                    "fix",
                    "--input", str(test_file),
                    "--apply"
                ])
            finally:
                sys.stderr = old_stderr

            self.assertEqual(exit_code, 1)
            self.assertIn("PRE-FIX ABORT: Duplicate POI ID detected", captured_err.getvalue())
            # File must NOT have been touched
            self.assertEqual(test_file.read_bytes(), orig_bytes)

    def test_cli_fix_aborts_on_structural_errors(self):
        """Pre-fix validation must abort on structural corruptions."""
        corrupted_file = EXAMPLES_DIR / "invalid_corrupted.json"
        orig_bytes = corrupted_file.read_bytes()

        captured_err = io.StringIO()
        old_stderr = sys.stderr
        try:
            sys.stderr = captured_err
            exit_code = main([
                "fix",
                "--input", str(corrupted_file),
                "--apply"
            ])
        finally:
            sys.stderr = old_stderr

        self.assertEqual(exit_code, 1)
        self.assertIn("PRE-FIX ABORT", captured_err.getvalue())
        self.assertEqual(corrupted_file.read_bytes(), orig_bytes)


if __name__ == "__main__":
    unittest.main()
