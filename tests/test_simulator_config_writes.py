import pytest

from app.exceptions import ModbusExceptionResponse, ModbusTimeoutError
from app.gaspump_client import GasPumpModbusClient
from app.modbus_rtu import build_read_request
from app.simulator import GasPumpSimulator, SimulatedSerialTransport


def _client() -> tuple[GasPumpModbusClient, GasPumpSimulator, SimulatedSerialTransport]:
    simulator = GasPumpSimulator()
    transport = SimulatedSerialTransport(simulator)
    transport.open()
    return GasPumpModbusClient(transport, slave_id=1), simulator, transport


def test_unlock_config_success() -> None:
    client, _, _ = _client()

    status = client.unlock_config(1234)

    assert status.unlocked is True


def test_unlock_config_wrong_password_raises() -> None:
    client, _, _ = _client()

    with pytest.raises(ModbusExceptionResponse):
        client.unlock_config(9999)


def test_set_unit_price_updates_live_data() -> None:
    client, _, _ = _client()
    client.unlock_config(1234)

    result = client.set_unit_price(25000)

    assert result.success is True
    assert client.read_live_data().unit_price == 25000


def test_set_hotkey_amount_updates_live_data() -> None:
    client, _, _ = _client()
    client.unlock_config(1234)

    result = client.set_hotkey_amount("F1", 15000)

    assert result.success is True
    assert client.read_live_data().hotkeys["F1"].amount == 15000


def test_set_hotkey_liters_updates_live_data() -> None:
    client, _, _ = _client()
    client.unlock_config(1234)

    result = client.set_hotkey_liters_x1000("F1", 1500)

    assert result.success is True
    assert client.read_live_data().hotkeys["F1"].liters_x1000 == 1500


def test_clear_daily_total_zeroes_daily_data() -> None:
    client, _, _ = _client()
    client.unlock_config(1234)

    result = client.clear_daily_total(verify=True)
    live = client.read_live_data()

    assert result.success is True
    assert live.daily_amount == 0
    assert live.daily_liters_x1000 == 0


def test_set_slave_address_updates_client_and_simulator() -> None:
    client, simulator, transport = _client()
    client.unlock_config(1234)

    result = client.set_slave_address(2)

    assert result.success is True
    assert client.slave_id == 2
    assert simulator.slave_id == 2
    with pytest.raises(ModbusTimeoutError):
        transport.transceive(build_read_request(1, 0x03, 0x0000, 1))
