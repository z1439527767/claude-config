#!/usr/bin/env python3
"""guess-lang — fast language guessing from short text without ML dependency.
Falls back to heuristic-based detection. For accurate results use detect-lang.py (ELD-C).
Usage: python guess-lang.py [text] | echo "text" | python guess-lang.py"""

import sys, re
from collections import Counter

# Character-range heuristics (Unicode blocks)
CJK_RANGES = [
    (0x4E00, 0x9FFF),   # CJK Unified
    (0x3400, 0x4DBF),   # CJK Ext-A
    (0x20000, 0x2A6DF), # CJK Ext-B
    (0xF900, 0xFAFF),   # CJK Compat
]
JP_KANA = (0x3040, 0x309F), (0x30A0, 0x30FF)  # Hiragana, Katakana
KR_HANGUL = (0xAC00, 0xD7AF), (0x1100, 0x11FF)

# Common word markers per language
MARKERS = {
    "zh": [r"的", r"了", r"是", r"在", r"我", r"不", r"这", r"们", r"他", r"么"],
    "zh-TW": [r"的", r"了", r"是", r"在", r"我", r"不", r"這", r"們", r"他", r"麼"],
    "ja": [r"です", r"ます", r"した", r"こと", r"もの", r"いる", r"ある", r"ない"],
    "ko": [r"습니다", r"입니다", r"하는", r"그리고", r"하지만", r"이", r"가", r"을", r"는", r"은"],
    "ru": [r"[а-яА-ЯёЁ]"],
    "ar": [r"[؀-ۿ]"],
    "th": [r"[฀-๿]"],
    "vi": [r"của", r"và", r"một", r"cho", r"được", r"không"],
    "de": [r"\b(der|die|das|und|ist|ein|eine|nicht|mit|auf|für)\b"],
    "fr": [r"\b(le|la|les|des|est|pas|une|dans|pour|avec|que)\b"],
    "es": [r"\b(el|la|los|las|una|con|para|por|del|que|más)\b"],
    "pt": [r"\b(o|a|os|as|um|uma|não|para|com|que|mais)\b"],
    "it": [r"\b(il|la|di|che|non|per|una|con|sono|più)\b"],
    "nl": [r"\b(de|het|een|van|en|niet|op|voor|met|dat)\b"],
}


def char_in_range(ch: str, ranges):
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in ranges)


def guess(text: str) -> str:
    text = text.strip()
    if not text:
        return "und"

    # Count character types
    cjk = sum(1 for c in text if char_in_range(c, CJK_RANGES))
    hiragana = sum(1 for c in text if char_in_range(c, [JP_KANA[0]]))
    katakana = sum(1 for c in text if char_in_range(c, [JP_KANA[1]]))
    hangul = sum(1 for c in text if char_in_range(c, KR_HANGUL))
    cyrillic = sum(1 for c in text if 0x0400 <= ord(c) <= 0x04FF)
    arabic = sum(1 for c in text if 0x0600 <= ord(c) <= 0x06FF)
    thai = sum(1 for c in text if 0x0E00 <= ord(c) <= 0x0E7F)
    latin = sum(1 for c in text if c.isascii() and c.isalpha())

    total_chars = len([c for c in text if not c.isspace()])

    # Script-based detection
    if hangul > total_chars * 0.15:
        return "ko"
    if hiragana + katakana > total_chars * 0.1:
        return "ja"
    if cjk > total_chars * 0.2:
        # Distinguish zh vs zh-TW
        tw_markers = sum(1 for m in MARKERS["zh-TW"] if m in text)
        if tw_markers > 1:
            return "zh-TW"
        return "zh"
    if cyrillic > total_chars * 0.3:
        return "ru"
    if arabic > total_chars * 0.3:
        return "ar"
    if thai > total_chars * 0.2:
        return "th"

    # Word-marker matching for Latin-script languages
    if latin > total_chars * 0.5:
        scores = Counter()
        for lang in ["de", "fr", "es", "pt", "it", "nl", "vi"]:
            for pattern in MARKERS.get(lang, []):
                if re.search(pattern, text, re.IGNORECASE):
                    scores[lang] += 1
        if scores:
            return scores.most_common(1)[0][0]
        return "en"  # default Latin → English

    return "und"


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        text = " ".join(sys.argv[1:])
    else:
        text = sys.stdin.read()

    result = guess(text)
    print(result)


if __name__ == "__main__":
    main()
