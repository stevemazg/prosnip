"""Screenshot entry point. The production executable does not import this."""

import sys
from pathlib import Path

from demo_screenshots import capture_demo_screenshots


def main() -> int:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("screenshots")
    return capture_demo_screenshots(folder)


if __name__ == "__main__":
    raise SystemExit(main())
