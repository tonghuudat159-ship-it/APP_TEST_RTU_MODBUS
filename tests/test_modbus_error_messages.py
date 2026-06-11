import pytest

from app.exceptions import ModbusCrcError, ModbusFrameError
from app.modbus_rtu import append_crc, parse_read_response


def test_crc_mismatch_message_contains_response_and_crc_values() -> None:
    response = bytes.fromhex("01 03 04 00 00 00 07 00 00")

    with pytest.raises(ModbusCrcError) as exc_info:
        parse_read_response(response, 1, 0x03)

    message = str(exc_info.value)
    assert "01 03 04 00 00 00 07 00 00" in message
    assert "received" in message
    assert "calculated" in message


def test_unexpected_slave_id_message_contains_expected_actual_and_response() -> None:
    response = append_crc(bytes.fromhex("02 03 02 00 07"))

    with pytest.raises(ModbusFrameError) as exc_info:
        parse_read_response(response, 1, 0x03)

    message = str(exc_info.value)
    assert "expected 1" in message
    assert "got 2" in message
    assert "02 03 02 00 07" in message


def test_malformed_frame_message_contains_frame_hex() -> None:
    response = bytes.fromhex("01 03")

    with pytest.raises(ModbusFrameError) as exc_info:
        parse_read_response(response, 1, 0x03)

    assert "01 03" in str(exc_info.value)


def test_expected_quantity_mismatch_message_contains_expected_and_actual() -> None:
    response = bytes.fromhex("01 03 04 00 00 00 07 BB F1")

    with pytest.raises(ModbusFrameError) as exc_info:
        parse_read_response(response, 1, 0x03, expected_quantity=3)

    message = str(exc_info.value)
    assert "expected quantity 3" in message
    assert "actual quantity 2" in message
    assert "01 03 04 00 00 00 07 BB F1" in message
