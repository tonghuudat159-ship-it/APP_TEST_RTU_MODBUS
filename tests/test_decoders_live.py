import pytest

from app.decoders import decode_config_status, decode_live_data, split_u32


def _live_registers() -> list[int]:
    values = [
        12345,
        536,
        23000,
        100000,
        4348,
        500000,
        21740,
        100536,
        10000,
        20000,
        50000,
        100000,
        1000,
        2000,
        5000,
        10000,
    ]
    registers: list[int] = []
    for value in values:
        registers.extend(split_u32(value))
    return registers


def test_decode_live_data() -> None:
    live = decode_live_data(_live_registers())

    assert live.current_amount == 12345
    assert live.current_liters_x1000 == 536
    assert live.current_liters == 0.536
    assert live.unit_price == 23000
    assert live.target_amount == 100000
    assert live.target_liters == 4.348
    assert live.daily_amount == 500000
    assert live.daily_liters == 21.740
    assert live.total_liters == 100.536
    assert live.hotkeys["F1"].liters == 1.000
    assert live.hotkeys["F4"].amount == 100000
    assert live.raw_registers == _live_registers()


def test_decode_live_data_validates_length() -> None:
    with pytest.raises(ValueError):
        decode_live_data([0] * 31)


def test_decode_config_status() -> None:
    status = decode_config_status([0x0001])

    assert status.value == 0x0001
    assert status.names == ["config_unlocked"]
    assert status.unlocked is True
