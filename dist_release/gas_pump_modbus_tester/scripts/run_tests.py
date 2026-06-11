"""Run release QA checks."""

from __future__ import annotations

import subprocess
import sys


COMMANDS = [
    [sys.executable, "-m", "pytest"],
    [sys.executable, "-m", "app.cli", "--help"],
    [sys.executable, "-m", "app.cli", "version"],
    [sys.executable, "-m", "app.cli", "smoke-test"],
]


def main() -> int:
    for command in COMMANDS:
        print(f"$ {' '.join(command)}")
        completed = subprocess.run(command)
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
