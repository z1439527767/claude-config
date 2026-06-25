#!/usr/bin/env python3
r"""ralph-infer.py -- run the fine-tuned Ralph model for inference.
The "小钢炮" in action: fast, domain-specialized Q&A.
Supports conversation memory — remembers past exchanges and learns from them.

Usage:
  python ralph-infer.py                          # Interactive chat
  python ralph-infer.py "什么是OODA循环？"        # Single query
  python ralph-infer.py --learn "new_fact"        # Add knowledge to brain
"""

import sys, json, io, os
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HOME = Path(__file__).resolve().parent.parent
MODEL_DIR = Path(os.environ.get("RALPH_MODEL_DIR", r"C:\Users\z1439\OneDrive\Desktop\模型"))
MODEL_PATH = MODEL_DIR / "ralph-smollm-v1"
BRAIN_DATA = MODEL_DIR / "brain_dataset.jsonl"
CONVERSATION_MEMORY = MODEL_DIR / "conversation_memory.jsonl"

def load_model():
    """Load the fine-tuned model or fall back to base."""
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
    except ImportError:
        print("ERROR: transformers/torch not installed")
        return None, None

    if MODEL_PATH.exists() and (MODEL_PATH / "adapter_config.json").exists():
        print(f"Loading tuned model: {MODEL_PATH}")
        tokenizer = AutoTokenizer.from_pretrained(str(MODEL_PATH))
        model = AutoModelForCausalLM.from_pretrained(
            str(MODEL_PATH), torch_dtype=torch.float32, device_map="cpu"
        )
    else:
        # Use BGE embeddings as fallback "model"
        print("Tuned model not found. Using embedding-based retrieval as fallback.")
        return None, None

    return model, tokenizer

def embedding_search(query: str) -> str:
    """Fallback: use embedding model to search brain dataset."""
    from fastembed import TextEmbedding
    import numpy as np

    model = TextEmbedding(model_name="BAAI/bge-small-zh-v1.5", cache_dir=str(MODEL_DIR))

    # Load brain data
    data = []
    if BRAIN_DATA.exists():
        with open(BRAIN_DATA, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data.append(json.loads(line))

    if not data:
        return "Brain dataset not found. Run distill-brain.py first."

    # Embed query
    q_emb = list(model.embed([query]))[0]

    # Search
    best_score = -1
    best_output = ""
    for ex in data:
        inst = ex.get("instruction", "")
        i_emb = list(model.embed([inst]))[0] if inst else np.zeros(512)
        score = float(np.dot(q_emb, i_emb))
        if score > best_score:
            best_score = score
            best_output = ex.get("output", "")

    if best_score > 0.3:
        return f"[retrieved, score={best_score:.3f}]\n{best_output}"
    return "No matching knowledge found."

def generate_response(model, tokenizer, query: str) -> str:
    """Generate response from tuned model."""
    if model is None:
        return embedding_search(query)

    prompt = f"### Instruction:\n{query}\n\n### Response:\n"
    inputs = tokenizer(prompt, return_tensors="pt")

    import torch
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=200,
            temperature=0.7,
            do_sample=True,
            top_p=0.9,
            pad_token_id=tokenizer.eos_token_id,
        )

    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    if "### Response:" in response:
        response = response.split("### Response:")[-1].strip()
    return response

def learn_from_conversation(query: str, response: str):
    """Store conversation as training data for future evolution."""
    CONVERSATION_MEMORY.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "instruction": query,
        "input": "",
        "output": response,
        "source": "conversation",
    }
    with open(CONVERSATION_MEMORY, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Also append to brain dataset
    with open(BRAIN_DATA, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def interactive():
    """Interactive chat mode."""
    model, tokenizer = load_model()

    print("=" * 50)
    print("  Ralph 小钢炮 — Interactive Mode")
    print("  Type 'quit' to exit, '!learn' to force learn")
    print("=" * 50)

    history = []
    while True:
        try:
            query = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            break

        response = generate_response(model, tokenizer, query)
        print(f"\nRalph: {response}")

        # Store for learning
        learn_from_conversation(query, response)
        history.append({"q": query, "a": response})

    print(f"\nSession stored: {len(history)} exchanges → brain dataset")

def main():
    if "--learn" in sys.argv:
        idx = sys.argv.index("--learn")
        if idx + 1 < len(sys.argv):
            fact = sys.argv[idx + 1]
            learn_from_conversation("manual injection", fact)
            print(f"Learned: {fact}")
        return

    # Single query mode
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        query = " ".join(args)
        model, tokenizer = load_model()
        response = generate_response(model, tokenizer, query)
        print(response)
        learn_from_conversation(query, response)
        return

    # Interactive mode
    interactive()

if __name__ == "__main__":
    main()
