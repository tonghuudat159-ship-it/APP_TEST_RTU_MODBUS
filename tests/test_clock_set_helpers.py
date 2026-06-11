from datetime import datetime

import pytest

from app.decoders import (
    PumpClock,
    datetime_to_pump_clock,
    encode_clock_registers,
    pump_clock_to_datetime,
)
from app.gaspump_client import GasPumpModbusClient
from app.register_map import CLOCK_DAY_HOUR, CLOCK_MINUTE_SECOND, CLOCK_YEAR_MONTH


def test_datetime_to_pump_clock_and_encode() -> None:
    clock = datetime_to_pump_clock(datetime(2026, 4, 24, 15, 30, 45))

    assert clock == PumpClock(2026, 4, 24, 15, 30, 45)
    assert encode_clock_registers(clock) == [0x1A04, 0x180F, 0x1E2D]
    assert pump_clock_to_datetime(clock) == datetime(2026, 4, 24, 15, 30, 45)


@pytest.mark.parametrize(
    "clock",
    [
        PumpClock(1999, 4, 24, 15, 30, 45),
        PumpClock(2100, 4, 24, 15, 30, 45),
        PumpClock(2026, 2, 30, 15, 30, 45),
        PumpClock(2026, 4, 24, 24, 30, 45),
    ],
)
def test_invalid_clock_raises(clock: PumpClock) -> None:
    with pytest.raises(ValueError):
        encode_clock_registers(clock)


def test_set_clock_writes_three_registers_in_order() -> None:
    class FakeClient(GasPumpModbusClient):
        def __init__(self) -> None:
            self.writes: list[tuple[int, int]] = []

        def write_single_register(self, register_address: int, value: int) -> bool:
            self.writes.append((register_address, value))
            return True

    client = FakeClient()

    assert client.set_clock(PumpClock(2026, 4, 24, 15, 30, 45)) is True
    assert client.writes == [
        (CLOCK_YEAR_MONTH, 0x1A04),
        (CLOCK_DAY_HOUR, 0x180F),
        (CLOCK_MINUTE_SECOND, 0x1E2D),
    ]
