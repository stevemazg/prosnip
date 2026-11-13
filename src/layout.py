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


def tool_column_layout(count, available_height, max_button=52, min_button=44, spacing=4, margin=8):
    """Columns and button size so every tool is on screen without scrolling.

    One column at the large size is preferred. A short window wraps to two
    columns before the icons shrink.
    """
    import math

    count = max(1, int(count))
    available = max(1, int(available_height))
    max_button = int(max_button)
    min_button = int(min_button)

    def needed(columns, button):
        rows = math.ceil(count / columns)
        return margin * 2 + rows * button + max(0, rows - 1) * spacing

    if needed(1, max_button) <= available:
        return 1, max_button
    if needed(2, max_button) <= available:
        return 2, max_button
    button = max_button
    while button > min_button:
        button -= 2
        if needed(2, button) <= available:
            return 2, button
    return 2, min_button
