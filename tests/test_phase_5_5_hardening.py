import argparse

import pytest

from app import cli
from app.decoders import LogWindow, PumpClock
from app.exceptions import ModbusFrameError, ModbusTimeoutError
from app.gaspump_client import GasPumpModbusClient
from app.modbus_rtu import parse_read_response


class FakeTransport:
    def __init__(self) -> None:
        self.debug = False
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _valid_log(index: int = 0, count: int = 1) -> LogWindow:
    return LogWindow(
        log_count=count,
        log_select=index,
        log_status=0x0007,
        log_status_names=["has_log", "select_valid", "payload_loaded"],
        is_valid=True,
        pump_id=1,
        clock=PumpClock(2026, 4, 24, 15, 30, 45),
        sequence=index,
        amount=12345,
        liters_x1000=536,
        liters=0.536,
        unit_price=23000,
        total_liters_x1000=100536,
        total_liters=100.536,
        checksum=0x12345678,
    )


class LogValidationClient(GasPumpModbusClient):
    def __init__(self, log_count: int) -> None:
        super().__init__(FakeTransport())
        self.log_count = log_count
        self.selected_indices: list[int] = []

    def read_log_count(self) -> int:
        return self.log_count

    def select_log(self, index: int) -> bool:
        self.selected_indices.append(index)
        return True

    def read_log_window(self) -> LogWindow:
        return _valid_log(self.selected_indices[-1], self.log_count)


def test_read_log_negative_index_raises_before_select() -> None:
    client = LogValidationClient(log_count=7)

    with pytest.raises(ValueError, match="Invalid log index -1"):
        client.read_log(-1)

    assert client.selected_indices == []


def test_read_log_zero_count_raises_before_select() -> None:
    client = LogValidationClient(log_count=0)

    with pytest.raises(ValueError, match="No logs available on device"):
        client.read_log(0)

    assert client.selected_indices == []


def test_read_log_out_of_range_raises_before_select() -> None:
    client = LogValidationClient(log_count=7)

    with pytest.raises(ValueError, match="valid range is 0..6"):
        client.read_log(7)

    assert client.selected_indices == []


def test_read_log_valid_index_selects_and_reads() -> None:
    client = LogValidationClient(log_count=7)

    log = client.read_log(6)

    assert client.selected_indices == [6]
    assert log.log_select == 6


class ReadAllLogsClient(GasPumpModbusClient):
    def __init__(self) -> None:
        super().__init__(FakeTransport())

    def read_log_count(self) -> int:
        return 3

    def read_log(self, index: int) -> LogWindow:
        if index == 1:
            raise ModbusTimeoutError("timeout at index 1")
        return _valid_log(index, 3)


def test_read_all_logs_non_strict_records_skipped_errors() -> None:
    client = ReadAllLogsClient()

    logs = client.read_all_logs(strict=False)

    assert [log.log_select for log in logs] == [0, 2]
    assert client.last_log_read_errors == [
        {
            "index": "1",
            "error_type": "ModbusTimeoutError",
            "error_message": "timeout at index 1",
        }
    ]


def test_read_all_logs_strict_raises_original_error() -> None:
    client = ReadAllLogsClient()

    with pytest.raises(ModbusTimeoutError, match="timeout at index 1"):
        client.read_all_logs(strict=True)

    assert client.last_log_read_errors == []


def test_parse_read_response_expected_quantity_mismatch_raises() -> None:
    response = bytes.fromhex("01 03 04 00 00 00 07 BB F1")

    with pytest.raises(ModbusFrameError) as exc_info:
        parse_read_response(response, 1, 0x03, expected_quantity=3)

    message = str(exc_info.value)
    assert "expected quantity 3" in message
    assert "actual quantity 2" in message
    assert "01 03 04 00 00 00 07 BB F1" in message


class FakeWriteClient:
    def __init__(self) -> None:
        self.writes: list[tuple[int, int]] = []

    def write_single_register(self, address: int, value: int) -> bool:
        self.writes.append((address, value))
        return True


def _write_args(yes: bool) -> argparse.Namespace:
    return argparse.Namespace(
        port="COM5",
        slave=1,
        baudrate=9600,
        timeout=0.5,
        debug=False,
        addr=0x002A,
        value=0,
        yes=yes,
    )


def test_cli_raw_write_confirmation_cancel(monkeypatch, capsys) -> None:
    opened = False

    def fake_open_client(args):
        nonlocal opened
        opened = True
        return FakeTransport(), FakeWriteClient()

    monkeypatch.setattr(cli, "_open_client", fake_open_client)
    monkeypatch.setattr("builtins.input", lambda prompt: "NO")

    assert cli.handle_write(_write_args(yes=False)) == 1
    assert opened is False
    assert "Cancelled." in capsys.readouterr().out


def test_cli_raw_write_yes_bypasses_prompt(monkeypatch) -> None:
    transport = FakeTransport()
    client = FakeWriteClient()

    def fake_open_client(args):
        return transport, client

    def fail_input(prompt):
        raise AssertionError("input should not be called")

    monkeypatch.setattr(cli, "_open_client", fake_open_client)
    monkeypatch.setattr("builtins.input", fail_input)

    assert cli.handle_write(_write_args(yes=True)) == 0
    assert client.writes == [(0x002A, 0)]
    assert transport.closed is True


class FakeLogDumpClient:
    def __init__(self) -> None:
        self.last_log_read_errors: list[dict[str, str]] = []

    def read_log_count(self) -> int:
        return 1

    def read_all_logs(
        self,
        limit=None,
        include_invalid=False,
        strict=False,
    ) -> list[LogWindow]:
        return [_valid_log()]


def test_cli_log_dump_export_failure_returns_2(monkeypatch, capsys) -> None:
    transport = FakeTransport()

    def fake_open_client(args):
        return transport, FakeLogDumpClient()

    def fail_write(path, data):
        raise OSError("disk is read-only")

    args = argparse.Namespace(
        port="COM5",
        slave=1,
        baudrate=9600,
        timeout=0.5,
        debug=False,
        limit=None,
        include_invalid=False,
        strict=False,
        json="output/logs.json",
        csv=None,
    )

    monkeypatch.setattr(cli, "_open_client", fake_open_client)
    monkeypatch.setattr(cli, "write_json", fail_write)

    assert cli.handle_log_dump(args) == 2
    assert "ERROR: Failed to write export file output/logs.json" in capsys.readouterr().err
    assert transport.closed is True
