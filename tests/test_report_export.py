import json

from app.decoders import LogWindow, PumpClock
from app.report import dataclass_to_dict, write_json, write_logs_csv


def _sample_log() -> LogWindow:
    return LogWindow(
        log_count=7,
        log_select=0,
        log_status=0x0007,
        log_status_names=["has_log", "select_valid", "payload_loaded"],
        is_valid=True,
        pump_id=1,
        clock=PumpClock(2026, 4, 24, 15, 30, 45),
        sequence=7,
        amount=12345,
        liters_x1000=536,
        liters=0.536,
        unit_price=23000,
        total_liters_x1000=100536,
        total_liters=100.536,
        checksum=0x12345678,
    )


def test_dataclass_to_dict_nested() -> None:
    data = dataclass_to_dict(_sample_log())

    assert data["clock"]["year"] == 2026
    assert data["log_status_names"] == ["has_log", "select_valid", "payload_loaded"]


def test_write_json(tmp_path) -> None:
    path = tmp_path / "logs.json"

    write_json(path, [_sample_log()])

    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data[0]["checksum"] == 0x12345678
    assert data[0]["clock"]["second"] == 45


def test_write_logs_csv(tmp_path) -> None:
    path = tmp_path / "logs.csv"

    write_logs_csv(path, [_sample_log()])

    content = path.read_text(encoding="utf-8")
    assert path.exists()
    assert "index,log_count,log_select,is_valid" in content
    assert "2026-04-24 15:30:45" in content
    assert "0x12345678" in content
