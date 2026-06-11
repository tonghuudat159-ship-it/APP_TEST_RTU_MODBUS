import pytest

from app.cli import parse_slave_range


def test_parse_slave_range_range() -> None:
    assert parse_slave_range("1-3") == [1, 2, 3]


def test_parse_slave_range_list() -> None:
    assert parse_slave_range("1,2,5") == [1, 2, 5]


def test_parse_slave_range_removes_duplicates() -> None:
    assert parse_slave_range("1,2,1,5,2") == [1, 2, 5]


@pytest.mark.parametrize("value", ["0", "248", "10-1"])
def test_parse_slave_range_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        parse_slave_range(value)
