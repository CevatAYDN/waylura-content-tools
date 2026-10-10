"""Tests for dataset validator."""
import json
import pathlib
import unittest
from waylura_content_tools.validator import validate_dataset

EXAMPLES_DIR = pathlib.Path(__file__).resolve().parents[1] / "examples"


class ValidatorTests(unittest.TestCase):
    def test_valid_japan_dataset(self):
        data = json.loads((EXAMPLES_DIR / "valid_japan.json").read_text(encoding="utf-8"))
        findings = validate_dataset(data)
        errors = [f for f in findings if f.severity == "ERROR"]
        self.assertEqual(errors, [])

    def test_valid_turkey_dataset(self):
        data = json.loads((EXAMPLES_DIR / "valid_turkey.json").read_text(encoding="utf-8"))
        findings = validate_dataset(data)
        errors = [f for f in findings if f.severity == "ERROR"]
        self.assertEqual(errors, [])

    def test_invalid_corrupted_dataset_catches_all_errors(self):
        data = json.loads((EXAMPLES_DIR / "invalid_corrupted.json").read_text(encoding="utf-8"))
        findings = validate_dataset(data)
        issue_types = {f.issue_type for f in findings}

        self.assertIn("INVALID_COUNTRY_ID", issue_types)
        self.assertIn("INVALID_CATEGORY", issue_types)
        self.assertIn("INVALID_COORDINATES", issue_types)
        self.assertIn("DUPLICATE_POI_ID", issue_types)
        self.assertIn("MISSING_LANGUAGE_FIELDS", issue_types)
        self.assertIn("ORPHAN_NOW_CANDIDATE_ID", issue_types)

    def test_orphan_source_id_warning(self):
        data = {
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
                    "sourceId": "src-unknown-source"
                }
            ]
        }
        known_sources = {"src-official-kultur-gov-tr"}
        findings = validate_dataset(data, known_sources=known_sources)
        orphans = [f for f in findings if f.issue_type == "ORPHAN_SOURCE_ID"]
        self.assertEqual(len(orphans), 1)


if __name__ == "__main__":
    unittest.main()
