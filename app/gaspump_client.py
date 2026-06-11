"""Thin high-level client for the supported gas pump Modbus operations."""

from datetime import datetime

from app.config import DEFAULT_SLAVE_ID
from app.decoders import (
    ConfigStatus,
    FailEvent,
    LiveData,
    LogWindow,
    PumpClock,
    QuickStatus,
    SensorSnapshot,
    decode_clock_registers,
    decode_config_status,
    decode_fail_event,
    decode_live_data,
    decode_log_window,
    decode_quick_status,
    decode_sensor_snapshot,
    datetime_to_pump_clock,
    encode_clock_registers,
    u32_from_registers,
)
from app.modbus_rtu import (
    READ_HOLDING_REGISTERS,
    READ_INPUT_REGISTERS,
    build_read_request,
    build_write_single_register_request,
    parse_read_response,
    parse_write_single_register_response,
)
from app.register_map import (
    CLOCK_COUNT,
    CLOCK_START,
    CLOCK_DAY_HOUR,
    CLOCK_MINUTE_SECOND,
    CLOCK_YEAR_MONTH,
    CONFIG_STATUS_COUNT,
    CONFIG_STATUS_START,
    FAIL_EVENT_COUNT,
    FAIL_EVENT_START,
    LIVE_DATA_COUNT,
    LIVE_DATA_START,
    LOG_COUNT_HI,
    LOG_SELECT,
    LOG_WINDOW_COUNT,
    LOG_WINDOW_START,
    NOZZLE_STATUS,
    QUICK_STATUS_COUNT,
    QUICK_STATUS_START,
    SENSOR_COUNT,
    SENSOR_START,
)
from app.serial_transport import SerialTransport


class GasPumpModbusClient:
    """Convenience wrapper around raw Modbus request/response helpers."""

    def __init__(self, transport: SerialTransport, slave_id: int = DEFAULT_SLAVE_ID):
        self.transport = transport
        self.slave_id = slave_id

    def read_holding_registers(self, start_address: int, quantity: int) -> list[int]:
        """Read holding registers with function code 0x03."""
        request = build_read_request(
            self.slave_id,
            READ_HOLDING_REGISTERS,
            start_address,
            quantity,
        )
        response = self.transport.transceive(request)
        return parse_read_response(response, self.slave_id, READ_HOLDING_REGISTERS)

    def read_input_registers(self, start_address: int, quantity: int) -> list[int]:
        """Read input registers with function code 0x04."""
        request = build_read_request(
            self.slave_id,
            READ_INPUT_REGISTERS,
            start_address,
            quantity,
        )
        response = self.transport.transceive(request)
        return parse_read_response(response, self.slave_id, READ_INPUT_REGISTERS)

    def write_single_register(self, register_address: int, value: int) -> bool:
        """Write a single holding register with function code 0x06."""
        request = build_write_single_register_request(
            self.slave_id,
            register_address,
            value,
        )
        response = self.transport.transceive(request, expected_min_length=8)
        return parse_write_single_register_response(
            response,
            self.slave_id,
            register_address,
            value,
        )

    def read_quick_status(self) -> QuickStatus:
        """Read and decode the quick status block."""
        registers = self.read_holding_registers(QUICK_STATUS_START, QUICK_STATUS_COUNT)
        return decode_quick_status(registers)

    def read_nozzle_status(self) -> int:
        """Read the raw nozzle status register."""
        return self.read_holding_registers(NOZZLE_STATUS, 1)[0]

    def read_sensor_snapshot(self) -> SensorSnapshot:
        """Read and decode the sensor block."""
        registers = self.read_holding_registers(SENSOR_START, SENSOR_COUNT)
        return decode_sensor_snapshot(registers)

    def read_live_data(self) -> LiveData:
        """Read and decode the 32-register live data block."""
        registers = self.read_holding_registers(LIVE_DATA_START, LIVE_DATA_COUNT)
        return decode_live_data(registers)

    def read_clock(self) -> PumpClock:
        """Read and decode the pump clock."""
        registers = self.read_holding_registers(CLOCK_START, CLOCK_COUNT)
        return decode_clock_registers(registers)

    def set_clock(self, clock: PumpClock) -> bool:
        """Write the three packed pump clock registers in firmware commit order."""
        values = encode_clock_registers(clock)
        if not self.write_single_register(CLOCK_YEAR_MONTH, values[0]):
            return False
        if not self.write_single_register(CLOCK_DAY_HOUR, values[1]):
            return False
        return self.write_single_register(CLOCK_MINUTE_SECOND, values[2])

    def set_clock_from_datetime(self, value: datetime) -> bool:
        """Set the pump clock from a Python datetime."""
        return self.set_clock(datetime_to_pump_clock(value))

    def set_clock_now(self) -> bool:
        """Set the pump clock from the local system time."""
        return self.set_clock_from_datetime(datetime.now())

    def read_fail_event(self) -> FailEvent:
        """Read and decode the last fail event."""
        registers = self.read_holding_registers(FAIL_EVENT_START, FAIL_EVENT_COUNT)
        return decode_fail_event(registers)

    def read_config_status(self) -> ConfigStatus:
        """Read and decode the configuration status register."""
        registers = self.read_holding_registers(CONFIG_STATUS_START, CONFIG_STATUS_COUNT)
        return decode_config_status(registers)

    def read_log_count(self) -> int:
        """Read the EEPROM log count as an unsigned 32-bit value."""
        registers = self.read_holding_registers(LOG_COUNT_HI, 2)
        return u32_from_registers(registers[0], registers[1])

    def select_log(self, index: int) -> bool:
        """Select a log index in the firmware log window."""
        return self.write_single_register(LOG_SELECT, index)

    def read_log_window(self) -> LogWindow:
        """Read and decode the full EEPROM log window."""
        registers = self.read_holding_registers(LOG_WINDOW_START, LOG_WINDOW_COUNT)
        return decode_log_window(registers)

    def read_log(self, index: int) -> LogWindow:
        """Select and read a log window entry by index."""
        self.read_log_count()
        self.select_log(index)
        return self.read_log_window()

    def read_all_logs(
        self,
        limit: int | None = None,
        include_invalid: bool = False,
    ) -> list[LogWindow]:
        """Read valid log entries, optionally including invalid selections."""
        log_count = self.read_log_count()
        if log_count == 0:
            return []
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative or None")

        count_to_read = log_count if limit is None else min(log_count, limit)
        logs: list[LogWindow] = []
        for index in range(count_to_read):
            try:
                log = self.read_log(index)
            except Exception as exc:
                if getattr(self.transport, "debug", False):
                    print(f"Warning: failed to read log index {index}: {exc}")
                continue
            if log.is_valid or include_invalid:
                logs.append(log)
        return logs

    def ping(self) -> QuickStatus:
        """Confirm the device responds by reading quick status."""
        return self.read_quick_status()
