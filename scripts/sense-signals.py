#!/usr/bin/env python3
"""sense-signals — detect user frustration/confusion signals from conversation.
Reads conversation text from stdin or file, outputs structured signal report.
Usage: cat session.txt | python3 sense-signals.py
       python3 sense-signals.py --file session.txt"""

import sys, re, json, math
from collections import Counter

# ── Signal detectors ──

def detect_repetition(messages):
    """Detect repeated instructions (user saying same thing again)."""
    if len(messages) < 2:
        return 0.0
    repeats = 0
    for i in range(1, len(messages)):
        prev = messages[i-1].lower().strip()
        curr = messages[i].lower().strip()
        # Simple word overlap
        prev_words = set(prev.split())
        curr_words = set(curr.split())
        if prev_words and curr_words:
            overlap = len(prev_words & curr_words) / max(len(prev_words), len(curr_words))
            if overlap > 0.6:
                repeats += 1
    return min(1.0, repeats / max(len(messages) - 1, 1))

def detect_brevity_shift(messages):
    """Detect sudden shift to very short messages (frustration indicator)."""
    if len(messages) < 3:
        return 0.0
    lengths = [len(m) for m in messages]
    avg_len = sum(lengths) / len(lengths) if lengths else 0
    recent = lengths[-3:]
    short_count = sum(1 for l in recent if l < avg_len * 0.4 and l < 30)
    return short_count / 3.0

def detect_imperative_tone(messages):
    """Detect imperative/commanding tone (no politeness, short direct commands)."""
    if not messages:
        return 0.0
    politeness = {'please', 'thanks', 'thank', 'could', 'would', 'can you', '请', '谢谢', '麻烦'}
    imperatives = 0
    for m in messages[-5:]:
        low = m.lower().strip()
        # Short, starts with verb, no politeness
        words = low.split()
        if len(words) < 8 and not any(p in low for p in politeness):
            imperatives += 1
    return imperatives / min(len(messages[-5:]), 5)

def detect_correction_frequency(messages):
    """Detect correction patterns: 'no', '不是', '不对', '错了'."""
    if len(messages) < 3:
        return 0.0
    correction_words = {'no', 'wrong', "don't", 'dont', 'incorrect', '不是', '不对', '错了', '不', '别'}
    corrections = 0
    for m in messages[-5:]:
        low = m.lower()
        if any(c in low for c in correction_words):
            corrections += 1
    return min(1.0, corrections / 3.0)

def detect_caps_emphasis(messages):
    """Detect CAPS or excessive punctuation (!!, !?, ...)."""
    if not messages:
        return 0.0
    recent = messages[-3:]
    scores = []
    for m in recent:
        caps = sum(1 for c in m if c.isupper())
        total = len([c for c in m if c.isalpha()])
        cap_ratio = caps / max(total, 1)
        exclaim = m.count('!!') + m.count('！')
        scores.append(min(1.0, cap_ratio * 2 + exclaim * 0.3))
    return sum(scores) / len(scores) if scores else 0.0

# ── Composite score ──

WEIGHTS = {
    'repetition': 0.8,     # Strongest signal
    'brevity_shift': 0.4,  # Medium
    'imperative_tone': 0.5, # Medium
    'correction_frequency': 0.7, # Strong
    'caps_emphasis': 0.6,  # Medium
}

LEVELS = [
    (0.0, 0.2, 'normal',    '正常'),
    (0.2, 0.4, 'mild',      '轻微不适'),
    (0.4, 0.6, 'elevated',  '明显不满'),
    (0.6, 0.8, 'high',      '高度挫败'),
    (0.8, 1.0, 'critical',  '严重挫败'),
]

def analyze(messages):
    signals = {
        'repetition': round(detect_repetition(messages), 3),
        'brevity_shift': round(detect_brevity_shift(messages), 3),
        'imperative_tone': round(detect_imperative_tone(messages), 3),
        'correction_frequency': round(detect_correction_frequency(messages), 3),
        'caps_emphasis': round(detect_caps_emphasis(messages), 3),
    }
    weighted = sum(signals[k] * WEIGHTS[k] for k in signals)
    weighted /= sum(WEIGHTS.values())
    level = 'normal'
    level_cn = '正常'
    for lo, hi, en, cn in LEVELS:
        if lo <= weighted < hi:
            level, level_cn = en, cn
            break
    return {
        'score': round(weighted, 3),
        'level': level,
        'level_cn': level_cn,
        'signals': signals,
        'suggestion': get_suggestion(weighted),
    }

def get_suggestion(score):
    if score < 0.2:
        return '正常继续。'
    elif score < 0.4:
        return '放慢速度，多确认。简化回复，少展开。'
    elif score < 0.6:
        return '直接回答问题，不绕弯。承认之前的错误（如有）。用祈使句给出明确行动。'
    elif score < 0.8:
        return '停——用户很沮丧。一句话承认问题。只做用户要求的，不做额外的。'
    else:
        return '紧急：用户严重挫败。停止所有主动行为。只回答直接问题。建议用户重述需求。'

def extract_messages(text):
    """Extract individual messages from conversation text."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    # Try to split by common separators
    messages = []
    current = []
    for line in lines:
        # Skip metadata lines
        if line.startswith('[') and ']' in line[:20]:
            if current:
                messages.append(' '.join(current))
                current = []
            continue
        current.append(line)
    if current:
        messages.append(' '.join(current))
    return messages if messages else lines

if __name__ == '__main__':
    if '--file' in sys.argv:
        idx = sys.argv.index('--file')
        text = open(sys.argv[idx + 1], encoding='utf-8').read()
    elif len(sys.argv) > 1:
        text = ' '.join(sys.argv[1:])
    else:
        text = sys.stdin.read()

    messages = extract_messages(text)
    if not messages:
        print(json.dumps({'error': 'no messages found'}, ensure_ascii=False))
        sys.exit(1)

    result = analyze(messages)
    print(json.dumps(result, ensure_ascii=False, indent=2))
