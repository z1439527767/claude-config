#!/usr/bin/env python3
r"""finetune-smollm.py -- PURE PYTORCH LoRA fine-tuning. No scipy, no sklearn.
Direct training loop for maximum compatibility on Windows.

Usage: python finetune-smollm.py
"""

import sys, json, io, os, math, time
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HOME = Path(__file__).resolve().parent.parent
MODEL_DIR = Path(os.environ.get("RALPH_MODEL_DIR", r"C:\Users\z1439\OneDrive\Desktop\模型"))
OUTPUT_DIR = MODEL_DIR / "ralph-smollm-v1"
BRAIN_DATA = MODEL_DIR / "brain_dataset.jsonl"
BASE_MODEL = "Qwen/Qwen2.5-0.5B"

def load_dataset():
    if not BRAIN_DATA.exists():
        print(f"ERROR: {BRAIN_DATA} not found.")
        return []
    data = []
    with open(BRAIN_DATA, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data

def format_for_training(examples):
    formatted = []
    for ex in examples:
        inst = ex.get("instruction", "")
        inp = ex.get("input", "")
        out = ex.get("output", "")
        if inp:
            text = f"### Instruction:\n{inst}\n\n### Input:\n{inp}\n\n### Response:\n{out}"
        else:
            text = f"### Instruction:\n{inst}\n\n### Response:\n{out}"
        formatted.append(text)
    return formatted

def train():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, get_peft_model

    use_cpu = "--cpu" in sys.argv
    device = "cpu" if use_cpu else ("cuda" if torch.cuda.is_available() else "cpu")

    data = load_dataset()
    if not data:
        return
    texts = format_for_training(data)
    print(f"Brain dataset: {len(texts)} examples")
    print(f"Base model: {BASE_MODEL}")
    print(f"Device: {device}")
    if device == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory/1e9:.1f} GB")

    # Load tokenizer
    print("\nLoading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Tokenize
    print("Tokenizing...")
    encodings = tokenizer(texts, truncation=True, padding=True, max_length=512, return_tensors="pt")
    input_ids = encodings["input_ids"].to(device)
    attention_mask = encodings["attention_mask"].to(device)

    # Load model
    print("Loading model...")
    dtype = torch.float32 if device == "cpu" else torch.float16
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, torch_dtype=dtype, device_map=device if device == "cuda" else None,
        low_cpu_mem_usage=True,
    )
    if device == "cpu":
        model = model.to(device)

    # LoRA
    lora_config = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        bias="none", task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    model.train()
    if device == "cuda":
        model.gradient_checkpointing_enable()

    # Training setup
    batch_size = 2 if device == "cuda" else 1
    epochs = 6
    lr = 2e-4
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    num_batches = math.ceil(len(input_ids) / batch_size)

    print(f"\nTraining: {epochs} epochs × {num_batches} batches (batch={batch_size})")
    print(f"Total steps: {epochs * num_batches}, LR: {lr}")

    # Training loop
    total_loss = 0.0
    step = 0
    start_time = time.time()

    for epoch in range(epochs):
        epoch_loss = 0.0
        # Shuffle
        perm = torch.randperm(len(input_ids))
        shuffled_ids = input_ids[perm]
        shuffled_mask = attention_mask[perm]

        for i in range(0, len(shuffled_ids), batch_size):
            batch_ids = shuffled_ids[i:i+batch_size]
            batch_mask = shuffled_mask[i:i+batch_size]

            outputs = model(input_ids=batch_ids, attention_mask=batch_mask, labels=batch_ids)
            loss = outputs.loss

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            epoch_loss += loss.item()
            step += 1

            if step % 10 == 0:
                avg_loss = epoch_loss / (step % num_batches or 1)
                elapsed = time.time() - start_time
                print(f"  Step {step:4d}/{epochs*num_batches} | Loss: {loss.item():.4f} | Avg: {avg_loss:.4f} | {elapsed:.0f}s")

        avg_epoch_loss = epoch_loss / num_batches
        total_loss += avg_epoch_loss
        print(f"  Epoch {epoch+1}/{epochs} complete. Avg loss: {avg_epoch_loss:.4f}")

    elapsed = time.time() - start_time
    print(f"\nTraining finished in {elapsed:.0f}s ({elapsed/60:.1f} min)")

    # Save
    print(f"Saving to {OUTPUT_DIR}...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    meta = {
        "base_model": BASE_MODEL, "training_examples": len(texts),
        "training_date": datetime.now().isoformat(), "method": "LoRA fp16 pure PyTorch",
        "lora_rank": 16, "lora_alpha": 32, "epochs": epochs,
        "batch_size": batch_size, "learning_rate": lr,
        "final_loss": round(total_loss / epochs, 4),
        "training_time_seconds": round(elapsed),
        "device": device,
    }
    with open(OUTPUT_DIR / "training_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"Done! Model saved. Final loss: {total_loss/epochs:.4f}")


def test_inference():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    if not OUTPUT_DIR.exists():
        print("No trained model found. Run training first.")
        return

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading model from {OUTPUT_DIR} on {device}...")

    base = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, torch_dtype=torch.float16 if device=="cuda" else torch.float32,
        device_map=device if device=="cuda" else None,
    )
    if device == "cpu":
        base = base.to(device)
    model = PeftModel.from_pretrained(base, OUTPUT_DIR)
    tokenizer = AutoTokenizer.from_pretrained(OUTPUT_DIR)

    queries = [
        "错误处理的第一步是什么？",
        "什么是OODA循环？",
        "如何防止AI变得傲慢？",
    ]
    for q in queries:
        prompt = f"### Instruction:\n{q}\n\n### Response:\n"
        inputs = tokenizer(prompt, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=120, temperature=0.7,
                                     do_sample=True, top_p=0.9, pad_token_id=tokenizer.eos_token_id)
        resp = tokenizer.decode(outputs[0], skip_special_tokens=True)
        if "### Response:" in resp:
            resp = resp.split("### Response:")[-1].strip()
        print(f"\nQ: {q}\nA: {resp[:200]}")


def main():
    if "--test" in sys.argv:
        test_inference()
    else:
        train()

if __name__ == "__main__":
    main()
