"""Tests for dataset validator."""
import json
import pathlib
import unittest
from waylura_content_tools.validator import validate_dataset

EXAMPLES_DIR = pathlib.Path(__file__).resolve().parents[1] / "examples"


class ValidatorTests(unittest.TestCase):
    def test_valid_japan_dataset(self):
        data = json.loads((EXAMPLES_DIR / "valid_japan.json").read_text(encoding="utf-8"))
        findings = validate_dataset(data, known_sources={"src-official-jnto-go-jp"})
        errors = [f for f in findings if f.severity == "ERROR"]
        self.assertEqual(errors, [])

    def test_valid_turkey_dataset(self):
        data = json.loads((EXAMPLES_DIR / "valid_turkey.json").read_text(encoding="utf-8"))
        findings = validate_dataset(data, known_sources={"src-official-kultur-gov-tr"})
        errors = [f for f in findings if f.severity == "ERROR"]
        self.assertEqual(errors, [])

    def test_valid_waylura_c0_production_schema(self):
        """Test real Waylura C0 production schema with country object, cities, and viewpoint category."""
        data = json.loads((EXAMPLES_DIR / "valid_waylura_c0_turkey.json").read_text(encoding="utf-8"))
        sources_data = json.loads((EXAMPLES_DIR / "sources.json").read_text(encoding="utf-8"))
        known_sources = {s["id"] for s in sources_data["sources"]}

        findings = validate_dataset(data, known_sources=known_sources, schema_adapter="waylura-c0")
        errors = [f for f in findings if f.severity == "ERROR"]
        self.assertEqual(errors, [])

        # Ensure viewpoint category is present and accepted without error
        categories = {p["category"] for p in data["places"]}
        self.assertIn("viewpoint", categories)

    def test_invalid_corrupted_dataset_catches_all_errors(self):
        data = json.loads((EXAMPLES_DIR / "invalid_corrupted.json").read_text(encoding="utf-8"))
        findings = validate_dataset(data)
        issue_types = {f.issue_type for f in findings}

        self.assertIn("INVALID_COUNTRY_ID", issue_types)
        self.assertIn("INVALID_CATEGORY", issue_types)
        self.assertIn("INVALID_COORDINATES", issue_types)
        self.assertIn("DUPLICATE_POI_ID", issue_types)
        self.assertIn("MISSING_LANGUAGE_FIELDS", issue_types)
        self.assertIn("INVALID_CANDIDATE_ID_FORMAT", issue_types)
        self.assertIn("SOURCES_UNCHECKED", issue_types)

    def test_sources_omitted_flags_sources_unchecked_warning(self):
        """When known_sources inventory is omitted, relationship must NOT be marked as pass."""
        data = json.loads((EXAMPLES_DIR / "valid_turkey.json").read_text(encoding="utf-8"))
        findings = validate_dataset(data, known_sources=None)
        warnings = [f for f in findings if f.issue_type == "SOURCES_UNCHECKED"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("unverified", warnings[0].message)

    def test_orphan_source_id_detected_when_sources_provided(self):
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
        # Should NOT emit SOURCES_UNCHECKED when known_sources is explicitly passed
        self.assertFalse(any(f.issue_type == "SOURCES_UNCHECKED" for f in findings))

    def test_canonical_now_candidate_id_upstream_format_accepted(self):
        """canonicalNowCandidateId must reference upstream format and not be searched in places[].id."""
        data = {
            "schemaVersion": 1,
            "countryId": "country-tr-turkey",
            "places": [
                {
                    "id": "poi-ist-topkapi",
                    "cityId": "tr-istanbul",
                    "countryId": "country-tr-turkey",
                    "name": {"tr": "Topkapı Sarayı", "en": "Topkapi Palace", "local": "Topkapı Sarayı"},
                    "category": "history",
                    "latitude": 41.0115,
                    "longitude": 28.9833,
                    "sourceId": "src-kultur",
                    "canonicalNowCandidateId": "tr-istanbul-node-400192"
                }
            ]
        }
        findings = validate_dataset(data, known_sources={"src-kultur"})
        candidate_issues = [f for f in findings if "CANDIDATE" in f.issue_type]
        self.assertEqual(candidate_issues, [])


if __name__ == "__main__":
    unittest.main()
