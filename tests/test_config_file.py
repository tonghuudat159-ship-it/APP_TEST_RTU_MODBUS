import argparse

import pytest

from app import cli
from app.app_config_file import ConfigFileError, load_config_file, merge_config_with_args


def test_load_config_file_valid_json(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"port": "COM5", "slave_id": 1}', encoding="utf-8")

    assert load_config_file(path) == {"port": "COM5", "slave_id": 1}


def test_load_config_file_invalid_json(tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{bad", encoding="utf-8")

    with pytest.raises(ConfigFileError):
        load_config_file(path)


def test_merge_config_with_args_cli_priority() -> None:
    args = argparse.Namespace(
        port=None,
        baudrate=9600,
        timeout=0.5,
        slave=1,
        debug=False,
        capture_txt=None,
        capture_jsonl=None,
        out=None,
        txt=None,
    )

    merge_config_with_args(
        {
            "port": "COM7",
            "baudrate": 19200,
            "slave_id": 5,
            "default_report_json": "output/report.json",
        },
        args,
        provided_options={"baudrate"},
    )

    assert args.port == "COM7"
    assert args.baudrate == 9600
    assert args.slave == 5
    assert args.out == "output/report.json"


def test_cli_invalid_config_returns_2(tmp_path, capsys) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{bad", encoding="utf-8")

    assert cli.main(["ping", "--simulate", "--config", str(path)]) == 2
    assert "Config error:" in capsys.readouterr().err
