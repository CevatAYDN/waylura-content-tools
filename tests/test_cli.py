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

    def test_cli_fix_idempotent_second_run_preserves_sha(self):
        """First run fixes file with exit 0; second run yields NO CHANGES REQUIRED, exit 0, and same SHA."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "sample.json"
            test_file.write_bytes((EXAMPLES_DIR / "fixable_sample.json").read_bytes())

            # First fix run
            exit_1 = main(["fix", "--input", str(test_file), "--apply"])
            self.assertEqual(exit_1, 0)
            sha_1 = hashlib.sha256(test_file.read_bytes()).hexdigest()
            mtime_1 = test_file.stat().st_mtime_ns

            # Second fix run
            captured = io.StringIO()
            old_stdout = sys.stdout
            try:
                sys.stdout = captured
                exit_2 = main(["fix", "--input", str(test_file), "--apply"])
            finally:
                sys.stdout = old_stdout

            self.assertEqual(exit_2, 0)
            self.assertIn("NO CHANGES REQUIRED", captured.getvalue())
            sha_2 = hashlib.sha256(test_file.read_bytes()).hexdigest()
            mtime_2 = test_file.stat().st_mtime_ns

            self.assertEqual(sha_1, sha_2)
            self.assertEqual(mtime_1, mtime_2)

    def test_cli_strict_publication_mode_rejects_missing_sources(self):
        """Strict publication mode (--require-sources) must fail with exit 1 if sources inventory is missing."""
        # validate
        exit_val = main([
            "validate",
            "--input", str(EXAMPLES_DIR / "valid_japan.json"),
            "--require-sources",
        ])
        self.assertEqual(exit_val, 1)

        # fix
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "data.json"
            orig_bytes = (EXAMPLES_DIR / "valid_japan.json").read_bytes()
            test_file.write_bytes(orig_bytes)

            captured_err = io.StringIO()
            old_stderr = sys.stderr
            try:
                sys.stderr = captured_err
                exit_fix = main([
                    "fix",
                    "--input", str(test_file),
                    "--require-sources",
                    "--apply",
                ])
            finally:
                sys.stderr = old_stderr

            self.assertEqual(exit_fix, 1)
            self.assertIn("PRE-FIX ABORT", captured_err.getvalue())
            self.assertEqual(test_file.read_bytes(), orig_bytes)

    def test_cli_strict_publication_mode_rejects_orphan_source_id(self):
        """Strict publication mode must fail with exit 1 if a POI references an unregistered sourceId."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "data.json"
            dataset = json.loads((EXAMPLES_DIR / "valid_japan.json").read_text(encoding="utf-8"))
            dataset["places"][0]["sourceId"] = "orphan-unregistered-source"
            orig_bytes = json.dumps(dataset, indent=2).encode("utf-8")
            test_file.write_bytes(orig_bytes)

            # validate
            exit_val = main([
                "validate",
                "--input", str(test_file),
                "--sources", str(EXAMPLES_DIR / "sources.json"),
                "--require-sources",
            ])
            self.assertEqual(exit_val, 1)

            # fix
            captured_err = io.StringIO()
            old_stderr = sys.stderr
            try:
                sys.stderr = captured_err
                exit_fix = main([
                    "fix",
                    "--input", str(test_file),
                    "--sources", str(EXAMPLES_DIR / "sources.json"),
                    "--require-sources",
                    "--apply",
                ])
            finally:
                sys.stderr = old_stderr

            self.assertEqual(exit_fix, 1)
            self.assertIn("ORPHAN_SOURCE_ID", captured_err.getvalue())
            self.assertEqual(test_file.read_bytes(), orig_bytes)

    def test_cli_lenient_mode_allows_non_fatal_warnings(self):
        """Lenient mode allows validation and fixing even when sources inventory is omitted."""
        exit_val = main([
            "validate",
            "--input", str(EXAMPLES_DIR / "valid_japan.json"),
            "--lenient",
        ])
        self.assertEqual(exit_val, 0)

    def test_cli_transactional_abort_on_mixed_fatal_proposal_preserves_file(self):
        """When proposals contain 1 valid proposal + 1 fatal rejection, transaction aborts completely with exit 1."""
        from waylura_content_tools.proposer import ProposalRecord
        import waylura_content_tools.cli as cli_mod

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "data.json"
            orig_bytes = (EXAMPLES_DIR / "fixable_sample.json").read_bytes()
            test_file.write_bytes(orig_bytes)
            sha_before = hashlib.sha256(orig_bytes).hexdigest()
            mtime_before = test_file.stat().st_mtime_ns

            # Create mixed proposals: 1 valid proposal + 1 stale fatal proposal
            valid_prop = ProposalRecord(
                poi_id="poi-tky-sensoji",
                field="name.tr",
                current_value="Sensoji Tapinagi",
                proposed_value="Sensō-ji Tapınağı",
                reason="Valid fix",
                status="AUTO_SAFE",
            )
            stale_prop = ProposalRecord(
                poi_id="poi-tky-skytree",
                field="name.tr",
                current_value="WRONG_STALE_CURRENT_VALUE",
                proposed_value="Tokyo Skytree",
                reason="Stale fix",
                status="AUTO_SAFE",
            )

            # Monkeypatch generate_proposals to return mixed batch
            orig_gen = cli_mod.generate_proposals
            cli_mod.generate_proposals = lambda issues: [valid_prop, stale_prop]
            captured_err = io.StringIO()
            old_stderr = sys.stderr
            try:
                sys.stderr = captured_err
                exit_code = main([
                    "fix",
                    "--input", str(test_file),
                    "--apply",
                ])
            finally:
                cli_mod.generate_proposals = orig_gen
                sys.stderr = old_stderr

            self.assertEqual(exit_code, 1)
            self.assertIn("TRANSACTION ABORTED", captured_err.getvalue())
            self.assertIn("STALE_PROPOSAL", captured_err.getvalue())

            # File must NOT be modified (0 partial writes, same sha and mtime)
            sha_after = hashlib.sha256(test_file.read_bytes()).hexdigest()
            mtime_after = test_file.stat().st_mtime_ns
            self.assertEqual(sha_before, sha_after)
            self.assertEqual(mtime_before, mtime_after)

    def test_cli_subprocess_execution(self):
        """Verify real CLI subprocess invocation."""
        import subprocess
        res = subprocess.run(
            [sys.executable, "-m", "waylura_content_tools.cli", "validate", "--input", str(EXAMPLES_DIR / "valid_japan.json")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)


if __name__ == "__main__":
    unittest.main()
