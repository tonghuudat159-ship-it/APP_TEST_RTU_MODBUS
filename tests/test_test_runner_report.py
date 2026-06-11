import json

from app.report import write_test_report_json, write_test_report_txt
from app.test_runner import PASS, TestRunReport, TestStepResult


def _sample_report() -> TestRunReport:
    return TestRunReport(
        started_at="2026-06-11 10:22:01",
        finished_at="2026-06-11 10:22:04",
        duration_ms=3012.5,
        port="COM5",
        baudrate=9600,
        slave_id=1,
        summary={"PASS": 1, "WARN": 0, "FAIL": 0, "SKIP": 0, "TOTAL": 1},
        device={
            "protocol_version": 7,
            "reported_slave_address": 1,
            "nozzle_status": 0,
            "nozzle_status_text": "nozzle placed / idle",
            "status_flags": "0x0004",
            "status_flag_names": ["storage_ready"],
        },
        results=[
            TestStepResult(
                id="T01",
                name="Serial client initialized",
                status=PASS,
                message="OK",
                duration_ms=1.0,
            )
        ],
        overall_status=PASS,
    )


def test_write_test_report_json(tmp_path) -> None:
    path = tmp_path / "report.json"

    write_test_report_json(path, _sample_report())

    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["summary"]["PASS"] == 1
    assert data["overall_status"] == PASS


def test_write_test_report_txt(tmp_path) -> None:
    path = tmp_path / "report.txt"

    write_test_report_txt(path, _sample_report())

    content = path.read_text(encoding="utf-8")
    assert path.exists()
    assert "Gas Pump Modbus RTU Test Report" in content
    assert "[T01] PASS Serial client initialized - OK" in content
