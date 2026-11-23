"""Save and restore annotations beside a capture as a .psnip JSON file."""

import json
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor

from items import (
    ArrowItem,
    BlurItem,
    CalloutItem,
    EllipseItem,
    NumberItem,
    PolygonItem,
    RectItem,
    SpotlightItem,
    StampItem,
    StrokeItem,
    TextItem,
)


def psnip_path(image_path: str) -> Path:
    return Path(image_path).with_suffix(".psnip")


def _colour(value) -> str:
    colour = QColor(value)
    return colour.name(QColor.NameFormat.HexArgb)


def _point(point: QPointF) -> list[float]:
    return [float(point.x()), float(point.y())]


def _rect(rect: QRectF) -> list[float]:
    return [float(rect.x()), float(rect.y()), float(rect.width()), float(rect.height())]


def dump_item(item) -> dict | None:
    kind = item.__class__.__name__
    payload = {
        "kind": kind,
        "pos": _point(item.pos()),
        "rot": float(item.rotation()),
        "z": float(item.zValue()),
    }
    if isinstance(item, (RectItem, EllipseItem)):
        payload.update({
            "rect": _rect(item.rect()),
            "pen": _colour(item.pen_color),
            "fill": _colour(item.fill_color),
            "width": int(item.line_width),
            "radius": int(getattr(item, "corner_radius", 0)),
        })
        if isinstance(item, SpotlightItem):
            payload["darkness"] = int(item.darkness)
    elif isinstance(item, ArrowItem):
        payload.update({
            "start": _point(item.start),
            "end": _point(item.end),
            "pen": _colour(item.pen_color),
            "width": int(item.line_width),
            "style": item.style,
            "start_cap": item.start_cap,
            "end_cap": item.end_cap,
        })
    elif isinstance(item, TextItem):
        payload.update({
            "text": item.toPlainText(),
            "colour": _colour(item.text_color),
            "size": int(item.font_size),
            "bold": bool(item.font().bold()),
        })
    elif isinstance(item, CalloutItem):
        payload.update({
            "rect": _rect(item._rect),
            "text": item._text,
            "pen": _colour(item.pen_color),
            "fill": _colour(item.fill_color),
            "text_colour": _colour(item.text_color),
            "width": int(item.line_width),
            "size": int(item.font_size),
        })
    elif isinstance(item, NumberItem):
        payload.update({"number": int(item.number), "colour": _colour(item.color)})
    elif isinstance(item, StrokeItem):
        payload.update({
            "points": [_point(point) for point in item._points],
            "pen": _colour(item.pen_color),
            "width": int(item.line_width),
            "highlighter": bool(item.highlighter),
        })
    elif isinstance(item, PolygonItem):
        payload.update({
            "points": [_point(point) for point in item.points],
            "pen": _colour(item.pen_color),
            "fill": _colour(item.fill_color),
            "width": int(item.line_width),
        })
    elif isinstance(item, BlurItem):
        payload.update({"rect": _rect(item.rect()), "block": int(item.block)})
    elif isinstance(item, StampItem):
        payload["text"] = item.toPlainText()
    else:
        return None
    return payload


def load_item(payload: dict):
    kind = payload.get("kind")
    pos = QPointF(*payload.get("pos", [0, 0]))
    if kind == "RectItem":
        item = RectItem(QRectF(*payload["rect"]), QColor(payload["pen"]), QColor(payload["fill"]), int(payload["width"]))
        item.corner_radius = int(payload.get("radius") or 0)
    elif kind == "SpotlightItem":
        item = SpotlightItem(QRectF(*payload["rect"]), int(payload.get("darkness") or 140))
    elif kind == "EllipseItem":
        item = EllipseItem(QRectF(*payload["rect"]), QColor(payload["pen"]), QColor(payload["fill"]), int(payload["width"]))
    elif kind == "ArrowItem":
        item = ArrowItem(
            QPointF(*payload["start"]), QPointF(*payload["end"]),
            QColor(payload["pen"]), int(payload["width"]), payload.get("style") or "plain",
        )
        item.start_cap = payload.get("start_cap") or "none"
        item.end_cap = payload.get("end_cap") or "arrow"
    elif kind == "TextItem":
        item = TextItem(payload.get("text") or "", pos, QColor(payload["colour"]), int(payload.get("size") or 14))
        item.set_bold(bool(payload.get("bold")))
    elif kind == "CalloutItem":
        item = CalloutItem(
            pos, QColor(payload["pen"]), QColor(payload["fill"]), QColor(payload["text_colour"]),
            int(payload["width"]), int(payload.get("size") or 14),
        )
        item._text = payload.get("text") or ""
        item._doc.setPlainText(item._text)
        item.set_rect(QRectF(*payload["rect"]))
    elif kind == "NumberItem":
        item = NumberItem(int(payload.get("number") or 1), pos, QColor(payload["colour"]))
    elif kind == "StrokeItem":
        item = StrokeItem(QColor(payload["pen"]), int(payload["width"]), highlighter=bool(payload.get("highlighter")))
        for point in payload.get("points") or []:
            item.add_point(QPointF(*point))
    elif kind == "PolygonItem":
        item = PolygonItem(
            [QPointF(*point) for point in payload.get("points") or []],
            QColor(payload["pen"]), QColor(payload["fill"]), int(payload["width"]),
        )
    elif kind == "BlurItem":
        item = BlurItem(QRectF(*payload["rect"]), int(payload.get("block") or 14))
    elif kind == "StampItem":
        item = StampItem(payload.get("text") or "", pos)
    else:
        return None
    if not isinstance(item, (TextItem, NumberItem, StampItem, CalloutItem)):
        item.setPos(pos)
    item.setRotation(float(payload.get("rot") or 0))
    item.setZValue(float(payload.get("z") or 0))
    return item


def write_psnip(image_path: str, items, next_number: int) -> None:
    payload = {
        "next": int(next_number),
        "items": [row for row in (dump_item(item) for item in items) if row is not None],
    }
    path = psnip_path(image_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def read_psnip(image_path: str) -> tuple[list, int] | None:
    path = psnip_path(image_path)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(payload, dict):
        return None
    items = []
    for row in payload.get("items") or []:
        if not isinstance(row, dict):
            continue
        try:
            item = load_item(row)
        except (KeyError, TypeError, ValueError):
            continue
        if item is not None:
            items.append(item)
    try:
        nxt = int(payload.get("next") or 1)
    except (TypeError, ValueError):
        nxt = 1
    return items, max(1, nxt)
