"""Generate sample simulator output files."""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import cli


def main() -> int:
    examples = Path("examples")
    examples.mkdir(exist_ok=True)
    _write_cli_output(examples / "sample_ping.txt", ["ping", "--simulate", "--slave", "1"])
    _write_cli_output(examples / "sample_live.txt", ["live", "--simulate", "--slave", "1"])
    _write_cli_output(examples / "sample_log_latest.txt", ["log-latest", "--simulate", "--slave", "1"])
    cli.main(
        [
            "test",
            "--simulate",
            "--slave",
            "1",
            "--out",
            str(examples / "sample_test_report.json"),
            "--txt",
            str(examples / "sample_test_report.txt"),
        ]
    )
    cli.main(
        [
            "ping",
            "--simulate",
            "--slave",
            "1",
            "--capture-txt",
            str(examples / "sample_capture.txt"),
        ]
    )
    cli.main(
        [
            "log-dump",
            "--simulate",
            "--slave",
            "1",
            "--limit",
            "3",
            "--csv",
            str(examples / "sample_logs.csv"),
        ]
    )
    return 0


def _write_cli_output(path: Path, argv: list[str]) -> None:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        cli.main(argv)
    path.write_text(buffer.getvalue(), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
