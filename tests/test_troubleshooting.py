from app.capture import RawFrameRecord
from app.exceptions import (
    ModbusCrcError,
    ModbusExceptionResponse,
    ModbusFrameError,
    ModbusTimeoutError,
)
from app.troubleshooting import diagnose_capture, diagnose_exception


def _hint_text(hints) -> str:
    parts: list[str] = []
    for hint in hints:
        parts.extend([hint.title, hint.explanation, " ".join(hint.suggested_actions)])
    return " ".join(parts).lower()


def _record(
    direction: str,
    slave_id: int | None,
    function_code: int | None,
    frame_len: int,
    crc_valid: bool | None = None,
    note: str | None = None,
) -> RawFrameRecord:
    return RawFrameRecord(
        timestamp="2026-06-11 10:22:01.123",
        direction=direction,
        port="COM5",
        slave_id=slave_id,
        function_code=function_code,
        frame_hex="01 03" if frame_len else "",
        frame_len=frame_len,
        crc_valid=crc_valid,
        note=note,
    )


def test_timeout_hint_mentions_hardware_checks() -> None:
    text = _hint_text(diagnose_exception(ModbusTimeoutError("timeout")))

    assert "slave id" in text
    assert "tx/rx" in text
    assert "gnd" in text
    assert "9600 8n1" in text


def test_crc_hint_mentions_noise_serial_config_and_partial_frame() -> None:
    text = _hint_text(diagnose_exception(ModbusCrcError("bad crc")))

    assert "noise" in text
    assert "baudrate" in text
    assert "partial" in text


def test_modbus_exception_illegal_address_hint() -> None:
    text = _hint_text(diagnose_exception(ModbusExceptionResponse(1, 0x03, 0x02)))

    assert "illegal data address" in text
    assert "register address" in text


def test_frame_error_hint_mentions_malformed_response() -> None:
    text = _hint_text(diagnose_exception(ModbusFrameError("bad frame")))

    assert "malformed" in text
    assert "unexpected" in text


def test_generic_exception_hint() -> None:
    hints = diagnose_exception(Exception("boom"))

    assert hints[0].severity == "ERROR"
    assert "boom" in hints[0].explanation


def test_capture_diagnosis_tx_only_no_rx() -> None:
    hints = diagnose_capture([_record("TX", 1, 0x03, 8)])

    assert "no rx" in _hint_text(hints)


def test_capture_diagnosis_invalid_crc() -> None:
    hints = diagnose_capture([_record("RX", 1, 0x03, 8, crc_valid=False)])

    assert "invalid crc" in _hint_text(hints)


def test_capture_diagnosis_exception_response() -> None:
    hints = diagnose_capture([_record("RX", 1, 0x83, 5, crc_valid=True)])

    assert "exception response" in _hint_text(hints)


def test_capture_diagnosis_slave_id_mismatch() -> None:
    hints = diagnose_capture(
        [
            _record("TX", 1, 0x03, 8),
            _record("RX", 2, 0x03, 8, crc_valid=True),
        ]
    )

    assert "slave id differs" in _hint_text(hints)
