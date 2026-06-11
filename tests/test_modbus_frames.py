import pytest

from app.modbus_rtu import (
    build_read_request,
    build_write_single_register_request,
)


def test_build_read_request() -> None:
    assert (
        build_read_request(
            slave_id=1,
            function_code=0x03,
            start_address=0x0028,
            quantity=0x0014,
        )
        == bytes.fromhex("01 03 00 28 00 14 C5 CD")
    )


def test_build_write_single_register_request() -> None:
    assert (
        build_write_single_register_request(
            slave_id=1,
            register_address=0x002A,
            value=0x0000,
        )
        == bytes.fromhex("01 06 00 2A 00 00 A8 02")
    )


@pytest.mark.parametrize("function_code", [0x01, 0x02, 0x05, 0x06])
def test_build_read_request_rejects_unsupported_function(function_code: int) -> None:
    with pytest.raises(ValueError):
        build_read_request(1, function_code, 0, 1)


@pytest.mark.parametrize("quantity", [0, 126])
def test_build_read_request_rejects_invalid_quantity(quantity: int) -> None:
    with pytest.raises(ValueError):
        build_read_request(1, 0x03, 0, quantity)
