"""Where the editor window and its tool column sit on a monitor.

Sizes are in logical pixels except the snip, which is image pixels.
A 150% display reports devicePixelRatio 1.5, so a 1500px-wide snip
wants 1000 logical pixels before the toolbars are added.
"""


def fit_editor_frame(
    image_w, image_h, chrome_w, chrome_h, available, dpr=1.0,
    minimum_w=0, minimum_h=0,
):
    """Return ``(x, y, width, height)`` centred in ``available`` and clamped to it.

    ``available`` is a rectangle with ``x``, ``y``, ``width`` and ``height``
    (a monitor's available area, which may start at a negative origin).
    ``minimum_w`` and ``minimum_h`` keep the tool column and the top bar
    from being clipped when the snip itself is small.
    """
    try:
        scale = float(dpr)
    except (TypeError, ValueError):
        scale = 1.0
    if scale <= 0:
        scale = 1.0
    try:
        picture_w = int(round(float(image_w) / scale))
        picture_h = int(round(float(image_h) / scale))
    except (TypeError, ValueError):
        picture_w, picture_h = 0, 0
    want_w = max(1, picture_w) + max(0, int(chrome_w))
    want_h = max(1, picture_h) + max(0, int(chrome_h))
    want_w = max(want_w, int(minimum_w or 0))
    want_h = max(want_h, int(minimum_h or 0))
    limit_w = max(1, int(available.width()))
    limit_h = max(1, int(available.height()))
    width = min(want_w, limit_w)
    height = min(want_h, limit_h)
    x = int(available.x()) + max(0, (limit_w - width) // 2)
    y = int(available.y()) + max(0, (limit_h - height) // 2)
    return x, y, width, height


def tool_column_layout(count, available_height, button=32, spacing=4, margin=4):
    """Two compact columns, or three when a short window cannot fit two.

    Buttons stay at 32px while they fit, then shrink by 2px down to 24.
    """
    import math

    count = max(1, int(count))
    available = max(1, int(available_height))
    button = int(button)

    def needed(columns, size):
        rows = math.ceil(count / columns)
        return margin * 2 + rows * size + max(0, rows - 1) * spacing

    for columns in (2, 3):
        size = button
        while size >= 24:
            if needed(columns, size) <= available:
                return columns, size
            size -= 2
    return 3, 24
