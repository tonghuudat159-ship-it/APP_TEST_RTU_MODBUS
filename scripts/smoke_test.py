"""Windows-friendly smoke test wrapper."""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    return subprocess.run([sys.executable, "-m", "app.cli", "smoke-test"]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
