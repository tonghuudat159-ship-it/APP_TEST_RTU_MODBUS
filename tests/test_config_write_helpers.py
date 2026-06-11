import pytest

from app.decoders import (
    split_u32,
    validate_hotkey_name,
    validate_password,
    validate_slave_id,
)


def test_validate_password_bounds() -> None:
    assert validate_password(0) == 0
    assert validate_password(999999) == 999999
    with pytest.raises(ValueError):
        validate_password(-1)
    with pytest.raises(ValueError):
        validate_password(1000000)


def test_validate_slave_id_bounds() -> None:
    assert validate_slave_id(1) == 1
    assert validate_slave_id(247) == 247
    with pytest.raises(ValueError):
        validate_slave_id(0)
    with pytest.raises(ValueError):
        validate_slave_id(248)


def test_validate_hotkey_name_normalizes() -> None:
    assert validate_hotkey_name("f1") == "F1"
    with pytest.raises(ValueError):
        validate_hotkey_name("F5")


def test_split_u32_unit_price() -> None:
    assert split_u32(23000) == (0x0000, 0x59D8)
