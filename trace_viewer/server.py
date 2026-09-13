"""Local, read-only trace viewer for the Cartwheel support agent.

A thin FastAPI backend that proxies Langfuse's public REST API (so the
Langfuse secret key never reaches the browser) and serves a plain
HTML/CSS/JS frontend that renders one trace at a time, top to bottom,
instead of Langfuse's own multi-panel UI.

Run with:
    uv run uvicorn trace_viewer.server:app --port 8020
Then open http://localhost:8020
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"


def _load_env() -> None:
    path = REPO_ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and value:
            os.environ.setdefault(key, value)


_load_env()

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")
_AUTH = (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)

app = FastAPI(title="Cartwheel trace viewer")


def _fix_text(value: Any) -> Any:
    """Undo a common UTF-8-stored-as-Latin-1 mojibake seen in some
    Langfuse-recorded text (e.g. an emoji rendered as garbled bytes).
    Leaves anything that doesn't round-trip cleanly untouched.
    """
    if isinstance(value, str):
        try:
            return value.encode("cp1252").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            return value
    if isinstance(value, list):
        return [_fix_text(v) for v in value]
    if isinstance(value, dict):
        return {k: _fix_text(v) for k, v in value.items()}
    return value


def _first_text(messages: Any) -> str | None:
    """Pull the first text part out of an OTel GenAI message list."""
    if not isinstance(messages, list):
        return None
    for message in messages:
        for part in message.get("parts", []) if isinstance(message, dict) else []:
            if part.get("type") == "text" and part.get("content"):
                return part["content"]
    return None


def _truncate(text: str | None, limit: int = 140) -> str:
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _langfuse_get(path: str, **params: Any) -> dict[str, Any]:
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        raise HTTPException(
            status_code=500,
            detail="LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set in .env",
        )
    try:
        resp = httpx.get(
            f"{LANGFUSE_HOST}{path}", auth=_AUTH, params=params, timeout=15.0
        )
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach Langfuse at {LANGFUSE_HOST}: {exc}",
        ) from exc
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Not found in Langfuse")
    resp.raise_for_status()
    return resp.json()


def _observation_to_node(obs: dict[str, Any]) -> dict[str, Any]:
    output = obs.get("output")
    has_error = (
        obs.get("level") not in (None, "DEFAULT")
        or bool(obs.get("statusMessage"))
        or (isinstance(output, dict) and output.get("ok") is False)
    )
    return {
        "id": obs["id"],
        "parent_id": obs.get("parentObservationId"),
        "type": obs.get("type"),
        "name": obs.get("name"),
        "start_time": obs.get("startTime"),
        "end_time": obs.get("endTime"),
        "latency": obs.get("latency"),
        "level": obs.get("level"),
        "status_message": obs.get("statusMessage"),
        "input": _fix_text(obs.get("input")),
        "output": _fix_text(output),
        "attributes": (obs.get("metadata") or {}).get("attributes") or {},
        "model": obs.get("model"),
        "usage": obs.get("usage"),
        "cost": obs.get("calculatedTotalCost"),
        "has_error": has_error,
        "children": [],
    }


def _build_tree(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes = {obs["id"]: _observation_to_node(obs) for obs in observations}
    roots = []
    for node in nodes.values():
        parent_id = node["parent_id"]
        if parent_id and parent_id in nodes:
            nodes[parent_id]["children"].append(node)
        else:
            roots.append(node)

    def sort_children(node: dict[str, Any]) -> None:
        node["children"].sort(key=lambda c: c["start_time"] or "")
        for child in node["children"]:
            sort_children(child)

    for root in roots:
        sort_children(root)
    roots.sort(key=lambda r: r["start_time"] or "")
    return roots


def _any_error(nodes: list[dict[str, Any]]) -> bool:
    return any(n["has_error"] or _any_error(n["children"]) for n in nodes)


def _fetch_observations(trace_id: str) -> list[dict[str, Any]]:
    return _langfuse_get(
        "/api/public/observations", traceId=trace_id, limit=100
    ).get("data", [])


def _tool_order(observations: list[dict[str, Any]]) -> list[str]:
    tools = [o for o in observations if o.get("type") == "TOOL"]
    tools.sort(key=lambda o: o.get("startTime") or "")
    return [t.get("name") for t in tools]


@app.get("/api/traces")
def list_traces(limit: int = 50) -> list[dict[str, Any]]:
    payload = _langfuse_get("/api/public/traces", limit=limit)
    traces = []
    for trace in payload.get("data", []):
        attrs = (trace.get("metadata") or {}).get("attributes") or {}
        observations = _fetch_observations(trace["id"])
        tree = _build_tree(observations)
        traces.append(
            {
                "id": trace["id"],
                "name": trace.get("name"),
                "timestamp": trace.get("timestamp"),
                "user_role": attrs.get("cartwheel.user_role"),
                "user_id": attrs.get("cartwheel.user_id"),
                "prompt_version": attrs.get("cartwheel.prompt_version"),
                "latency": trace.get("latency"),
                "total_cost": trace.get("totalCost"),
                "preview_input": _truncate(_fix_text(_first_text(trace.get("input")))),
                "tool_order": _tool_order(observations),
                "has_error": _any_error(tree),
            }
        )
    traces.sort(key=lambda t: t["timestamp"] or "", reverse=True)
    return traces


@app.get("/api/traces/{trace_id}")
def get_trace(trace_id: str) -> dict[str, Any]:
    trace = _langfuse_get(f"/api/public/traces/{trace_id}")
    observations = _fetch_observations(trace_id)
    tree = _build_tree(observations)
    attrs = (trace.get("metadata") or {}).get("attributes") or {}
    return {
        "id": trace["id"],
        "name": trace.get("name"),
        "timestamp": trace.get("timestamp"),
        "latency": trace.get("latency"),
        "total_cost": trace.get("totalCost"),
        "langfuse_url": f"{LANGFUSE_HOST}{trace.get('htmlPath', '')}",
        "attributes": attrs,
        "messages": {
            "input": _fix_text(trace.get("input")),
            "output": _fix_text(trace.get("output")),
        },
        "observation_count": len(observations),
        "has_error": _any_error(tree),
        "tree": tree,
    }


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
