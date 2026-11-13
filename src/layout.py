"""Where the editor window sits on a monitor.

Sizes are in logical pixels except the snip, which is image pixels.
A 150% display reports devicePixelRatio 1.5, so a 1500px-wide snip
wants 1000 logical pixels before the toolbars are added.
"""


def fit_editor_frame(image_w, image_h, chrome_w, chrome_h, available, dpr=1.0):
    """Return ``(x, y, width, height)`` centred in ``available`` and clamped to it.

    ``available`` is a rectangle with ``x``, ``y``, ``width`` and ``height``
    (a monitor's available area, which may start at a negative origin).
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
    limit_w = max(1, int(available.width()))
    limit_h = max(1, int(available.height()))
    width = min(want_w, limit_w)
    height = min(want_h, limit_h)
    x = int(available.x()) + max(0, (limit_w - width) // 2)
    y = int(available.y()) + max(0, (limit_h - height) // 2)
    return x, y, width, height
