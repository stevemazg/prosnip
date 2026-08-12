# ProSnip — Product Scope

**Version:** 1.0 Draft
**Date:** 12 August 2026
**Status:** Scoping — Not started

---

## Overview

ProSnip is a lightweight Windows image capture and annotation tool. Images only — no video. Fast, clean, purpose-built for annotating screenshots and sharing them quickly.

---

## Core Features

### 1. Capture
- Region snip (drag to select area)
- Full screen capture
- Active window capture
- Clipboard paste (paste image in, start annotating)

### 2. Annotation Tools
| Tool | Detail |
|---|---|
| Arrow | Straight arrows, curved arrows, directional styles |
| Callout | Speech bubble / box callout with text inside |
| Text | Free text box, font size/colour control |
| Stamp | Preset stamps: ✅ ✗ ⚠️ 👍 numbered circles (1, 2, 3…) |
| Shape | Rectangle, circle, highlight box |
| Crop | Crop the image after capture |
| Resize | Resize canvas or image dimensions |

### 3. Picture on Picture
- Insert a second image on top of the main image
- Drag to position, resize handles
- Use case: logo watermarks, inset screenshots, comparison overlays

### 4. Quick Styles
- Preset colour/style themes (e.g. Red, Blue, Corporate, High Contrast)
- One-click apply to all annotations
- Custom style saved per user

### 5. Output
- Save as PNG, JPG, or WEBP
- Copy to clipboard (one-click)
- Optional: save to a default folder with auto-filename (ProSnip_YYYYMMDD_HHMMSS)

---

## UI / UX Notes
- Lightweight toolbar — no ribbon, no clutter
- Canvas-style editor (click to place, drag to resize)
- Undo / Redo (Ctrl+Z / Ctrl+Y)
- Keyboard shortcut to launch capture (global hotkey, e.g. Ctrl+Shift+S)
- Dark or light mode

---

## Out of Scope (v1)
- Video / GIF recording
- Cloud upload / sharing links
- Scrolling capture
- OCR
- Multi-page / multi-image projects
- Mobile version

---

## Recommended Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Language | Python | Fast to build, good library support |
| UI framework | PyQt6 | Native-feel Windows app, canvas support |
| Capture | mss + win32api | Lightweight, accurate region capture |
| Image handling | Pillow (PIL) | Crop, resize, compositing |
| Packaging | PyInstaller | Single .exe — no install needed |

---

## Milestones (suggested)

| # | Milestone | Description |
|---|---|---|
| 1 | Capture engine | Region / full screen / window / clipboard |
| 2 | Canvas editor | Place, move, resize annotations |
| 3 | Annotation tools | Arrow, text, callout, stamp, shape |
| 4 | Picture on picture | Insert image overlay |
| 5 | Quick styles | Preset themes |
| 6 | Output | Save / copy to clipboard |
| 7 | Packaging | PyInstaller .exe build |

---

## Open Questions (before build)

- Default save folder — Documents/ProSnip or user-chosen?
- Stamp library — use defaults above or custom set?
- Quick styles — how many presets to start with?
- Global hotkey — confirm default key combo
- Branding — any logo / colour scheme for the app itself?

---

*Scope by Jess. Build not started.*
