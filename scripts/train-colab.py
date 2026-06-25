#!/usr/bin/env python3
r"""train-colab.py -- Google Colab fine-tuning script for SmolLM2-135M.
Copy-paste this entire script into a Colab cell and run.
Colab has Linux + free T4 GPU + no Windows DLL issues.

Requirements (auto-installed in Colab):
!pip install transformers datasets peft accelerate bitsandbytes torch huggingface_hub

After training, downloads GGUF for local inference.
"""

# ═══════════════════════════════════════════
# PASTE INTO GOOGLE COLAB: https://colab.research.google.com
# ═══════════════════════════════════════════

COLAB_SCRIPT = r'''
# Step 1: Install dependencies
!pip install -q transformers datasets peft accelerate bitsandbytes huggingface_hub

# Step 2: Upload brain dataset
from google.colab import files
print("Upload brain_dataset.jsonl from your desktop 模型 folder:")
uploaded = files.upload()

import json
brain_data = []
for fn in uploaded.keys():
    if fn.endswith('.jsonl'):
        with open(fn, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    brain_data.append(json.loads(line))
print(f"Loaded {len(brain_data)} training examples")

# Step 3: Format training data
def format_data(examples):
    formatted = []
    for ex in examples:
        inst = ex.get("instruction", "")
        inp = ex.get("input", "")
        out = ex.get("output", "")
        if inp:
            text = f"### Instruction:\n{inst}\n\n### Input:\n{inp}\n\n### Response:\n{out}"
        else:
            text = f"### Instruction:\n{inst}\n\n### Response:\n{out}"
        formatted.append({"text": text})
    return formatted

from datasets import Dataset
dataset = Dataset.from_list(format_data(brain_data))
print(f"Dataset ready: {len(dataset)} examples")

# Step 4: Load model with QLoRA
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

MODEL_ID = "HuggingFaceTB/SmolLM2-135M"

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
tokenizer.pad_token = tokenizer.eos_token

def tokenize(examples):
    result = tokenizer(examples["text"], truncation=True, padding="max_length", max_length=512)
    result["labels"] = result["input_ids"].copy()
    return result

tokenized = dataset.map(tokenize, batched=True, remove_columns=["text"])

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True, bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True,
)

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID, quantization_config=bnb_config, device_map="auto"
)
model = prepare_model_for_kbit_training(model)

lora_config = LoraConfig(
    r=16, lora_alpha=32, lora_dropout=0.05,
    target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],
    bias="none", task_type="CAUSAL_LM",
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# Step 5: Train
from transformers import Trainer, DataCollatorForLanguageModeling

args = TrainingArguments(
    output_dir="./ralph-smollm-v1", num_train_epochs=3,
    per_device_train_batch_size=4, gradient_accumulation_steps=2,
    warmup_steps=20, learning_rate=2e-4, fp16=True,
    logging_steps=10, save_strategy="epoch", report_to="none",
)

trainer = Trainer(
    model=model, args=args, train_dataset=tokenized,
    data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
)

print("Starting training...")
trainer.train()

# Step 6: Save and download
model.save_pretrained("./ralph-smollm-v1")
tokenizer.save_pretrained("./ralph-smollm-v1")

!zip -r ralph-smollm-v1.zip ./ralph-smollm-v1
from google.colab import files
files.download("ralph-smollm-v1.zip")
print("Done! Download the zip and extract to your desktop 模型 folder.")
'''

def main():
    print("=" * 60)
    print("  Colab Training Script")
    print("=" * 60)
    print()
    print("To train the model:")
    print("1. Open https://colab.research.google.com")
    print("2. Create a new notebook")
    print("3. Set Runtime → Change runtime type → T4 GPU")
    print("4. Paste the following script and run")
    print()
    print("Also upload this file first:")
    print(f"  C:\\Users\\z1439\\OneDrive\\Desktop\\模型\\brain_dataset.jsonl")
    print()
    print("=" * 60)
    print("Training takes ~15 min on free T4 GPU")
    print("After training, download and extract to:")
    print(f"  C:\\Users\\z1439\\OneDrive\\Desktop\\模型\\ralph-smollm-v1")
    print()
    print("Then run local inference: python scripts/ralph-infer.py")
    print("=" * 60)

    # Also print the full Colab script for copy-paste
    print()
    print("--- COPY BELOW THIS LINE ---")
    print(COLAB_SCRIPT)
    print("--- COPY ABOVE THIS LINE ---")

if __name__ == "__main__":
    main()
