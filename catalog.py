"""Cursor's published parameter selections, without picker-row duplication."""
from functools import lru_cache
import json
from pathlib import Path

PATH = Path(__file__).with_name("model-selections.json")
EFFORT_KEYS = ("reasoning_effort", "effort", "reasoning")
NATIVE_KEYS = {*EFFORT_KEYS, "thinking", "fast"}
EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max")


@lru_cache(maxsize=1)
def _read(stamp):
    return json.loads(PATH.read_text())


def selections():
    return _read(PATH.stat().st_mtime_ns)


def models():
    return list(dict.fromkeys(v["id"] for v in selections().values()))


def _params(selection):
    return {p["id"]: p["value"] for p in selection["params"]}


def _rows(model):
    selected = selections().get(model)
    if selected is None:
        raise ValueError(f"Unknown Cursor model selection: {model}")
    return selected, [(key, row) for key, row in selections().items() if row["id"] == selected["id"]]


def _values(rows):
    values = {}
    for _, row in rows:
        for key, value in _params(row).items():
            values.setdefault(key, set()).add(value)
    return values


def _canonical(value):
    return "xhigh" if value == "extra-high" else value


def capabilities(model):
    _, rows = _rows(model)
    values = _values(rows)
    effort_key = next((key for key in EFFORT_KEYS if key in values), None)
    levels = {_canonical(v) for v in values.get(effort_key, ())} - {"none"}
    return {
        "fast": "true" in values.get("fast", ()),
        "reasoning": bool(effort_key or "thinking" in values),
        "can_disable_reasoning": "false" in values.get("thinking", ()) or "none" in values.get(effort_key, ()),
        "supported_efforts": [v for v in EFFORTS if v in levels],
        "advanced_options": [{"id": key, "label": {"context": "Context size", "cyber": "Cyber mode"}.get(key, key),
                              "values": sorted(allowed)} for key, allowed in values.items() if key not in NATIVE_KEYS],
        "model_selections": [{"model": key, "params": _params(row)} for key, row in rows],
    }


def resolve(model, *, reasoning=None, fast=None):
    selected, rows = _rows(model)
    params = _params(selected)
    values = _values(rows)
    key = next((name for name in EFFORT_KEYS if name in values), None)
    if reasoning is not None and (key or "thinking" in values):
        requested = _canonical(str(reasoning.get("effort") or "").strip().lower())
        if reasoning.get("enabled") is False or requested == "none":
            if "false" in values.get("thinking", ()):
                params["thinking"] = "false"
            elif key and "none" in values[key]:
                params[key] = "none"
            else:
                raise ValueError(f"Cursor model {selected['id']} cannot disable thinking")
        else:
            if "thinking" in values:
                params["thinking"] = "true"
            if key and requested:
                from agent.reasoning_effort import clamp_effort
                allowed = capabilities(model)["supported_efforts"]
                effort = clamp_effort(requested, allowed)
                if effort not in allowed:
                    raise ValueError(f"Unknown Cursor reasoning effort: {requested}")
                params[key] = next(v for v in values[key] if _canonical(v) == effort)
    if fast is not None:
        if fast and "true" not in values.get("fast", ()):
            raise ValueError(f"Cursor Fast is unavailable for {selected['id']}")
        if "fast" in values:
            if not fast and "false" not in values["fast"]:
                params.pop("fast", None)
            else:
                params["fast"] = "true" if fast else "false"
    # Never synthesize a combination absent from Cursor's published selections.
    if params and not any(all(_params(row).get(k) == v for k, v in params.items()) for _, row in rows):
        raise ValueError(f"Unsupported Cursor parameter combination for {selected['id']}")
    return {"id": selected["id"], "params": [{"id": k, "value": v} for k, v in params.items()]}
