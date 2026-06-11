import pytest

from app.decoders import (
    as_i16,
    decode_fail_event,
    decode_humidity_x100,
    decode_quick_status,
    decode_sensor_snapshot,
    decode_temperature_c_x100,
    u32_from_registers,
)


def test_u16_i16_u32_helpers() -> None:
    assert u32_from_registers(0x0000, 0x3A98) == 15000
    assert as_i16(0x09E4) == 2532
    assert as_i16(0xFF9C) == -100
    assert decode_temperature_c_x100(0x09E4) == 25.32
    assert decode_temperature_c_x100(0xFF9C) == -1.00
    assert decode_humidity_x100(0x1996) == 65.50


def test_decode_quick_status() -> None:
    status = decode_quick_status([7, 1, 0x0004, 0, 0, 0, 0, 2])

    assert status.protocol_version == 7
    assert status.slave_address == 1
    assert "storage_ready" in status.status_flag_names
    assert status.nozzle_status == 2
    assert "pumping" in status.nozzle_status_text


def test_decode_sensor_snapshot_valid_ambient() -> None:
    sensor = decode_sensor_snapshot([0x0001, 0x09E4, 0x0BBA, 0x1996])

    assert sensor.ambient_valid is True
    assert sensor.mcu_temp_c == 25.32
    assert sensor.ambient_temp_c == 30.02
    assert sensor.humidity_percent == 65.50


def test_decode_sensor_snapshot_invalid_ambient() -> None:
    sensor = decode_sensor_snapshot([0x0000, 0x09E4, 0x0000, 0x0000])

    assert sensor.ambient_valid is False
    assert sensor.mcu_temp_c == 25.32
    assert sensor.ambient_temp_c is None
    assert sensor.humidity_percent is None


def test_decode_fail_event() -> None:
    event = decode_fail_event([0x0402, 9])

    assert event.code_text == "MODBUS_CRC_MISMATCH"
    assert event.sequence == 9


@pytest.mark.parametrize(
    ("decoder", "registers"),
    [
        (decode_quick_status, [1]),
        (decode_sensor_snapshot, [1]),
        (decode_fail_event, [1]),
    ],
)
def test_decoders_validate_lengths(decoder, registers: list[int]) -> None:
    with pytest.raises(ValueError):
        decoder(registers)
