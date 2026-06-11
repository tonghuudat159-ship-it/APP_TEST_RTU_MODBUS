import json

from app.capture import (
    RawCaptureBuffer,
    RawFrameRecord,
    infer_function_code,
    infer_slave_id,
    write_capture_jsonl,
    write_capture_txt,
)


def _record(direction: str, frame_hex: str) -> RawFrameRecord:
    frame = bytes.fromhex(frame_hex) if frame_hex else b""
    return RawFrameRecord(
        timestamp="2026-06-11 10:22:01.123",
        direction=direction,
        port="COM5",
        slave_id=infer_slave_id(frame),
        function_code=infer_function_code(frame),
        frame_hex=frame_hex,
        frame_len=len(frame),
        crc_valid=True if direction == "RX" and frame else None,
    )


def test_capture_buffer_stores_and_returns_copy() -> None:
    buffer = RawCaptureBuffer()
    tx = _record("TX", "01 03 00 28 00 14 C5 CD")
    rx = _record("RX", "01 03 02 00 07 F9 86")

    buffer.add(tx)
    buffer.add(rx)
    records = buffer.records()
    records.clear()

    assert buffer.records() == [tx, rx]
    assert buffer.to_dicts()[0]["direction"] == "TX"


def test_capture_buffer_discards_oldest() -> None:
    buffer = RawCaptureBuffer(max_records=2)

    buffer.add(_record("TX", "01 03 00 00 00 08 44 0C"))
    buffer.add(_record("RX", "01 03 02 00 07 F9 86"))
    buffer.add(_record("TX", "01 03 00 28 00 14 C5 CD"))

    assert [record.frame_hex for record in buffer.records()] == [
        "01 03 02 00 07 F9 86",
        "01 03 00 28 00 14 C5 CD",
    ]


def test_capture_exports_jsonl_and_txt(tmp_path) -> None:
    records = [
        _record("TX", "01 03 00 28 00 14 C5 CD"),
        _record("RX", "01 03 02 00 07 F9 86"),
    ]
    jsonl_path = tmp_path / "capture.jsonl"
    txt_path = tmp_path / "capture.txt"

    write_capture_jsonl(jsonl_path, records)
    write_capture_txt(txt_path, records)

    json_line = json.loads(jsonl_path.read_text(encoding="utf-8").splitlines()[0])
    txt = txt_path.read_text(encoding="utf-8")
    assert json_line["frame_hex"] == "01 03 00 28 00 14 C5 CD"
    assert "Raw Modbus RTU Capture" in txt
    assert "01 03 02 00 07 F9 86" in txt
