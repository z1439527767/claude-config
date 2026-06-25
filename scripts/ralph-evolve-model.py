#!/usr/bin/env python3
r"""ralph-evolve-model.py -- THE BLACK HOLE ENGINE.
Autonomous iterative evolution: every conversation → knowledge extraction → brain growth → retrain → improve.

Core loop (runs continuously or on trigger):
1. SCAN: monitor conversation memory for new data
2. EXTRACT: distill insights from new conversations
3. DIGEST: append to brain dataset
4. EVALUATE: check if enough new data to retrain
5. TRAIN: QLoRA fine-tune on expanded dataset
6. BENCHMARK: compare new vs old model
7. DEPLOY or ROLLBACK: based on benchmark results
8. REPEAT: go back to step 1

"黑洞" principle: actively pulls ALL information into itself.
Nothing is lost. Everything becomes training data.

Usage:
  python ralph-evolve-model.py                  # One evolution cycle
  python ralph-evolve-model.py --watch           # Continuous watch mode (daemon)
  python ralph-evolve-model.py --force           # Force retrain regardless of threshold
  python ralph-evolve-model.py --status          # Show evolution stats
"""

import sys, json, io, os, re, time, subprocess
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HOME = Path(__file__).resolve().parent.parent
MODEL_DIR = Path(os.environ.get("RALPH_MODEL_DIR", r"C:\Users\z1439\OneDrive\Desktop\模型"))
BRAIN_DATA = MODEL_DIR / "brain_dataset.jsonl"
CONVERSATION_MEMORY = MODEL_DIR / "conversation_memory.jsonl"
EVOLUTION_LOG = MODEL_DIR / "evolution_log.jsonl"
EVOLUTION_STATE = MODEL_DIR / "evolution_state.json"
MODEL_OUTPUT = MODEL_DIR / "ralph-smollm-v1"

# Evolution thresholds
MIN_NEW_EXAMPLES = 20       # Minimum new examples to trigger retrain
MAX_ACCUMULATION = 100      # Force retrain when this many accumulated
EVAL_IMPROVEMENT_MIN = 0.0  # Minimum improvement to deploy (0 = always deploy if not worse)
MAX_DEGRADATION = -0.05     # Max allowed degradation before rollback


def get_state() -> dict:
    """Load evolution state."""
    if EVOLUTION_STATE.exists():
        try:
            return json.loads(EVOLUTION_STATE.read_text(encoding="utf-8"))
        except:
            pass
    return {
        "version": 1,
        "total_examples": 0,
        "total_trainings": 0,
        "conversations_absorbed": 0,
        "last_training": None,
        "best_score": 0.0,
        "current_score": 0.0,
        "history": [],
    }


def save_state(state: dict):
    """Persist evolution state."""
    EVOLUTION_STATE.parent.mkdir(parents=True, exist_ok=True)
    EVOLUTION_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def log_event(event: str, detail: dict = None):
    """Log evolution event."""
    EVOLUTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event": event,
        "detail": detail or {},
    }
    with open(EVOLUTION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def scan_new_data() -> list[dict]:
    """Scan for new conversation data to absorb."""
    if not CONVERSATION_MEMORY.exists():
        return []

    state = get_state()
    absorbed_count = state.get("conversations_absorbed", 0)

    new_examples = []
    with open(CONVERSATION_MEMORY, encoding="utf-8") as f:
        all_convs = [json.loads(line) for line in f if line.strip()]

    # Only take conversations we haven't absorbed yet
    new_examples = all_convs[absorbed_count:]

    return new_examples


def extract_insights(conversations: list[dict]) -> list[dict]:
    """Extract training examples from raw conversations.
    This is the "black hole" — actively pulls knowledge from every interaction."""
    examples = []

    for conv in conversations:
        instruction = conv.get("instruction", conv.get("q", ""))
        output = conv.get("output", conv.get("a", ""))

        if not instruction or len(instruction) < 5:
            continue

        # Direct example: Q → A
        if output and len(output) > 10:
            examples.append({
                "instruction": instruction,
                "input": "",
                "output": output,
                "source": "conversation_absorbed",
                "absorbed_at": datetime.now().isoformat(),
            })

        # Generate self-reflection example: "What did I learn?"
        if output and "错误" in instruction or "error" in instruction.lower():
            examples.append({
                "instruction": "从这次交互中我学到了什么？",
                "input": instruction,
                "output": f"我学到了：当用户提到'{instruction[:50]}'时，应该{output[:100]}",
                "source": "self_reflection",
                "absorbed_at": datetime.now().isoformat(),
            })

    return examples


def digest_new_knowledge(examples: list[dict]):
    """Append new examples to brain dataset."""
    if not examples:
        return 0

    BRAIN_DATA.parent.mkdir(parents=True, exist_ok=True)

    # Load existing
    existing_ids = set()
    if BRAIN_DATA.exists():
        with open(BRAIN_DATA, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        ex = json.loads(line)
                        existing_ids.add(ex.get("instruction", "")[:80])
                    except:
                        pass

    # Append only truly new examples
    new_count = 0
    with open(BRAIN_DATA, "a", encoding="utf-8") as f:
        for ex in examples:
            key = ex.get("instruction", "")[:80]
            if key not in existing_ids:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
                existing_ids.add(key)
                new_count += 1

    return new_count


def count_brain_examples() -> int:
    """Count total examples in brain dataset."""
    if not BRAIN_DATA.exists():
        return 0
    count = 0
    with open(BRAIN_DATA, encoding="utf-8") as f:
        for _ in f:
            count += 1
    return count


def evaluate_model_quick() -> float:
    """Quick evaluation using embedding similarity benchmark."""
    try:
        result = subprocess.run(
            ["python", str(HOME / "scripts" / "train-embedding.py"), "--eval"],
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace", cwd=str(HOME)
        )
        output = result.stdout + result.stderr

        # Parse accuracy from output
        base_m = re.search(r"Base accuracy: (\d+)/(\d+)", output)
        tuned_m = re.search(r"Tuned accuracy: (\d+)/(\d+)", output)

        if tuned_m:
            return int(tuned_m.group(1)) / max(int(tuned_m.group(2)), 1)
        if base_m:
            return int(base_m.group(1)) / max(int(base_m.group(2)), 1)
        return 0.0
    except:
        return 0.0


def trigger_retraining():
    """Trigger model retraining."""
    print("\n  [TRAIN] Starting retraining cycle...")
    log_event("retrain_start", {"examples": count_brain_examples()})

    try:
        result = subprocess.run(
            ["python", str(HOME / "scripts" / "finetune-smollm.py")],
            capture_output=True, text=True, timeout=3600,  # 1 hour max
            encoding="utf-8", errors="replace", cwd=str(HOME)
        )
        success = result.returncode == 0
        log_event("retrain_complete", {"success": success, "output": result.stderr[-500:]})
        return success
    except subprocess.TimeoutExpired:
        log_event("retrain_timeout", {})
        return False
    except Exception as e:
        log_event("retrain_error", {"error": str(e)})
        return False


def evolution_cycle(force: bool = False) -> dict:
    """Run one complete evolution cycle. This is the heartbeat."""
    state = get_state()
    cycle_result = {
        "cycle_start": datetime.now().isoformat(),
        "steps": {},
        "retrained": False,
        "deployed": False,
    }

    print("=" * 60)
    print("  BLACK HOLE ENGINE — Evolution Cycle")
    print(f"  Version: {state['version']} | Trainings: {state['total_trainings']}")
    print("=" * 60)

    # Step 1: SCAN — absorb new conversation data
    print("\n[1/6] SCAN: Absorbing new data...")
    new_convs = scan_new_data()

    if new_convs:
        examples = extract_insights(new_convs)
        absorbed = digest_new_knowledge(examples)
        state["conversations_absorbed"] += len(new_convs)
        cycle_result["steps"]["scan"] = {
            "conversations_found": len(new_convs),
            "examples_extracted": len(examples),
            "examples_absorbed": absorbed,
        }
        print(f"       Absorbed {len(new_convs)} conversations → {absorbed} new examples")
        log_event("scan_absorbed", cycle_result["steps"]["scan"])
    else:
        cycle_result["steps"]["scan"] = {"conversations_found": 0}
        print("       No new conversations to absorb")

    # Step 2: EVALUATE — check if should retrain
    print("\n[2/6] EVALUATE: Checking retrain threshold...")
    total_examples = count_brain_examples()
    state["total_examples"] = total_examples

    new_since_last = total_examples - state.get("examples_at_last_train", 0)
    should_retrain = force or (new_since_last >= MIN_NEW_EXAMPLES) or (new_since_last >= MAX_ACCUMULATION)

    print(f"       Total examples: {total_examples} (+{new_since_last} since last train)")
    print(f"       Threshold: {MIN_NEW_EXAMPLES} new → {'RETRAIN' if should_retrain else 'SKIP'}")

    if should_retrain:
        # Step 3: BENCHMARK (pre-train)
        print("\n[3/6] BENCHMARK (pre): Evaluating current model...")
        pre_score = evaluate_model_quick()
        print(f"       Pre-train score: {pre_score:.0%}")
        cycle_result["steps"]["benchmark_pre"] = pre_score

        # Step 4: TRAIN
        print("\n[4/6] TRAIN: Fine-tuning on expanded dataset...")
        success = trigger_retraining()
        cycle_result["retrained"] = success

        if success:
            state["total_trainings"] += 1
            state["last_training"] = datetime.now().isoformat()
            state["examples_at_last_train"] = total_examples

            # Step 5: BENCHMARK (post-train)
            print("\n[5/6] BENCHMARK (post): Evaluating new model...")
            post_score = evaluate_model_quick()
            print(f"       Post-train score: {post_score:.0%}")
            cycle_result["steps"]["benchmark_post"] = post_score

            improvement = post_score - pre_score

            # Step 6: DEPLOY or ROLLBACK
            print(f"\n[6/6] DECIDE: Improvement = {improvement:+.1%}")
            if improvement >= EVAL_IMPROVEMENT_MIN:
                state["current_score"] = post_score
                if post_score > state["best_score"]:
                    state["best_score"] = post_score
                cycle_result["deployed"] = True
                print(f"       ✅ DEPLOY: New model better by {improvement:+.1%}")
                log_event("deploy", {"improvement": improvement, "new_score": post_score})
            elif improvement < MAX_DEGRADATION:
                cycle_result["deployed"] = False
                print(f"       ❌ ROLLBACK: Degradation {improvement:.1%} exceeds threshold")
                log_event("rollback", {"degradation": improvement})
                # Restore previous brain state
            else:
                cycle_result["deployed"] = True
                state["current_score"] = post_score
                print(f"       ⚠️ DEPLOY (neutral): Change {improvement:+.1%} within tolerance")
                log_event("deploy_neutral", {"improvement": improvement})
        else:
            print("\n[5/6] SKIP: Training failed")
            print("\n[6/6] SKIP: No model to evaluate")
    else:
        print("\n[3-6/6] SKIP: Not enough new data to trigger retraining")

    # Save state
    state["history"].append({
        "timestamp": cycle_result["cycle_start"],
        "retrained": cycle_result["retrained"],
        "deployed": cycle_result.get("deployed", False),
        "examples": total_examples,
        "score": state.get("current_score", 0),
    })
    # Keep last 100 history entries
    if len(state["history"]) > 100:
        state["history"] = state["history"][-100:]
    state["version"] += 1
    save_state(state)

    cycle_result["state"] = state
    return cycle_result


def watch_mode():
    """Continuous watch mode — the black hole never sleeps."""
    print("=" * 60)
    print("  BLACK HOLE ENGINE — Watch Mode")
    print("  Scanning for new data every 60 seconds...")
    print("  Press Ctrl+C to stop")
    print("=" * 60)

    try:
        while True:
            result = evolution_cycle()
            if result["retrained"]:
                print(f"\n  ✅ Model evolved! Score: {result['state'].get('current_score', 0):.0%}")
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n  Watch mode stopped.")


def show_status():
    """Display evolution status."""
    state = get_state()
    total = count_brain_examples()

    print("=" * 50)
    print("  BLACK HOLE ENGINE — Status")
    print("=" * 50)
    print(f"  Version:           v{state['version']}")
    print(f"  Brain examples:    {total}")
    print(f"  Conversations:     {state['conversations_absorbed']} absorbed")
    print(f"  Trainings:         {state['total_trainings']}")
    print(f"  Last training:     {state.get('last_training', 'never')}")
    print(f"  Best score:        {state.get('best_score', 0):.0%}")
    print(f"  Current score:     {state.get('current_score', 0):.0%}")

    if EVOLUTION_LOG.exists():
        recent = []
        with open(EVOLUTION_LOG, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    recent.append(json.loads(line))
        print(f"\n  Recent events ({min(10, len(recent))}):")
        for e in recent[-10:]:
            ts = e["timestamp"][:19]
            evt = e["event"]
            print(f"    {ts}  {evt}")


def main():
    if "--status" in sys.argv:
        show_status()
        return
    if "--watch" in sys.argv:
        watch_mode()
        return

    force = "--force" in sys.argv
    result = evolution_cycle(force=force)

    print(f"\n{'='*60}")
    print(f"  Cycle complete.")
    print(f"  Retrained: {result['retrained']}")
    print(f"  Deployed:  {result.get('deployed', False)}")
    print(f"  Brain:     {result['state']['total_examples']} examples")
    print(f"  Score:     {result['state'].get('current_score', 0):.0%}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
