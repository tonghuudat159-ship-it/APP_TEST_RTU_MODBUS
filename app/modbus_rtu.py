"""Manual Modbus RTU frame helpers.

This module intentionally does not depend on a high-level Modbus library. It
builds request frames, calculates standard Modbus RTU CRC16 values, and parses
the small response set needed by the CLI foundation.
"""

from app.exceptions import (
    ModbusCrcError,
    ModbusExceptionResponse,
    ModbusFrameError,
)

READ_HOLDING_REGISTERS = 0x03
READ_INPUT_REGISTERS = 0x04
WRITE_SINGLE_REGISTER = 0x06

_MIN_SLAVE_ID = 1
_MAX_SLAVE_ID = 247
_MAX_READ_QUANTITY = 125


def crc16_modbus(data: bytes) -> int:
    """Return the standard Modbus RTU CRC16 for *data*.

    The returned integer is in normal numeric form. When appended to a frame,
    the low byte must be transmitted before the high byte.
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
            crc &= 0xFFFF
    return crc


def append_crc(frame_without_crc: bytes) -> bytes:
    """Append Modbus RTU CRC bytes in CRC_LO, CRC_HI order."""
    crc = crc16_modbus(frame_without_crc)
    return frame_without_crc + bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def verify_crc(frame: bytes) -> bool:
    """Return True if *frame* contains a valid trailing Modbus RTU CRC."""
    if len(frame) < 3:
        return False
    expected = crc16_modbus(frame[:-2])
    received = frame[-2] | (frame[-1] << 8)
    return expected == received


def bytes_to_hex(data: bytes) -> str:
    """Format bytes as uppercase two-digit hex separated by spaces."""
    return " ".join(f"{byte:02X}" for byte in data)


def build_read_request(
    slave_id: int,
    function_code: int,
    start_address: int,
    quantity: int,
) -> bytes:
    """Build a read holding/input registers request frame."""
    _validate_slave_id(slave_id)
    if function_code not in (READ_HOLDING_REGISTERS, READ_INPUT_REGISTERS):
        raise ValueError("read function_code must be 0x03 or 0x04")
    _validate_register_value(start_address, "start_address")
    if not 1 <= quantity <= _MAX_READ_QUANTITY:
        raise ValueError("quantity must be in range 1..125")

    payload = bytes(
        (
            slave_id,
            function_code,
            (start_address >> 8) & 0xFF,
            start_address & 0xFF,
            (quantity >> 8) & 0xFF,
            quantity & 0xFF,
        )
    )
    return append_crc(payload)


def build_write_single_register_request(
    slave_id: int,
    register_address: int,
    value: int,
) -> bytes:
    """Build a write single holding register request frame."""
    _validate_slave_id(slave_id)
    _validate_register_value(register_address, "register_address")
    _validate_register_value(value, "value")

    payload = bytes(
        (
            slave_id,
            WRITE_SINGLE_REGISTER,
            (register_address >> 8) & 0xFF,
            register_address & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF,
        )
    )
    return append_crc(payload)


def parse_read_response(
    response: bytes,
    expected_slave_id: int,
    expected_function_code: int,
) -> list[int]:
    """Parse a read register response into a list of 16-bit register values."""
    _validate_slave_id(expected_slave_id)
    if expected_function_code not in (READ_HOLDING_REGISTERS, READ_INPUT_REGISTERS):
        raise ValueError("expected_function_code must be 0x03 or 0x04")

    _ensure_min_frame_length(response, 5)
    parse_exception_response(response)
    _ensure_crc(response)

    slave_id = response[0]
    function_code = response[1]
    byte_count = response[2]
    data = response[3:-2]

    if slave_id != expected_slave_id:
        raise ModbusFrameError(
            f"unexpected slave id {slave_id}, expected {expected_slave_id}"
        )
    if function_code != expected_function_code:
        raise ModbusFrameError(
            f"unexpected function code 0x{function_code:02X}, "
            f"expected 0x{expected_function_code:02X}"
        )
    if byte_count % 2 != 0:
        raise ModbusFrameError("read response byte_count must be even")
    if byte_count != len(data):
        raise ModbusFrameError(
            f"byte_count {byte_count} does not match data length {len(data)}"
        )

    return [
        (data[index] << 8) | data[index + 1]
        for index in range(0, len(data), 2)
    ]


def parse_write_single_register_response(
    response: bytes,
    expected_slave_id: int,
    expected_register_address: int,
    expected_value: int,
) -> bool:
    """Validate a write single register response echo frame."""
    _validate_slave_id(expected_slave_id)
    _validate_register_value(expected_register_address, "expected_register_address")
    _validate_register_value(expected_value, "expected_value")

    _ensure_min_frame_length(response, 5)
    parse_exception_response(response)
    if len(response) != 8:
        raise ModbusFrameError("write single register response must be 8 bytes")
    _ensure_crc(response)

    slave_id = response[0]
    function_code = response[1]
    register_address = (response[2] << 8) | response[3]
    value = (response[4] << 8) | response[5]

    if slave_id != expected_slave_id:
        raise ModbusFrameError(
            f"unexpected slave id {slave_id}, expected {expected_slave_id}"
        )
    if function_code != WRITE_SINGLE_REGISTER:
        raise ModbusFrameError(
            f"unexpected function code 0x{function_code:02X}, expected 0x06"
        )
    if register_address != expected_register_address:
        raise ModbusFrameError(
            f"unexpected register address 0x{register_address:04X}, "
            f"expected 0x{expected_register_address:04X}"
        )
    if value != expected_value:
        raise ModbusFrameError(
            f"unexpected value 0x{value:04X}, expected 0x{expected_value:04X}"
        )
    return True


def parse_exception_response(response: bytes) -> None:
    """Raise ModbusExceptionResponse if *response* is an exception frame."""
    _ensure_min_frame_length(response, 3)
    function_code = response[1]
    if not function_code & 0x80:
        return

    if len(response) != 5:
        raise ModbusFrameError("Modbus exception response must be 5 bytes")
    _ensure_crc(response)
    raise ModbusExceptionResponse(
        slave_id=response[0],
        function_code=function_code & 0x7F,
        exception_code=response[2],
    )


def _ensure_crc(frame: bytes) -> None:
    if not verify_crc(frame):
        raise ModbusCrcError(f"CRC mismatch for frame: {bytes_to_hex(frame)}")


def _ensure_min_frame_length(frame: bytes, minimum: int) -> None:
    if len(frame) < minimum:
        raise ModbusFrameError(
            f"frame too short: expected at least {minimum} bytes, got {len(frame)}"
        )


def _validate_slave_id(slave_id: int) -> None:
    if not _MIN_SLAVE_ID <= slave_id <= _MAX_SLAVE_ID:
        raise ValueError("slave_id must be in range 1..247")


def _validate_register_value(value: int, name: str) -> None:
    if not 0 <= value <= 0xFFFF:
        raise ValueError(f"{name} must be in range 0..0xFFFF")
