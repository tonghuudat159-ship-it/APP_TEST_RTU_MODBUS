from app.decoders import ConfigStatus, HotkeyPreset, LiveData, QuickStatus
from app.gaspump_client import GasPumpModbusClient
from app.register_map import (
    CONFIG_CLEAR_DAILY,
    CONFIG_CLEAR_DAILY_MAGIC,
    CONFIG_NEW_PASSWORD_HI,
    CONFIG_NEW_PASSWORD_LO,
    CONFIG_UNLOCK_PASSWORD_HI,
    CONFIG_UNLOCK_PASSWORD_LO,
    HOTKEY_AMOUNT_F1_HI,
    HOTKEY_AMOUNT_F1_LO,
    HOTKEY_LITERS_F1_HI,
    HOTKEY_LITERS_F1_LO,
    SLAVE_ADDRESS,
    UNIT_PRICE_HI,
    UNIT_PRICE_LO,
)


class FakeTransport:
    debug = False


class FakeConfigClient(GasPumpModbusClient):
    def __init__(self) -> None:
        super().__init__(FakeTransport(), slave_id=1)
        self.writes: list[tuple[int, int, int]] = []
        self.unit_price = 23000
        self.hotkey_amount = 10000
        self.hotkey_liters_x1000 = 1000

    def write_single_register(self, register_address: int, value: int) -> bool:
        self.writes.append((self.slave_id, register_address, value))
        if register_address == SLAVE_ADDRESS:
            self.reported_slave_id = value
        return True

    def read_config_status(self) -> ConfigStatus:
        return ConfigStatus(value=1, names=["config_unlocked"], unlocked=True)

    def read_holding_registers(self, start_address: int, quantity: int) -> list[int]:
        if start_address == UNIT_PRICE_HI and quantity == 2:
            return [0x0000, self.unit_price]
        return [0] * quantity

    def read_quick_status(self) -> QuickStatus:
        return QuickStatus(
            protocol_version=7,
            slave_address=self.slave_id,
            status_flags=0,
            status_flag_names=[],
            pump_mode=0,
            key_mode=0,
            screen=0,
            selected_field=0,
            nozzle_status=0,
            nozzle_status_text="nozzle placed / idle",
        )

    def read_live_data(self) -> LiveData:
        return LiveData(
            current_amount=0,
            current_liters_x1000=0,
            current_liters=0.0,
            unit_price=self.unit_price,
            target_amount=0,
            target_liters_x1000=0,
            target_liters=0.0,
            daily_amount=0,
            daily_liters_x1000=0,
            daily_liters=0.0,
            total_liters_x1000=0,
            total_liters=0.0,
            hotkeys={
                "F1": HotkeyPreset(
                    amount=self.hotkey_amount,
                    liters_x1000=self.hotkey_liters_x1000,
                    liters=1.0,
                ),
                "F2": HotkeyPreset(0, 0, 0.0),
                "F3": HotkeyPreset(0, 0, 0.0),
                "F4": HotkeyPreset(0, 0, 0.0),
            },
            raw_registers=[0] * 32,
        )


def test_unlock_config_writes_password_hi_then_lo() -> None:
    client = FakeConfigClient()

    client.unlock_config(1234)

    assert client.writes == [
        (1, CONFIG_UNLOCK_PASSWORD_HI, 0x0000),
        (1, CONFIG_UNLOCK_PASSWORD_LO, 0x04D2),
    ]


def test_set_unit_price_writes_hi_then_lo() -> None:
    client = FakeConfigClient()

    client.set_unit_price(23000, verify=False)

    assert client.writes == [
        (1, UNIT_PRICE_HI, 0x0000),
        (1, UNIT_PRICE_LO, 0x59D8),
    ]


def test_set_slave_address_writes_and_updates_client_id() -> None:
    client = FakeConfigClient()

    result = client.set_slave_address(2, verify=False)

    assert result.success is True
    assert client.writes == [(1, SLAVE_ADDRESS, 2)]
    assert client.slave_id == 2


def test_set_hotkey_amount_writes_selected_pair() -> None:
    client = FakeConfigClient()

    client.set_hotkey_amount("F1", 10000, verify=False)

    assert client.writes == [
        (1, HOTKEY_AMOUNT_F1_HI, 0x0000),
        (1, HOTKEY_AMOUNT_F1_LO, 0x2710),
    ]


def test_set_hotkey_liters_writes_selected_pair() -> None:
    client = FakeConfigClient()

    client.set_hotkey_liters_x1000("F1", 1000, verify=False)

    assert client.writes == [
        (1, HOTKEY_LITERS_F1_HI, 0x0000),
        (1, HOTKEY_LITERS_F1_LO, 0x03E8),
    ]


def test_clear_daily_total_writes_magic() -> None:
    client = FakeConfigClient()

    client.clear_daily_total()

    assert client.writes == [(1, CONFIG_CLEAR_DAILY, CONFIG_CLEAR_DAILY_MAGIC)]


def test_change_manager_password_writes_new_password_hi_then_lo() -> None:
    client = FakeConfigClient()

    client.change_manager_password(1234, 5678)

    assert client.writes == [
        (1, CONFIG_UNLOCK_PASSWORD_HI, 0x0000),
        (1, CONFIG_UNLOCK_PASSWORD_LO, 0x04D2),
        (1, CONFIG_NEW_PASSWORD_HI, 0x0000),
        (1, CONFIG_NEW_PASSWORD_LO, 0x162E),
    ]
