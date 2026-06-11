from app import cli


def test_ping_help_includes_simulate(capsys) -> None:
    parser = cli.build_parser()

    try:
        parser.parse_args(["ping", "--help"])
    except SystemExit as exc:
        assert exc.code == 0

    assert "--simulate" in capsys.readouterr().out


def test_ping_simulate(capsys) -> None:
    assert cli.main(["ping", "--simulate", "--slave", "1"]) == 0
    assert "PASS: device responded" in capsys.readouterr().out


def test_live_simulate(capsys) -> None:
    assert cli.main(["live", "--simulate", "--slave", "1"]) == 0
    assert "Unit price: 23000" in capsys.readouterr().out


def test_log_latest_simulate(capsys) -> None:
    assert cli.main(["log-latest", "--simulate", "--slave", "1"]) == 0
    assert "Valid: yes" in capsys.readouterr().out


def test_test_runner_simulate(capsys) -> None:
    assert cli.main(["test", "--simulate", "--slave", "1"]) == 0
    assert "Overall: PASS" in capsys.readouterr().out


def test_sim_demo(capsys) -> None:
    assert cli.main(["sim-demo"]) == 0
    output = capsys.readouterr().out
    assert "Gas Pump Modbus RTU Simulator Demo" in output
    assert "Overall: PASS" in output


def test_simulate_capture_export(tmp_path) -> None:
    capture_path = tmp_path / "ping_capture.txt"

    assert cli.main(["ping", "--simulate", "--slave", "1", "--capture-txt", str(capture_path)]) == 0

    text = capture_path.read_text(encoding="utf-8")
    assert "Raw Modbus RTU Capture" in text
    assert "TX" in text
    assert "RX" in text
