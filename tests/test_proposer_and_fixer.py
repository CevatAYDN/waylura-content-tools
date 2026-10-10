"""Tests for proposal generation and surgical fixing."""
import copy
import hashlib
import json
import os
import pathlib
import tempfile
import unittest

from waylura_content_tools.fixer import apply_proposals_safely, atomic_write_dataset
from waylura_content_tools.name_auditor import audit_place_names
from waylura_content_tools.proposer import ProposalRecord, generate_proposals

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

    def test_stale_proposal_rejected(self):
        """Negative test: proposal.current_value must match active value, otherwise reject."""
        stale_proposal = ProposalRecord(
            poi_id="poi-tky-sensoji",
            field="name.tr",
            current_value="Something Old That Does Not Match Active Dataset",
            proposed_value="Sensō-ji Tapınağı",
            reason="Stale fix attempt",
            status="AUTO_SAFE",
        )
        result = apply_proposals_safely(self.dataset, [stale_proposal])
        self.assertEqual(len(result.applied), 0)
        self.assertEqual(len(result.skipped), 1)
        self.assertFalse(result.is_changed)
        self.assertEqual(result.rejections[0]["reason"], "STALE_PROPOSAL")

    def test_conflicting_proposals_for_same_field_rejected(self):
        """Negative test: conflicting proposals for same POI/field must be rejected."""
        prop_a = ProposalRecord(
            poi_id="poi-tky-sensoji",
            field="name.tr",
            current_value="Sensoji Tapinagi",
            proposed_value="Sensō-ji Tapınağı Variant A",
            reason="Candidate A",
            status="AUTO_SAFE",
        )
        prop_b = ProposalRecord(
            poi_id="poi-tky-sensoji",
            field="name.tr",
            current_value="Sensoji Tapinagi",
            proposed_value="Sensō-ji Tapınağı Variant B",
            reason="Candidate B",
            status="AUTO_SAFE",
        )
        result = apply_proposals_safely(self.dataset, [prop_a, prop_b])
        self.assertEqual(len(result.applied), 0)
        self.assertEqual(len(result.skipped), 2)
        self.assertFalse(result.is_changed)
        for rej in result.rejections:
            self.assertEqual(rej["reason"], "CONFLICTING_PROPOSALS")

    def test_non_auto_safe_proposal_rejected_without_explicit_review_confirmation(self):
        """Ambiguous or non-AUTO_SAFE proposal cannot be applied without explicit confirmation."""
        active_val = self.dataset["places"][0]["name"]["tr"]
        ambiguous_prop = ProposalRecord(
            poi_id="poi-tky-sensoji",
            field="name.tr",
            current_value=active_val,
            proposed_value="Sensō-ji Tapınağı (Ambiguous Variant)",
            reason="Ambiguous candidate",
            status="REVIEW_REQUIRED",
        )
        # Without confirmation
        res1 = apply_proposals_safely(self.dataset, [ambiguous_prop], confirm_review=False)
        self.assertEqual(len(res1.applied), 0)
        self.assertEqual(len(res1.skipped), 1)
        self.assertFalse(res1.is_changed)
        self.assertEqual(res1.rejections[0]["reason"], "REVIEW_REQUIRED")

        # With explicit confirmation
        res2 = apply_proposals_safely(self.dataset, [ambiguous_prop], confirm_review=True)
        self.assertEqual(len(res2.applied), 1)
        self.assertTrue(res2.is_changed)

    def test_atomic_write_zero_changes_leaves_sha256_unaltered(self):
        """Zero changes must not rewrite file; SHA-256 and mtime must remain strictly unchanged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = pathlib.Path(tmpdir) / "test_data.json"
            content = json.dumps(self.dataset, indent=2, ensure_ascii=False) + "\n"
            file_path.write_text(content, encoding="utf-8")

            sha_before = hashlib.sha256(file_path.read_bytes()).hexdigest()
            mtime_before = os.path.getmtime(file_path)

            # Attempt atomic write with is_changed=False
            written = atomic_write_dataset(file_path, self.dataset, is_changed=False)
            self.assertFalse(written)

            sha_after = hashlib.sha256(file_path.read_bytes()).hexdigest()
            mtime_after = os.path.getmtime(file_path)

            self.assertEqual(sha_before, sha_after)
            self.assertEqual(mtime_before, mtime_after)

    def test_atomic_write_creates_replacement_with_fsync(self):
        """When is_changed=True, writes cleanly using atomic replace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = pathlib.Path(tmpdir) / "output.json"
            modified = copy.deepcopy(self.dataset)
            modified["places"][0]["name"]["tr"] = "Surgically Modified Name"

            written = atomic_write_dataset(file_path, modified, is_changed=True)
            self.assertTrue(written)
            self.assertTrue(file_path.exists())

            loaded = json.loads(file_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["places"][0]["name"]["tr"], "Surgically Modified Name")

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
