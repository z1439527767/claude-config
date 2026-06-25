#!/usr/bin/env python3
r"""finetune-smollm.py -- QLoRA fine-tune SmolLM2-135M on brain dataset.
"小钢炮" training: small model + domain knowledge + continual evolution.

Requirements: pip install transformers datasets peft accelerate bitsandbytes torch
Hardware: Any GPU with 4GB+ VRAM (T4, RTX 2060+, etc.)
CPU fallback: Works on CPU with --cpu flag (slower, ~10x)

Usage:
  python finetune-smollm.py               # Full training (GPU)
  python finetune-smollm.py --cpu          # CPU training (slow but works anywhere)
  python finetune-smollm.py --test         # Test inference after training
  python finetune-smollm.py --merge        # Merge LoRA weights for deployment
"""

import sys, json, io, os, re
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HOME = Path(__file__).resolve().parent.parent
MODEL_DIR = Path(os.environ.get("RALPH_MODEL_DIR", r"C:\Users\z1439\OneDrive\Desktop\模型"))
OUTPUT_DIR = MODEL_DIR / "ralph-smollm-v1"
BRAIN_DATA = MODEL_DIR / "brain_dataset.jsonl"

# Model config
BASE_MODEL = "HuggingFaceTB/SmolLM2-135M"  # 135M params, can run on CPU
# Alternative: "Qwen/Qwen2.5-0.5B" for bigger model

def load_dataset():
    """Load brain dataset."""
    if not BRAIN_DATA.exists():
        print(f"ERROR: {BRAIN_DATA} not found. Run distill-brain.py + expand-brain-data.py first.")
        return []
    data = []
    with open(BRAIN_DATA, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data

def format_for_training(examples):
    """Format examples for instruction fine-tuning."""
    formatted = []
    for ex in examples:
        inst = ex.get("instruction", "")
        inp = ex.get("input", "")
        out = ex.get("output", "")

        # Alpaca-style prompt format
        if inp:
            text = f"### Instruction:\n{inst}\n\n### Input:\n{inp}\n\n### Response:\n{out}"
        else:
            text = f"### Instruction:\n{inst}\n\n### Response:\n{out}"

        formatted.append({"text": text})
    return formatted

def train():
    """QLoRA fine-tuning."""
    try:
        import torch
        from transformers import (
            AutoModelForCausalLM, AutoTokenizer, TrainingArguments,
            BitsAndBytesConfig, Trainer, DataCollatorForLanguageModeling,
        )
        from datasets import Dataset
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    except ImportError as e:
        print(f"Missing dependencies: {e}")
        print("Install: pip install transformers datasets peft accelerate bitsandbytes torch")
        return

    use_cpu = "--cpu" in sys.argv

    # Load data
    data = load_dataset()
    if not data:
        return
    formatted = format_for_training(data)
    dataset = Dataset.from_list(formatted)

    print(f"Dataset: {len(dataset)} examples")
    print(f"Base model: {BASE_MODEL}")
    print(f"Device: {'CPU' if use_cpu else 'GPU (auto-detect)'}")

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def tokenize_fn(examples):
        result = tokenizer(
            examples["text"],
            truncation=True,
            padding="max_length",
            max_length=512,
        )
        result["labels"] = result["input_ids"].copy()
        return result

    tokenized = dataset.map(tokenize_fn, batched=True, remove_columns=["text"])

    # Load model with QLoRA
    if use_cpu:
        model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL,
            torch_dtype=torch.float32,
            device_map="cpu",
        )
    else:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
        )
        model = prepare_model_for_kbit_training(model)

    # LoRA config
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Training args
    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=3,
        per_device_train_batch_size=1 if use_cpu else 4,
        gradient_accumulation_steps=8 if use_cpu else 2,
        warmup_steps=20,
        learning_rate=2e-4,
        fp16=not use_cpu,
        logging_steps=10,
        save_strategy="epoch",
        report_to="none",
        gradient_checkpointing=not use_cpu,
    )

    # Data collator
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,
    )

    # Train
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized,
        data_collator=data_collator,
    )

    print("\nStarting training...")
    trainer.train()

    # Save
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    # Save metadata
    meta = {
        "base_model": BASE_MODEL,
        "training_examples": len(dataset),
        "training_date": datetime.now().isoformat(),
        "method": "QLoRA 4-bit" if not use_cpu else "Full fine-tune (CPU)",
        "lora_rank": 16,
        "lora_alpha": 32,
    }
    with open(OUTPUT_DIR / "training_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"\nModel saved to: {OUTPUT_DIR}")
    print("Run with --test to test inference")


def test_inference():
    """Test the fine-tuned model."""
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
    except ImportError:
        print("Missing transformers/torch. Install: pip install transformers torch")
        return

    model_path = OUTPUT_DIR if OUTPUT_DIR.exists() else BASE_MODEL
    print(f"Loading model from: {model_path}")

    tokenizer = AutoTokenizer.from_pretrained(str(model_path))
    model = AutoModelForCausalLM.from_pretrained(
        str(model_path),
        torch_dtype=torch.float32,
        device_map="cpu",
    )

    test_queries = [
        "错误处理的第一步是什么？",
        "如何诊断进化系统停止了？",
        "什么是RAG混合检索？",
        "OODA循环的四个步骤是什么？",
        "代码修改前必须做什么？",
        "如何防止AI系统变得傲慢？",
    ]

    for query in test_queries:
        prompt = f"### Instruction:\n{query}\n\n### Response:\n"
        inputs = tokenizer(prompt, return_tensors="pt")
        outputs = model.generate(
            **inputs,
            max_new_tokens=150,
            temperature=0.7,
            do_sample=True,
            top_p=0.9,
        )
        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        # Extract only the response part
        if "### Response:" in response:
            response = response.split("### Response:")[-1].strip()
        print(f"\nQ: {query}")
        print(f"A: {response[:200]}...")


def merge_lora():
    """Merge LoRA weights into base model for deployment."""
    try:
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
    except ImportError:
        print("Missing dependencies. Install: pip install transformers peft torch")
        return

    print(f"Merging LoRA weights from {OUTPUT_DIR} into {BASE_MODEL}")
    merged_dir = OUTPUT_DIR.parent / "ralph-smollm-merged"

    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.float32,
        device_map="cpu",
    )
    model = PeftModel.from_pretrained(base_model, str(OUTPUT_DIR))
    model = model.merge_and_unload()

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model.save_pretrained(str(merged_dir))
    tokenizer.save_pretrained(str(merged_dir))

    print(f"Merged model saved to: {merged_dir}")
    print("Ready for deployment. Size: ~270MB (can run on CPU)")


def main():
    if "--test" in sys.argv:
        test_inference()
    elif "--merge" in sys.argv:
        merge_lora()
    else:
        train()


if __name__ == "__main__":
    main()
