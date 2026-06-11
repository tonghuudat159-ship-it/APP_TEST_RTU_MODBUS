from app.decoders import decode_log_window


def test_decode_valid_log_window() -> None:
    registers = [
        0x0000,
        0x0007,
        0x0000,
        0x0007,
        0x0001,
        0x1A04,
        0x180F,
        0x1E2D,
        0x0000,
        0x0007,
        0x0000,
        0x3039,
        0x0000,
        0x0218,
        0x0000,
        0x59D8,
        0x0001,
        0x88B8,
        0x1234,
        0x5678,
    ]

    log = decode_log_window(registers)

    assert log.is_valid is True
    assert log.log_count == 7
    assert log.pump_id == 1
    assert log.clock is not None
    assert log.clock.year == 2026
    assert log.clock.month == 4
    assert log.clock.day == 24
    assert log.clock.hour == 15
    assert log.clock.minute == 30
    assert log.clock.second == 45
    assert log.sequence == 7
    assert log.amount == 12345
    assert log.liters_x1000 == 536
    assert log.liters == 0.536
    assert log.unit_price == 23000
    assert log.total_liters_x1000 == 100536
    assert log.total_liters == 100.536
    assert log.checksum == 0x12345678


def test_decode_invalid_log_window() -> None:
    registers = [
        0x0000,
        0x0007,
        0x0000,
        0x0001,
        0x0001,
        0x1A04,
        0x180F,
        0x1E2D,
        0x0000,
        0x0007,
        0x0000,
        0x3039,
        0x0000,
        0x0218,
        0x0000,
        0x59D8,
        0x0001,
        0x88B8,
        0x1234,
        0x5678,
    ]

    log = decode_log_window(registers)

    assert log.is_valid is False
    assert log.log_count == 7
    assert log.log_select == 0
    assert log.log_status == 0x0001
    assert log.clock is None
