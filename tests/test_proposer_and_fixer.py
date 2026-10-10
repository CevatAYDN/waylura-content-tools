"""Tests for proposal generation and surgical fixing."""
import copy
import json
import pathlib
import unittest
from waylura_content_tools.fixer import apply_proposals_safely
from waylura_content_tools.name_auditor import audit_place_names
from waylura_content_tools.proposer import generate_proposals

EXAMPLES_DIR = pathlib.Path(__file__).resolve().parents[1] / "examples"


class ProposerAndFixerTests(unittest.TestCase):
    def setUp(self):
        self.dataset = json.loads((EXAMPLES_DIR / "fixable_sample.json").read_text(encoding="utf-8"))

    def test_proposals_generated_correctly(self):
        issues = audit_place_names(self.dataset["places"])
        proposals = generate_proposals(issues)
        self.assertGreaterEqual(len(proposals), 2)

        sensoji_prop = next(p for p in proposals if p.poi_id == "poi-tky-sensoji")
        self.assertEqual(sensoji_prop.proposed_value, "Sensō-ji Tapınağı")
        self.assertEqual(sensoji_prop.status, "AUTO_SAFE")
        self.assertIn("---", sensoji_prop.diff)
        self.assertIn("+++", sensoji_prop.diff)

    def test_safe_fixer_applies_only_safe_proposals(self):
        issues = audit_place_names(self.dataset["places"])
        proposals = generate_proposals(issues)

        # Baseline snapshot of non-name fields
        orig_places = self.dataset["places"]
        orig_ids = [p["id"] for p in orig_places]
        orig_cats = [p["category"] for p in orig_places]
        orig_lats = [p["latitude"] for p in orig_places]
        orig_sources = [p["sourceId"] for p in orig_places]
        orig_status = self.dataset.get("publicationStatus")

        result = apply_proposals_safely(self.dataset, proposals)
        self.assertTrue(result.is_changed)

        fixed_places = result.modified_data["places"]
        self.assertEqual([p["id"] for p in fixed_places], orig_ids)
        self.assertEqual([p["category"] for p in fixed_places], orig_cats)
        self.assertEqual([p["latitude"] for p in fixed_places], orig_lats)
        self.assertEqual([p["sourceId"] for p in fixed_places], orig_sources)
        self.assertEqual(result.modified_data.get("publicationStatus"), orig_status)

        # Verify fixed value
        sensoji = next(p for p in fixed_places if p["id"] == "poi-tky-sensoji")
        self.assertEqual(sensoji["name"]["tr"], "Sensō-ji Tapınağı")

    def test_fixer_is_idempotent(self):
        issues = audit_place_names(self.dataset["places"])
        proposals = generate_proposals(issues)

        # First application
        res1 = apply_proposals_safely(self.dataset, proposals)
        self.assertTrue(res1.is_changed)

        # Re-audit fixed data
        new_issues = audit_place_names(res1.modified_data["places"])
        new_proposals = generate_proposals(new_issues)

        # Second application should result in no further changes for already fixed fields
        res2 = apply_proposals_safely(res1.modified_data, new_proposals)
        self.assertEqual(len(res2.applied), 0)
        self.assertFalse(res2.is_changed)


if __name__ == "__main__":
    unittest.main()
