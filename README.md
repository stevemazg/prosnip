# ProSnip-Bob

Lightweight Windows screen-snip and annotation tool built with Python and PyQt6.

## Requirements

- Python 3.10+ to run from source. The Windows build uses Python 3.12.
- Windows for the packaged executable. The global hotkey uses the `keyboard` library.

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python src/main.py
```

ProSnip-Bob starts minimised to the system tray.

## Capture

Press **Ctrl+Shift+S** (global hotkey, works even when the app is minimised) or click the tray icon to open the capture overlay. An overlay is shown on every connected monitor, including monitors placed to the left of or above the primary and monitors that use different scale factors (for example 150% on one screen and 100% on another). Click and drag to select a region. Press **Escape** to cancel.

A second capture request is ignored while one is already open or waiting to open. Each successful snip opens its own editor window, so earlier snips stay open.

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

Use the **Quick Styles** dropdown to apply colour and style presets (Red, Blue, Green, Corporate, High Contrast, Yellow Highlight).

## Resize Handles

Select any annotation item and drag the white square handles to resize it.

## Save / Export

| Action | Method |
|--------|--------|
| Save PNG | **Ctrl+S** or the Save PNG button |
| Save JPG | the Save JPG button |
| Copy to clipboard | **Ctrl+Shift+C** or the Copy button |
| Resize canvas | the Resize… button |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Ctrl+Shift+S | Global capture hotkey |
| Ctrl+S | Save as PNG |
| Ctrl+Shift+C | Copy to clipboard |
| Ctrl+Z | Undo last annotation |
| Delete / Backspace | Delete selected items. While a text box is being edited, these keys edit the text instead. |
| Escape | Switch to the Select tool (cancels a capture while the overlay is open) |

## Log

ProSnip-Bob writes `ProSnip-Bob.log` next to the executable. If that folder cannot be written, the log is saved under `%LOCALAPPDATA%\ProSnip-Bob\`. An unexpected error is written to the log and shown in a message box, so a windowed build does not close without an explanation.

## Build to EXE (Windows)

```bat
build.bat
```

Output: `dist/ProSnip-Bob.exe` — a single executable, no installer needed.

GitHub Actions (`.github/workflows/build-windows.yml`) builds the same executable on `windows-latest` when `prosnip-bob` is pushed, and when the workflow is run by hand. The executable is uploaded as the `ProSnip-Bob` artifact.

## File Structure

```
ProSnip-Bob/
├── src/
│   ├── main.py          # Entry point, tray, hotkey, logging
│   ├── capture.py       # Per-monitor capture overlay
│   ├── editor.py        # Main editor window
│   ├── canvas.py        # QGraphicsScene + QGraphicsView
│   ├── toolbar.py       # Vertical tool panel
│   ├── items.py         # Annotation graphics items
│   ├── stamp_picker.py  # Emoji stamp picker dialog
│   └── styles.py        # Quick style definitions
├── tests/
│   └── test_prosnip_bob.py
├── .github/workflows/build-windows.yml
├── requirements.txt
├── build.bat
└── README.md
```
