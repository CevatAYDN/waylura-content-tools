"""Unicode normalization and multilingual script detection utilities."""
from __future__ import annotations

import re
import unicodedata

# Unicode script ranges
CYRILLIC_PATTERN = re.compile(r"[\u0400-\u04FF\u0500-\u052F]")
HIRAGANA_PATTERN = re.compile(r"[\u3040-\u309F]")
KATAKANA_PATTERN = re.compile(r"[\u30A0-\u30FF]")
KANJI_PATTERN = re.compile(r"[\u4E00-\u9FFF\u3400-\u4DBF]")
CJK_PATTERN = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u3400-\u4DBF]")
LATIN_PATTERN = re.compile(r"[A-Za-z\u00C0-\u024F\u1E00-\u1EFF]")


def normalize_nfc(text: str) -> str:
    """Return the NFC-normalized form of a string."""
    return unicodedata.normalize("NFC", text)


def is_nfc(text: str) -> bool:
    """Return True if the string is already normalized to NFC."""
    return unicodedata.is_normalized("NFC", text)


def contains_cyrillic(text: str) -> bool:
    """Return True if string contains Cyrillic characters."""
    return bool(CYRILLIC_PATTERN.search(text))


def contains_cjk(text: str) -> bool:
    """Return True if string contains Kanji, Hiragana, or Katakana."""
    return bool(CJK_PATTERN.search(text))


def contains_latin(text: str) -> bool:
    """Return True if string contains Latin alphabet characters."""
    return bool(LATIN_PATTERN.search(text))


def detect_unexpected_scripts(text: str, allowed_scripts: set[str]) -> list[str]:
    """Detect presence of scripts outside the allowed set.
    
    Allowed scripts can include: 'latin', 'cjk', 'cyrillic', 'common'.
    """
    found = []
    if "cyrillic" not in allowed_scripts and contains_cyrillic(text):
        found.append("cyrillic")
    if "cjk" not in allowed_scripts and contains_cjk(text):
        found.append("cjk")
    if "latin" not in allowed_scripts and contains_latin(text):
        found.append("latin")
    return found
