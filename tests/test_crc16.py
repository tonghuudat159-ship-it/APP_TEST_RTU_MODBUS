import pytest

from app.modbus_rtu import append_crc, crc16_modbus


@pytest.mark.parametrize(
    ("data_hex", "crc_low", "crc_high"),
    [
        ("01 03 00 28 00 14", 0xC5, 0xCD),
        ("01 06 00 2A 00 00", 0xA8, 0x02),
        ("01 03 00 07 00 01", 0x35, 0xCB),
        ("01 03 00 3C 00 03", 0xC5, 0xC7),
    ],
)
def test_crc16_vectors(data_hex: str, crc_low: int, crc_high: int) -> None:
    data = bytes.fromhex(data_hex)

    assert crc16_modbus(data) == (crc_high << 8) | crc_low
    assert append_crc(data) == data + bytes((crc_low, crc_high))
