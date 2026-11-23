"""Write version_info.txt from APP_VERSION in src/editor.py.

Both build.bat and the Windows workflow run this before PyInstaller so the
executable's FileVersion cannot drift from the source.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "src" / "editor.py"
TARGET = ROOT / "version_info.txt"

TEMPLATE = """# UTF-8
# Windows VERSIONINFO for ProSnip-Bob.exe. Generated from src/editor.py.
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={filevers},
    prodvers={prodvers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'Steve Maz'),
          StringStruct('FileDescription', 'ProSnip-Bob screen capture and annotation tool'),
          StringStruct('FileVersion', '{version}'),
          StringStruct('InternalName', 'ProSnip-Bob'),
          StringStruct('LegalCopyright', 'Copyright (C) 2026 Steve Maz'),
          StringStruct('OriginalFilename', 'ProSnip-Bob.exe'),
          StringStruct('ProductName', 'ProSnip-Bob'),
          StringStruct('ProductVersion', '{version}'),
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def read_version() -> str:
    text = EDITOR.read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION\s*=\s*"([0-9]+(?:\.[0-9]+){3})"', text)
    if match is None:
        raise SystemExit("APP_VERSION was not found in src/editor.py")
    return match.group(1)


def render(version: str) -> str:
    parts = tuple(int(piece) for piece in version.split("."))
    return TEMPLATE.format(version=version, filevers=parts, prodvers=parts)


def main() -> None:
    version = read_version()
    TARGET.write_text(render(version), encoding="utf-8")
    print(f"Wrote {TARGET.name} for {version}")


if __name__ == "__main__":
    main()
