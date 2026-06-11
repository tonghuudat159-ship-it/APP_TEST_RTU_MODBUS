import pytest

from app.decoders import (
    PumpClock,
    decode_clock_registers,
    encode_clock_registers,
)


def test_decode_clock_registers() -> None:
    clock = decode_clock_registers([0x1A04, 0x180F, 0x1E2D])

    assert clock.year == 2026
    assert clock.month == 4
    assert clock.day == 24
    assert clock.hour == 15
    assert clock.minute == 30
    assert clock.second == 45


def test_encode_clock_registers() -> None:
    clock = PumpClock(
        year=2026,
        month=4,
        day=24,
        hour=15,
        minute=30,
        second=45,
    )

    assert encode_clock_registers(clock) == [0x1A04, 0x180F, 0x1E2D]


@pytest.mark.parametrize(
    "registers",
    [
        [0x1A00, 0x180F, 0x1E2D],
        [0x1A0D, 0x180F, 0x1E2D],
        [0x1A04, 0x000F, 0x1E2D],
        [0x1A04, 0x1818, 0x1E2D],
        [0x1A04, 0x180F, 0x3C2D],
        [0x1A04, 0x180F, 0x1E3C],
    ],
)
def test_decode_clock_registers_validates_ranges(registers: list[int]) -> None:
    with pytest.raises(ValueError):
        decode_clock_registers(registers)
