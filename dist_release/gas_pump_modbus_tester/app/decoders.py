"""Typed decoders for gas pump firmware register blocks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app import register_map as reg


@dataclass
class QuickStatus:
    protocol_version: int
    slave_address: int
    status_flags: int
    status_flag_names: list[str]
    pump_mode: int
    key_mode: int
    screen: int
    selected_field: int
    nozzle_status: int
    nozzle_status_text: str


@dataclass
class SensorSnapshot:
    sensor_status: int
    ambient_valid: bool
    mcu_temp_c: float
    ambient_temp_c: float | None
    humidity_percent: float | None


@dataclass
class HotkeyPreset:
    amount: int
    liters_x1000: int
    liters: float


@dataclass
class LiveData:
    current_amount: int
    current_liters_x1000: int
    current_liters: float
    unit_price: int
    target_amount: int
    target_liters_x1000: int
    target_liters: float
    daily_amount: int
    daily_liters_x1000: int
    daily_liters: float
    total_liters_x1000: int
    total_liters: float
    hotkeys: dict[str, HotkeyPreset]
    raw_registers: list[int]


@dataclass
class ConfigStatus:
    value: int
    names: list[str]
    unlocked: bool


@dataclass
class PumpClock:
    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int


@dataclass
class LogWindow:
    log_count: int
    log_select: int
    log_status: int
    log_status_names: list[str]
    is_valid: bool
    pump_id: int
    clock: PumpClock | None
    sequence: int
    amount: int
    liters_x1000: int
    liters: float
    unit_price: int
    total_liters_x1000: int
    total_liters: float
    checksum: int


@dataclass
class FailEvent:
    code: int
    code_text: str
    sequence: int


def as_u16(value: int) -> int:
    """Return *value* constrained to unsigned 16-bit form."""
    return value & 0xFFFF


def as_i16(value: int) -> int:
    """Interpret *value* as a signed 16-bit integer."""
    value = as_u16(value)
    if value & 0x8000:
        return value - 0x10000
    return value


def u32_from_registers(hi: int, lo: int) -> int:
    """Combine two 16-bit Modbus registers into an unsigned 32-bit integer."""
    return (as_u16(hi) << 16) | as_u16(lo)


def validate_u16(value: int, name: str = "value") -> int:
    if not 0 <= value <= 0xFFFF:
        raise ValueError(f"{name} must be in range 0..0xFFFF")
    return value


def validate_u32(value: int, name: str = "value") -> int:
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f"{name} must be in range 0..0xFFFFFFFF")
    return value


def validate_password(value: int, name: str = "password") -> int:
    if not 0 <= value <= 999999:
        raise ValueError(f"{name} must be in range 0..999999")
    return value


def validate_slave_id(value: int) -> int:
    if not 1 <= value <= 247:
        raise ValueError("slave id must be in range 1..247")
    return value


def validate_hotkey_name(value: str) -> str:
    normalized = value.upper()
    if normalized not in ("F1", "F2", "F3", "F4"):
        raise ValueError("hotkey must be one of F1, F2, F3, F4")
    return normalized


def split_u32(value: int) -> tuple[int, int]:
    """Split an unsigned 32-bit integer into high and low 16-bit registers."""
    validate_u32(value)
    return (value >> 16) & 0xFFFF, value & 0xFFFF


def high_byte(value: int) -> int:
    """Return the high byte of a 16-bit register."""
    return (as_u16(value) >> 8) & 0xFF


def low_byte(value: int) -> int:
    """Return the low byte of a 16-bit register."""
    return as_u16(value) & 0xFF


def decode_bitmask(value: int, bit_map: dict[int, str]) -> list[str]:
    """Return names for all set bits present in *bit_map*."""
    return [name for bit, name in bit_map.items() if value & bit]


def decode_temperature_c_x100(raw: int) -> float:
    """Decode signed centi-degrees Celsius."""
    return as_i16(raw) / 100.0


def decode_humidity_x100(raw: int) -> float:
    """Decode unsigned centi-percent relative humidity."""
    return as_u16(raw) / 100.0


def decode_clock_registers(registers: list[int]) -> PumpClock:
    """Decode three packed clock registers into a PumpClock."""
    _require_length(registers, reg.CLOCK_COUNT, "clock")

    year_offset = high_byte(registers[0])
    month = low_byte(registers[0])
    day = high_byte(registers[1])
    hour = low_byte(registers[1])
    minute = high_byte(registers[2])
    second = low_byte(registers[2])

    clock = PumpClock(
        year=2000 + year_offset,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        second=second,
    )
    pump_clock_to_datetime(clock)
    return clock


def encode_clock_registers(clock: PumpClock) -> list[int]:
    """Encode a PumpClock into three packed clock registers."""
    pump_clock_to_datetime(clock)
    year_offset = clock.year - 2000
    return [
        (year_offset << 8) | clock.month,
        (clock.day << 8) | clock.hour,
        (clock.minute << 8) | clock.second,
    ]


def pump_clock_to_datetime(clock: PumpClock) -> datetime:
    """Convert a PumpClock to a Python datetime, validating calendar fields."""
    if not 2000 <= clock.year <= 2099:
        raise ValueError(f"year must be in range 2000..2099, got {clock.year}")
    try:
        return datetime(
            clock.year,
            clock.month,
            clock.day,
            clock.hour,
            clock.minute,
            clock.second,
        )
    except ValueError as exc:
        raise ValueError(f"invalid pump clock: {exc}") from exc


def datetime_to_pump_clock(value: datetime) -> PumpClock:
    """Convert a Python datetime to PumpClock."""
    clock = PumpClock(
        year=value.year,
        month=value.month,
        day=value.day,
        hour=value.hour,
        minute=value.minute,
        second=value.second,
    )
    pump_clock_to_datetime(clock)
    return clock


def decode_quick_status(registers: list[int]) -> QuickStatus:
    """Decode the quick status block at 0x0000."""
    _require_length(registers, reg.QUICK_STATUS_COUNT, "quick status")
    nozzle_status = as_u16(registers[7])
    return QuickStatus(
        protocol_version=as_u16(registers[0]),
        slave_address=as_u16(registers[1]),
        status_flags=as_u16(registers[2]),
        status_flag_names=decode_bitmask(as_u16(registers[2]), reg.STATUS_FLAG_BITS),
        pump_mode=as_u16(registers[3]),
        key_mode=as_u16(registers[4]),
        screen=as_u16(registers[5]),
        selected_field=as_u16(registers[6]),
        nozzle_status=nozzle_status,
        nozzle_status_text=reg.NOZZLE_STATUS_TEXT.get(
            nozzle_status,
            f"unknown nozzle status {nozzle_status}",
        ),
    )


def decode_sensor_snapshot(registers: list[int]) -> SensorSnapshot:
    """Decode sensor status and temperature/humidity readings."""
    _require_length(registers, reg.SENSOR_COUNT, "sensor snapshot")
    sensor_status = as_u16(registers[0])
    ambient_valid = bool(sensor_status & 0x0001)
    return SensorSnapshot(
        sensor_status=sensor_status,
        ambient_valid=ambient_valid,
        mcu_temp_c=decode_temperature_c_x100(registers[1]),
        ambient_temp_c=decode_temperature_c_x100(registers[2]) if ambient_valid else None,
        humidity_percent=decode_humidity_x100(registers[3]) if ambient_valid else None,
    )


def decode_live_data(registers: list[int]) -> LiveData:
    """Decode the 32-register live data block at 0x0008."""
    _require_length(registers, reg.LIVE_DATA_COUNT, "live data")
    current_liters_x1000 = _u32_at(registers, 2)
    target_liters_x1000 = _u32_at(registers, 8)
    daily_liters_x1000 = _u32_at(registers, 12)
    total_liters_x1000 = _u32_at(registers, 14)

    hotkey_amounts = {
        "F1": _u32_at(registers, 16),
        "F2": _u32_at(registers, 18),
        "F3": _u32_at(registers, 20),
        "F4": _u32_at(registers, 22),
    }
    hotkey_liters = {
        "F1": _u32_at(registers, 24),
        "F2": _u32_at(registers, 26),
        "F3": _u32_at(registers, 28),
        "F4": _u32_at(registers, 30),
    }

    return LiveData(
        current_amount=_u32_at(registers, 0),
        current_liters_x1000=current_liters_x1000,
        current_liters=current_liters_x1000 / 1000.0,
        unit_price=_u32_at(registers, 4),
        target_amount=_u32_at(registers, 6),
        target_liters_x1000=target_liters_x1000,
        target_liters=target_liters_x1000 / 1000.0,
        daily_amount=_u32_at(registers, 10),
        daily_liters_x1000=daily_liters_x1000,
        daily_liters=daily_liters_x1000 / 1000.0,
        total_liters_x1000=total_liters_x1000,
        total_liters=total_liters_x1000 / 1000.0,
        hotkeys={
            name: HotkeyPreset(
                amount=hotkey_amounts[name],
                liters_x1000=hotkey_liters[name],
                liters=hotkey_liters[name] / 1000.0,
            )
            for name in ("F1", "F2", "F3", "F4")
        },
        raw_registers=[as_u16(value) for value in registers],
    )


def decode_config_status(registers: list[int]) -> ConfigStatus:
    """Decode the one-register configuration status block."""
    _require_length(registers, reg.CONFIG_STATUS_COUNT, "config status")
    value = as_u16(registers[0])
    return ConfigStatus(
        value=value,
        names=decode_bitmask(value, reg.CONFIG_STATUS_BITS),
        unlocked=bool(value & 0x0001),
    )


def decode_log_window(registers: list[int]) -> LogWindow:
    """Decode the 20-register EEPROM log window."""
    _require_length(registers, reg.LOG_WINDOW_COUNT, "log window")
    log_count = u32_from_registers(registers[0], registers[1])
    log_select = as_u16(registers[2])
    log_status = as_u16(registers[3])
    log_status_names = decode_bitmask(log_status, reg.LOG_STATUS_BITS)
    is_valid = log_status == 0x0007

    if not is_valid:
        return LogWindow(
            log_count=log_count,
            log_select=log_select,
            log_status=log_status,
            log_status_names=log_status_names,
            is_valid=False,
            pump_id=0,
            clock=None,
            sequence=0,
            amount=0,
            liters_x1000=0,
            liters=0.0,
            unit_price=0,
            total_liters_x1000=0,
            total_liters=0.0,
            checksum=0,
        )

    liters_x1000 = u32_from_registers(registers[12], registers[13])
    total_liters_x1000 = u32_from_registers(registers[16], registers[17])
    return LogWindow(
        log_count=log_count,
        log_select=log_select,
        log_status=log_status,
        log_status_names=log_status_names,
        is_valid=True,
        pump_id=as_u16(registers[4]),
        clock=decode_clock_registers(registers[5:8]),
        sequence=u32_from_registers(registers[8], registers[9]),
        amount=u32_from_registers(registers[10], registers[11]),
        liters_x1000=liters_x1000,
        liters=liters_x1000 / 1000.0,
        unit_price=u32_from_registers(registers[14], registers[15]),
        total_liters_x1000=total_liters_x1000,
        total_liters=total_liters_x1000 / 1000.0,
        checksum=u32_from_registers(registers[18], registers[19]),
    )


def decode_fail_event(registers: list[int]) -> FailEvent:
    """Decode the last fail event block."""
    _require_length(registers, reg.FAIL_EVENT_COUNT, "fail event")
    code = as_u16(registers[0])
    return FailEvent(
        code=code,
        code_text=reg.FAIL_CODE_TEXT.get(code, f"UNKNOWN_0x{code:04X}"),
        sequence=as_u16(registers[1]),
    )


def decode_registers(registers: list[int]) -> list[int]:
    """Return raw registers unchanged for callers that need raw access."""
    return registers


def _require_length(registers: list[int], expected: int, label: str) -> None:
    if len(registers) != expected:
        raise ValueError(
            f"{label} requires {expected} register(s), got {len(registers)}"
        )


def _validate_range(value: int, minimum: int, maximum: int, label: str) -> None:
    if not minimum <= value <= maximum:
        raise ValueError(f"{label} must be in range {minimum}..{maximum}, got {value}")


def _u32_at(registers: list[int], index: int) -> int:
    return u32_from_registers(registers[index], registers[index + 1])
