"""Troubleshooting hints for Modbus RTU hardware communication failures."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.capture import RawFrameRecord
from app.exceptions import (
    ModbusCrcError,
    ModbusExceptionResponse,
    ModbusFrameError,
    ModbusTimeoutError,
    SerialTransportError,
)


@dataclass
class DiagnosticHint:
    severity: str
    title: str
    explanation: str
    suggested_actions: list[str]


def hints_to_dicts(hints: list[DiagnosticHint]) -> list[dict[str, Any]]:
    return [asdict(hint) for hint in hints]


def diagnose_exception(exc: Exception) -> list[DiagnosticHint]:
    if isinstance(exc, SerialTransportError):
        return [
            DiagnosticHint(
                severity="ERROR",
                title="Serial port problem",
                explanation="The serial port could not be opened or used.",
                suggested_actions=[
                    "Check COM port name.",
                    "Close Serial Monitor, PuTTY, TeraTerm, Modbus Poll, or any app using the port.",
                    "Check USB-UART driver.",
                    "Replug USB-UART adapter.",
                ],
            )
        ]
    if isinstance(exc, ModbusTimeoutError):
        return [
            DiagnosticHint(
                severity="ERROR",
                title="No response from device",
                explanation="A Modbus request was transmitted, but no response was received before timeout.",
                suggested_actions=[
                    "Check slave id.",
                    "Check that device is powered.",
                    "Check TX/RX wiring.",
                    "PC TX should go to STM32 PC11/UART4_RX.",
                    "PC RX should go to STM32 PC10/UART4_TX.",
                    "Check common GND.",
                    "Check baudrate is 9600 8N1.",
                    "Check that you are connected to UART4 data channel, not a debug UART.",
                    "If using RS485, check A/B polarity.",
                    "If using RS485, check DE/RE direction-control circuit.",
                ],
            )
        ]
    if isinstance(exc, ModbusCrcError):
        return [
            DiagnosticHint(
                severity="ERROR",
                title="CRC mismatch",
                explanation="A response was received, but its Modbus CRC did not match the frame contents.",
                suggested_actions=[
                    "Check noise or long wires.",
                    "Check baudrate/parity/stopbits.",
                    "Increase timeout if frame may be partially read.",
                    "Check RS485 A/B wiring.",
                    "Ensure only one slave responds to the request.",
                    "Ensure debug ASCII text is not mixed into the Modbus binary stream.",
                ],
            )
        ]
    if isinstance(exc, ModbusExceptionResponse):
        return [_diagnose_modbus_exception(exc)]
    if isinstance(exc, ModbusFrameError):
        return [
            DiagnosticHint(
                severity="ERROR",
                title="Malformed or unexpected Modbus response",
                explanation="The response frame was malformed or did not match the request.",
                suggested_actions=[
                    "Check timeout.",
                    "Check serial config.",
                    "Check whether firmware prints debug text on the same UART.",
                    "Check that response slave id and function code match the request.",
                    "Capture raw frame for analysis.",
                ],
            )
        ]
    return [
        DiagnosticHint(
            severity="ERROR",
            title=f"Unexpected error: {type(exc).__name__}",
            explanation=str(exc),
            suggested_actions=["Review the error message and capture raw frames if hardware communication was involved."],
        )
    ]


def diagnose_capture(records: list[RawFrameRecord]) -> list[DiagnosticHint]:
    hints: list[DiagnosticHint] = []
    tx_records = [record for record in records if record.direction == "TX"]
    rx_records = [record for record in records if record.direction == "RX"]
    nonempty_rx = [record for record in rx_records if record.frame_len > 0]

    if tx_records and not nonempty_rx:
        hints.append(
            DiagnosticHint(
                severity="ERROR",
                title="TX sent but no RX received",
                explanation="The PC transmitted Modbus request frames, but no response bytes were captured.",
                suggested_actions=[
                    "Check slave id.",
                    "Check TX/RX wiring.",
                    "Check common GND.",
                    "Check that the device is connected to UART4, not a debug UART.",
                ],
            )
        )

    if any(record.crc_valid is False for record in rx_records):
        hints.append(
            DiagnosticHint(
                severity="ERROR",
                title="Captured RX frame has invalid CRC",
                explanation="At least one received frame failed CRC validation.",
                suggested_actions=[
                    "Check noise or long wires.",
                    "Check baudrate/parity/stopbits.",
                    "Increase timeout if a response may be partially read.",
                    "Ensure debug ASCII text is not mixed into the Modbus binary stream.",
                ],
            )
        )

    for index, record in enumerate(records):
        if record.direction != "RX" or record.frame_len == 0:
            continue
        previous_tx = _previous_tx(records, index)
        if (
            previous_tx is not None
            and previous_tx.slave_id is not None
            and record.slave_id is not None
            and record.slave_id != previous_tx.slave_id
        ):
            hints.append(
                DiagnosticHint(
                    severity="WARN",
                    title="Response slave id differs from request",
                    explanation=(
                        f"Request slave id was {previous_tx.slave_id}, "
                        f"but response slave id was {record.slave_id}."
                    ),
                    suggested_actions=[
                        "Check the configured slave id.",
                        "Ensure only one slave responds on the bus.",
                    ],
                )
            )
            break

    if any(
        record.direction == "RX"
        and record.function_code is not None
        and record.function_code & 0x80
        for record in rx_records
    ):
        hints.append(
            DiagnosticHint(
                severity="WARN",
                title="Device returned Modbus exception response",
                explanation="A captured response has the Modbus exception bit set in the function code.",
                suggested_actions=[
                    "Check function code, register address, register count, or written value.",
                    "Decode the exception code from the raw frame.",
                ],
            )
        )

    timeout_count = sum(
        1
        for record in rx_records
        if record.frame_len == 0 and record.note and "timeout" in record.note.lower()
    )
    if timeout_count >= 2:
        hints.append(
            DiagnosticHint(
                severity="ERROR",
                title="Repeated timeouts detected",
                explanation=f"{timeout_count} captured requests ended with timeout/no response.",
                suggested_actions=[
                    "Check wiring and common GND.",
                    "Check slave id and baudrate.",
                    "Check UART4 connection and RS485 direction control if used.",
                ],
            )
        )
    return hints


def _diagnose_modbus_exception(exc: ModbusExceptionResponse) -> DiagnosticHint:
    names = {
        0x01: "Illegal Function",
        0x02: "Illegal Data Address",
        0x03: "Illegal Data Value",
        0x04: "Slave Device Failure",
    }
    actions = {
        0x01: [
            "Check function code.",
            "Firmware supports only 0x03, 0x04, 0x06.",
        ],
        0x02: [
            "Check register address.",
            "Check requested register count.",
        ],
        0x03: [
            "Check register value range.",
            "If writing clock, check datetime validity.",
            "If writing config, check password/unlock state.",
        ],
        0x04: [
            "Check firmware/device internal state.",
            "Check device logs/fail event registers.",
        ],
    }
    message = names.get(exc.exception_code, f"Unknown exception code 0x{exc.exception_code:02X}")
    return DiagnosticHint(
        severity="ERROR",
        title=f"Modbus exception response: {message}",
        explanation=(
            f"Slave {exc.slave_id} returned exception 0x{exc.exception_code:02X} "
            f"for function 0x{exc.function_code:02X}."
        ),
        suggested_actions=actions.get(
            exc.exception_code,
            ["Check firmware documentation for this exception code."],
        ),
    )


def _previous_tx(records: list[RawFrameRecord], index: int) -> RawFrameRecord | None:
    for candidate in reversed(records[:index]):
        if candidate.direction == "TX":
            return candidate
    return None
