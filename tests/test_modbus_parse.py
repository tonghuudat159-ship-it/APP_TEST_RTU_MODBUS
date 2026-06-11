import pytest

from app.exceptions import (
    ModbusCrcError,
    ModbusExceptionResponse,
    ModbusFrameError,
)
from app.modbus_rtu import (
    parse_exception_response,
    parse_read_response,
    parse_write_single_register_response,
)


def test_parse_valid_read_response() -> None:
    response = bytes.fromhex("01 03 04 00 00 00 07 BB F1")

    assert parse_read_response(response, 1, 0x03) == [0x0000, 0x0007]


def test_parse_valid_write_response() -> None:
    response = bytes.fromhex("01 06 00 2A 00 00 A8 02")

    assert parse_write_single_register_response(response, 1, 0x002A, 0x0000) is True


def test_parse_exception_response_raises() -> None:
    response = bytes.fromhex("01 83 02 C0 F1")

    with pytest.raises(ModbusExceptionResponse) as exc_info:
        parse_exception_response(response)

    assert exc_info.value.slave_id == 1
    assert exc_info.value.function_code == 0x03
    assert exc_info.value.exception_code == 0x02
    assert "Illegal Data Address" in str(exc_info.value)


def test_crc_mismatch_raises() -> None:
    response = bytes.fromhex("01 03 04 00 00 00 07 00 00")

    with pytest.raises(ModbusCrcError):
        parse_read_response(response, 1, 0x03)


def test_malformed_short_frame_raises() -> None:
    with pytest.raises(ModbusFrameError):
        parse_read_response(bytes.fromhex("01 03 04"), 1, 0x03)


def test_odd_byte_count_raises() -> None:
    response = bytes.fromhex("01 03 03 00 00 00 45 8E")

    with pytest.raises(ModbusFrameError):
        parse_read_response(response, 1, 0x03)
