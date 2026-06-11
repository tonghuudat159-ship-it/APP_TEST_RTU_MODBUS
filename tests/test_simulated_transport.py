import pytest

from app.capture import RawCaptureBuffer
from app.exceptions import ModbusTimeoutError
from app.modbus_rtu import build_read_request, parse_read_response
from app.simulator import GasPumpSimulator, SimulatedSerialTransport


def test_simulated_transport_open_close() -> None:
    transport = SimulatedSerialTransport()

    assert transport.is_open() is False
    transport.open()
    assert transport.is_open() is True
    transport.close()
    assert transport.is_open() is False


def test_simulated_transport_valid_request() -> None:
    transport = SimulatedSerialTransport(GasPumpSimulator())
    transport.open()

    response = transport.transceive(build_read_request(1, 0x03, 0x0000, 1))

    assert parse_read_response(response, 1, 0x03, expected_quantity=1) == [7]


def test_simulated_transport_wrong_slave_timeout() -> None:
    transport = SimulatedSerialTransport(GasPumpSimulator(slave_id=1))
    transport.open()

    with pytest.raises(ModbusTimeoutError):
        transport.transceive(build_read_request(2, 0x03, 0x0000, 1))


def test_simulated_transport_capture_records_tx_and_rx() -> None:
    capture = RawCaptureBuffer()
    transport = SimulatedSerialTransport(GasPumpSimulator(), capture=capture)
    transport.open()

    transport.transceive(build_read_request(1, 0x03, 0x0000, 1))

    records = capture.records()
    assert [record.direction for record in records] == ["TX", "RX"]
    assert records[1].crc_valid is True


def test_simulated_transport_debug_does_not_crash(capsys) -> None:
    transport = SimulatedSerialTransport(GasPumpSimulator(), debug=True)
    transport.open()

    transport.transceive(build_read_request(1, 0x03, 0x0000, 1))

    output = capsys.readouterr().out
    assert "TX:" in output
    assert "RX:" in output
