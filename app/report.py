"""Reporting and export helpers."""

from __future__ import annotations

import csv
import json
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.decoders import LogWindow
from app.test_runner import TestRunReport


def format_summary(results: list[object]) -> str:
    """Return a compact text summary for test or export results."""
    return f"{len(results)} result(s)"


def dataclass_to_dict(obj: Any) -> Any:
    """Convert dataclasses, containers, and datetime-like values to JSON data."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {
            field.name: dataclass_to_dict(getattr(obj, field.name))
            for field in fields(obj)
        }
    if isinstance(obj, dict):
        return {str(key): dataclass_to_dict(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [dataclass_to_dict(value) for value in obj]
    if isinstance(obj, datetime):
        return obj.isoformat(sep=" ")
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


def write_json(path: str | Path, data: Any) -> None:
    """Write JSON data to *path*, creating parent directories if needed."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dataclass_to_dict(data), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def write_logs_csv(path: str | Path, logs: list[LogWindow]) -> None:
    """Write log windows to a CSV file."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "index",
        "log_count",
        "log_select",
        "is_valid",
        "pump_id",
        "datetime",
        "sequence",
        "amount",
        "liters_x1000",
        "liters",
        "unit_price",
        "total_liters_x1000",
        "total_liters",
        "checksum_hex",
        "log_status_hex",
        "log_status_names",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for index, log in enumerate(logs):
            writer.writerow(
                {
                    "index": index,
                    "log_count": log.log_count,
                    "log_select": log.log_select,
                    "is_valid": log.is_valid,
                    "pump_id": log.pump_id,
                    "datetime": _format_clock(log) if log.clock is not None else "",
                    "sequence": log.sequence,
                    "amount": log.amount,
                    "liters_x1000": log.liters_x1000,
                    "liters": f"{log.liters:.3f}",
                    "unit_price": log.unit_price,
                    "total_liters_x1000": log.total_liters_x1000,
                    "total_liters": f"{log.total_liters:.3f}",
                    "checksum_hex": f"0x{log.checksum:08X}",
                    "log_status_hex": f"0x{log.log_status:04X}",
                    "log_status_names": ",".join(log.log_status_names),
                }
            )


def write_test_report_json(path: str | Path, report: TestRunReport) -> None:
    """Write an automated test report as structured JSON."""
    write_json(path, report)


def write_test_report_txt(path: str | Path, report: TestRunReport) -> None:
    """Write an automated test report as human-readable text."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_format_test_report_txt(report), encoding="utf-8")


def _format_clock(log: LogWindow) -> str:
    assert log.clock is not None
    clock = log.clock
    return (
        f"{clock.year:04d}-{clock.month:02d}-{clock.day:02d} "
        f"{clock.hour:02d}:{clock.minute:02d}:{clock.second:02d}"
    )


def _format_test_report_txt(report: TestRunReport) -> str:
    device = report.device
    lines = [
        "Gas Pump Modbus RTU Test Report",
        "================================",
        "",
        f"Started: {report.started_at}",
        f"Finished: {report.finished_at or ''}",
        f"Duration: {report.duration_ms:.1f} ms" if report.duration_ms is not None else "Duration:",
        "",
        "Connection",
        "----------",
        f"Port: {report.port}",
        f"Baudrate: {report.baudrate}",
        f"Slave ID: {report.slave_id}",
        "",
        "Device",
        "------",
        f"Protocol version: {device.get('protocol_version', '')}",
        f"Reported slave address: {device.get('reported_slave_address', '')}",
        (
            f"Nozzle: {device.get('nozzle_status', '')} - "
            f"{device.get('nozzle_status_text', '')}"
        ),
        (
            f"Status flags: {device.get('status_flags', '')} "
            f"[{', '.join(device.get('status_flag_names', []))}]"
        ),
        "",
        "Summary",
        "-------",
        f"PASS: {report.summary.get('PASS', 0)}",
        f"WARN: {report.summary.get('WARN', 0)}",
        f"FAIL: {report.summary.get('FAIL', 0)}",
        f"SKIP: {report.summary.get('SKIP', 0)}",
        f"TOTAL: {report.summary.get('TOTAL', 0)}",
        f"Overall: {report.overall_status}",
        "",
        "Results",
        "-------",
    ]
    for result in report.results:
        lines.append(
            f"[{result.id}] {result.status} {result.name} - {result.message}"
        )
        if result.error_type or result.error_message:
            lines.append(
                f"    Error: {result.error_type or ''}: {result.error_message or ''}"
            )
    lines.append("")
    return "\n".join(lines)
