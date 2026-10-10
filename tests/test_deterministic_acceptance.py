"""Deterministic execution and developer acceptance verification tests."""
import hashlib
import json
import pathlib
import tempfile
import unittest

from waylura_content_tools.cli import main
from waylura_content_tools.fixer import apply_proposals_safely
from waylura_content_tools.name_auditor import audit_place_names
from waylura_content_tools.proposer import generate_proposals

EXAMPLES_DIR = pathlib.Path(__file__).resolve().parents[1] / "examples"


class DeterministicAcceptanceTests(unittest.TestCase):
    def test_deterministic_proposal_generation(self):
        sample = json.loads((EXAMPLES_DIR / "fixable_sample.json").read_text(encoding="utf-8"))

        # Run 1
        issues1 = audit_place_names(sample["places"])
        props1 = generate_proposals(issues1)
        json1 = json.dumps([p.to_dict() for p in props1], sort_keys=True)
        hash1 = hashlib.sha256(json1.encode("utf-8")).hexdigest()

        # Run 2
        issues2 = audit_place_names(sample["places"])
        props2 = generate_proposals(issues2)
        json2 = json.dumps([p.to_dict() for p in props2], sort_keys=True)
        hash2 = hashlib.sha256(json2.encode("utf-8")).hexdigest()

        self.assertEqual(hash1, hash2)
        self.assertEqual(json1, json2)

    def test_deterministic_fix_output(self):
        sample = json.loads((EXAMPLES_DIR / "fixable_sample.json").read_text(encoding="utf-8"))
        issues = audit_place_names(sample["places"])
        props = generate_proposals(issues)

        res1 = apply_proposals_safely(sample, props)
        res2 = apply_proposals_safely(sample, props)

        out1 = json.dumps(res1.modified_data, sort_keys=True)
        out2 = json.dumps(res2.modified_data, sort_keys=True)

        self.assertEqual(hashlib.sha256(out1.encode()).hexdigest(), hashlib.sha256(out2.encode()).hexdigest())

    def test_no_private_keys_or_secrets_in_examples(self):
        for json_file in EXAMPLES_DIR.glob("*.json"):
            content = json_file.read_text(encoding="utf-8").lower()
            forbidden = ["password", "secret", "bearer", "private_key", "poco", "ghp_"]
            for term in forbidden:
                self.assertNotIn(term, content, f"Forbidden term {term!r} found in example file {json_file.name}")


if __name__ == "__main__":
    unittest.main()
