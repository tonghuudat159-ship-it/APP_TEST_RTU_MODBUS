"""Custom exceptions for Modbus RTU and serial transport failures."""

MODBUS_EXCEPTION_MESSAGES = {
    0x01: "Illegal Function",
    0x02: "Illegal Data Address",
    0x03: "Illegal Data Value",
    0x04: "Slave Device Failure",
}


class ModbusError(Exception):
    """Base class for Modbus protocol errors."""


class ModbusTimeoutError(ModbusError):
    """Raised when no Modbus response is received before timeout."""


class ModbusCrcError(ModbusError):
    """Raised when a frame has an invalid Modbus CRC."""


class ModbusExceptionResponse(ModbusError):
    """Raised when the slave returns a Modbus exception response."""

    def __init__(self, slave_id: int, function_code: int, exception_code: int):
        self.slave_id = slave_id
        self.function_code = function_code
        self.exception_code = exception_code
        self.exception_message = MODBUS_EXCEPTION_MESSAGES.get(
            exception_code,
            f"Unknown exception code 0x{exception_code:02X}",
        )
        super().__init__(
            f"Modbus exception from slave {slave_id}: "
            f"function 0x{function_code:02X}, "
            f"exception 0x{exception_code:02X} ({self.exception_message})"
        )


class ModbusFrameError(ModbusError):
    """Raised when a Modbus frame is malformed or unexpected."""


class SerialTransportError(Exception):
    """Raised when serial transport setup or I/O fails."""
