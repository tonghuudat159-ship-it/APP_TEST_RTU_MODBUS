import argparse

import pytest

from app import cli
from app.config_models import WriteResult
from app.decoders import ConfigStatus


class FakeTransport:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeConfigClient:
    def __init__(self) -> None:
        self.unlocked = False
        self.unit_price_calls: list[int] = []
        self.new_slave_ids: list[int] = []

    def unlock_config(self, password: int, verify: bool = True) -> ConfigStatus:
        self.unlocked = True
        return ConfigStatus(value=1, names=["config_unlocked"], unlocked=True)

    def set_unit_price(self, value: int, verify: bool = True) -> WriteResult:
        self.unit_price_calls.append(value)
        return WriteResult("set_unit_price", True, "Unit price updated", {"verified": not not verify})

    def set_slave_address(self, new_slave_id: int, verify: bool = True) -> WriteResult:
        self.new_slave_ids.append(new_slave_id)
        return WriteResult("set_slave_address", True, "Slave id updated", {"verified": not not verify})

    def clear_daily_total(self, verify: bool = False) -> WriteResult:
        return WriteResult("clear_daily_total", True, "Daily total clear command sent", {"verified": verify})

    def change_manager_password(
        self,
        old_password: int,
        new_password: int,
        verify_unlock_new: bool = False,
    ) -> WriteResult:
        return WriteResult(
            "change_manager_password",
            True,
            "Manager password updated",
            {"old_password": "****", "new_password": "****", "verified": verify_unlock_new},
        )


def _base_args(**overrides) -> argparse.Namespace:
    values = {
        "port": "COM5",
        "slave": 1,
        "baudrate": 9600,
        "timeout": 0.5,
        "debug": False,
        "capture_jsonl": None,
        "capture_txt": None,
        "password": 1234,
        "no_verify": False,
        "yes": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_config_command_cancel_does_not_open(monkeypatch, capsys) -> None:
    opened = False

    def fake_open_client(args):
        nonlocal opened
        opened = True
        return FakeTransport(), FakeConfigClient()

    monkeypatch.setattr(cli, "_open_client", fake_open_client)
    monkeypatch.setattr("builtins.input", lambda prompt: "NO")

    rc = cli.handle_config_set_unit_price(_base_args(value=23000))

    assert rc == 1
    assert opened is False
    output = capsys.readouterr().out
    assert "Cancelled." in output
    assert "1234" not in output
    assert "****" in output


def test_config_yes_bypasses_prompt(monkeypatch) -> None:
    transport = FakeTransport()
    client = FakeConfigClient()

    def fake_open_client(args):
        return transport, client

    def fail_input(prompt):
        raise AssertionError("input should not be called")

    monkeypatch.setattr(cli, "_open_client", fake_open_client)
    monkeypatch.setattr("builtins.input", fail_input)

    rc = cli.handle_config_set_unit_price(_base_args(value=23000, yes=True))

    assert rc == 0
    assert client.unit_price_calls == [23000]
    assert transport.closed is True


def test_config_password_not_printed_on_success(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "_open_client",
        lambda args: (FakeTransport(), FakeConfigClient()),
    )

    rc = cli.handle_config_change_password(
        _base_args(old_password=1234, new_password=5678, verify_new_password=False, yes=True)
    )

    assert rc == 0
    output = capsys.readouterr().out
    assert "1234" not in output
    assert "5678" not in output


def test_invalid_slave_id_fails_before_open(monkeypatch, capsys) -> None:
    opened = False

    def fake_open_client(args):
        nonlocal opened
        opened = True
        return FakeTransport(), FakeConfigClient()

    monkeypatch.setattr(cli, "_open_client", fake_open_client)

    rc = cli.main(
        [
            "config-set-slave-id",
            "--port",
            "COM5",
            "--slave",
            "1",
            "--password",
            "1234",
            "--new-id",
            "248",
            "--yes",
        ]
    )

    assert rc == 1
    assert opened is False
    assert "slave id must be in range" in capsys.readouterr().err


def test_hotkey_liters_requires_exactly_one_value() -> None:
    parser = cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "config-set-hotkey-liters",
                "--port",
                "COM5",
                "--password",
                "1234",
                "--key",
                "F1",
            ]
        )
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "config-set-hotkey-liters",
                "--port",
                "COM5",
                "--password",
                "1234",
                "--key",
                "F1",
                "--liters",
                "1.0",
                "--liters-x1000",
                "1000",
            ]
        )


def test_clear_daily_warning_contains_cannot_be_undone(monkeypatch, capsys) -> None:
    monkeypatch.setattr("builtins.input", lambda prompt: "NO")

    rc = cli.handle_config_clear_daily(_base_args(verify=False))

    assert rc == 1
    assert "cannot be undone" in capsys.readouterr().out.lower()


def test_set_slave_id_output_mentions_new_id_next_command(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "_open_client",
        lambda args: (FakeTransport(), FakeConfigClient()),
    )

    rc = cli.handle_config_set_slave_id(_base_args(new_id=2, yes=True))

    assert rc == 0
    output = capsys.readouterr().out
    assert "--slave 2" in output
    assert "New slave id: 2" in output
