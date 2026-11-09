# ProSnip-Bob

Lightweight Windows screen-snip and annotation tool built with Python and PyQt6.

## Requirements

- Python 3.10+ to run from source. The Windows build uses Python 3.12.
- Windows for the packaged application. Ctrl+Shift+S is registered with the Windows `RegisterHotKey` API. On other systems, use New Capture.

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python src/main.py
```

ProSnip-Bob opens its main window when it starts. The window shows the name, the version, **New Capture**, the hotkey status and **Quit**. It is not minimised and it is brought to the front.

Closing the window with the X button hides it in the notification area. The first time you do that, a tray message says ProSnip-Bob is still running. Click the tray icon, or choose **Show ProSnip-Bob**, to open the window again. **Quit** on the window or in the tray menu exits and unregisters the hotkey.

Starting ProSnip-Bob again while it is already running brings the existing window to the front instead of opening a second copy.

## Capture

Press **Ctrl+Shift+S** (a normal Windows hotkey, including while the window is hidden) or **New Capture**. If another application already owns that hotkey, the window says the shortcut is unavailable and New Capture still works. The main window is hidden while the capture overlays are up, then restored. An overlay is shown on every connected monitor, including monitors placed to the left of or above the primary and monitors that use different scale factors (for example 150% on one screen and 100% on another). Click and drag to select a region. Press **Escape** to cancel.

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

ProSnip-Bob writes `ProSnip-Bob.log` in the same folder as `ProSnip-Bob.exe`. In the folder build that is next to the `_internal` directory, not inside it. If that folder cannot be written, the log is saved under `%LOCALAPPDATA%\ProSnip-Bob\`. An unexpected error is written to the log and shown in a message box, so a windowed build does not close without an explanation.

## Build (Windows)

```bat
build.bat
```

That runs:

```bat
pyinstaller --noconfirm --clean --onedir --windowed --noupx --name ProSnip-Bob --exclude-module tkinter --version-file version_info.txt src/main.py
```

Output: `dist/ProSnip-Bob/`, containing `ProSnip-Bob.exe` and `_internal`. Run `ProSnip-Bob.exe` from that folder. The executable needs `_internal` beside it. Version information in the executable names the product ProSnip-Bob, version 1.1.1.0. UPX is not used.

GitHub Actions (`.github/workflows/build-windows.yml`) builds the same folder on `windows-latest` when `prosnip-bob` is pushed, and when the workflow is run by hand. It zips `dist/ProSnip-Bob/` to `ProSnip-Bob.zip` and uploads that zip as the `ProSnip-Bob` artifact.

ProSnip-Bob is not code-signed. Windows SmartScreen may warn the first time you run it. If you trust the build, choose More info and then Run anyway. Antivirus software may also warn about a new unsigned application. The build does not use a packer, and it does not install a low-level keyboard hook.

## File Structure

```
ProSnip-Bob/
├── src/
│   ├── main.py          # Entry point, tray, logging
│   ├── main_window.py   # Window shown at startup
│   ├── instance.py      # Single-instance activation
│   ├── hotkey.py        # Ctrl+Shift+S via RegisterHotKey
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
├── version_info.txt     # Windows version resource
├── build.bat
└── README.md
```
