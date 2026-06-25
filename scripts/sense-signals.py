#!/usr/bin/env python3
"""sense-signals — detect user friction/frustration signals from stdin or args.
Outputs JSON with signal types, severity, and suggested response adjustments.
Usage: python sense-signals.py [text] | python sense-signals.py --file <path>"""

import sys, json, re, io
from pathlib import Path

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

SIGNALS = {
    "repetition": {
        "patterns": [
            r"(又|再次|还是|还是没|又没|怎么又|怎么还是)",
            r"\b(again|still|still not|once more|yet again)\b",
            r"还是不对|还是不行|还是没",
        ],
        "severity": "medium",
        "action": "查记忆 → 查上次方案 → 用不同方法重试。同错两次=停找根因。",
    },
    "correction": {
        "patterns": [
            r"(不是|不对|错了|不是这样|不应该|不应该这样)",
            r"\b(wrong|incorrect|not right|shouldn't|don't do that)\b",
            r"我不是说|我说的是|搞错了",
        ],
        "severity": "high",
        "action": "立即纠正行为，写规则防止再犯。询问用户期望的正确行为。",
    },
    "short_response": {
        "patterns": [],  # heuristic: text length < 20 chars
        "severity": "low",
        "max_len": 20,
        "action": "用户可能不耐烦。简洁回复、跳过解释、直接做事。",
    },
    "imperative": {
        "patterns": [
            r"\b(不要|别|不准|禁止|停止|马上|立刻|直接|快)\b",
            r"\b(do|don't|stop|never|just|simply|quickly)\b",
        ],
        "severity": "medium",
        "action": "用户在下命令。减少解释，增加执行速度。检查是否有规则冲突。",
    },
    "dissatisfaction": {
        "patterns": [
            r"(太慢|太差|不好|不行|没用|没帮助|浪费时间|还是不行)",
            r"\b(useless|slow|terrible|bad|not helping|waste)\b",
            r"为什么总是|有什么用|没意义",
        ],
        "severity": "high",
        "action": "用户不满。立即改变策略：更简洁、更快速、更准确。检查是否有系统性问题。",
    },
    "confusion": {
        "patterns": [
            r"(不懂|不明白|没理解|什么意思|到底|混乱|搞混)",
            r"\b(confused|don't understand|what do you mean|unclear)\b",
        ],
        "severity": "medium",
        "action": "用户困惑。用更简单的语言重新解释。给具体例子。",
    },
}


def detect_signals(text: str) -> list[dict]:
    """Detect all friction signals in text."""
    results = []

    # Check text length for short-response signal
    clean = text.strip()
    if len(clean) < SIGNALS["short_response"]["max_len"]:
        results.append({
            "signal": "short_response",
            "severity": SIGNALS["short_response"]["severity"],
            "action": SIGNALS["short_response"]["action"],
        })

    # Check pattern-based signals
    for name, config in SIGNALS.items():
        if name == "short_response":
            continue
        for pattern in config["patterns"]:
            if re.search(pattern, clean, re.IGNORECASE):
                results.append({
                    "signal": name,
                    "severity": config["severity"],
                    "pattern_matched": pattern,
                    "action": config["action"],
                })
                break  # one match per signal type

    return results


def compute_friction_score(signals: list[dict]) -> float:
    """Compute overall friction score 0-1."""
    weights = {"high": 0.4, "medium": 0.25, "low": 0.1}
    score = sum(weights.get(s["severity"], 0.1) for s in signals)
    return min(score, 1.0)


def main():
    text = ""
    if len(sys.argv) > 1:
        if sys.argv[1] == "--file" and len(sys.argv) > 2:
            text = Path(sys.argv[2]).read_text(encoding="utf-8")
        elif sys.argv[1] in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        else:
            text = " ".join(sys.argv[1:])
    else:
        text = sys.stdin.read()

    if not text.strip():
        print(json.dumps({"signals": [], "friction": 0.0, "note": "empty input"}))
        sys.exit(0)

    signals = detect_signals(text)
    friction = compute_friction_score(signals)

    output = {
        "signals": signals,
        "friction": round(friction, 3),
        "count": len(signals),
        "input_length": len(text.strip()),
        "verdict": (
            "clean" if friction < 0.15
            else "mild" if friction < 0.3
            else "moderate" if friction < 0.5
            else "high_friction"
        ),
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))
    sys.exit(0 if friction < 0.5 else 1)


if __name__ == "__main__":
    main()
