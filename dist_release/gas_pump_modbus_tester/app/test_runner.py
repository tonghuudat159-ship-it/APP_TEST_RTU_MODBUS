"""Automated non-destructive diagnostic test runner."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, ClassVar

from app.capture import RawCaptureBuffer
from app.decoders import (
    ConfigStatus,
    FailEvent,
    LiveData,
    LogWindow,
    PumpClock,
    QuickStatus,
    SensorSnapshot,
    pump_clock_to_datetime,
)
from app.exceptions import ModbusExceptionResponse, ModbusTimeoutError
from app.gaspump_client import GasPumpModbusClient
from app.troubleshooting import (
    diagnose_capture,
    diagnose_exception,
    hints_to_dicts,
)

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
WARN = "WARN"
STATUSES = (PASS, FAIL, SKIP, WARN)


@dataclass
class TestStepResult:
    __test__: ClassVar[bool] = False

    id: str
    name: str
    status: str
    message: str
    duration_ms: float
    details: dict[str, Any] = field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class TestRunReport:
    __test__: ClassVar[bool] = False

    started_at: str
    finished_at: str | None
    duration_ms: float | None
    port: str
    baudrate: int
    slave_id: int
    summary: dict[str, int]
    device: dict[str, Any]
    results: list[TestStepResult]
    overall_status: str = FAIL


@dataclass
class _StepOutcome:
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


class GasPumpTestRunner:
    """Runs a safe diagnostic sequence against a gas pump Modbus device."""

    def __init__(
        self,
        client: GasPumpModbusClient,
        port: str,
        baudrate: int,
        slave_id: int,
        debug: bool = False,
        expected_protocol_version: int = 7,
        include_slow_tests: bool = False,
        capture: RawCaptureBuffer | None = None,
    ):
        self.client = client
        self.port = port
        self.baudrate = baudrate
        self.slave_id = slave_id
        self.debug = debug
        self.expected_protocol_version = expected_protocol_version
        self.include_slow_tests = include_slow_tests
        self.capture = capture
        self.context: dict[str, Any] = {}
        self.device: dict[str, Any] = {}

    def run_all(self) -> TestRunReport:
        """Run all safe automated tests and return a structured report."""
        started_perf = time.perf_counter()
        started_at = _now_text()
        results = [
            self._run_step("T01", "Serial client initialized", self._test_client_ready),
            self._run_step("T02", "Read quick status", self._test_read_quick_status),
            self._run_step("T03", "Protocol version check", self._test_protocol_version),
            self._run_step("T04", "Slave address check", self._test_slave_address),
            self._run_step("T05", "Status flags sanity", self._test_status_flags),
            self._run_step("T06", "Nozzle status sanity", self._test_nozzle_status),
            self._run_step("T07", "Read live data", self._test_read_live_data),
            self._run_step("T08", "Live data sanity", self._test_live_data_sanity),
            self._run_step("T09", "Read sensor snapshot", self._test_read_sensor),
            self._run_step("T10", "Sensor sanity", self._test_sensor_sanity),
            self._run_step("T11", "Read pump clock", self._test_read_clock),
            self._run_step("T12", "Read fail event", self._test_read_fail_event),
            self._run_step("T13", "Read log count", self._test_read_log_count),
            self._run_step("T14", "Select latest log", self._test_select_latest_log),
            self._run_step("T15", "Read latest log window", self._test_read_latest_log),
            self._run_step("T16", "Read all logs limited", self._test_read_all_logs_limited),
            self._run_step("T17", "Illegal address exception test", self._test_illegal_address),
            self._run_step("T18", "Wrong slave id no-response test", self._test_wrong_slave),
            self._run_step("T19", "Config status read", self._test_config_status),
        ]
        finished_at = _now_text()
        duration_ms = (time.perf_counter() - started_perf) * 1000.0
        summary = _summarize(results)
        overall_status = FAIL if summary[FAIL] else PASS
        return TestRunReport(
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            port=self.port,
            baudrate=self.baudrate,
            slave_id=self.slave_id,
            summary=summary,
            device=self.device,
            results=results,
            overall_status=overall_status,
        )

    def _run_step(
        self,
        test_id: str,
        name: str,
        func: Callable[[], _StepOutcome | tuple[str, dict[str, Any] | None]],
    ) -> TestStepResult:
        started = time.perf_counter()
        try:
            outcome = func()
            if isinstance(outcome, tuple):
                message, details = outcome
                outcome = self._pass(message, details)
            status = outcome.status if outcome.status in STATUSES else FAIL
            return TestStepResult(
                id=test_id,
                name=name,
                status=status,
                message=outcome.message,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                details=outcome.details,
            )
        except Exception as exc:
            if self.debug:
                print(f"Warning: {test_id} {name} failed with {type(exc).__name__}: {exc}")
            diagnostic_hints = diagnose_exception(exc)
            if self.capture is not None:
                diagnostic_hints.extend(diagnose_capture(self.capture.records()))
            return TestStepResult(
                id=test_id,
                name=name,
                status=FAIL,
                message="Unhandled test exception",
                duration_ms=(time.perf_counter() - started) * 1000.0,
                details={"diagnostic_hints": hints_to_dicts(diagnostic_hints)},
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

    def _test_client_ready(self) -> _StepOutcome:
        if self.client is None:
            return self._fail("Client object is not initialized")
        return self._pass(
            "OK",
            {
                "port": self.port,
                "baudrate": self.baudrate,
                "slave_id": self.slave_id,
            },
        )

    def _test_read_quick_status(self) -> _StepOutcome:
        status = self.client.read_quick_status()
        self.context["quick_status"] = status
        self.device.update(_quick_status_device(status))
        return self._pass(
            f"Protocol version {status.protocol_version}",
            _quick_status_details(status),
        )

    def _test_protocol_version(self) -> _StepOutcome:
        status = self._quick_status()
        if status is None:
            return self._fail("Quick status unavailable")
        details = {
            "expected": self.expected_protocol_version,
            "actual": status.protocol_version,
        }
        if status.protocol_version == self.expected_protocol_version:
            return self._pass("Expected version matched", details)
        return self._warn("Readable protocol version does not match expected", details)

    def _test_slave_address(self) -> _StepOutcome:
        status = self._quick_status()
        if status is None:
            return self._fail("Quick status unavailable")
        details = {"requested": self.slave_id, "reported": status.slave_address}
        if status.slave_address == self.slave_id:
            return self._pass("Reported slave address matched request", details)
        return self._warn("Reported slave address differs from request", details)

    def _test_status_flags(self) -> _StepOutcome:
        status = self._quick_status()
        if status is None:
            return self._fail("Quick status unavailable")
        details = {
            "status_flags": f"0x{status.status_flags:04X}",
            "status_flag_names": status.status_flag_names,
        }
        if status.status_flag_names:
            return self._pass("Status flags decoded", details)
        return self._warn("No known status flag is set", details)

    def _test_nozzle_status(self) -> _StepOutcome:
        status = self._quick_status()
        if status is None:
            return self._fail("Quick status unavailable")
        details = {
            "nozzle_status": status.nozzle_status,
            "nozzle_status_text": status.nozzle_status_text,
        }
        if status.nozzle_status in (0, 1, 2):
            return self._pass("Nozzle status is valid", details)
        return self._fail("Nozzle status is outside valid range 0..2", details)

    def _test_read_live_data(self) -> _StepOutcome:
        live = self.client.read_live_data()
        self.context["live_data"] = live
        return self._pass("Live data decoded", _live_details(live))

    def _test_live_data_sanity(self) -> _StepOutcome:
        live = self.context.get("live_data")
        if live is None:
            return self._fail("Live data unavailable")
        values = _live_numeric_values(live)
        bad = {
            name: value
            for name, value in values.items()
            if value < 0 or not math.isfinite(float(value))
        }
        if bad:
            return self._fail("Live data contains invalid numeric values", bad)
        details = {"unit_price": live.unit_price}
        if live.unit_price == 0:
            return self._warn("Unit price is zero", details)
        return self._pass("Live data values are sane", details)

    def _test_read_sensor(self) -> _StepOutcome:
        sensor = self.client.read_sensor_snapshot()
        self.context["sensor"] = sensor
        details = _sensor_details(sensor)
        if sensor.ambient_valid:
            return self._pass("Sensor snapshot decoded", details)
        return self._pass("Sensor snapshot decoded; ambient data unavailable", details)

    def _test_sensor_sanity(self) -> _StepOutcome:
        sensor = self.context.get("sensor")
        if sensor is None:
            return self._fail("Sensor snapshot unavailable")
        warnings: list[str] = []
        if not -40.0 <= sensor.mcu_temp_c <= 125.0:
            warnings.append("MCU temperature outside normal range")
        if not sensor.ambient_valid:
            return self._skip("Ambient temperature and humidity are unavailable", _sensor_details(sensor))
        if sensor.ambient_temp_c is None or not -40.0 <= sensor.ambient_temp_c <= 85.0:
            warnings.append("Ambient temperature outside normal range")
        if sensor.humidity_percent is None or not 0.0 <= sensor.humidity_percent <= 100.0:
            warnings.append("Humidity outside normal range")
        details = _sensor_details(sensor)
        if warnings:
            details["warnings"] = warnings
            return self._warn("; ".join(warnings), details)
        return self._pass("Sensor values are within normal ranges", details)

    def _test_read_clock(self) -> _StepOutcome:
        clock = self.client.read_clock()
        self.context["clock"] = clock
        pump_datetime = pump_clock_to_datetime(clock)
        details = {"clock": _format_clock(clock)}
        current_year = datetime.now().year
        if abs(pump_datetime.year - current_year) > 3:
            return self._warn("Pump clock year is far from system year", details)
        return self._pass("Pump clock decoded", details)

    def _test_read_fail_event(self) -> _StepOutcome:
        event = self.client.read_fail_event()
        self.context["fail_event"] = event
        details = {
            "code": f"0x{event.code:04X}",
            "code_text": event.code_text,
            "sequence": event.sequence,
        }
        if event.code != 0:
            return self._warn("Last fail code is not NONE", details)
        return self._pass("No fail event reported", details)

    def _test_read_log_count(self) -> _StepOutcome:
        log_count = self.client.read_log_count()
        self.context["log_count"] = log_count
        return self._pass("Log count read", {"log_count": log_count})

    def _test_select_latest_log(self) -> _StepOutcome:
        log_count = self.context.get("log_count")
        if log_count is None:
            return self._fail("Log count unavailable")
        if log_count == 0:
            return self._skip("no log available", {"log_count": log_count})
        ok = self.client.select_log(0)
        if ok:
            return self._pass("Latest log selected", {"index": 0})
        return self._fail("LOG_SELECT write echo was invalid", {"index": 0})

    def _test_read_latest_log(self) -> _StepOutcome:
        log_count = self.context.get("log_count")
        if log_count is None:
            return self._fail("Log count unavailable")
        if log_count == 0:
            return self._skip("no log available", {"log_count": log_count})
        log = self.client.read_log_window()
        self.context["latest_log"] = log
        details = _log_details(log)
        if log.is_valid:
            return self._pass("Latest log payload is valid", details)
        return self._warn("Latest log window decoded but payload is not valid", details)

    def _test_read_all_logs_limited(self) -> _StepOutcome:
        log_count = self.context.get("log_count")
        if log_count is None:
            return self._fail("Log count unavailable")
        if log_count == 0:
            return self._skip("no log available", {"log_count": log_count})
        requested = min(log_count, 10)
        logs = self.client.read_all_logs(limit=requested, include_invalid=True)
        valid = sum(1 for log in logs if log.is_valid)
        invalid = len(logs) - valid
        details = {
            "requested": requested,
            "read": len(logs),
            "valid": valid,
            "invalid": invalid,
        }
        if valid == 0:
            return self._warn("No valid logs found", details)
        return self._pass("Limited log read completed", details)

    def _test_illegal_address(self) -> _StepOutcome:
        try:
            self.client.read_holding_registers(0x7FFF, 1)
        except ModbusExceptionResponse as exc:
            details = {
                "exception_code": f"0x{exc.exception_code:02X}",
                "function_code": f"0x{exc.function_code:02X}",
                "message": exc.exception_message,
            }
            if exc.exception_code == 0x02:
                return self._pass("Illegal data address exception received", details)
            return self._fail("Unexpected Modbus exception code", details)
        except ModbusTimeoutError as exc:
            return self._warn("Invalid address timed out; firmware may ignore it", {"error": str(exc)})
        return self._fail("Invalid address returned a normal response")

    def _test_wrong_slave(self) -> _StepOutcome:
        if not self.include_slow_tests:
            return self._skip("slow wrong-slave timeout test disabled")
        wrong_slave = self.slave_id + 1 if self.slave_id != 247 else 1
        try:
            wrong_client = GasPumpModbusClient(self.client.transport, slave_id=wrong_slave)
            wrong_client.read_quick_status()
        except ModbusTimeoutError as exc:
            return self._pass("Wrong slave id produced no response", {"wrong_slave_id": wrong_slave, "error": str(exc)})
        return self._warn("Wrong slave id received a response", {"wrong_slave_id": wrong_slave})

    def _test_config_status(self) -> _StepOutcome:
        status = self.client.read_config_status()
        self.context["config_status"] = status
        details = {
            "config_status": f"0x{status.value:04X}",
            "unlocked": status.unlocked,
            "names": status.names,
        }
        if status.unlocked:
            return self._warn("Configuration is currently unlocked", details)
        return self._pass("Configuration is locked", details)

    def _quick_status(self) -> QuickStatus | None:
        return self.context.get("quick_status")

    def _pass(self, message: str, details: dict[str, Any] | None = None) -> _StepOutcome:
        return _StepOutcome(PASS, message, details or {})

    def _fail(self, message: str, details: dict[str, Any] | None = None) -> _StepOutcome:
        return _StepOutcome(FAIL, message, details or {})

    def _skip(self, message: str, details: dict[str, Any] | None = None) -> _StepOutcome:
        return _StepOutcome(SKIP, message, details or {})

    def _warn(self, message: str, details: dict[str, Any] | None = None) -> _StepOutcome:
        return _StepOutcome(WARN, message, details or {})


def _summarize(results: list[TestStepResult]) -> dict[str, int]:
    summary = {PASS: 0, FAIL: 0, WARN: 0, SKIP: 0, "TOTAL": len(results)}
    for result in results:
        summary[result.status] = summary.get(result.status, 0) + 1
    return summary


def _now_text() -> str:
    return datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def _quick_status_device(status: QuickStatus) -> dict[str, Any]:
    return {
        "protocol_version": status.protocol_version,
        "reported_slave_address": status.slave_address,
        "status_flags": f"0x{status.status_flags:04X}",
        "status_flag_names": status.status_flag_names,
        "nozzle_status": status.nozzle_status,
        "nozzle_status_text": status.nozzle_status_text,
    }


def _quick_status_details(status: QuickStatus) -> dict[str, Any]:
    return _quick_status_device(status)


def _live_details(live: LiveData) -> dict[str, Any]:
    return {
        "current_amount": live.current_amount,
        "current_liters": live.current_liters,
        "unit_price": live.unit_price,
        "target_amount": live.target_amount,
        "target_liters": live.target_liters,
        "daily_amount": live.daily_amount,
        "daily_liters": live.daily_liters,
        "total_liters": live.total_liters,
    }


def _live_numeric_values(live: LiveData) -> dict[str, int | float]:
    values: dict[str, int | float] = {
        "current_amount": live.current_amount,
        "current_liters_x1000": live.current_liters_x1000,
        "current_liters": live.current_liters,
        "unit_price": live.unit_price,
        "target_amount": live.target_amount,
        "target_liters_x1000": live.target_liters_x1000,
        "target_liters": live.target_liters,
        "daily_amount": live.daily_amount,
        "daily_liters_x1000": live.daily_liters_x1000,
        "daily_liters": live.daily_liters,
        "total_liters_x1000": live.total_liters_x1000,
        "total_liters": live.total_liters,
    }
    for name, preset in live.hotkeys.items():
        values[f"hotkey_{name}_amount"] = preset.amount
        values[f"hotkey_{name}_liters_x1000"] = preset.liters_x1000
        values[f"hotkey_{name}_liters"] = preset.liters
    return values


def _sensor_details(sensor: SensorSnapshot) -> dict[str, Any]:
    return {
        "sensor_status": f"0x{sensor.sensor_status:04X}",
        "ambient_valid": sensor.ambient_valid,
        "mcu_temp_c": sensor.mcu_temp_c,
        "ambient_temp_c": sensor.ambient_temp_c,
        "humidity_percent": sensor.humidity_percent,
    }


def _format_clock(clock: PumpClock) -> str:
    return (
        f"{clock.year:04d}-{clock.month:02d}-{clock.day:02d} "
        f"{clock.hour:02d}:{clock.minute:02d}:{clock.second:02d}"
    )


def _log_details(log: LogWindow) -> dict[str, Any]:
    details: dict[str, Any] = {
        "log_count": log.log_count,
        "log_select": log.log_select,
        "log_status": f"0x{log.log_status:04X}",
        "log_status_names": log.log_status_names,
        "is_valid": log.is_valid,
    }
    if log.is_valid and log.clock is not None:
        details.update(
            {
                "pump_id": log.pump_id,
                "clock": _format_clock(log.clock),
                "sequence": log.sequence,
                "amount": log.amount,
                "liters": log.liters,
                "unit_price": log.unit_price,
                "total_liters": log.total_liters,
                "checksum": f"0x{log.checksum:08X}",
            }
        )
    return details
