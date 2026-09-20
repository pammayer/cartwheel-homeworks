"""HW5: prepare judge inputs, split labels, and (later) run the judge.

Judged mode: ``internal_policy_id_shown`` (Pass = no internal policy ID in any
reply the customer sees, Fail = one appears).

Run from the repository root:

    .venv/Scripts/python.exe -m analysis.run_judges prepare
    .venv/Scripts/python.exe -m analysis.run_judges split
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from analysis.helpers import _state, selection, split_labels

MODE = "internal_policy_id_shown"
REPO = Path(__file__).resolve().parent.parent
TRACE_EXPORT = REPO / "traces" / "support_traces.json"
INPUTS_PATH = REPO / "analysis" / "state" / "hw5_trace_inputs.json"
JUDGE_MODEL = "anthropic/claude-haiku-4-5-20251001"

_CP1252 = None


def _fix_text(text: str) -> str:
    """Undo UTF-8 text that was decoded as cp1252 (e.g. an em dash shown as three symbols)."""
    try:
        return text.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _labeled_trace_ids(mode: str) -> list[str]:
    path = _state.state_path("hw5_labels", f"{mode}.jsonl")
    return [row["trace_id"] for row in _state.read_jsonl(path) if not row.get("superseded_by")]


def prepare_inputs(mode: str = MODE) -> list[dict]:
    """Save one input record per labeled conversation.

    Only what the judged question needs is kept: the customer's messages and the
    assistant's replies, in order. Tool calls and tool results are left out
    because the failure concerns what the customer sees (and tool results
    contain policy IDs the customer never reads). Human labels, review notes and
    scenario metadata are never included.
    """
    wanted = _labeled_trace_ids(mode)
    by_id = {trace["id"]: trace for trace in selection.load_traces(TRACE_EXPORT)}
    missing = [tid for tid in wanted if tid not in by_id]
    if missing:
        raise ValueError(f"{len(missing)} labeled traces are missing from {TRACE_EXPORT.name}: {missing[:3]}")

    records = []
    for tid in wanted:
        messages = []
        for message in by_id[tid]["trace"]:
            role = message.get("role")
            if role not in ("user", "assistant"):
                continue
            text = _fix_text(str(message.get("text") or "")).strip()
            if text:
                messages.append({"role": role, "text": text})
        records.append({"trace_id": tid, "trace": messages})

    INPUTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    INPUTS_PATH.write_text(json.dumps(records, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    if len(records) != len(wanted):
        raise ValueError("input records do not match the eligible labels")
    return records


def split_data(mode: str = MODE) -> dict[str, list[str]]:
    """20% training, 40% development, 40% test, stratified by label. Run once."""
    records = json.loads(INPUTS_PATH.read_text(encoding="utf-8"))
    return split_labels(
        mode,
        fractions=(0.20, 0.40, 0.40),
        seed=7,
        min_per_class=10,
        eligible_trace_ids=[record["trace_id"] for record in records],
    )


def run_development(mode: str = MODE, prompt_path: str | Path = "analysis/prompts/internal_policy_id_shown-v0.txt") -> dict:
    """Register a prompt version, run it on the development split, save metrics.

    Resumable: rerunning ``run_judge``/``judge_alignment`` with the same judge id
    only pays for missing predictions. Never touches the test split.
    """
    from observability.instrument import load_env

    from analysis.helpers import judge_alignment, register_judge, run_judge

    load_env()
    os.environ.setdefault("CARTWHEEL_JUDGE_TRACE_SOURCE", str(INPUTS_PATH))
    record = register_judge(
        mode=mode,
        prompt_text=Path(prompt_path).read_text(encoding="utf-8"),
        judge_model=JUDGE_MODEL,
    )
    judge_id = record["judge_id"]
    print("registered", judge_id)
    run_judge(judge_id, split="dev", batch_size=10)
    development = judge_alignment(judge_id, split="dev")
    out = REPO / "analysis" / "report" / f"dev-{judge_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(development, indent=2), encoding="utf-8")
    return {"judge_id": judge_id, **development}


def run_test(judge_id: str) -> dict:
    """Freeze the chosen prompt (once), evaluate the held-out test split, save metrics."""
    from observability.instrument import load_env

    from analysis.helpers import freeze_judge, judge_alignment, run_judge

    load_env()
    os.environ.setdefault("CARTWHEEL_JUDGE_TRACE_SOURCE", str(INPUTS_PATH))
    freeze_judge(judge_id)  # one-way: unlocks the test split
    run_judge(judge_id, split="test", batch_size=10)
    test = judge_alignment(judge_id, split="test")
    out = REPO / "analysis" / "report" / f"test-{judge_id}.json"
    out.write_text(json.dumps(test, indent=2), encoding="utf-8")
    return test


def code_baseline(mode: str = MODE, split: str = "test") -> dict:
    """The regex check on the same split, scored the same way (Pass positive)."""
    import re

    splits = json.loads(_state.state_path("splits.json").read_text(encoding="utf-8"))[mode]
    inputs = {r["trace_id"]: r for r in json.loads(INPUTS_PATH.read_text(encoding="utf-8"))}
    labels = {
        row["trace_id"]: row["label"]
        for row in _state.read_jsonl(_state.state_path("hw5_labels", f"{mode}.jsonl"))
    }
    tp = fn = tn = fp = 0
    for tid in splits[split]:
        replies = " ".join(m["text"] for m in inputs[tid]["trace"] if m["role"] == "assistant")
        predicted_pass = 0 if re.search(r"\bcw-[a-z]+(?:-[a-z]+)*\b", replies) else 1
        human_pass = labels[tid]
        if human_pass and predicted_pass:
            tp += 1
        elif human_pass:
            fn += 1
        elif not predicted_pass:
            tn += 1
        else:
            fp += 1
    return {"method": "regex cw-<word> in assistant replies", "split": split, "tp": tp, "fn": fn, "tn": tn, "fp": fp,
            "tpr": tp / (tp + fn) if tp + fn else None, "tnr": tn / (tn + fp) if tn + fp else None}


def _class_counts(mode: str, ids: list[str]) -> tuple[int, int]:
    labels = {
        row["trace_id"]: row["label"]
        for row in _state.read_jsonl(_state.state_path("hw5_labels", f"{mode}.jsonl"))
    }
    passes = sum(1 for tid in ids if labels[tid] == 1)
    return passes, len(ids) - passes


if __name__ == "__main__":
    os.environ.setdefault("CARTWHEEL_JUDGE_TRACE_SOURCE", str(INPUTS_PATH))
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "prepare":
        records = prepare_inputs()
        print(f"saved {len(records)} input records to {INPUTS_PATH}")
    elif command == "split":
        splits = split_data()
        for name in ("train", "dev", "test"):
            passes, fails = _class_counts(MODE, splits[name])
            print(f"{name:5} {len(splits[name]):3} traces: {passes} Pass, {fails} Fail")
    elif command == "dev":
        prompt = sys.argv[2] if len(sys.argv) > 2 else "analysis/prompts/internal_policy_id_shown-v0.txt"
        result = run_development(MODE, prompt)
        print(json.dumps({k: v for k, v in result.items() if k != "disagreements"}, indent=2))
        print("disagreements:", len(result["disagreements"]))
    elif command == "test":
        result = run_test(sys.argv[2] if len(sys.argv) > 2 else "internal_policy_id_shown-v0")
        print(json.dumps({k: v for k, v in result.items() if k != "disagreements"}, indent=2))
        print("disagreements:", len(result["disagreements"]))
    elif command == "baseline":
        print(json.dumps(code_baseline(), indent=2))
    else:
        print(__doc__)
