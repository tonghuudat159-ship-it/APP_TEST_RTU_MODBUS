"""Thin high-level client for the supported gas pump Modbus operations."""

from datetime import datetime

from app.config_models import WriteResult
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
    split_u32,
    u32_from_registers,
    validate_hotkey_name,
    validate_password,
    validate_slave_id,
    validate_u32,
)
from app.exceptions import ModbusError
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
    CONFIG_CLEAR_DAILY,
    CONFIG_CLEAR_DAILY_MAGIC,
    CONFIG_NEW_PASSWORD_HI,
    CONFIG_NEW_PASSWORD_LO,
    CONFIG_STATUS_COUNT,
    CONFIG_STATUS_START,
    CONFIG_UNLOCK_PASSWORD_HI,
    CONFIG_UNLOCK_PASSWORD_LO,
    FAIL_EVENT_COUNT,
    FAIL_EVENT_START,
    HOTKEY_AMOUNT_REGISTERS,
    HOTKEY_LITERS_REGISTERS,
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
    SLAVE_ADDRESS,
    UNIT_PRICE_HI,
    UNIT_PRICE_LO,
)
from app.serial_transport import SerialTransport


class GasPumpModbusClient:
    """Convenience wrapper around raw Modbus request/response helpers."""

    def __init__(self, transport: SerialTransport, slave_id: int = DEFAULT_SLAVE_ID):
        self.transport = transport
        self.slave_id = slave_id
        self.last_log_read_errors: list[dict[str, str]] = []

    def read_holding_registers(self, start_address: int, quantity: int) -> list[int]:
        """Read holding registers with function code 0x03."""
        request = build_read_request(
            self.slave_id,
            READ_HOLDING_REGISTERS,
            start_address,
            quantity,
        )
        response = self.transport.transceive(request)
        return parse_read_response(
            response,
            self.slave_id,
            READ_HOLDING_REGISTERS,
            expected_quantity=quantity,
        )

    def read_input_registers(self, start_address: int, quantity: int) -> list[int]:
        """Read input registers with function code 0x04."""
        request = build_read_request(
            self.slave_id,
            READ_INPUT_REGISTERS,
            start_address,
            quantity,
        )
        response = self.transport.transceive(request)
        return parse_read_response(
            response,
            self.slave_id,
            READ_INPUT_REGISTERS,
            expected_quantity=quantity,
        )

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
        if index < 0:
            raise ValueError(f"Invalid log index {index}; index must be >= 0")
        log_count = self.read_log_count()
        if log_count == 0:
            raise ValueError("No logs available on device")
        if index >= log_count:
            raise ValueError(
                f"Invalid log index {index}; device reports only {log_count} logs, "
                f"valid range is 0..{log_count - 1}"
            )
        self.select_log(index)
        return self.read_log_window()

    def read_all_logs(
        self,
        limit: int | None = None,
        include_invalid: bool = False,
        strict: bool = False,
    ) -> list[LogWindow]:
        """Read valid log entries, optionally including invalid selections."""
        self.last_log_read_errors = []
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
                if strict:
                    raise
                self.last_log_read_errors.append(
                    {
                        "index": str(index),
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )
                if getattr(self.transport, "debug", False):
                    print(f"Warning: failed to read log index {index}: {exc}")
                continue
            if log.is_valid or include_invalid:
                logs.append(log)
        return logs

    def ping(self) -> QuickStatus:
        """Confirm the device responds by reading quick status."""
        return self.read_quick_status()

    def write_u32_register_pair(
        self,
        hi_register: int,
        lo_register: int,
        value: int,
    ) -> bool:
        """Write a uint32 register pair in HI then LO commit order."""
        hi, lo = split_u32(validate_u32(value))
        hi_ok = self.write_single_register(hi_register, hi)
        lo_ok = self.write_single_register(lo_register, lo)
        return hi_ok and lo_ok

    def unlock_config(self, password: int, verify: bool = True) -> ConfigStatus:
        """Unlock protected config writes with a manager password."""
        hi, lo = split_u32(validate_password(password))
        self.write_single_register(CONFIG_UNLOCK_PASSWORD_HI, hi)
        self.write_single_register(CONFIG_UNLOCK_PASSWORD_LO, lo)
        status = self.read_config_status() if verify else ConfigStatus(0, [], False)
        if verify and not status.unlocked:
            raise ModbusError("Config unlock failed; CONFIG_STATUS did not report unlocked")
        return status

    def ensure_config_unlocked(self) -> ConfigStatus:
        """Raise if protected config writes are not currently unlocked."""
        status = self.read_config_status()
        if not status.unlocked:
            raise ModbusError("Configuration is locked; unlock config before writing")
        return status

    def set_unit_price(self, value: int, verify: bool = True) -> WriteResult:
        value = validate_u32(value, "unit price")
        self.ensure_config_unlocked()
        ok = self.write_u32_register_pair(UNIT_PRICE_HI, UNIT_PRICE_LO, value)
        details = {"value": value, "verified": False}
        if verify and ok:
            actual = u32_from_registers(*self.read_holding_registers(UNIT_PRICE_HI, 2))
            details.update({"readback": actual, "verified": actual == value})
            if actual != value:
                return WriteResult(
                    "set_unit_price",
                    False,
                    "Unit price write may have succeeded but verification failed",
                    details,
                )
        return WriteResult("set_unit_price", ok, "Unit price updated" if ok else "Unit price write failed", details)

    def set_slave_address(self, new_slave_id: int, verify: bool = True) -> WriteResult:
        new_slave_id = validate_slave_id(new_slave_id)
        self.ensure_config_unlocked()
        old_slave_id = self.slave_id
        ok = self.write_single_register(SLAVE_ADDRESS, new_slave_id)
        details = {
            "old_slave_id": old_slave_id,
            "new_slave_id": new_slave_id,
            "verified": False,
        }
        if ok:
            self.slave_id = new_slave_id
        if verify and ok:
            try:
                status = self.read_quick_status()
                details.update(
                    {
                        "reported_slave_address": status.slave_address,
                        "verified": status.slave_address == new_slave_id,
                    }
                )
                if status.slave_address != new_slave_id:
                    return WriteResult(
                        "set_slave_address",
                        False,
                        "Slave id write may have succeeded but verification failed",
                        details,
                    )
            except Exception as exc:
                return WriteResult(
                    "set_slave_address",
                    False,
                    f"Slave id write may have succeeded but verification failed: {exc}",
                    details,
                )
        return WriteResult("set_slave_address", ok, "Slave id updated" if ok else "Slave id write failed", details)

    def set_hotkey_amount(
        self,
        hotkey: str,
        amount: int,
        verify: bool = True,
    ) -> WriteResult:
        hotkey = validate_hotkey_name(hotkey)
        amount = validate_u32(amount, "hotkey amount")
        self.ensure_config_unlocked()
        hi_register, lo_register = HOTKEY_AMOUNT_REGISTERS[hotkey]
        ok = self.write_u32_register_pair(hi_register, lo_register, amount)
        details = {"hotkey": hotkey, "amount": amount, "verified": False}
        if verify and ok:
            actual = self.read_live_data().hotkeys[hotkey].amount
            details.update({"readback": actual, "verified": actual == amount})
            if actual != amount:
                return WriteResult(
                    "set_hotkey_amount",
                    False,
                    "Hotkey amount write may have succeeded but verification failed",
                    details,
                )
        return WriteResult("set_hotkey_amount", ok, "Hotkey amount updated" if ok else "Hotkey amount write failed", details)

    def set_hotkey_liters_x1000(
        self,
        hotkey: str,
        liters_x1000: int,
        verify: bool = True,
    ) -> WriteResult:
        hotkey = validate_hotkey_name(hotkey)
        liters_x1000 = validate_u32(liters_x1000, "hotkey liters_x1000")
        self.ensure_config_unlocked()
        hi_register, lo_register = HOTKEY_LITERS_REGISTERS[hotkey]
        ok = self.write_u32_register_pair(hi_register, lo_register, liters_x1000)
        details = {"hotkey": hotkey, "liters_x1000": liters_x1000, "verified": False}
        if verify and ok:
            actual = self.read_live_data().hotkeys[hotkey].liters_x1000
            details.update({"readback": actual, "verified": actual == liters_x1000})
            if actual != liters_x1000:
                return WriteResult(
                    "set_hotkey_liters_x1000",
                    False,
                    "Hotkey liters write may have succeeded but verification failed",
                    details,
                )
        return WriteResult("set_hotkey_liters_x1000", ok, "Hotkey liters updated" if ok else "Hotkey liters write failed", details)

    def set_hotkey_liters(
        self,
        hotkey: str,
        liters: float,
        verify: bool = True,
    ) -> WriteResult:
        if liters < 0:
            raise ValueError("liters must be >= 0")
        return self.set_hotkey_liters_x1000(hotkey, round(liters * 1000), verify)

    def clear_daily_total(self, verify: bool = False) -> WriteResult:
        self.ensure_config_unlocked()
        ok = self.write_single_register(CONFIG_CLEAR_DAILY, CONFIG_CLEAR_DAILY_MAGIC)
        details = {"magic": f"0x{CONFIG_CLEAR_DAILY_MAGIC:04X}", "verified": False}
        if verify and ok:
            live = self.read_live_data()
            verified = live.daily_amount == 0 and live.daily_liters_x1000 == 0
            details.update(
                {
                    "daily_amount": live.daily_amount,
                    "daily_liters_x1000": live.daily_liters_x1000,
                    "verified": verified,
                }
            )
            if not verified:
                return WriteResult(
                    "clear_daily_total",
                    False,
                    "Daily total clear may have succeeded but verification failed",
                    details,
                )
        return WriteResult("clear_daily_total", ok, "Daily total clear command sent" if ok else "Daily total clear write failed", details)

    def change_manager_password(
        self,
        old_password: int,
        new_password: int,
        verify_unlock_new: bool = False,
    ) -> WriteResult:
        validate_password(old_password, "old password")
        validate_password(new_password, "new password")
        self.unlock_config(old_password)
        ok = self.write_u32_register_pair(
            CONFIG_NEW_PASSWORD_HI,
            CONFIG_NEW_PASSWORD_LO,
            new_password,
        )
        details = {
            "old_password": _masked_password(old_password),
            "new_password": _masked_password(new_password),
            "verified": False,
        }
        if verify_unlock_new and ok:
            status = self.unlock_config(new_password)
            details["verified"] = status.unlocked
        return WriteResult(
            "change_manager_password",
            ok,
            "Manager password updated" if ok else "Manager password write failed",
            details,
        )


def _masked_password(value: int) -> str:
    return "*" * max(1, len(str(value)))
