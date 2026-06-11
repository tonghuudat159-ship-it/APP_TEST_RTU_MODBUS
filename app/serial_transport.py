"""Raw serial transport for Modbus RTU frames."""

from __future__ import annotations

import time
from datetime import datetime

from app.capture import (
    RawCaptureBuffer,
    RawFrameRecord,
    infer_function_code,
    infer_slave_id,
)
from app.config import (
    DEFAULT_BAUDRATE,
    DEFAULT_BYTESIZE,
    DEFAULT_FRAME_GAP_SECONDS,
    DEFAULT_PARITY,
    DEFAULT_STOPBITS,
    DEFAULT_TIMEOUT,
)
from app.exceptions import ModbusTimeoutError, SerialTransportError
from app.modbus_rtu import bytes_to_hex, verify_crc

try:
    import serial
    from serial import SerialException
except ImportError:  # pragma: no cover - exercised only without dependency
    serial = None

    class SerialException(Exception):
        """Fallback when pyserial is not installed."""


class SerialTransport:
    """Simple pyserial wrapper that sends and receives raw Modbus RTU frames."""

    def __init__(
        self,
        port: str,
        baudrate: int = DEFAULT_BAUDRATE,
        bytesize: int = DEFAULT_BYTESIZE,
        parity: str = DEFAULT_PARITY,
        stopbits: int = DEFAULT_STOPBITS,
        timeout: float = DEFAULT_TIMEOUT,
        frame_gap_seconds: float = DEFAULT_FRAME_GAP_SECONDS,
        debug: bool = False,
        capture: RawCaptureBuffer | None = None,
    ):
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self.frame_gap_seconds = frame_gap_seconds
        self.debug = debug
        self.capture = capture
        self._serial = None

    def open(self) -> None:
        """Open the configured serial port."""
        if serial is None:
            raise SerialTransportError("pyserial is required for serial transport")
        if self.is_open():
            return
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=self.timeout,
                write_timeout=self.timeout,
            )
        except SerialException as exc:
            raise SerialTransportError(f"failed to open serial port {self.port}: {exc}") from exc

    def close(self) -> None:
        """Close the serial port if it is open."""
        if self._serial is not None:
            try:
                self._serial.close()
            except SerialException as exc:
                raise SerialTransportError(f"failed to close serial port: {exc}") from exc

    def is_open(self) -> bool:
        """Return True when the underlying serial port is open."""
        return bool(self._serial is not None and self._serial.is_open)

    def transceive(self, request: bytes, expected_min_length: int = 5) -> bytes:
        """Send raw bytes and read a raw response until timeout."""
        if not self.is_open():
            self.open()
        assert self._serial is not None

        started = time.perf_counter()
        try:
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            time.sleep(self.frame_gap_seconds)

            if self.debug:
                print(f"TX: {bytes_to_hex(request)}")
            self._capture_frame("TX", request)

            self._serial.write(request)
            self._serial.flush()

            response = bytearray()
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                waiting = self._serial.in_waiting
                if waiting:
                    response.extend(self._serial.read(waiting))
                    deadline = time.monotonic() + self.frame_gap_seconds
                elif len(response) >= expected_min_length:
                    time.sleep(self.frame_gap_seconds)
                    if self._serial.in_waiting == 0:
                        break
                else:
                    chunk = self._serial.read(1)
                    if chunk:
                        response.extend(chunk)
                        deadline = time.monotonic() + self.frame_gap_seconds

            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if self.debug:
                print(f"RX: {bytes_to_hex(bytes(response))}")
                print(f"Elapsed: {elapsed_ms:.1f} ms")

            if not response:
                self._capture_frame(
                    "RX",
                    b"",
                    elapsed_ms=elapsed_ms,
                    crc_valid=None,
                    note="timeout/no response",
                )
                raise ModbusTimeoutError("no response received before timeout")
            response_bytes = bytes(response)
            if len(response_bytes) >= 4:
                crc_valid = verify_crc(response_bytes)
                note = None
            else:
                crc_valid = None
                note = "response too short to validate CRC"
            self._capture_frame(
                "RX",
                response_bytes,
                elapsed_ms=elapsed_ms,
                crc_valid=crc_valid,
                note=note,
            )
            return response_bytes
        except SerialException as exc:
            raise SerialTransportError(f"serial I/O failed: {exc}") from exc

    def _capture_frame(
        self,
        direction: str,
        frame: bytes,
        elapsed_ms: float | None = None,
        crc_valid: bool | None = None,
        note: str | None = None,
    ) -> None:
        if self.capture is None:
            return
        self.capture.add(
            RawFrameRecord(
                timestamp=_timestamp(),
                direction=direction,
                port=self.port,
                slave_id=infer_slave_id(frame),
                function_code=infer_function_code(frame),
                frame_hex=bytes_to_hex(frame),
                frame_len=len(frame),
                elapsed_ms=elapsed_ms,
                crc_valid=crc_valid,
                note=note,
            )
        )


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
