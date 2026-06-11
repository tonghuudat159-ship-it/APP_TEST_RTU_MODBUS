import pytest

from app.decoders import (
    decode_clock_registers,
    decode_fail_event,
    decode_live_data,
    decode_quick_status,
    decode_sensor_snapshot,
)
from app.exceptions import ModbusExceptionResponse
from app.modbus_rtu import append_crc, build_read_request, parse_exception_response, parse_read_response
from app.register_map import (
    CLOCK_COUNT,
    CLOCK_START,
    FAIL_EVENT_COUNT,
    FAIL_EVENT_START,
    LIVE_DATA_COUNT,
    LIVE_DATA_START,
    QUICK_STATUS_COUNT,
    QUICK_STATUS_START,
    SENSOR_COUNT,
    SENSOR_START,
)
from app.simulator import GasPumpSimulator


def _read(simulator: GasPumpSimulator, start: int, count: int) -> list[int]:
    response = simulator.handle_request(build_read_request(1, 0x03, start, count))
    assert response is not None
    return parse_read_response(response, 1, 0x03, expected_quantity=count)


def test_read_quick_status() -> None:
    status = decode_quick_status(_read(GasPumpSimulator(), QUICK_STATUS_START, QUICK_STATUS_COUNT))

    assert status.protocol_version == 7
    assert status.slave_address == 1


def test_read_live_data_defaults() -> None:
    live = decode_live_data(_read(GasPumpSimulator(), LIVE_DATA_START, LIVE_DATA_COUNT))

    assert live.current_amount == 12345
    assert live.unit_price == 23000
    assert live.hotkeys["F1"].amount == 10000


def test_sensor_profiles() -> None:
    normal = decode_sensor_snapshot(_read(GasPumpSimulator(), SENSOR_START, SENSOR_COUNT))
    invalid = decode_sensor_snapshot(_read(GasPumpSimulator(profile="sensor-invalid"), SENSOR_START, SENSOR_COUNT))

    assert normal.ambient_valid is True
    assert invalid.ambient_valid is False


def test_read_clock_default() -> None:
    clock = decode_clock_registers(_read(GasPumpSimulator(), CLOCK_START, CLOCK_COUNT))

    assert (clock.year, clock.month, clock.day, clock.hour, clock.minute, clock.second) == (
        2026,
        4,
        24,
        15,
        30,
        45,
    )


def test_fail_event_profile() -> None:
    event = decode_fail_event(_read(GasPumpSimulator(profile="fail-event"), FAIL_EVENT_START, FAIL_EVENT_COUNT))

    assert event.code == 0x0402
    assert event.sequence == 9


def test_bad_protocol_profile() -> None:
    status = decode_quick_status(
        _read(GasPumpSimulator(profile="bad-protocol"), QUICK_STATUS_START, QUICK_STATUS_COUNT)
    )

    assert status.protocol_version == 8


def test_no_logs_profile_reports_zero_logs() -> None:
    registers = _read(GasPumpSimulator(profile="no-logs"), 0x0028, 2)

    assert registers == [0, 0]


def test_wrong_slave_returns_none() -> None:
    request = build_read_request(2, 0x03, QUICK_STATUS_START, QUICK_STATUS_COUNT)

    assert GasPumpSimulator(slave_id=1).handle_request(request) is None


def test_unsupported_function_returns_exception() -> None:
    response = GasPumpSimulator().handle_request(append_crc(bytes.fromhex("01 10 00 00 00 01")))
    assert response is not None

    with pytest.raises(ModbusExceptionResponse) as exc_info:
        parse_exception_response(response)

    assert exc_info.value.exception_code == 0x01


def test_invalid_address_returns_exception() -> None:
    response = GasPumpSimulator().handle_request(build_read_request(1, 0x03, 0x7FFF, 1))
    assert response is not None

    with pytest.raises(ModbusExceptionResponse) as exc_info:
        parse_exception_response(response)

    assert exc_info.value.exception_code == 0x02
