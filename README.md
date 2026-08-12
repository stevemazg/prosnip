# ProSnip

Lightweight Windows screen annotation tool built with Python + PyQt6.

## Requirements

- Python 3.10+
- Windows (global hotkey via `keyboard` library requires Windows/Linux)

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python src/main.py
```

ProSnip starts minimised to the system tray.

## Capture

Press **Ctrl+Shift+S** (global hotkey, works even when the app is minimised) or click the tray icon to open the capture overlay. Click and drag to select a region. Press **Escape** to cancel.

## Annotation Tools

| Tool | Description |
|------|-------------|
| Select | Move/resize/select items |
| Arrow | Draw an arrow line |
| Text | Click to place editable text. Double-click to edit. |
| Callout | Draw a callout bubble. Double-click to edit text. |
| Stamp | Choose an emoji stamp (✅ ❌ ⚠️ 👍 💡 etc.) |
| Rectangle | Draw a filled rectangle |
| Ellipse | Draw a filled ellipse |
| Image | Insert an image overlay (picture-on-picture) |
| Crop | Drag to crop the canvas |

Use the **Quick Styles** dropdown to apply colour/style presets (Red, Blue, Green, Corporate, High Contrast, Yellow Highlight).

## Resize Handles

Select any annotation item and drag the white square handles to resize it.

## Save / Export

| Action | Method |
|--------|--------|
| Save PNG | **Ctrl+S** or "Save PNG" button |
| Save JPG | "Save JPG" button |
| Copy to clipboard | **Ctrl+Shift+C** or "Copy" button |
| Resize canvas | "Resize…" button |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Ctrl+Shift+S | Global capture hotkey |
| Ctrl+S | Save as PNG |
| Ctrl+Z | Undo last annotation |
| Delete | Delete selected items |
| Escape | Switch to Select tool |

## Build to EXE (Windows)

```bat
build.bat
```

Output: `dist/ProSnip.exe` — single executable, no installer needed.

## File Structure

```
ProSnip/
├── src/
│   ├── main.py          # Entry point, tray, hotkey
│   ├── capture.py       # Screen capture overlay
│   ├── editor.py        # Main editor window
│   ├── canvas.py        # QGraphicsScene + QGraphicsView
│   ├── toolbar.py       # Vertical tool panel
│   ├── items.py         # Annotation graphics items
│   ├── stamp_picker.py  # Emoji stamp picker dialog
│   └── styles.py        # Quick style definitions
├── requirements.txt
├── build.bat
└── README.md
```
