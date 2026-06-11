from datetime import datetime

from app.decoders import (
    ConfigStatus,
    FailEvent,
    HotkeyPreset,
    LiveData,
    LogWindow,
    PumpClock,
    QuickStatus,
    SensorSnapshot,
)
from app.exceptions import ModbusExceptionResponse
from app.test_runner import FAIL, PASS, SKIP, WARN, GasPumpTestRunner


class FakeClient:
    def __init__(
        self,
        protocol_version: int = 7,
        nozzle_status: int = 0,
        log_count: int = 1,
        valid_log: bool = True,
    ):
        year = datetime.now().year
        self.quick_status = QuickStatus(
            protocol_version=protocol_version,
            slave_address=1,
            status_flags=0x0004,
            status_flag_names=["storage_ready"],
            pump_mode=0,
            key_mode=0,
            screen=0,
            selected_field=0,
            nozzle_status=nozzle_status,
            nozzle_status_text=(
                "nozzle placed / idle"
                if nozzle_status == 0
                else f"unknown nozzle status {nozzle_status}"
            ),
        )
        self.live_data = LiveData(
            current_amount=12345,
            current_liters_x1000=536,
            current_liters=0.536,
            unit_price=23000,
            target_amount=0,
            target_liters_x1000=0,
            target_liters=0.0,
            daily_amount=100000,
            daily_liters_x1000=4350,
            daily_liters=4.35,
            total_liters_x1000=102536,
            total_liters=102.536,
            hotkeys={
                "F1": HotkeyPreset(10000, 1000, 1.0),
                "F2": HotkeyPreset(20000, 2000, 2.0),
                "F3": HotkeyPreset(50000, 5000, 5.0),
                "F4": HotkeyPreset(100000, 10000, 10.0),
            },
            raw_registers=[0] * 32,
        )
        self.sensor = SensorSnapshot(
            sensor_status=0x0001,
            ambient_valid=True,
            mcu_temp_c=25.32,
            ambient_temp_c=30.02,
            humidity_percent=65.5,
        )
        self.clock = PumpClock(year, 4, 24, 15, 30, 45)
        self.fail_event = FailEvent(0x0000, "NONE", 0)
        self.log_count = log_count
        self.latest_log = LogWindow(
            log_count=log_count,
            log_select=0,
            log_status=0x0007 if valid_log else 0x0001,
            log_status_names=["has_log", "select_valid", "payload_loaded"]
            if valid_log
            else ["has_log"],
            is_valid=valid_log,
            pump_id=1 if valid_log else 0,
            clock=self.clock if valid_log else None,
            sequence=7 if valid_log else 0,
            amount=12345 if valid_log else 0,
            liters_x1000=536 if valid_log else 0,
            liters=0.536 if valid_log else 0.0,
            unit_price=23000 if valid_log else 0,
            total_liters_x1000=100536 if valid_log else 0,
            total_liters=100.536 if valid_log else 0.0,
            checksum=0x12345678 if valid_log else 0,
        )
        self.config_status = ConfigStatus(value=0, names=[], unlocked=False)

    def read_quick_status(self):
        return self.quick_status

    def read_live_data(self):
        return self.live_data

    def read_sensor_snapshot(self):
        return self.sensor

    def read_clock(self):
        return self.clock

    def read_fail_event(self):
        return self.fail_event

    def read_log_count(self):
        return self.log_count

    def select_log(self, index):
        return index == 0

    def read_log_window(self):
        return self.latest_log

    def read_all_logs(self, limit=None, include_invalid=False):
        if self.log_count == 0:
            return []
        count = self.log_count if limit is None else min(self.log_count, limit)
        logs = [self.latest_log for _ in range(count)]
        return logs if include_invalid else [log for log in logs if log.is_valid]

    def read_config_status(self):
        return self.config_status

    def read_holding_registers(self, start, count):
        if start == 0x7FFF and count == 1:
            raise ModbusExceptionResponse(1, 0x03, 0x02)
        return [0] * count


def _run(fake_client: FakeClient):
    return GasPumpTestRunner(
        client=fake_client,
        port="COM5",
        baudrate=9600,
        slave_id=1,
    ).run_all()


def _result(report, test_id: str):
    return next(result for result in report.results if result.id == test_id)


def test_all_pass_fake_device() -> None:
    report = _run(FakeClient())

    assert report.summary[FAIL] == 0
    assert report.overall_status == PASS
    assert report.summary[PASS] > 0


def test_protocol_mismatch_becomes_warn() -> None:
    report = _run(FakeClient(protocol_version=8))

    assert _result(report, "T03").status == WARN
    assert report.overall_status == PASS


def test_invalid_nozzle_becomes_fail() -> None:
    report = _run(FakeClient(nozzle_status=9))

    assert _result(report, "T06").status == FAIL
    assert report.overall_status == FAIL


def test_no_logs_skip_log_dependent_steps() -> None:
    report = _run(FakeClient(log_count=0))

    assert _result(report, "T14").status == SKIP
    assert _result(report, "T15").status == SKIP
    assert _result(report, "T16").status == SKIP
    assert report.overall_status == PASS


def test_illegal_address_exception_accepted() -> None:
    report = _run(FakeClient())

    assert _result(report, "T17").status == PASS
