"""Raw Modbus RTU capture records and export helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class RawFrameRecord:
    timestamp: str
    direction: str
    port: str | None
    slave_id: int | None
    function_code: int | None
    frame_hex: str
    frame_len: int
    elapsed_ms: float | None = None
    crc_valid: bool | None = None
    note: str | None = None


class RawCaptureBuffer:
    """Bounded in-memory buffer for raw TX/RX Modbus frames."""

    def __init__(self, max_records: int = 1000):
        if max_records <= 0:
            raise ValueError("max_records must be positive")
        self.max_records = max_records
        self._records: list[RawFrameRecord] = []

    def add(self, record: RawFrameRecord) -> None:
        self._records.append(record)
        excess = len(self._records) - self.max_records
        if excess > 0:
            del self._records[:excess]

    def clear(self) -> None:
        self._records.clear()

    def records(self) -> list[RawFrameRecord]:
        return list(self._records)

    def to_dicts(self) -> list[dict[str, Any]]:
        return [asdict(record) for record in self._records]


def infer_slave_id(frame: bytes) -> int | None:
    if len(frame) >= 1:
        return frame[0]
    return None


def infer_function_code(frame: bytes) -> int | None:
    if len(frame) >= 2:
        return frame[1]
    return None


def write_capture_jsonl(path: str | Path, records: list[RawFrameRecord]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(asdict(record), ensure_ascii=False) for record in records]
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_capture_txt(path: str | Path, records: list[RawFrameRecord]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["Raw Modbus RTU Capture", "======================", ""]
    for record in records:
        parts = [
            f"[{record.timestamp}]",
            record.direction,
            f"len={record.frame_len}",
        ]
        if record.slave_id is not None:
            parts.append(f"slave={record.slave_id}")
        if record.function_code is not None:
            parts.append(f"fn=0x{record.function_code:02X}")
        if record.elapsed_ms is not None:
            parts.append(f"elapsed={record.elapsed_ms:.1f}ms")
        if record.direction == "RX":
            parts.append(f"crc={_crc_text(record.crc_valid)}")
        if record.note:
            parts.append(f"note={record.note}")
        lines.append(" ".join(parts))
        lines.append(record.frame_hex if record.frame_hex else "<none>")
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _crc_text(value: bool | None) -> str:
    if value is True:
        return "OK"
    if value is False:
        return "BAD"
    return "UNKNOWN"
