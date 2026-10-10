"""Tests for unicode_utils module."""
import unittest
import unicodedata
from waylura_content_tools.unicode_utils import (
    contains_cjk,
    contains_cyrillic,
    contains_latin,
    detect_unexpected_scripts,
    is_nfc,
    normalize_nfc,
)


class UnicodeUtilsTests(unittest.TestCase):
    def test_nfc_normalization(self):
        # NFD form of 'ç' (c + combining cedilla)
        nfd_c = "c\u0327"
        nfc_c = "ç"
        self.assertFalse(is_nfc(nfd_c))
        self.assertTrue(is_nfc(nfc_c))
        self.assertEqual(normalize_nfc(nfd_c), nfc_c)

    def test_cyrillic_detection(self):
        self.assertTrue(contains_cyrillic("Храм Сенсодзи"))
        self.assertTrue(contains_cyrillic("Москва"))
        self.assertFalse(contains_cyrillic("Sensō-ji"))
        self.assertFalse(contains_cyrillic("浅草寺"))

    def test_cjk_detection(self):
        self.assertTrue(contains_cjk("金閣寺"))
        self.assertTrue(contains_cjk("とうきょう"))
        self.assertTrue(contains_cjk("タリーズコーヒー"))
        self.assertFalse(contains_cjk("Tokyo Tower"))
        self.assertFalse(contains_cjk("Ayasofya"))

    def test_latin_detection(self):
        self.assertTrue(contains_latin("Istanbul"))
        self.assertTrue(contains_latin("Kaleiçi"))
        self.assertFalse(contains_latin("金閣寺"))
        self.assertFalse(contains_latin("12345"))

    def test_detect_unexpected_scripts(self):
        text = "Sensō-ji Храм"
        unexpected = detect_unexpected_scripts(text, allowed_scripts={"latin"})
        self.assertIn("cyrillic", unexpected)


if __name__ == "__main__":
    unittest.main()
