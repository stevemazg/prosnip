"""Per-tool option defaults. Version 1 of the settings schema.

A missing file, a damaged blob, or a single bad field falls back to the
built-in value for that field. Unknown tools are ignored.
"""

import logging

log = logging.getLogger("prosnip")

SCHEMA = 1

NAMES = {
    "rect": "Rectangle",
    "ellipse": "Ellipse",
    "arrow": "Arrow",
    "pen": "Pen",
    "highlight": "Highlighter",
    "text": "Text",
    "callout": "Callout",
    "number": "Numbered step",
    "polygon": "Polygon",
    "blur": "Blur",
    "spotlight": "Spotlight",
    "eraser": "Eraser",
    "stamp": "Stamp",
}

_COMMON = {
    "colour": "#e63946",
    "fill": "#e63946",
    "text_colour": "#e63946",
    "fill_opacity": 0,
    "border_opacity": 100,
    "width": 2,
    "font": 14,
    "opacity": 100,
    "shadow": False,
    "shadow_offset": 4,
    "shadow_blur": 8,
    "radius": 0,
    "outline": True,
    "curve": False,
    "start_cap": "none",
    "end_cap": "arrow",
    "darkness": 140,
    "block": 14,
}


def builtin(tool: str) -> dict:
    values = dict(_COMMON)
    if tool == "highlight":
        values["colour"] = "#f4a261"
        values["width"] = 14
        values["opacity"] = 40
    elif tool == "text":
        values["font"] = 16
    elif tool == "number":
        values["font"] = 14
    elif tool == "eraser":
        values["width"] = 16
    elif tool == "blur":
        values["width"] = 14
        values["block"] = 14
    elif tool == "spotlight":
        values["darkness"] = 140
    return values


def _bool(value, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    return fallback


def _int(value, fallback: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


def _colour(value, fallback: str) -> str:
    text = str(value or "").strip()
    if len(text) == 7 and text.startswith("#"):
        try:
            int(text[1:], 16)
        except ValueError:
            return fallback
        return text.lower()
    if len(text) == 9 and text.startswith("#"):
        try:
            int(text[1:], 16)
        except ValueError:
            return fallback
        return text.lower()
    return fallback


def _cap(value, fallback: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"none", "arrow", "dot", "square"}:
        return text
    return fallback


def sanitize(tool: str, raw) -> dict:
    """Return a complete value dict. Bad fields keep the built-in value."""
    base = builtin(tool)
    if not isinstance(raw, dict):
        if raw is not None:
            log.warning("Tool default for %s was damaged; the built-in values are used", tool)
        return base
    cleaned = dict(base)
    cleaned["colour"] = _colour(raw.get("colour"), base["colour"])
    cleaned["fill"] = _colour(raw.get("fill"), base["fill"])
    cleaned["text_colour"] = _colour(raw.get("text_colour"), base["text_colour"])
    cleaned["fill_opacity"] = _int(raw.get("fill_opacity"), base["fill_opacity"], 0, 100)
    cleaned["border_opacity"] = _int(raw.get("border_opacity"), base["border_opacity"], 0, 100)
    cleaned["width"] = _int(raw.get("width"), base["width"], 1, 48)
    cleaned["font"] = _int(raw.get("font"), base["font"], 8, 72)
    cleaned["opacity"] = _int(raw.get("opacity"), base["opacity"], 10, 100)
    cleaned["shadow"] = _bool(raw.get("shadow"), base["shadow"])
    cleaned["shadow_offset"] = _int(raw.get("shadow_offset"), base["shadow_offset"], 0, 24)
    cleaned["shadow_blur"] = _int(raw.get("shadow_blur"), base["shadow_blur"], 0, 32)
    cleaned["radius"] = _int(raw.get("radius"), base["radius"], 0, 48)
    cleaned["outline"] = _bool(raw.get("outline"), base["outline"])
    cleaned["curve"] = _bool(raw.get("curve"), base["curve"])
    cleaned["start_cap"] = _cap(raw.get("start_cap"), base["start_cap"])
    cleaned["end_cap"] = _cap(raw.get("end_cap"), base["end_cap"])
    cleaned["darkness"] = _int(raw.get("darkness"), base["darkness"], 20, 220)
    cleaned["block"] = _int(raw.get("block"), base["block"], 4, 48)
    return cleaned


def read_store(blob) -> dict:
    """Parse the saved blob. A missing blob is an empty store, not a warning."""
    if blob is None:
        return {}
    if not isinstance(blob, dict):
        log.warning("Tool defaults were damaged and were ignored")
        return {}
    try:
        schema = int(blob.get("schema", SCHEMA))
    except (TypeError, ValueError):
        log.warning("Tool defaults were damaged and were ignored")
        return {}
    if schema != SCHEMA:
        log.warning("Tool defaults use schema %s and were ignored", schema)
        return {}
    tools = blob.get("tools", {})
    if not isinstance(tools, dict):
        log.warning("Tool defaults were damaged and were ignored")
        return {}
    parsed = {}
    for name, raw in tools.items():
        if name not in NAMES:
            continue
        parsed[name] = sanitize(name, raw)
    return parsed


def pack_store(tools: dict) -> dict:
    packed = {}
    for name, values in tools.items():
        if name not in NAMES:
            continue
        packed[name] = sanitize(name, values)
    return {"schema": SCHEMA, "tools": packed}
