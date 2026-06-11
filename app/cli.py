"""Command line interface for the gas pump Modbus RTU tester."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from app.config import (
    DEFAULT_BAUDRATE,
    DEFAULT_SLAVE_ID,
    DEFAULT_TIMEOUT,
)
from app.decoders import (
    LogWindow,
    PumpClock,
    datetime_to_pump_clock,
    encode_clock_registers,
)
from app.exceptions import ModbusError, SerialTransportError
from app.gaspump_client import GasPumpModbusClient
from app.modbus_rtu import READ_HOLDING_REGISTERS, READ_INPUT_REGISTERS
from app.register_map import (
    CLOCK_DAY_HOUR,
    CLOCK_MINUTE_SECOND,
    CLOCK_YEAR_MONTH,
    CONFIG_STATUS_BITS,
    NOZZLE_STATUS_TEXT,
    SENSOR_STATUS_BITS,
)
from app.report import (
    write_json,
    write_logs_csv,
    write_test_report_json,
    write_test_report_txt,
)
from app.serial_transport import SerialTransport
from app.test_runner import GasPumpTestRunner


def parse_int(value: str) -> int:
    """Parse decimal or 0x-prefixed integer CLI input."""
    try:
        return int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid integer: {value}") from exc


def parse_datetime(value: str) -> datetime:
    """Parse supported CLI datetime formats."""
    normalized = value.replace("T", " ")
    try:
        return datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "datetime must use 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DDTHH:MM:SS'"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser."""
    parser = argparse.ArgumentParser(
        prog="gas_pump_modbus_tester",
        description="Test gas pump firmware over Modbus RTU serial.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    read_parser = subparsers.add_parser("read", help="read holding or input registers")
    _add_common_serial_options(read_parser)
    read_parser.add_argument("--addr", required=True, type=parse_int, help="start address")
    read_parser.add_argument("--count", required=True, type=parse_int, help="register count")
    read_parser.add_argument(
        "--function",
        default=READ_HOLDING_REGISTERS,
        type=parse_int,
        choices=(READ_HOLDING_REGISTERS, READ_INPUT_REGISTERS),
        help="read function code: 3 for holding, 4 for input",
    )
    read_parser.set_defaults(handler=handle_read)

    write_parser = subparsers.add_parser("write", help="write a single holding register")
    _add_common_serial_options(write_parser)
    write_parser.add_argument("--addr", required=True, type=parse_int, help="register address")
    write_parser.add_argument("--value", required=True, type=parse_int, help="register value")
    write_parser.set_defaults(handler=handle_write)

    for command, help_text, handler in (
        ("status", "read quick pump status", handle_status),
        ("nozzle", "read nozzle status", handle_nozzle),
        ("sensor", "read sensor snapshot", handle_sensor),
        ("clock", "read pump clock", handle_clock),
        ("fail", "read last fail event", handle_fail),
        ("ping", "check that the device responds", handle_ping),
        ("live", "read live pump data", handle_live),
        ("config-status", "read configuration status", handle_config_status),
    ):
        command_parser = subparsers.add_parser(command, help=help_text)
        _add_common_serial_options(command_parser)
        command_parser.set_defaults(handler=handler)

    clock_set_parser = subparsers.add_parser("clock-set", help="set pump clock")
    _add_common_serial_options(clock_set_parser)
    clock_set_parser.add_argument(
        "--datetime",
        required=True,
        type=parse_datetime,
        help="clock value: YYYY-MM-DD HH:MM:SS",
    )
    clock_set_parser.add_argument("--yes", action="store_true", help="skip confirmation")
    clock_set_parser.set_defaults(handler=handle_clock_set)

    clock_set_now_parser = subparsers.add_parser(
        "clock-set-now",
        help="set pump clock from local system time",
    )
    _add_common_serial_options(clock_set_now_parser)
    clock_set_now_parser.add_argument("--yes", action="store_true", help="skip confirmation")
    clock_set_now_parser.set_defaults(handler=handle_clock_set_now)

    log_latest_parser = subparsers.add_parser("log-latest", help="read latest log entry")
    _add_common_serial_options(log_latest_parser)
    log_latest_parser.set_defaults(handler=handle_log_latest)

    log_read_parser = subparsers.add_parser("log-read", help="read log entry by index")
    _add_common_serial_options(log_read_parser)
    log_read_parser.add_argument("--index", required=True, type=parse_int, help="log index")
    log_read_parser.set_defaults(handler=handle_log_read)

    log_dump_parser = subparsers.add_parser("log-dump", help="dump logs to terminal, JSON, or CSV")
    _add_common_serial_options(log_dump_parser)
    log_dump_parser.add_argument("--limit", type=parse_int, default=None, help="maximum logs to read")
    log_dump_parser.add_argument(
        "--include-invalid",
        action="store_true",
        help="include invalid log windows in output",
    )
    log_dump_parser.add_argument("--json", type=Path, default=None, help="JSON output path")
    log_dump_parser.add_argument("--csv", type=Path, default=None, help="CSV output path")
    log_dump_parser.set_defaults(handler=handle_log_dump)

    test_parser = subparsers.add_parser("test", help="run automated diagnostic tests")
    _add_common_serial_options(test_parser)
    test_parser.add_argument("--out", type=Path, default=None, help="JSON report path")
    test_parser.add_argument("--txt", type=Path, default=None, help="TXT report path")
    test_parser.add_argument(
        "--include-slow-tests",
        action="store_true",
        help="enable wrong slave id timeout test",
    )
    test_parser.add_argument(
        "--expected-version",
        type=parse_int,
        default=7,
        help="expected protocol version",
    )
    test_parser.set_defaults(handler=handle_test)

    return parser


def handle_read(args: argparse.Namespace) -> int:
    """Execute the raw read command."""
    client = _build_client(args)
    if args.function == READ_INPUT_REGISTERS:
        registers = client.read_input_registers(args.addr, args.count)
    else:
        registers = client.read_holding_registers(args.addr, args.count)

    for offset, value in enumerate(registers):
        address = args.addr + offset
        print(f"0x{address:04X}: 0x{value:04X} ({value})")
    return 0


def handle_write(args: argparse.Namespace) -> int:
    """Execute the raw write command."""
    client = _build_client(args)
    valid = client.write_single_register(args.addr, args.value)
    print(f"Write echo valid: {valid}")
    return 0


def handle_status(args: argparse.Namespace) -> int:
    """Print quick pump status."""
    status = _build_client(args).read_quick_status()
    print(f"Protocol version: {status.protocol_version}")
    print(f"Slave address: {status.slave_address}")
    print(f"Status flags: 0x{status.status_flags:04X} {_format_names(status.status_flag_names)}")
    print(f"Pump mode: {status.pump_mode}")
    print(f"Key mode: {status.key_mode}")
    print(f"Screen: {status.screen}")
    print(f"Selected field: {status.selected_field}")
    print(f"Nozzle status: {status.nozzle_status} - {status.nozzle_status_text}")
    return 0


def handle_ping(args: argparse.Namespace) -> int:
    """Print a short response check."""
    status = _build_client(args).ping()
    print("PASS: device responded")
    print(f"Protocol version: {status.protocol_version}")
    print(f"Slave address: {status.slave_address}")
    print(f"Nozzle: {status.nozzle_status} - {status.nozzle_status_text}")
    return 0


def handle_nozzle(args: argparse.Namespace) -> int:
    """Print nozzle status."""
    nozzle_status = _build_client(args).read_nozzle_status()
    text = NOZZLE_STATUS_TEXT.get(nozzle_status, f"unknown nozzle status {nozzle_status}")
    print(f"Nozzle status: {nozzle_status} - {text}")
    return 0


def handle_sensor(args: argparse.Namespace) -> int:
    """Print sensor readings."""
    sensor = _build_client(args).read_sensor_snapshot()
    names = [
        name for bit, name in SENSOR_STATUS_BITS.items() if sensor.sensor_status & bit
    ]
    print(f"Sensor status: 0x{sensor.sensor_status:04X} {_format_names(names)}")
    print(f"MCU temperature: {sensor.mcu_temp_c:.2f} C")
    if sensor.ambient_valid:
        print(f"Ambient temperature: {sensor.ambient_temp_c:.2f} C")
        print(f"Humidity: {sensor.humidity_percent:.2f} %RH")
    else:
        print("Ambient temperature: unavailable")
        print("Humidity: unavailable")
    return 0


def handle_live(args: argparse.Namespace) -> int:
    """Print live pump data."""
    live = _build_client(args).read_live_data()
    print(f"Current amount: {live.current_amount}")
    print(f"Current liters: {live.current_liters:.3f} L")
    print(f"Unit price: {live.unit_price}")
    print(f"Target amount: {live.target_amount}")
    print(f"Target liters: {live.target_liters:.3f} L")
    print(f"Daily amount: {live.daily_amount}")
    print(f"Daily liters: {live.daily_liters:.3f} L")
    print(f"Total liters: {live.total_liters:.3f} L")
    print()
    print("Hotkeys:")
    for name in ("F1", "F2", "F3", "F4"):
        preset = live.hotkeys[name]
        print(f"{name}: amount={preset.amount}, liters={preset.liters:.3f} L")
    return 0


def handle_config_status(args: argparse.Namespace) -> int:
    """Print configuration status."""
    status = _build_client(args).read_config_status()
    names = [name for bit, name in CONFIG_STATUS_BITS.items() if status.value & bit]
    print(f"Config status: 0x{status.value:04X} {_format_names(names)}")
    print(f"Unlocked: {'yes' if status.unlocked else 'no'}")
    return 0


def handle_clock(args: argparse.Namespace) -> int:
    """Print pump clock."""
    clock = _build_client(args).read_clock()
    print(f"Pump clock: {_format_clock(clock)}")
    return 0


def handle_clock_set(args: argparse.Namespace) -> int:
    """Set pump clock from a CLI datetime."""
    clock = datetime_to_pump_clock(args.datetime)
    return _confirm_and_set_clock(args, clock)


def handle_clock_set_now(args: argparse.Namespace) -> int:
    """Set pump clock from system local time."""
    clock = datetime_to_pump_clock(datetime.now().replace(microsecond=0))
    return _confirm_and_set_clock(args, clock)


def handle_fail(args: argparse.Namespace) -> int:
    """Print last fail event."""
    event = _build_client(args).read_fail_event()
    print(f"Fail code: 0x{event.code:04X} - {event.code_text}")
    print(f"Sequence: {event.sequence}")
    return 0


def handle_log_latest(args: argparse.Namespace) -> int:
    """Print the latest log entry."""
    log = _build_client(args).read_log(0)
    _print_log_window(log)
    return 0


def handle_log_read(args: argparse.Namespace) -> int:
    """Print a selected log entry."""
    log = _build_client(args).read_log(args.index)
    _print_log_window(log)
    return 0


def handle_log_dump(args: argparse.Namespace) -> int:
    """Dump logs to terminal or export files."""
    client = _build_client(args)
    log_count = client.read_log_count()
    logs = client.read_all_logs(
        limit=args.limit,
        include_invalid=args.include_invalid,
    )

    if args.json is not None:
        write_json(args.json, logs)
    if args.csv is not None:
        write_logs_csv(args.csv, logs)

    if args.json is None and args.csv is None:
        for log in logs:
            _print_log_window(log)
            print()

    print(f"Log count reported by device: {log_count}")
    print(f"Logs exported: {len(logs)}")
    if args.json is not None:
        print(f"JSON: {args.json}")
    if args.csv is not None:
        print(f"CSV: {args.csv}")
    return 0


def handle_test(args: argparse.Namespace) -> int:
    """Run the automated non-destructive diagnostic suite."""
    transport = SerialTransport(
        port=args.port,
        baudrate=args.baudrate,
        timeout=args.timeout,
        debug=args.debug,
    )
    try:
        transport.open()
    except SerialTransportError as exc:
        print(f"Setup error: {exc}", file=sys.stderr)
        return 2

    try:
        client = GasPumpModbusClient(transport=transport, slave_id=args.slave)
        runner = GasPumpTestRunner(
            client=client,
            port=args.port,
            baudrate=args.baudrate,
            slave_id=args.slave,
            debug=args.debug,
            expected_protocol_version=args.expected_version,
            include_slow_tests=args.include_slow_tests,
        )
        report = runner.run_all()

        if args.out is not None:
            write_test_report_json(args.out, report)
        if args.txt is not None:
            write_test_report_txt(args.txt, report)

        print("Gas Pump Modbus RTU Auto Test")
        print(f"Port: {args.port}")
        print(f"Slave: {args.slave}")
        print()
        print(
            f"PASS: {report.summary.get('PASS', 0)} | "
            f"WARN: {report.summary.get('WARN', 0)} | "
            f"FAIL: {report.summary.get('FAIL', 0)} | "
            f"SKIP: {report.summary.get('SKIP', 0)} | "
            f"TOTAL: {report.summary.get('TOTAL', 0)}"
        )
        print(f"Overall: {report.overall_status}")
        print()
        if args.out is not None:
            print(f"JSON report: {args.out}")
        if args.txt is not None:
            print(f"TXT report: {args.txt}")
        return 1 if report.summary.get("FAIL", 0) else 0
    finally:
        try:
            transport.close()
        except SerialTransportError as exc:
            if args.debug:
                print(f"Warning: failed to close serial transport: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (ModbusError, SerialTransportError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _add_common_serial_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--port", required=True, help="serial port, e.g. COM5")
    parser.add_argument("--slave", type=parse_int, default=DEFAULT_SLAVE_ID, help="slave id")
    parser.add_argument("--baudrate", type=parse_int, default=DEFAULT_BAUDRATE, help="baudrate")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="read timeout seconds")
    parser.add_argument("--debug", action="store_true", help="print raw TX/RX hex")


def _build_client(args: argparse.Namespace) -> GasPumpModbusClient:
    transport = SerialTransport(
        port=args.port,
        baudrate=args.baudrate,
        timeout=args.timeout,
        debug=args.debug,
    )
    return GasPumpModbusClient(transport=transport, slave_id=args.slave)


def _confirm_and_set_clock(args: argparse.Namespace, clock: PumpClock) -> int:
    values = encode_clock_registers(clock)
    print(f"About to set pump clock to: {_format_clock(clock)}")
    print("Registers:")
    print(f"0x{CLOCK_YEAR_MONTH:04X} = 0x{values[0]:04X}")
    print(f"0x{CLOCK_DAY_HOUR:04X} = 0x{values[1]:04X}")
    print(f"0x{CLOCK_MINUTE_SECOND:04X} = 0x{values[2]:04X}")

    if not args.yes:
        confirmation = input("Type YES to continue: ")
        if confirmation != "YES":
            print("Cancelled.")
            return 1

    valid = _build_client(args).set_clock(clock)
    print(f"Clock write valid: {valid}")
    return 0 if valid else 1


def _format_names(names: list[str]) -> str:
    return "[" + ", ".join(names) + "]" if names else "[]"


def _format_clock(clock: PumpClock) -> str:
    return (
        f"{clock.year:04d}-{clock.month:02d}-{clock.day:02d} "
        f"{clock.hour:02d}:{clock.minute:02d}:{clock.second:02d}"
    )


def _print_log_window(log: LogWindow) -> None:
    print(f"Log count: {log.log_count}")
    print(f"Selected index: {log.log_select}")
    print(f"Log status: 0x{log.log_status:04X} {_format_names(log.log_status_names)}")
    print(f"Valid: {'yes' if log.is_valid else 'no'}")
    if not log.is_valid:
        print("Reason: LOG_STATUS is not 0x0007")
        return

    assert log.clock is not None
    print(f"Pump ID: {log.pump_id}")
    print(f"Datetime: {_format_clock(log.clock)}")
    print(f"Sequence: {log.sequence}")
    print(f"Amount: {log.amount}")
    print(f"Liters: {log.liters:.3f}")
    print(f"Unit price: {log.unit_price}")
    print(f"Total liters: {log.total_liters:.3f}")
    print(f"Checksum: 0x{log.checksum:08X}")


if __name__ == "__main__":
    raise SystemExit(main())
