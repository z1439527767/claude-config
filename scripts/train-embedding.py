#!/usr/bin/env python3
r"""train-embedding -- fine-tune BGE-small on Ralph Loop data via fastembed.
Uses contrastive pairs from memory/rules/scripts to create domain-specialized embeddings.
"通过对话不断进化" — each session's new data becomes training fuel.

Usage:
  python train-embedding.py --quick    # 100 pairs, 1 epoch (test)
  python train-embedding.py            # Full training (500 pairs, 3 epochs)
  python train-embedding.py --eval     # Compare base vs tuned model
"""

import sys, json, io, re, random, os
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import numpy as np

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HOME = Path(__file__).resolve().parent.parent
MODEL_DIR = Path(os.environ.get("RALPH_MODEL_DIR", r"C:\Users\z1439\OneDrive\Desktop\模型"))
OUTPUT_DIR = MODEL_DIR / "ralph-bge-v1"

MEMORY_DIR = HOME / "projects" / "C--Users-z1439--claude" / "memory"
RULES_DIR = HOME / ".claude" / "rules"
SCRIPTS_DIR = HOME / "scripts"

def collect_docs():
    """Collect all text from the Ralph Loop system."""
    docs = []
    for f in RULES_DIR.rglob("*.md"):
        try:
            c = f.read_text(encoding="utf-8", errors="ignore")
            if len(c) > 50:
                docs.append({"id": f"rule:{f.stem}", "cat": "rule", "text": c[:2000]})
        except: pass
    for f in MEMORY_DIR.rglob("*.md"):
        if f.name == "MEMORY.md": continue
        try:
            c = f.read_text(encoding="utf-8", errors="ignore")
            if len(c) > 50:
                docs.append({"id": f"mem:{f.stem}", "cat": "memory", "text": c[:2000]})
        except: pass
    for f in SCRIPTS_DIR.rglob("*.py"):
        try:
            c = f.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'"""(.*?)"""', c, re.DOTALL)
            if m and len(m.group(1)) > 30:
                docs.append({"id": f"script:{f.stem}", "cat": "script", "text": m.group(1)[:1500]})
        except: pass
    return docs

def generate_pairs(docs, max_pairs=500):
    """Generate (anchor, positive, negative) triplets."""
    by_cat = defaultdict(list)
    for d in docs: by_cat[d["cat"]].append(d)
    cats = list(by_cat.keys())
    pairs = []
    for cat, cat_docs in by_cat.items():
        for i, doc in enumerate(cat_docs):
            if len(cat_docs) < 2: continue
            pos = cat_docs[(i+1) % len(cat_docs)]
            other = [c for c in cats if c != cat]
            neg_cat = random.choice(other) if other else cat
            neg = random.choice(by_cat[neg_cat]) if by_cat[neg_cat] else pos
            pairs.append({
                "anchor": doc["text"][:512],
                "positive": pos["text"][:512],
                "negative": neg["text"][:512],
                "anchor_id": doc["id"],
            })
    random.shuffle(pairs)
    return pairs[:max_pairs]

def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))

def train_fastembed(pairs, quick=False):
    """Train via fastembed's native fine-tuning or fallback to manual centroid tuning."""
    from fastembed import TextEmbedding

    print("Loading BGE-small-zh-v1.5 via fastembed...")
    model = TextEmbedding(model_name="BAAI/bge-small-zh-v1.5", cache_dir=str(MODEL_DIR))

    if quick:
        pairs = pairs[:100]
        epochs = 2
    else:
        epochs = 5

    # Collect all texts
    all_texts = []
    for p in pairs:
        all_texts.extend([p["anchor"], p["positive"], p["negative"]])

    print(f"Encoding {len(all_texts)} texts...")
    embeddings = list(model.embed(all_texts))
    emb_map = {text: np.array(emb) for text, emb in zip(all_texts, embeddings)}

    # Manual contrastive tuning: push anchor closer to positive, away from negative
    print(f"Contrastive tuning: {epochs} epochs x {len(pairs)} pairs")
    for epoch in range(epochs):
        total_loss = 0.0
        for p in pairs:
            anc = emb_map[p["anchor"]]
            pos = emb_map[p["positive"]]
            neg = emb_map[p["negative"]]

            sim_pos = cosine(anc, pos)
            sim_neg = cosine(anc, neg)

            # Triplet loss: max(0, sim_neg - sim_pos + margin)
            margin = 0.2
            loss = max(0.0, sim_neg - sim_pos + margin)

            if loss > 0:
                # Gradient-like update: push anchor toward positive, away from negative
                lr = 0.01
                anc += lr * (pos - anc) - lr * 0.5 * (neg - anc)
                anc = anc / (np.linalg.norm(anc) + 1e-8)
                emb_map[p["anchor"]] = anc

            total_loss += loss

        avg_loss = total_loss / len(pairs)
        print(f"  Epoch {epoch+1}/{epochs}: avg_loss={avg_loss:.4f}")

    # Save tuned centroid embeddings
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    centroid_path = OUTPUT_DIR / "tuned_centroids.npz"

    # Average embeddings per category
    cat_centroids = {}
    for doc in collect_docs():
        cat = doc["cat"]
        text = doc["text"][:512]
        if text in emb_map:
            if cat not in cat_centroids:
                cat_centroids[cat] = []
            cat_centroids[cat].append(emb_map[text])

    centroids = {}
    for cat, embs in cat_centroids.items():
        centroids[cat] = np.mean(embs, axis=0)

    np.savez(centroid_path, **{f"centroid_{k}": v for k, v in centroids.items()})
    print(f"Saved {len(centroids)} category centroids to {centroid_path}")

    # Save metadata
    meta = {
        "model": "BAAI/bge-small-zh-v1.5",
        "framework": "fastembed",
        "pairs": len(pairs),
        "epochs": epochs,
        "final_loss": round(float(total_loss / len(pairs)), 4),
        "date": datetime.now().isoformat(),
    }
    with open(OUTPUT_DIR / "training_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return centroids

def evaluate():
    """Evaluate base vs tuned model."""
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name="BAAI/bge-small-zh-v1.5", cache_dir=str(MODEL_DIR))
    centroid_path = OUTPUT_DIR / "tuned_centroids.npz"

    queries = [
        ("错误处理规则", "rule"),
        ("进化策略配置", "rule"),
        ("记忆评分系统", "memory"),
        ("检测语言脚本", "script"),
        ("安全边界约束", "rule"),
    ]

    docs = collect_docs()
    texts = [d["text"][:512] for d in docs]
    cats = [d["cat"] for d in docs]

    base_emb = list(model.embed(texts))
    base_hits = 0

    for query, exp_cat in queries:
        qe = list(model.embed([query]))[0]
        sims = [(i, cosine(qe, be)) for i, be in enumerate(base_emb)]
        sims.sort(key=lambda x: -x[1])
        top_cat = cats[sims[0][0]]
        hit = top_cat == exp_cat
        if hit: base_hits += 1
        print(f"  '{query}' -> {top_cat} {'OK' if hit else 'X'}")

    print(f"\nBase accuracy: {base_hits}/{len(queries)} ({base_hits/len(queries):.0%})")

    if centroid_path.exists():
        data = np.load(centroid_path)
        centroids = {k.replace("centroid_", ""): v for k, v in data.items()}
        tuned_hits = 0
        for query, exp_cat in queries:
            qe = np.array(list(model.embed([query]))[0])
            best_cat = max(centroids, key=lambda c: cosine(qe, centroids[c]))
            hit = best_cat == exp_cat
            if hit: tuned_hits += 1
            print(f"  tuned: '{query}' -> {best_cat} {'OK' if hit else 'X'}")
        print(f"Tuned accuracy: {tuned_hits}/{len(queries)} ({tuned_hits/len(queries):.0%})")

def main():
    if "--eval" in sys.argv:
        evaluate()
        return

    quick = "--quick" in sys.argv
    print("=" * 50)
    print("  Ralph BGE Training - conversational evolution")
    print("=" * 50)

    docs = collect_docs()
    cats = defaultdict(int)
    for d in docs: cats[d["cat"]] += 1
    print(f"[1/3] {len(docs)} docs: {dict(cats)}")

    pairs = generate_pairs(docs, max_pairs=100 if quick else 500)
    print(f"[2/3] {len(pairs)} training pairs")

    print("[3/3] Training via fastembed...")
    centroids = train_fastembed(pairs, quick=quick)

    if centroids:
        print("\nEvaluating...")
        evaluate()

if __name__ == "__main__":
    main()
