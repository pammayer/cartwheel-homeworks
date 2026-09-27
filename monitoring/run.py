"""Sample, judge, correct, and score one monitoring period.

Two ways to pick a window:

- ``--period before|after`` reads a fixed window from ``monitoring/config.json``
  and groups traces by ``meta.scenario_id`` — the 50 monitoring scenarios,
  each one conversation regardless of how many turns it took.
- ``--last-hours N`` (the scheduled job's form) takes a rolling window ending
  now and groups by ``meta.session_id`` instead, since live traffic has no
  scenario ID.

Both paths converge on ``run_period``: fetch, validate, build conversation
records, sample, judge, correct, score, and append one line to
``monitoring/history.jsonl``. ``--dry-run`` stops right before the judge call
so the trace/judge counts can be checked (and the cost approved) first.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from analysis.helpers import langfuse_io
from analysis.helpers.normalization import _flatten
from monitoring.correct import corrected_mode_prevalence
from monitoring.run_judges import judge_sample, judge_test_data
from monitoring.sample import DEFAULT_RISK_GROUPS, select_traces
from monitoring.write_scores import build_score_records, post_scores

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.json"
HISTORY_PATH = ROOT / "history.jsonl"
SCENARIOS_PATH = Path("scenarios/monitoring_scenarios.jsonl")


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _known_scenario_ids() -> set[str]:
    ids: set[str] = set()
    with SCENARIOS_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            ids.add(json.loads(line)["id"])
    return ids


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _fetch_window(from_ts: datetime, to_ts: datetime) -> list[dict[str, Any]]:
    traces = langfuse_io.fetch_traces(limit=5000)
    return [t for t in traces if from_ts <= _parse_ts(t["timestamp"]) <= to_ts]


def _group_by(traces: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trace in traces:
        group_id = trace.get("meta", {}).get(key)
        if group_id:
            groups[group_id].append(trace)
    for group_id in groups:
        groups[group_id].sort(key=lambda t: t["timestamp"])
    return groups


def _build_conversation(group_id: str, group: list[dict[str, Any]]) -> dict[str, Any]:
    """One conversation record for a group of same-scenario/session traces.

    Turns merge in order into one normalized text (Homework 5's format: no
    labels, no failure annotations, no scenario metadata). Tool names and the
    user-turn count come straight from the trace evidence, not the reply, for
    the risk-group predicates in ``DEFAULT_RISK_GROUPS``. The record's id is
    the FINAL trace's id, so the score lands on the trace Langfuse shows last
    for that conversation.
    """
    messages: list[dict[str, Any]] = []
    for trace in group:
        messages.extend(trace.get("trace") or [])
    tools = sorted(
        {
            str(m.get("name"))
            for m in messages
            if m.get("role") == "tool_call" and m.get("name")
        }
    )
    turn_count = sum(1 for m in messages if m.get("role") == "user")
    models: list[str] = []
    for trace in group:
        for model in trace.get("models") or []:
            if model not in models:
                models.append(model)
    return {
        "id": group[-1]["id"],
        "group_id": group_id,
        "text": _flatten(messages),
        "tools": tools,
        "turn_count": turn_count,
        "models": models,
        "timestamp": group[0]["timestamp"],
    }


def build_conversations(
    traces: list[dict[str, Any]],
    group_key: str,
    expected_ids: set[str] | None,
    expected_model: str,
) -> list[dict[str, Any]]:
    # A fixed period's window is shared Langfuse real estate — other runs
    # (e.g. the full ~250-scenario HW3 run this 50-scenario subset is drawn
    # from) can and do land traces in the same window. Filter down to the
    # known set first; only a truly MISSING scenario id is an error.
    if expected_ids is not None:
        traces = [t for t in traces if t.get("meta", {}).get(group_key) in expected_ids]
    groups = _group_by(traces, group_key)
    if expected_ids is not None:
        missing = expected_ids - set(groups)
        if missing:
            raise ValueError(f"missing scenario ids: {sorted(missing)}")
    conversations = [_build_conversation(gid, g) for gid, g in groups.items()]
    bad_model = [c["id"] for c in conversations if not any(expected_model in m for m in c["models"])]
    if bad_model:
        raise ValueError(f"conversations not on {expected_model}: {bad_model}")
    return conversations


def run_period(
    config: dict[str, Any],
    label: str,
    from_ts: datetime,
    to_ts: datetime,
    *,
    group_key: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    traces = _fetch_window(from_ts, to_ts)
    expected_ids = _known_scenario_ids() if group_key == "scenario_id" else None
    conversations = build_conversations(traces, group_key, expected_ids, config["model"])

    print(f"[{label}] {len(traces)} langfuse traces -> {len(conversations)} conversations")

    if not conversations:
        row = {
            "label": label, "judge_id": config["judge_id"], "model": config["model"],
            "n_traces": len(traces), "n_conversations": 0, "n_random": 0, "n_risk": 0,
            "note": "no eligible conversations", "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        with HISTORY_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        print(f"[{label}] no eligible conversations; recorded a zero count")
        return row

    risk_predicates = {name: DEFAULT_RISK_GROUPS[name] for name in config["risk_groups"]}
    plan = select_traces(conversations, config["random_rate"], risk_predicates, seed=7)

    n_random = len(plan["random"])
    n_risk = sum(len(v) for v in plan["risk_groups"].values())
    n_judge = len(plan["to_judge"])
    print(f"[{label}] random sample: {n_random} | risk selections: {n_risk} | judge calls (union): {n_judge}")

    if dry_run:
        return {
            "label": label, "n_traces": len(traces), "n_conversations": len(conversations),
            "n_random": n_random, "n_risk": n_risk, "n_judge": n_judge,
        }

    verdicts = judge_sample(config["judge_id"], plan["to_judge"]) if plan["to_judge"] else {}
    random_verdicts = {t["id"]: verdicts[t["id"]] for t in plan["random"]}
    risk_ids = {t["id"] for group in plan["risk_groups"].values() for t in group}
    risk_verdicts = {tid: verdicts[tid] for tid in risk_ids}

    sample_preds = list(random_verdicts.values())
    test_labels, test_preds = judge_test_data(config["judge_id"])
    estimate = corrected_mode_prevalence(sample_preds, test_labels, test_preds, seed=7)

    records = build_score_records(config["judge_mode"], random_verdicts, risk_verdicts, estimate, label)
    n_written = post_scores(records)
    print(f"[{label}] wrote {n_written} scores to langfuse")

    history_row = {
        "label": label, "judge_id": config["judge_id"], "model": config["model"],
        "n_traces": len(traces), "n_conversations": len(conversations),
        "n_random": n_random, "n_risk": n_risk,
        "raw": estimate["raw"], "corrected": estimate["corrected"],
        "ci_low": estimate["ci_low"], "ci_high": estimate["ci_high"],
        "failure_sensitivity": estimate["failure_sensitivity"],
        "pass_specificity": estimate["pass_specificity"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    with HISTORY_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(history_row) + "\n")
    return history_row


def build_chart() -> None:
    from monitoring.chart import prevalence_chart

    config = load_config()
    rows_by_label: dict[str, dict[str, Any]] = {}
    with HISTORY_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if "corrected" in row:
                rows_by_label[row["label"]] = row  # last successful run per label wins

    order = [p["label"] for p in config["periods"]]
    points = [
        {
            "label": label,
            "corrected": rows_by_label[label]["corrected"],
            "ci_low": rows_by_label[label]["ci_low"],
            "ci_high": rows_by_label[label]["ci_high"],
        }
        for label in order
        if label in rows_by_label
    ]
    svg = prevalence_chart(points, config["threshold"], config["judge_mode"])
    (ROOT / "prevalence.svg").write_text(svg, encoding="utf-8")
    print(f"wrote monitoring/prevalence.svg with {len(points)} point(s)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--period", choices=["before", "after"])
    group.add_argument("--last-hours", type=float)
    group.add_argument("--chart", action="store_true", help="build monitoring/prevalence.svg from history.jsonl")
    parser.add_argument("--dry-run", action="store_true", help="stop before the judge call")
    args = parser.parse_args()

    if args.chart:
        build_chart()
        return

    config = load_config()

    if args.period:
        period = next(p for p in config["periods"] if p["label"] == args.period)
        run_period(
            config, args.period, _parse_ts(period["from"]), _parse_ts(period["to"]),
            group_key="scenario_id", dry_run=args.dry_run,
        )
    elif args.last_hours is not None:
        to_ts = datetime.now(timezone.utc)
        from_ts = to_ts - timedelta(hours=args.last_hours)
        run_period(
            config, f"last-{args.last_hours:g}h", from_ts, to_ts,
            group_key="session_id", dry_run=args.dry_run,
        )
    else:
        parser.error("pass --period, --last-hours, or --chart")


if __name__ == "__main__":
    main()
