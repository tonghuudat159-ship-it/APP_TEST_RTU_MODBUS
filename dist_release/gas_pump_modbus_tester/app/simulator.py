"""Offline Modbus RTU simulator for the gas pump firmware register map."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

from app.capture import RawCaptureBuffer, RawFrameRecord, infer_function_code, infer_slave_id
from app.exceptions import ModbusTimeoutError, SerialTransportError
from app.modbus_rtu import (
    READ_HOLDING_REGISTERS,
    READ_INPUT_REGISTERS,
    WRITE_SINGLE_REGISTER,
    append_crc,
    bytes_to_hex,
    verify_crc,
)
from app import register_map as reg


@dataclass
class SimulatedLogRecord:
    pump_id: int
    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int
    sequence: int
    amount: int
    liters_x1000: int
    unit_price: int
    total_liters_x1000: int
    checksum: int


@dataclass
class SimulatorProfile:
    name: str
    description: str


SIMULATOR_PROFILES = {
    "normal": SimulatorProfile("normal", "Default healthy simulated pump."),
    "no-logs": SimulatorProfile("no-logs", "Healthy pump with no EEPROM logs."),
    "sensor-invalid": SimulatorProfile("sensor-invalid", "Ambient sensor invalid."),
    "bad-protocol": SimulatorProfile("bad-protocol", "Protocol version mismatch."),
    "fail-event": SimulatorProfile("fail-event", "Pump reports a recent fail event."),
    "locked-config": SimulatorProfile("locked-config", "Normal pump with locked config."),
}


class GasPumpSimulator:
    """Stateful Modbus RTU slave simulator for offline CLI testing."""

    def __init__(
        self,
        slave_id: int = 1,
        password: int = 1234,
        profile: str = "normal",
    ):
        if profile not in SIMULATOR_PROFILES:
            raise ValueError(f"unknown simulator profile: {profile}")
        self.slave_id = slave_id
        self.password = password
        self.profile = profile
        self.config_unlocked = False
        self.unlock_deadline_monotonic = 0.0
        self.registers: dict[int, int] = {}
        self.logs: list[SimulatedLogRecord] = []
        self.selected_log_index = 0
        self.clock_staging: dict[int, int] = {}
        self._unlock_password_hi = 0
        self._new_password_hi = 0
        self._pending_slave_change: int | None = None
        self._init_registers()
        self._apply_profile(profile)
        self.refresh_log_window()
        self.refresh_config_status()

    def handle_request(self, request: bytes) -> bytes | None:
        if len(request) < 4 or not verify_crc(request):
            return None
        slave_id = request[0]
        function_code = request[1]
        if slave_id != self.slave_id:
            return None
        if function_code in (READ_HOLDING_REGISTERS, READ_INPUT_REGISTERS):
            return self._handle_read(slave_id, function_code, request)
        if function_code == WRITE_SINGLE_REGISTER:
            return self._handle_write(slave_id, request)
        return self.build_exception(slave_id, function_code, 0x01)

    def build_read_response(
        self,
        slave_id: int,
        function_code: int,
        registers: list[int],
    ) -> bytes:
        payload = bytes((slave_id, function_code, len(registers) * 2))
        for value in registers:
            payload += bytes(((value >> 8) & 0xFF, value & 0xFF))
        return append_crc(payload)

    def build_write_echo(self, slave_id: int, register_address: int, value: int) -> bytes:
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

    def build_exception(
        self,
        slave_id: int,
        function_code: int,
        exception_code: int,
    ) -> bytes:
        return append_crc(bytes((slave_id, function_code | 0x80, exception_code)))

    def set_u32(self, hi_addr: int, lo_addr: int, value: int) -> None:
        self.registers[hi_addr] = (value >> 16) & 0xFFFF
        self.registers[lo_addr] = value & 0xFFFF

    def get_u32(self, hi_addr: int, lo_addr: int) -> int:
        return (self.registers.get(hi_addr, 0) << 16) | self.registers.get(lo_addr, 0)

    def refresh_log_window(self) -> None:
        self.set_u32(reg.LOG_COUNT_HI, reg.LOG_COUNT_LO, len(self.logs))
        self.registers[reg.LOG_SELECT] = self.selected_log_index & 0xFFFF
        payload_addresses = range(reg.LOG_ID_PUMP, reg.LOG_CHECKSUM_LO + 1)
        if not self.logs:
            self.registers[reg.LOG_STATUS] = 0
            for address in payload_addresses:
                self.registers[address] = 0
            return
        if not 0 <= self.selected_log_index < len(self.logs):
            self.registers[reg.LOG_STATUS] = 0x0001
            for address in payload_addresses:
                self.registers[address] = 0
            return
        log = self.logs[self.selected_log_index]
        self.registers[reg.LOG_STATUS] = 0x0007
        self.registers[reg.LOG_ID_PUMP] = log.pump_id
        self.registers[reg.LOG_YEAR_MONTH] = ((log.year - 2000) << 8) | log.month
        self.registers[reg.LOG_DAY_HOUR] = (log.day << 8) | log.hour
        self.registers[reg.LOG_MINUTE_SECOND] = (log.minute << 8) | log.second
        self.set_u32(reg.LOG_SEQUENCE_HI, reg.LOG_SEQUENCE_LO, log.sequence)
        self.set_u32(reg.LOG_AMOUNT_HI, reg.LOG_AMOUNT_LO, log.amount)
        self.set_u32(reg.LOG_LITERS_X1000_HI, reg.LOG_LITERS_X1000_LO, log.liters_x1000)
        self.set_u32(reg.LOG_UNIT_PRICE_HI, reg.LOG_UNIT_PRICE_LO, log.unit_price)
        self.set_u32(
            reg.LOG_TOTAL_LITERS_X1000_HI,
            reg.LOG_TOTAL_LITERS_X1000_LO,
            log.total_liters_x1000,
        )
        self.set_u32(reg.LOG_CHECKSUM_HI, reg.LOG_CHECKSUM_LO, log.checksum)

    def refresh_config_status(self) -> None:
        if self.config_unlocked and time.monotonic() > self.unlock_deadline_monotonic:
            self.config_unlocked = False
        self.registers[reg.CONFIG_STATUS] = 0x0001 if self.config_unlocked else 0x0000

    def _handle_read(self, slave_id: int, function_code: int, request: bytes) -> bytes:
        if len(request) != 8:
            return self.build_exception(slave_id, function_code, 0x03)
        start = (request[2] << 8) | request[3]
        count = (request[4] << 8) | request[5]
        if count < 1 or count > 125 or not self._range_supported(start, count):
            return self.build_exception(slave_id, function_code, 0x02)
        if start <= reg.LOG_WINDOW_START <= start + count - 1:
            self.refresh_log_window()
        if start <= reg.CONFIG_STATUS <= start + count - 1:
            self.refresh_config_status()
        values = [self.registers.get(start + offset, 0) for offset in range(count)]
        return self.build_read_response(slave_id, function_code, values)

    def _handle_write(self, slave_id: int, request: bytes) -> bytes:
        if len(request) != 8:
            return self.build_exception(slave_id, WRITE_SINGLE_REGISTER, 0x03)
        address = (request[2] << 8) | request[3]
        value = (request[4] << 8) | request[5]
        if not self._address_supported(address):
            return self.build_exception(slave_id, WRITE_SINGLE_REGISTER, 0x02)
        result = self._write_register(address, value)
        if result != 0:
            return self.build_exception(slave_id, WRITE_SINGLE_REGISTER, result)
        response = self.build_write_echo(slave_id, address, value)
        if self._pending_slave_change is not None:
            self.slave_id = self._pending_slave_change
            self.registers[reg.SLAVE_ADDRESS] = self.slave_id
            self._pending_slave_change = None
        return response

    def _write_register(self, address: int, value: int) -> int:
        if address == reg.LOG_SELECT:
            self.selected_log_index = value
            self.refresh_log_window()
            return 0
        if address in (reg.CLOCK_YEAR_MONTH, reg.CLOCK_DAY_HOUR, reg.CLOCK_MINUTE_SECOND):
            return self._write_clock(address, value)
        if address == reg.CONFIG_UNLOCK_PASSWORD_HI:
            self._unlock_password_hi = value
            self.registers[address] = value
            return 0
        if address == reg.CONFIG_UNLOCK_PASSWORD_LO:
            attempted = (self._unlock_password_hi << 16) | value
            if attempted != self.password:
                return 0x03
            self.config_unlocked = True
            self.unlock_deadline_monotonic = time.monotonic() + 60.0
            self.registers[address] = value
            self.refresh_config_status()
            return 0
        if address in _PROTECTED_WRITES and not self._is_unlocked():
            return 0x03
        if address == reg.SLAVE_ADDRESS:
            if not 1 <= value <= 247:
                return 0x03
            self._pending_slave_change = value
            return 0
        if address == reg.CONFIG_NEW_PASSWORD_HI:
            self._new_password_hi = value
            self.registers[address] = value
            return 0
        if address == reg.CONFIG_NEW_PASSWORD_LO:
            self.password = (self._new_password_hi << 16) | value
            self.registers[address] = value
            return 0
        if address in _U32_LO_TO_HI:
            hi_addr = _U32_LO_TO_HI[address]
            self.registers[address] = value
            self._commit_u32_pair(hi_addr, address)
            return 0
        if address in _U32_HI_ADDRESSES:
            self.registers[address] = value
            return 0
        if address == reg.CONFIG_CLEAR_DAILY:
            if value != reg.CONFIG_CLEAR_DAILY_MAGIC:
                return 0x03
            self.set_u32(reg.DAILY_AMOUNT_HI, reg.DAILY_AMOUNT_LO, 0)
            self.set_u32(reg.DAILY_LITERS_X1000_HI, reg.DAILY_LITERS_X1000_LO, 0)
            self.registers[address] = value
            return 0
        if address in _WRITABLE_RAW_ADDRESSES:
            self.registers[address] = value
            return 0
        return 0x02

    def _write_clock(self, address: int, value: int) -> int:
        self.clock_staging[address] = value
        if all(
            clock_address in self.clock_staging
            for clock_address in (
                reg.CLOCK_YEAR_MONTH,
                reg.CLOCK_DAY_HOUR,
                reg.CLOCK_MINUTE_SECOND,
            )
        ):
            year_month = self.clock_staging[reg.CLOCK_YEAR_MONTH]
            day_hour = self.clock_staging[reg.CLOCK_DAY_HOUR]
            minute_second = self.clock_staging[reg.CLOCK_MINUTE_SECOND]
            try:
                datetime(
                    2000 + ((year_month >> 8) & 0xFF),
                    year_month & 0xFF,
                    (day_hour >> 8) & 0xFF,
                    day_hour & 0xFF,
                    (minute_second >> 8) & 0xFF,
                    minute_second & 0xFF,
                )
            except ValueError:
                return 0x03
            self.registers.update(self.clock_staging)
        return 0

    def _commit_u32_pair(self, hi_addr: int, lo_addr: int) -> None:
        value = self.get_u32(hi_addr, lo_addr)
        self.set_u32(hi_addr, lo_addr, value)

    def _is_unlocked(self) -> bool:
        self.refresh_config_status()
        return self.config_unlocked

    def _range_supported(self, start: int, count: int) -> bool:
        return all(self._address_supported(start + offset) for offset in range(count))

    def _address_supported(self, address: int) -> bool:
        return 0x0000 <= address <= reg.LAST_FAIL_SEQUENCE

    def _init_registers(self) -> None:
        for address in range(0x0000, reg.LAST_FAIL_SEQUENCE + 1):
            self.registers[address] = 0
        self.registers[reg.PROTOCOL_VERSION] = 7
        self.registers[reg.SLAVE_ADDRESS] = self.slave_id
        self.registers[reg.STATUS_FLAGS] = 0x0004
        self.registers[reg.NOZZLE_STATUS] = 0
        self.set_u32(reg.CURRENT_AMOUNT_HI, reg.CURRENT_AMOUNT_LO, 12345)
        self.set_u32(reg.CURRENT_LITERS_X1000_HI, reg.CURRENT_LITERS_X1000_LO, 536)
        self.set_u32(reg.UNIT_PRICE_HI, reg.UNIT_PRICE_LO, 23000)
        self.set_u32(reg.TARGET_AMOUNT_HI, reg.TARGET_AMOUNT_LO, 0)
        self.set_u32(reg.TARGET_LITERS_X1000_HI, reg.TARGET_LITERS_X1000_LO, 0)
        self.set_u32(reg.DAILY_AMOUNT_HI, reg.DAILY_AMOUNT_LO, 100000)
        self.set_u32(reg.DAILY_LITERS_X1000_HI, reg.DAILY_LITERS_X1000_LO, 4350)
        self.set_u32(reg.TOTAL_LITERS_X1000_HI, reg.TOTAL_LITERS_X1000_LO, 100536)
        for name, amount in {"F1": 10000, "F2": 20000, "F3": 50000, "F4": 100000}.items():
            self.set_u32(*reg.HOTKEY_AMOUNT_REGISTERS[name], amount)
        for name, liters in {"F1": 1000, "F2": 2000, "F3": 5000, "F4": 10000}.items():
            self.set_u32(*reg.HOTKEY_LITERS_REGISTERS[name], liters)
        self.registers[reg.CLOCK_YEAR_MONTH] = 0x1A04
        self.registers[reg.CLOCK_DAY_HOUR] = 0x180F
        self.registers[reg.CLOCK_MINUTE_SECOND] = 0x1E2D
        self.registers[reg.SENSOR_STATUS] = 0x0001
        self.registers[reg.MCU_TEMP_C_X100] = 2532
        self.registers[reg.AMBIENT_TEMP_C_X100] = 3002
        self.registers[reg.HUMIDITY_X100] = 6550
        self.registers[reg.LAST_FAIL_CODE] = 0
        self.registers[reg.LAST_FAIL_SEQUENCE] = 0
        self.logs = [
            SimulatedLogRecord(1, 2026, 4, 24, 15, 30, 45, 7, 12345, 536, 23000, 100536, 0x12345678),
            SimulatedLogRecord(1, 2026, 4, 24, 14, 15, 10, 6, 20000, 870, 23000, 100000, 0x22345678),
            SimulatedLogRecord(1, 2026, 4, 23, 18, 5, 2, 5, 50000, 2174, 23000, 99130, 0x32345678),
        ]

    def _apply_profile(self, profile: str) -> None:
        if profile == "no-logs":
            self.logs = []
        elif profile == "sensor-invalid":
            self.registers[reg.SENSOR_STATUS] = 0
            self.registers[reg.AMBIENT_TEMP_C_X100] = 0
            self.registers[reg.HUMIDITY_X100] = 0
        elif profile == "bad-protocol":
            self.registers[reg.PROTOCOL_VERSION] = 8
        elif profile == "fail-event":
            self.registers[reg.LAST_FAIL_CODE] = 0x0402
            self.registers[reg.LAST_FAIL_SEQUENCE] = 9


class SimulatedSerialTransport:
    """SerialTransport-compatible wrapper around GasPumpSimulator."""

    def __init__(
        self,
        simulator: GasPumpSimulator | None = None,
        port: str = "SIM",
        timeout: float = 0.5,
        debug: bool = False,
        capture: RawCaptureBuffer | None = None,
    ):
        self.simulator = simulator or GasPumpSimulator()
        self.port = port
        self.timeout = timeout
        self.debug = debug
        self.capture = capture
        self._open = False

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def is_open(self) -> bool:
        return self._open

    def transceive(self, request: bytes, expected_min_length: int = 5) -> bytes:
        if not self.is_open():
            raise SerialTransportError("simulated serial transport is not open")
        started = time.perf_counter()
        if self.debug:
            print(f"TX: {bytes_to_hex(request)}")
        self._capture_frame("TX", request)
        response = self.simulator.handle_request(request)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if response is None:
            if self.debug:
                print("RX: ")
                print(f"Elapsed: {elapsed_ms:.1f} ms")
            self._capture_frame(
                "RX",
                b"",
                elapsed_ms=elapsed_ms,
                crc_valid=None,
                note="timeout/no response",
            )
            raise ModbusTimeoutError("no response received before timeout")
        if self.debug:
            print(f"RX: {bytes_to_hex(response)}")
            print(f"Elapsed: {elapsed_ms:.1f} ms")
        self._capture_frame(
            "RX",
            response,
            elapsed_ms=elapsed_ms,
            crc_valid=verify_crc(response) if len(response) >= 4 else None,
            note=None if len(response) >= 4 else "response too short to validate CRC",
        )
        return response

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
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
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


_U32_PAIRS = [
    (reg.UNIT_PRICE_HI, reg.UNIT_PRICE_LO),
    *reg.HOTKEY_AMOUNT_REGISTERS.values(),
    *reg.HOTKEY_LITERS_REGISTERS.values(),
    (reg.CONFIG_NEW_PASSWORD_HI, reg.CONFIG_NEW_PASSWORD_LO),
]
_U32_HI_ADDRESSES = {hi for hi, _ in _U32_PAIRS}
_U32_LO_TO_HI = {lo: hi for hi, lo in _U32_PAIRS}
_PROTECTED_WRITES = {
    reg.SLAVE_ADDRESS,
    reg.CONFIG_CLEAR_DAILY,
    reg.CONFIG_NEW_PASSWORD_HI,
    reg.CONFIG_NEW_PASSWORD_LO,
    *[address for pair in reg.HOTKEY_AMOUNT_REGISTERS.values() for address in pair],
    *[address for pair in reg.HOTKEY_LITERS_REGISTERS.values() for address in pair],
    reg.UNIT_PRICE_HI,
    reg.UNIT_PRICE_LO,
}
_WRITABLE_RAW_ADDRESSES = {
    reg.CONFIG_UNLOCK_PASSWORD_HI,
    reg.CONFIG_UNLOCK_PASSWORD_LO,
}
