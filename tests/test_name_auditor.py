"""Tests for name_auditor module."""
import json
import pathlib
import unittest
from waylura_content_tools.name_auditor import audit_place_names, is_record_evidence_complete

EXAMPLES_DIR = pathlib.Path(__file__).resolve().parents[1] / "examples"


class NameAuditorTests(unittest.TestCase):
    def test_clean_places_produce_no_errors(self):
        data = json.loads((EXAMPLES_DIR / "valid_japan.json").read_text(encoding="utf-8"))
        issues = audit_place_names(data["places"])
        errors = [i for i in issues if i.severity == "ERROR"]
        self.assertEqual(errors, [])

    def test_cyrillic_leakage_detected(self):
        places = [
            {
                "id": "poi-tky-sensoji",
                "name": {
                    "tr": "Храм Сенсодзи 金龍山 浅草寺",
                    "en": "Sensō-ji",
                    "local": "金龍山 浅草寺"
                }
            }
        ]
        issues = audit_place_names(places)
        cyrillic = [i for i in issues if i.issue_type == "CYRILLIC_SCRIPT_LEAKAGE"]
        self.assertEqual(len(cyrillic), 1)
        self.assertEqual(cyrillic[0].proposed_value, "Sensō-ji Tapınağı")
        self.assertEqual(cyrillic[0].classification, "SEMANTIC_NAME_CHANGE")

    def test_raw_cjk_in_turkish_field_detected(self):
        places = [
            {
                "id": "poi-kyo-kinkakuji",
                "name": {
                    "tr": "金閣寺",
                    "en": "Kinkaku-ji",
                    "local": "金閣寺"
                }
            }
        ]
        issues = audit_place_names(places)
        cjk_issues = [i for i in issues if i.issue_type == "UNTRANSLATED_CJK_IN_TARGET_LANGUAGE"]
        self.assertEqual(len(cjk_issues), 1)
        self.assertEqual(cjk_issues[0].proposed_value, "Kinkaku-ji (Altın Köşk Tapınağı)")
        self.assertEqual(cjk_issues[0].classification, "SEMANTIC_NAME_CHANGE")

    def test_poi_id_name_semantic_mismatch_detected(self):
        places = [
            {
                "id": "poi-tky-akihabara-station",
                "name": {
                    "tr": "Akihabara Bölgesi",
                    "en": "Akihabara District",
                    "local": "秋葉原"
                }
            }
        ]
        issues = audit_place_names(places)
        mismatches = [i for i in issues if i.issue_type == "POI_ID_NAME_SEMANTIC_MISMATCH"]
        self.assertEqual(len(mismatches), 1)
        self.assertTrue(mismatches[0].review_required)

    def test_mechanical_normalization_is_distinguished_from_semantic(self):
        # Denormalized string with combining acute (e + \u0301)
        denorm = "Cafe\u0301"
        places = [
            {
                "id": "poi-ist-cafe-example",
                "name": {
                    "tr": denorm,
                    "en": "Cafe",
                    "local": "Cafe"
                }
            }
        ]
        issues = audit_place_names(places)
        nfc_issues = [i for i in issues if i.issue_type == "UNICODE_NFC_DENORMALIZED"]
        self.assertEqual(len(nfc_issues), 1)
        self.assertEqual(nfc_issues[0].classification, "MECHANICAL_NORMALIZATION")
        self.assertFalse(nfc_issues[0].review_required)

    def test_evidence_completeness_evaluator(self):
        complete = {
            "verificationStatus": "OFFICIAL_VERIFIED",
            "sourceUrl": "https://whc.unesco.org/en/list/688/",
            "evidence": "UNESCO official listing citation documents 'Ninna-ji'."
        }
        self.assertTrue(is_record_evidence_complete(complete))

        # Missing URL
        missing_url = {
            "verificationStatus": "OFFICIAL_VERIFIED",
            "evidence": "Some evidence"
        }
        self.assertFalse(is_record_evidence_complete(missing_url))

        # Status not OFFICIAL_VERIFIED
        unverified_status = {
            "verificationStatus": "COMMUNITY_EVIDENCED",
            "sourceUrl": "https://example.com",
            "evidence": "Some evidence"
        }
        self.assertFalse(is_record_evidence_complete(unverified_status))


if __name__ == "__main__":
    unittest.main()
