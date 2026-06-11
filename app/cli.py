"""Command line interface for the gas pump Modbus RTU tester."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from app.capture import (
    RawCaptureBuffer,
    RawFrameRecord,
    write_capture_jsonl,
    write_capture_txt,
)
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
    validate_hotkey_name,
    validate_password,
    validate_slave_id,
    validate_u32,
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
from app.simulator import GasPumpSimulator, SIMULATOR_PROFILES, SimulatedSerialTransport
from app.test_runner import GasPumpTestRunner
from app.troubleshooting import (
    DiagnosticHint,
    diagnose_capture,
    diagnose_exception,
)


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


def parse_slave_range(value: str) -> list[int]:
    """Parse slave id ranges like 1-10 or comma lists like 1,2,5."""
    try:
        if "," in value:
            raw_ids = [int(part.strip(), 0) for part in value.split(",") if part.strip()]
        elif "-" in value:
            start_text, end_text = value.split("-", 1)
            start = int(start_text.strip(), 0)
            end = int(end_text.strip(), 0)
            if start > end:
                raise ValueError("range start must be <= range end")
            raw_ids = list(range(start, end + 1))
        else:
            raw_ids = [int(value, 0)]
    except ValueError as exc:
        raise ValueError(f"invalid slave range: {value}") from exc

    seen: set[int] = set()
    slave_ids: list[int] = []
    for slave_id in raw_ids:
        if not 1 <= slave_id <= 247:
            raise ValueError(f"invalid slave id {slave_id}; valid range is 1..247")
        if slave_id not in seen:
            seen.add(slave_id)
            slave_ids.append(slave_id)
    if not slave_ids:
        raise ValueError("slave range must contain at least one id")
    return slave_ids


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
    write_parser.add_argument("--yes", action="store_true", help="skip confirmation")
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

    unlock_parser = subparsers.add_parser("config-unlock", help="unlock protected config writes")
    _add_common_serial_options(unlock_parser)
    unlock_parser.add_argument("--password", required=True, type=parse_int, help="manager password")
    unlock_parser.add_argument("--no-verify", action="store_true", help="skip CONFIG_STATUS verification")
    unlock_parser.add_argument("--yes", action="store_true", help="skip confirmation")
    unlock_parser.set_defaults(handler=handle_config_unlock)

    unit_price_parser = subparsers.add_parser("config-set-unit-price", help="set pump unit price")
    _add_common_serial_options(unit_price_parser)
    unit_price_parser.add_argument("--password", required=True, type=parse_int, help="manager password")
    unit_price_parser.add_argument("--value", required=True, type=parse_int, help="unit price")
    unit_price_parser.add_argument("--no-verify", action="store_true", help="skip read-back verification")
    unit_price_parser.add_argument("--yes", action="store_true", help="skip confirmation")
    unit_price_parser.set_defaults(handler=handle_config_set_unit_price)

    slave_id_parser = subparsers.add_parser("config-set-slave-id", help="set device slave id")
    _add_common_serial_options(slave_id_parser)
    slave_id_parser.add_argument("--password", required=True, type=parse_int, help="manager password")
    slave_id_parser.add_argument("--new-id", required=True, type=parse_int, help="new slave id")
    slave_id_parser.add_argument("--no-verify", action="store_true", help="skip read-back verification")
    slave_id_parser.add_argument("--yes", action="store_true", help="skip confirmation")
    slave_id_parser.set_defaults(handler=handle_config_set_slave_id)

    hotkey_amount_parser = subparsers.add_parser("config-set-hotkey-amount", help="set hotkey amount")
    _add_common_serial_options(hotkey_amount_parser)
    hotkey_amount_parser.add_argument("--password", required=True, type=parse_int, help="manager password")
    hotkey_amount_parser.add_argument("--key", required=True, help="hotkey F1/F2/F3/F4")
    hotkey_amount_parser.add_argument("--amount", required=True, type=parse_int, help="hotkey amount")
    hotkey_amount_parser.add_argument("--no-verify", action="store_true", help="skip live-data verification")
    hotkey_amount_parser.add_argument("--yes", action="store_true", help="skip confirmation")
    hotkey_amount_parser.set_defaults(handler=handle_config_set_hotkey_amount)

    hotkey_liters_parser = subparsers.add_parser("config-set-hotkey-liters", help="set hotkey liters")
    _add_common_serial_options(hotkey_liters_parser)
    hotkey_liters_parser.add_argument("--password", required=True, type=parse_int, help="manager password")
    hotkey_liters_parser.add_argument("--key", required=True, help="hotkey F1/F2/F3/F4")
    liters_group = hotkey_liters_parser.add_mutually_exclusive_group(required=True)
    liters_group.add_argument("--liters", type=float, help="liters value")
    liters_group.add_argument("--liters-x1000", type=parse_int, help="raw liters_x1000 value")
    hotkey_liters_parser.add_argument("--no-verify", action="store_true", help="skip live-data verification")
    hotkey_liters_parser.add_argument("--yes", action="store_true", help="skip confirmation")
    hotkey_liters_parser.set_defaults(handler=handle_config_set_hotkey_liters)

    clear_daily_parser = subparsers.add_parser("config-clear-daily", help="clear daily amount/liters counters")
    _add_common_serial_options(clear_daily_parser)
    clear_daily_parser.add_argument("--password", required=True, type=parse_int, help="manager password")
    clear_daily_parser.add_argument("--verify", action="store_true", help="verify daily totals are zero")
    clear_daily_parser.add_argument("--yes", action="store_true", help="skip confirmation")
    clear_daily_parser.set_defaults(handler=handle_config_clear_daily)

    password_parser = subparsers.add_parser("config-change-password", help="change manager password")
    _add_common_serial_options(password_parser)
    password_parser.add_argument("--old-password", required=True, type=parse_int, help="old manager password")
    password_parser.add_argument("--new-password", required=True, type=parse_int, help="new manager password")
    password_parser.add_argument("--verify-new-password", action="store_true", help="try unlock with new password")
    password_parser.add_argument("--yes", action="store_true", help="skip confirmation")
    password_parser.set_defaults(handler=handle_config_change_password)

    diagnose_parser = subparsers.add_parser(
        "diagnose",
        help="diagnose hardware communication and capture raw frames",
    )
    _add_common_serial_options(diagnose_parser)
    diagnose_parser.add_argument(
        "--try-slaves",
        type=parse_slave_range,
        default=None,
        metavar="RANGE",
        help="try slave ids, e.g. 1-10 or 1,2,5",
    )
    diagnose_parser.add_argument(
        "--quick",
        action="store_true",
        help="run only the quick response check",
    )
    diagnose_parser.set_defaults(handler=handle_diagnose)

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
    log_dump_parser.add_argument(
        "--strict",
        action="store_true",
        help="fail immediately if any log index cannot be read",
    )
    log_dump_parser.add_argument("--json", type=Path, default=None, help="JSON output path")
    log_dump_parser.add_argument("--csv", type=Path, default=None, help="CSV output path")
    log_dump_parser.set_defaults(handler=handle_log_dump)

    sim_demo_parser = subparsers.add_parser("sim-demo", help="run offline simulator demo")
    sim_demo_parser.add_argument("--slave", type=parse_int, default=DEFAULT_SLAVE_ID, help="slave id")
    sim_demo_parser.add_argument(
        "--sim-profile",
        choices=tuple(SIMULATOR_PROFILES),
        default="normal",
        help="simulator profile",
    )
    sim_demo_parser.add_argument("--debug", action="store_true", help="print raw TX/RX hex")
    sim_demo_parser.add_argument("--capture-jsonl", type=Path, default=None, help="raw capture JSONL output path")
    sim_demo_parser.add_argument("--capture-txt", type=Path, default=None, help="raw capture TXT output path")
    sim_demo_parser.set_defaults(handler=handle_sim_demo)

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
    transport, client = _open_client(args)
    try:
        if args.function == READ_INPUT_REGISTERS:
            registers = client.read_input_registers(args.addr, args.count)
        else:
            registers = client.read_holding_registers(args.addr, args.count)

        for offset, value in enumerate(registers):
            address = args.addr + offset
            print(f"0x{address:04X}: 0x{value:04X} ({value})")
        return 0
    finally:
        _close_transport(transport, args)


def handle_write(args: argparse.Namespace) -> int:
    """Execute the raw write command."""
    if not args.yes:
        print("WARNING: This raw write command can change pump/device state.")
        print(f"Address: 0x{args.addr:04X}")
        print(f"Value: 0x{args.value:04X}")
        confirmation = input("Type YES to continue: ")
        if confirmation != "YES":
            print("Cancelled.")
            return 1

    transport, client = _open_client(args)
    try:
        valid = client.write_single_register(args.addr, args.value)
        print(f"Write echo valid: {valid}")
        return 0
    finally:
        _close_transport(transport, args)


def handle_status(args: argparse.Namespace) -> int:
    """Print quick pump status."""
    transport, client = _open_client(args)
    try:
        status = client.read_quick_status()
        print(f"Protocol version: {status.protocol_version}")
        print(f"Slave address: {status.slave_address}")
        print(f"Status flags: 0x{status.status_flags:04X} {_format_names(status.status_flag_names)}")
        print(f"Pump mode: {status.pump_mode}")
        print(f"Key mode: {status.key_mode}")
        print(f"Screen: {status.screen}")
        print(f"Selected field: {status.selected_field}")
        print(f"Nozzle status: {status.nozzle_status} - {status.nozzle_status_text}")
        return 0
    finally:
        _close_transport(transport, args)


def handle_ping(args: argparse.Namespace) -> int:
    """Print a short response check."""
    transport, client = _open_client(args)
    try:
        status = client.ping()
        print("PASS: device responded")
        print(f"Protocol version: {status.protocol_version}")
        print(f"Slave address: {status.slave_address}")
        print(f"Nozzle: {status.nozzle_status} - {status.nozzle_status_text}")
        return 0
    finally:
        _close_transport(transport, args)


def handle_nozzle(args: argparse.Namespace) -> int:
    """Print nozzle status."""
    transport, client = _open_client(args)
    try:
        nozzle_status = client.read_nozzle_status()
        text = NOZZLE_STATUS_TEXT.get(nozzle_status, f"unknown nozzle status {nozzle_status}")
        print(f"Nozzle status: {nozzle_status} - {text}")
        return 0
    finally:
        _close_transport(transport, args)


def handle_sensor(args: argparse.Namespace) -> int:
    """Print sensor readings."""
    transport, client = _open_client(args)
    try:
        sensor = client.read_sensor_snapshot()
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
    finally:
        _close_transport(transport, args)


def handle_live(args: argparse.Namespace) -> int:
    """Print live pump data."""
    transport, client = _open_client(args)
    try:
        live = client.read_live_data()
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
    finally:
        _close_transport(transport, args)


def handle_config_status(args: argparse.Namespace) -> int:
    """Print configuration status."""
    transport, client = _open_client(args)
    try:
        status = client.read_config_status()
        names = [name for bit, name in CONFIG_STATUS_BITS.items() if status.value & bit]
        print(f"Config status: 0x{status.value:04X} {_format_names(names)}")
        print(f"Unlocked: {'yes' if status.unlocked else 'no'}")
        return 0
    finally:
        _close_transport(transport, args)


def handle_clock(args: argparse.Namespace) -> int:
    """Print pump clock."""
    transport, client = _open_client(args)
    try:
        clock = client.read_clock()
        print(f"Pump clock: {_format_clock(clock)}")
        return 0
    finally:
        _close_transport(transport, args)


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
    transport, client = _open_client(args)
    try:
        event = client.read_fail_event()
        print(f"Fail code: 0x{event.code:04X} - {event.code_text}")
        print(f"Sequence: {event.sequence}")
        return 0
    finally:
        _close_transport(transport, args)


def handle_config_unlock(args: argparse.Namespace) -> int:
    """Unlock protected configuration writes."""
    validate_password(args.password)
    message = (
        "WARNING: This unlock enables protected configuration writes for about 60 seconds.\n"
        f"Password: {mask_password(args.password)}"
    )
    if not require_confirmation(message, args.yes):
        return 1

    def operation(client: GasPumpModbusClient) -> int:
        status = client.unlock_config(args.password, verify=not args.no_verify)
        _print_config_status(status)
        return 0

    return _run_config_action(args, operation)


def handle_config_set_unit_price(args: argparse.Namespace) -> int:
    """Set pump unit price after protected unlock."""
    validate_password(args.password)
    validate_u32(args.value, "unit price")
    message = (
        "WARNING: This changes the pump unit price and writes configuration to EEPROM.\n"
        f"New unit price: {args.value}\n"
        f"Password: {mask_password(args.password)}"
    )
    if not require_confirmation(message, args.yes):
        return 1

    def operation(client: GasPumpModbusClient) -> int:
        client.unlock_config(args.password)
        result = client.set_unit_price(args.value, verify=not args.no_verify)
        _print_write_result(result)
        return 0 if result.success else 1

    return _run_config_action(args, operation)


def handle_config_set_slave_id(args: argparse.Namespace) -> int:
    """Set device slave id after protected unlock."""
    validate_password(args.password)
    validate_slave_id(args.new_id)
    old_id = args.slave
    message = (
        "WARNING: This changes the device slave id.\n"
        "After success, future commands must use the new id.\n"
        "The write ACK is expected from the old slave id.\n"
        f"Old slave id: {old_id}\n"
        f"New slave id: {args.new_id}\n"
        f"Password: {mask_password(args.password)}"
    )
    if not require_confirmation(message, args.yes):
        return 1

    def operation(client: GasPumpModbusClient) -> int:
        client.unlock_config(args.password)
        result = client.set_slave_address(args.new_id, verify=not args.no_verify)
        _print_write_result(result)
        print(f"Old slave id: {old_id}")
        print(f"New slave id: {args.new_id}")
        if getattr(args, "simulate", False):
            print(f"Next command example: python -m app.cli ping --simulate --slave {args.new_id}")
        else:
            print(f"Next command example: python -m app.cli ping --port {args.port} --slave {args.new_id}")
        return 0 if result.success else 1

    return _run_config_action(args, operation)


def handle_config_set_hotkey_amount(args: argparse.Namespace) -> int:
    """Set a hotkey amount after protected unlock."""
    validate_password(args.password)
    hotkey = validate_hotkey_name(args.key)
    validate_u32(args.amount, "hotkey amount")
    message = (
        "WARNING: This changes a pump hotkey amount and writes configuration to EEPROM.\n"
        f"Hotkey: {hotkey}\n"
        f"Amount: {args.amount}\n"
        f"Password: {mask_password(args.password)}"
    )
    if not require_confirmation(message, args.yes):
        return 1

    def operation(client: GasPumpModbusClient) -> int:
        client.unlock_config(args.password)
        result = client.set_hotkey_amount(hotkey, args.amount, verify=not args.no_verify)
        _print_write_result(result)
        return 0 if result.success else 1

    return _run_config_action(args, operation)


def handle_config_set_hotkey_liters(args: argparse.Namespace) -> int:
    """Set a hotkey liters preset after protected unlock."""
    validate_password(args.password)
    hotkey = validate_hotkey_name(args.key)
    if args.liters is not None:
        if args.liters < 0:
            raise ValueError("liters must be >= 0")
        liters_x1000 = validate_u32(round(args.liters * 1000), "liters_x1000")
    else:
        liters_x1000 = validate_u32(args.liters_x1000, "liters_x1000")
    message = (
        "WARNING: This changes a pump hotkey liters preset and writes configuration to EEPROM.\n"
        f"Hotkey: {hotkey}\n"
        f"Liters x1000: {liters_x1000}\n"
        f"Password: {mask_password(args.password)}"
    )
    if not require_confirmation(message, args.yes):
        return 1

    def operation(client: GasPumpModbusClient) -> int:
        client.unlock_config(args.password)
        result = client.set_hotkey_liters_x1000(
            hotkey,
            liters_x1000,
            verify=not args.no_verify,
        )
        _print_write_result(result)
        return 0 if result.success else 1

    return _run_config_action(args, operation)


def handle_config_clear_daily(args: argparse.Namespace) -> int:
    """Clear daily total counters after protected unlock."""
    validate_password(args.password)
    message = (
        "WARNING: This clears daily amount/liters counters.\n"
        "This cannot be undone.\n"
        f"Password: {mask_password(args.password)}"
    )
    if not require_confirmation(message, args.yes):
        return 1

    def operation(client: GasPumpModbusClient) -> int:
        client.unlock_config(args.password)
        result = client.clear_daily_total(verify=args.verify)
        _print_write_result(result)
        return 0 if result.success else 1

    return _run_config_action(args, operation)


def handle_config_change_password(args: argparse.Namespace) -> int:
    """Change manager password after protected unlock."""
    validate_password(args.old_password, "old password")
    validate_password(args.new_password, "new password")
    message = (
        "WARNING: This changes the manager password.\n"
        "Losing the password may prevent future Modbus config writes.\n"
        f"Old password: {mask_password(args.old_password)}\n"
        f"New password: {mask_password(args.new_password)}"
    )
    if not require_confirmation(message, args.yes):
        return 1

    def operation(client: GasPumpModbusClient) -> int:
        result = client.change_manager_password(
            args.old_password,
            args.new_password,
            verify_unlock_new=args.verify_new_password,
        )
        _print_write_result(result)
        return 0 if result.success else 1

    return _run_config_action(args, operation)


def handle_diagnose(args: argparse.Namespace) -> int:
    """Run a non-destructive hardware diagnosis."""
    if getattr(args, "_capture_buffer", None) is None:
        args._capture_buffer = RawCaptureBuffer()
    print("Gas Pump Modbus RTU Diagnose")
    print(f"Port: {_display_port(args)}")
    print(f"Baudrate: {args.baudrate} 8N1")
    print(f"Requested slave: {args.slave}")
    print()

    try:
        transport, client = _open_client(args)
    except SerialTransportError as exc:
        print("Result: FAIL")
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        _print_hints(diagnose_exception(exc))
        export_capture_from_args(args, getattr(args, "_capture_buffer", None))
        return 2

    try:
        if args.try_slaves:
            return _handle_diagnose_try_slaves(args, transport)
        status = client.ping()
        print("Result: PASS")
        print("Device responded.")
        print(f"Protocol version: {status.protocol_version}")
        print(f"Reported slave address: {status.slave_address}")
        print(f"Nozzle: {status.nozzle_status} - {status.nozzle_status_text}")
        print(f"Status flags: 0x{status.status_flags:04X} {_format_names(status.status_flag_names)}")
        return 0
    except Exception as exc:
        print("Result: FAIL")
        print(f"Error: {type(exc).__name__}: {exc}")
        hints = diagnose_exception(exc) + diagnose_capture(_capture_records(args))
        _print_hints(hints)
        _print_raw_capture_summary(_capture_records(args))
        return 1
    finally:
        _close_transport(transport, args)


def handle_log_latest(args: argparse.Namespace) -> int:
    """Print the latest log entry."""
    transport, client = _open_client(args)
    try:
        log = client.read_log(0)
        _print_log_window(log)
        return 0
    finally:
        _close_transport(transport, args)


def handle_log_read(args: argparse.Namespace) -> int:
    """Print a selected log entry."""
    transport, client = _open_client(args)
    try:
        log = client.read_log(args.index)
        _print_log_window(log)
        return 0
    finally:
        _close_transport(transport, args)


def handle_log_dump(args: argparse.Namespace) -> int:
    """Dump logs to terminal or export files."""
    transport, client = _open_client(args)
    try:
        log_count = client.read_log_count()
        logs = client.read_all_logs(
            limit=args.limit,
            include_invalid=args.include_invalid,
            strict=args.strict,
        )

        if args.json is not None:
            if not _write_export_file(args.json, write_json, args.json, logs):
                return 2
        if args.csv is not None:
            if not _write_export_file(args.csv, write_logs_csv, args.csv, logs):
                return 2

        if args.json is None and args.csv is None:
            for log in logs:
                _print_log_window(log)
                print()

        _print_log_read_warnings(client.last_log_read_errors)
        print(f"Log count reported by device: {log_count}")
        print(f"Logs exported: {len(logs)}")
        if args.json is not None:
            print(f"JSON: {args.json}")
        if args.csv is not None:
            print(f"CSV: {args.csv}")
        return 0
    finally:
        _close_transport(transport, args)


def handle_test(args: argparse.Namespace) -> int:
    """Run the automated non-destructive diagnostic suite."""
    capture = create_capture_from_args(args)
    transport = create_transport_from_args(args, capture)
    try:
        transport.open()
    except SerialTransportError as exc:
        print(f"Setup error: {exc}", file=sys.stderr)
        return 2

    try:
        client = GasPumpModbusClient(transport=transport, slave_id=args.slave)
        runner = GasPumpTestRunner(
            client=client,
            port=_display_port(args),
            baudrate=args.baudrate,
            slave_id=args.slave,
            debug=args.debug,
            expected_protocol_version=args.expected_version,
            include_slow_tests=args.include_slow_tests,
            capture=capture,
        )
        report = runner.run_all()

        if args.out is not None:
            if not _write_report_file(args.out, write_test_report_json, args.out, report):
                return 2
        if args.txt is not None:
            if not _write_report_file(args.txt, write_test_report_txt, args.txt, report):
                return 2

        print("Gas Pump Modbus RTU Auto Test")
        print(f"Port: {_display_port(args)}")
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
        export_capture_from_args(args, capture)


def handle_sim_demo(args: argparse.Namespace) -> int:
    """Run an offline simulator demonstration."""
    args.simulate = True
    args.port = "SIM"
    args.timeout = DEFAULT_TIMEOUT
    args.baudrate = DEFAULT_BAUDRATE
    capture = create_capture_from_args(args)
    transport = create_transport_from_args(args, capture)
    transport.open()
    try:
        client = GasPumpModbusClient(transport=transport, slave_id=args.slave)
        print("Gas Pump Modbus RTU Simulator Demo")
        print("==================================")
        print()
        print(f"Profile: {args.sim_profile}")
        print(f"Slave: {args.slave}")
        print()

        print("[1] Ping")
        status = client.ping()
        print("PASS: device responded")
        print(f"Protocol version: {status.protocol_version}")
        print()

        print("[2] Status")
        print(f"Status flags: 0x{status.status_flags:04X} {_format_names(status.status_flag_names)}")
        print(f"Nozzle: {status.nozzle_status} - {status.nozzle_status_text}")
        print()

        print("[3] Live data")
        live = client.read_live_data()
        print(f"Current amount: {live.current_amount}")
        print(f"Current liters: {live.current_liters:.3f} L")
        print(f"Unit price: {live.unit_price}")
        print()

        print("[4] Sensor")
        sensor = client.read_sensor_snapshot()
        print(f"MCU temperature: {sensor.mcu_temp_c:.2f} C")
        print(f"Ambient valid: {'yes' if sensor.ambient_valid else 'no'}")
        print()

        print("[5] Clock")
        print(f"Pump clock: {_format_clock(client.read_clock())}")
        print()

        print("[6] Fail event")
        fail = client.read_fail_event()
        print(f"Fail code: 0x{fail.code:04X} - {fail.code_text}")
        print()

        print("[7] Latest log")
        try:
            _print_log_window(client.read_log(0))
        except ValueError as exc:
            print(f"SKIP: {exc}")
        print()

        print("[8] Log dump limit 3")
        logs = client.read_all_logs(limit=3, include_invalid=True)
        print(f"Logs read: {len(logs)}")
        print()

        print("[9] Auto test")
        report = GasPumpTestRunner(
            client=client,
            port="SIM",
            baudrate=DEFAULT_BAUDRATE,
            slave_id=args.slave,
            debug=args.debug,
            capture=capture,
        ).run_all()
        print(
            f"PASS: {report.summary.get('PASS', 0)} | "
            f"WARN: {report.summary.get('WARN', 0)} | "
            f"FAIL: {report.summary.get('FAIL', 0)} | "
            f"SKIP: {report.summary.get('SKIP', 0)} | "
            f"TOTAL: {report.summary.get('TOTAL', 0)}"
        )
        print(f"Overall: {report.overall_status}")
        return 0 if report.overall_status == "PASS" else 1
    finally:
        _close_transport(transport, args)


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
    parser.add_argument("--port", default=None, help="serial port, e.g. COM5")
    parser.add_argument("--slave", type=parse_int, default=DEFAULT_SLAVE_ID, help="slave id")
    parser.add_argument("--baudrate", type=parse_int, default=DEFAULT_BAUDRATE, help="baudrate")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="read timeout seconds")
    parser.add_argument("--debug", action="store_true", help="print raw TX/RX hex")
    parser.add_argument("--capture-jsonl", type=Path, default=None, help="raw capture JSONL output path")
    parser.add_argument("--capture-txt", type=Path, default=None, help="raw capture TXT output path")
    parser.add_argument("--simulate", action="store_true", help="use offline simulator instead of a COM port")
    parser.add_argument(
        "--sim-profile",
        choices=tuple(SIMULATOR_PROFILES),
        default="normal",
        help="simulator profile",
    )


def _open_client(args: argparse.Namespace) -> tuple[SerialTransport, GasPumpModbusClient]:
    capture = create_capture_from_args(args)
    transport = create_transport_from_args(args, capture)
    transport.open()
    return transport, GasPumpModbusClient(transport=transport, slave_id=args.slave)


def _build_client(args: argparse.Namespace) -> GasPumpModbusClient:
    """Build a client without opening its transport.

    Kept for compatibility with tests or external callers; CLI handlers should
    prefer _open_client so the transport can be closed in a finally block.
    """
    transport = create_transport_from_args(args, create_capture_from_args(args))
    return GasPumpModbusClient(transport=transport, slave_id=args.slave)


def create_transport_from_args(
    args: argparse.Namespace,
    capture: RawCaptureBuffer | None = None,
):
    if getattr(args, "simulate", False):
        simulator = GasPumpSimulator(
            slave_id=args.slave,
            profile=getattr(args, "sim_profile", "normal"),
        )
        return SimulatedSerialTransport(
            simulator=simulator,
            port="SIM",
            timeout=args.timeout,
            debug=args.debug,
            capture=capture,
        )
    if not args.port:
        raise SerialTransportError("--port is required unless --simulate is used")
    return SerialTransport(
        port=args.port,
        baudrate=args.baudrate,
        timeout=args.timeout,
        debug=args.debug,
        capture=capture,
    )


def _display_port(args: argparse.Namespace) -> str:
    if getattr(args, "simulate", False):
        return "SIM"
    return args.port or ""


def _close_transport(transport: SerialTransport, args: argparse.Namespace) -> None:
    try:
        transport.close()
    except SerialTransportError as exc:
        if args.debug:
            print(f"Warning: failed to close serial transport: {exc}", file=sys.stderr)
    export_result = export_capture_from_args(args, getattr(args, "_capture_buffer", None))
    if export_result:
        args._capture_export_result = export_result


def require_confirmation(message: str, yes: bool = False) -> bool:
    if yes:
        return True
    print(message)
    confirmation = input("Type YES to continue: ")
    if confirmation != "YES":
        print("Cancelled.")
        return False
    return True


def mask_password(value: int) -> str:
    return "*" * max(1, len(str(value)))


def _run_config_action(args: argparse.Namespace, operation) -> int:
    transport = None
    result = 1
    try:
        transport, client = _open_client(args)
        result = operation(client)
    except SerialTransportError as exc:
        print(f"ERROR: Serial/setup problem: {exc}", file=sys.stderr)
        _print_hints(diagnose_exception(exc))
        result = 2
    except ModbusError as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        _print_hints(diagnose_exception(exc))
        result = 1
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        result = 1
    finally:
        if transport is not None:
            _close_transport(transport, args)
        else:
            export_capture_from_args(args, getattr(args, "_capture_buffer", None))
    if getattr(args, "_capture_export_result", 0):
        return 2
    return result


def _print_config_status(status) -> None:
    print(f"Config status: 0x{status.value:04X} {_format_names(status.names)}")
    print(f"Unlocked: {'yes' if status.unlocked else 'no'}")


def _print_write_result(result) -> None:
    print(f"Result: {'PASS' if result.success else 'FAIL'}")
    print(result.message)
    verified = result.details.get("verified")
    if verified is not None:
        print(f"Verified: {'yes' if verified else 'no'}")
    for key, value in result.details.items():
        if "password" in key:
            print(f"{key}: {value}")


def create_capture_from_args(args: argparse.Namespace) -> RawCaptureBuffer | None:
    if getattr(args, "_capture_buffer", None) is not None:
        return args._capture_buffer
    if getattr(args, "capture_jsonl", None) is None and getattr(args, "capture_txt", None) is None:
        return None
    args._capture_buffer = RawCaptureBuffer()
    return args._capture_buffer


def export_capture_from_args(
    args: argparse.Namespace,
    capture: RawCaptureBuffer | None,
) -> int:
    if capture is None or getattr(args, "_capture_exported", False):
        return 0
    result = 0
    records = capture.records()
    if getattr(args, "capture_jsonl", None) is not None:
        try:
            write_capture_jsonl(args.capture_jsonl, records)
        except OSError as exc:
            print(
                f"ERROR: Failed to write capture file {args.capture_jsonl}: {exc}",
                file=sys.stderr,
            )
            result = 2
    if getattr(args, "capture_txt", None) is not None:
        try:
            write_capture_txt(args.capture_txt, records)
        except OSError as exc:
            print(
                f"ERROR: Failed to write capture file {args.capture_txt}: {exc}",
                file=sys.stderr,
            )
            result = 2
    args._capture_exported = True
    return result


def _capture_records(args: argparse.Namespace) -> list[RawFrameRecord]:
    capture = getattr(args, "_capture_buffer", None)
    return capture.records() if capture is not None else []


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

    transport, client = _open_client(args)
    try:
        valid = client.set_clock(clock)
        print(f"Clock write valid: {valid}")
        return 0 if valid else 1
    finally:
        _close_transport(transport, args)


def _write_export_file(path: Path, writer, *writer_args) -> bool:
    try:
        writer(*writer_args)
        return True
    except OSError as exc:
        print(f"ERROR: Failed to write export file {path}: {exc}", file=sys.stderr)
        return False


def _write_report_file(path: Path, writer, *writer_args) -> bool:
    try:
        writer(*writer_args)
        return True
    except OSError as exc:
        print(f"ERROR: Failed to write report file {path}: {exc}", file=sys.stderr)
        return False


def _print_log_read_warnings(errors: list[dict[str, str]]) -> None:
    if not errors:
        return
    print(f"WARNING: {len(errors)} log indices failed and were skipped.")
    for error in errors:
        print(
            f"- index={error['index']} "
            f"{error['error_type']}: {error['error_message']}"
        )


def _handle_diagnose_try_slaves(
    args: argparse.Namespace,
    transport: SerialTransport,
) -> int:
    last_error: Exception | None = None
    for slave_id in args.try_slaves:
        client = GasPumpModbusClient(transport=transport, slave_id=slave_id)
        try:
            status = client.read_quick_status()
        except Exception as exc:
            last_error = exc
            continue
        print("Result: PASS")
        print(f"Discovered slave id: {slave_id}")
        print(f"Protocol version: {status.protocol_version}")
        print(f"Reported slave address: {status.slave_address}")
        print(f"Nozzle: {status.nozzle_status} - {status.nozzle_status_text}")
        return 0

    print("Result: FAIL")
    print(f"No responding slave found in: {','.join(str(value) for value in args.try_slaves)}")
    hints: list[DiagnosticHint] = []
    if last_error is not None:
        print(f"Last error: {type(last_error).__name__}: {last_error}")
        hints.extend(diagnose_exception(last_error))
    hints.extend(diagnose_capture(_capture_records(args)))
    _print_hints(hints)
    _print_raw_capture_summary(_capture_records(args))
    return 1


def _print_hints(hints: list[DiagnosticHint]) -> None:
    if not hints:
        return
    print()
    print("Likely causes:")
    for hint in hints:
        print(f"[{hint.severity}] {hint.title}")
        if hint.explanation:
            print(hint.explanation)
        for action in hint.suggested_actions:
            print(f"- {action}")
        print()


def _print_raw_capture_summary(records: list[RawFrameRecord]) -> None:
    if not records:
        return
    print("Raw capture:")
    for record in records:
        frame = record.frame_hex if record.frame_hex else "<none>"
        print(f"{record.direction} {frame}")


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
