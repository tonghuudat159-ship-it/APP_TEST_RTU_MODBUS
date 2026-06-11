from app import cli
from app.version import APP_NAME, APP_VERSION


def test_version_command(capsys) -> None:
    assert cli.main(["version"]) == 0
    output = capsys.readouterr().out
    assert APP_NAME in output
    assert APP_VERSION in output
    assert "Python:" in output


def test_smoke_test_command(tmp_path, capsys) -> None:
    assert (
        cli.main(
            [
                "smoke-test",
                "--out",
                str(tmp_path / "smoke.json"),
                "--txt",
                str(tmp_path / "smoke.txt"),
                "--capture-txt",
                str(tmp_path / "smoke_capture.txt"),
                "--capture-jsonl",
                str(tmp_path / "smoke_capture.jsonl"),
            ]
        )
        == 0
    )
    assert "Overall: PASS" in capsys.readouterr().out
    assert (tmp_path / "smoke.json").exists()
    assert (tmp_path / "smoke.txt").exists()
