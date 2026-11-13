"""Colour codes, loupe zoom, and the remembered recent-colour list.

No Qt here. The picker and the tests share this so HEX, RGB, and HSL
stay consistent with what is copied to the clipboard.
"""

import json
import os
from pathlib import Path

FORMATS = ("hex", "rgb", "hsl")
HISTORY_LIMIT = 12
ZOOM_MIN = 2
ZOOM_MAX = 32
ZOOM_DEFAULT = 8


def _channel(value) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(255, number))


def rgb_to_hsl(red: int, green: int, blue: int) -> tuple[int, int, int]:
    """Return hue 0–360, saturation percent, and lightness percent."""
    red, green, blue = _channel(red), _channel(green), _channel(blue)
    rf, gf, bf = red / 255.0, green / 255.0, blue / 255.0
    high = max(rf, gf, bf)
    low = min(rf, gf, bf)
    light = (high + low) / 2.0
    if high == low:
        hue = 0.0
        sat = 0.0
    else:
        span = high - low
        sat = span / (2.0 - high - low) if light > 0.5 else span / (high + low)
        if high == rf:
            hue = (gf - bf) / span + (6.0 if gf < bf else 0.0)
        elif high == gf:
            hue = (bf - rf) / span + 2.0
        else:
            hue = (rf - gf) / span + 4.0
        hue /= 6.0
    return round(hue * 360) % 360, round(sat * 100), round(light * 100)


def format_colour(red: int, green: int, blue: int, fmt: str = "hex") -> str:
    """Format one colour. HEX is uppercase, which is the default."""
    red, green, blue = _channel(red), _channel(green), _channel(blue)
    kind = fmt if fmt in FORMATS else "hex"
    if kind == "rgb":
        return f"rgb({red}, {green}, {blue})"
    if kind == "hsl":
        hue, sat, light = rgb_to_hsl(red, green, blue)
        return f"hsl({hue}, {sat}%, {light}%)"
    return f"#{red:02X}{green:02X}{blue:02X}"


def next_format(fmt: str) -> str:
    kind = fmt if fmt in FORMATS else "hex"
    return FORMATS[(FORMATS.index(kind) + 1) % len(FORMATS)]


def clamp_zoom(value) -> int:
    """Loupe magnification stays between 2× and 32×."""
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return ZOOM_DEFAULT
    return max(ZOOM_MIN, min(ZOOM_MAX, number))


def parse_hex(text: str) -> tuple[int, int, int] | None:
    raw = (text or "").strip()
    if raw.startswith("#"):
        raw = raw[1:]
    if len(raw) != 6:
        return None
    try:
        return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    except ValueError:
        return None


def settings_path() -> Path:
    """Remembered picker settings live beside the custom stamps."""
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return root / "ProSnip-Bob" / "settings.json"


class ColourHistory:
    """Last few colours, the chosen code format, and the loupe zoom."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else settings_path()
        self.format = "hex"
        self.zoom = ZOOM_DEFAULT
        self.colours: list[str] = []
        self.load()

    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return
        if not isinstance(data, dict):
            return
        fmt = data.get("colour_format", "hex")
        self.format = fmt if fmt in FORMATS else "hex"
        self.zoom = clamp_zoom(data.get("loupe_zoom", ZOOM_DEFAULT))
        colours = []
        for item in data.get("recent_colours", []):
            parsed = parse_hex(str(item))
            if parsed is None:
                continue
            code = format_colour(*parsed, "hex")
            if code not in colours:
                colours.append(code)
        self.colours = colours[:HISTORY_LIMIT]

    def save(self) -> None:
        payload = {
            "colour_format": self.format,
            "loupe_zoom": self.zoom,
            "recent_colours": list(self.colours),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            return

    def set_format(self, fmt: str) -> None:
        self.format = fmt if fmt in FORMATS else "hex"
        self.save()

    def set_zoom(self, zoom) -> None:
        self.zoom = clamp_zoom(zoom)
        self.save()

    def add_rgb(self, red: int, green: int, blue: int) -> str:
        code = format_colour(red, green, blue, "hex")
        self.colours = [code] + [item for item in self.colours if item != code]
        self.colours = self.colours[:HISTORY_LIMIT]
        self.save()
        return code

    def display(self, hex_code: str) -> str:
        parsed = parse_hex(hex_code)
        if parsed is None:
            return hex_code
        return format_colour(*parsed, self.format)
