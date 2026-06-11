# Phase 1-5 Review Report

## Test result

- `pytest`: could not run because `pytest` is not recognized on PATH.
- `python -m pytest`: passed.
- Result: 57 passed, 0 failed.
- Test command details: Python 3.14.4, pytest 9.0.3, collected 57 tests from `tests/`.

The test suite covers CRC vectors, Modbus frame builders/parsers, register-map constants, basic decoders, clock helpers, report export helpers, and test-runner behavior with fake clients.

## CLI command availability

Top-level command checked:

- `python -m app.cli --help`: OK.

Requested subcommand help checks:

- `python -m app.cli read --help`: OK.
- `python -m app.cli write --help`: OK.
- `python -m app.cli ping --help`: OK.
- `python -m app.cli status --help`: OK.
- `python -m app.cli live --help`: OK.
- `python -m app.cli sensor --help`: OK.
- `python -m app.cli clock --help`: OK.
- `python -m app.cli clock-set --help`: OK.
- `python -m app.cli clock-set-now --help`: OK.
- `python -m app.cli log-latest --help`: OK.
- `python -m app.cli log-read --help`: OK.
- `python -m app.cli log-dump --help`: OK.
- `python -m app.cli test --help`: OK.

Additional Phase 3 expected commands checked:

- `python -m app.cli nozzle --help`: OK.
- `python -m app.cli fail --help`: OK.

No expected CLI command was missing or broken during help inspection.

## Implemented features by phase

### Phase 1 - Project skeleton

Implemented.

Expected files exist:

- `README.md`
- `requirements.txt`
- `pyproject.toml`
- `app/__init__.py`
- `app/cli.py`
- `app/config.py`
- `app/serial_transport.py`
- `app/modbus_rtu.py`
- `app/register_map.py`
- `app/decoders.py`
- `app/gaspump_client.py`
- `app/test_runner.py`
- `app/report.py`
- `app/exceptions.py`
- `tests/`

Additional files/directories present:

- `MODBUS_RTU_GUIDE.md`
- `.pytest_cache/`
- `app/__pycache__/`
- `tests/__pycache__/`

The source layout is organized around the planned modules.

### Phase 2 - Modbus RTU core

Mostly implemented.

- Custom exceptions exist: `ModbusError`, `ModbusTimeoutError`, `ModbusCrcError`, `ModbusExceptionResponse`, `ModbusFrameError`, `SerialTransportError`.
- Default config values match the expected serial settings:
  - `DEFAULT_BAUDRATE = 9600`
  - `DEFAULT_BYTESIZE = 8`
  - `DEFAULT_PARITY = "N"`
  - `DEFAULT_STOPBITS = 1`
  - `DEFAULT_TIMEOUT = 0.5`
  - `DEFAULT_FRAME_GAP_SECONDS = 0.005`
  - `DEFAULT_SLAVE_ID = 1`
- Manual Modbus RTU helpers exist:
  - `crc16_modbus`
  - `append_crc`
  - `verify_crc`
  - `bytes_to_hex`
  - `build_read_request`
  - `build_write_single_register_request`
  - `parse_read_response`
  - `parse_write_single_register_response`
- CRC is appended low byte first, high byte second.
- CRC vectors are covered by tests, including:
  - `01 03 00 28 00 14 C5 CD`
  - `01 06 00 2A 00 00 A8 02`
  - `01 03 00 07 00 01 35 CB`
  - `01 03 00 3C 00 03 C5 C7`
- `SerialTransport` implements `open`, `close`, `is_open`, and `transceive`.
- `GasPumpModbusClient` implements `read_holding_registers`, `read_input_registers`, and `write_single_register`.
- Basic `read` and `write` CLI commands exist.

### Phase 3 - Register map and decoders

Implemented.

Expected block constants exist and match:

- `QUICK_STATUS_START = 0x0000`, `QUICK_STATUS_COUNT = 8`
- `LIVE_DATA_START = 0x0008`, `LIVE_DATA_COUNT = 32`
- `LOG_WINDOW_START = 0x0028`, `LOG_WINDOW_COUNT = 20`
- `CLOCK_START = 0x003C`, `CLOCK_COUNT = 3`
- `SENSOR_START = 0x003F`, `SENSOR_COUNT = 4`
- `CONFIG_STATUS_START = 0x0043`, `CONFIG_STATUS_COUNT = 1`
- `FAIL_EVENT_START = 0x0049`, `FAIL_EVENT_COUNT = 2`

Expected dataclasses exist:

- `QuickStatus`
- `SensorSnapshot`
- `PumpClock`
- `LogWindow`
- `FailEvent`

Expected helper functions exist:

- `as_u16`
- `as_i16`
- `u32_from_registers`
- `split_u32`
- `high_byte`
- `low_byte`
- `decode_bitmask`
- `decode_temperature_c_x100`
- `decode_humidity_x100`
- `decode_clock_registers`
- `encode_clock_registers`
- `decode_quick_status`
- `decode_sensor_snapshot`
- `decode_log_window`
- `decode_fail_event`

Important decoding behavior appears correct:

- `u32_from_registers(hi, lo)` uses `(HI << 16) | LO`.
- signed int16 temperature decoding is used for temperature fields.
- humidity is unsigned and divided by 100.
- `PumpClock.year` is decoded as a full year, for example `2026`.
- log payload fields are only decoded when `LOG_STATUS == 0x0007`; invalid log windows return safe empty payload fields.

Expected Phase 3 CLI commands exist:

- `status`
- `nozzle`
- `sensor`
- `clock`
- `fail`
- `log-latest`
- `log-read`

### Phase 4 - High-level workflows, live data, set clock, log dump

Mostly implemented.

Expected additional dataclasses exist:

- `HotkeyPreset`
- `LiveData`
- `ConfigStatus`

Expected decoders exist:

- `decode_live_data`
- `decode_config_status`

Expected clock helpers exist:

- `pump_clock_to_datetime`
- `datetime_to_pump_clock`

Expected client methods exist:

- `read_live_data`
- `read_config_status`
- `set_clock`
- `set_clock_from_datetime`
- `set_clock_now`
- `read_all_logs`
- `ping`

Clock write order is correct:

1. `0x003C CLOCK_YEAR_MONTH`
2. `0x003D CLOCK_DAY_HOUR`
3. `0x003E CLOCK_MINUTE_SECOND`

Log read workflow is implemented:

1. Read `LOG_COUNT`.
2. Write `LOG_SELECT = index`.
3. Read full log window.
4. Decode payload only when `LOG_STATUS == 0x0007`.

Expected report/export helpers exist:

- `dataclass_to_dict`
- `write_json`
- `write_logs_csv`

Expected Phase 4 CLI commands exist:

- `ping`
- `live`
- `config-status`
- `clock-set`
- `clock-set-now`
- `log-dump`

Clock writes ask for confirmation unless `--yes` is provided.

### Phase 5 - Auto test runner and PASS/FAIL report

Implemented.

Expected files exist:

- `app/test_runner.py`
- `app/report.py`

Expected dataclasses exist:

- `TestStepResult`
- `TestRunReport`

Expected runner exists:

- `GasPumpTestRunner.run_all()`

Expected status values exist:

- `PASS`
- `FAIL`
- `SKIP`
- `WARN`

Expected test cases T01 through T19 are present:

- T01 Serial client initialized
- T02 Read quick status
- T03 Protocol version check
- T04 Slave address check
- T05 Status flags sanity
- T06 Nozzle status sanity
- T07 Read live data
- T08 Live data sanity
- T09 Read sensor snapshot
- T10 Sensor sanity
- T11 Read pump clock
- T12 Read fail event
- T13 Read log count
- T14 Select latest log
- T15 Read latest log window
- T16 Read all logs limited
- T17 Illegal address exception test
- T18 Wrong slave id no-response test
- T19 Config status read

Expected report helpers exist:

- `write_test_report_json`
- `write_test_report_txt`

Expected CLI command exists:

- `python -m app.cli test --port COM5 --slave 1 --out output/report.json --txt output/report.txt`

Expected options exist:

- `--out PATH`
- `--txt PATH`
- `--include-slow-tests`
- `--expected-version 7`
- `--debug`

Expected exit-code behavior is implemented in `handle_test`:

- returns `0` if there are no `FAIL` results.
- returns `1` if at least one test result is `FAIL`.
- returns `2` if serial setup fails before the runner starts.

The default auto test does not perform dangerous writes. It writes `LOG_SELECT` only as part of log inspection.

## Missing features or deviations

- Bare `pytest` is not available on PATH in the current environment. The fallback `python -m pytest` works.
- `GasPumpModbusClient.read_log(index)` reads `LOG_COUNT` but does not validate `index` against the reported log count before writing `LOG_SELECT`.
- Raw CLI `write` performs a register write without confirmation. This was expected as a Phase 2 command, but it is still an operational safety deviation compared with the more guarded clock commands.
- Most non-test CLI commands build a serial transport lazily and do not explicitly close it. The process exit will normally release the handle, but explicit close behavior would be cleaner for repeated/integrated use.
- `parse_read_response` validates frame shape, CRC, slave id, function code, and byte count consistency, but it does not validate the response register count against the request count because the expected quantity is not part of its signature.

## Bugs found

- No failing automated tests were found.
- No incorrect expected register addresses were found in the reviewed constants.
- No CRC byte-order bug was found.
- No signed int16 temperature bug was found.
- No u32 HI/LO ordering bug was found.
- No clock encode/decode bug was found.
- No missing clock-write confirmation bug was found for `clock-set` or `clock-set-now`.

Potential implementation bugs or weak spots:

- `read_log(index)` can write an out-of-range `LOG_SELECT` value because the log count is read but not used for bounds checking.
- `read_all_logs()` catches all exceptions while reading individual logs and skips failures unless debug output is enabled. This can hide systematic communication or decoder errors during log dump workflows.
- Report writing errors, such as an invalid output path or permission problem, are not specially handled by the CLI. They may surface as uncaught exceptions instead of a clean CLI error message.

## Risky behavior

- `python -m app.cli write ...` has no confirmation prompt and can write any single register accepted by the firmware.
- `log-latest`, `log-read`, `log-dump`, and the default auto test can write `LOG_SELECT`. This is expected by the log workflow and is documented in `README.md`, but it is still a state-changing operation.
- `clock-set --yes` and `clock-set-now --yes` intentionally bypass confirmation.
- `log-read --index` accepts arbitrary integer input and relies on firmware/log-status behavior rather than client-side validation.

## Recommended fixes before Phase 6

1. Add client-side bounds checking for `read_log(index)` after reading `LOG_COUNT`.
2. Consider requiring confirmation for raw `write`, or add a prominent `--yes` gate for writes outside known safe workflow registers.
3. Make `read_all_logs()` optionally strict, or at least report skipped log indices in a structured way so communication failures are visible.
4. Explicitly close serial transports in non-test CLI handlers.
5. Improve CLI handling for report/export file write failures.
6. Consider extending `parse_read_response` or the client read path to verify the number of returned registers matches the requested quantity.
7. Ensure the project environment exposes `pytest` on PATH, or update documentation to recommend `python -m pytest`.

## Final readiness for Phase 6

NEEDS_FIXES_BEFORE_PHASE_6

Reason: the core Phase 1-5 implementation is broadly complete and tests pass, but the log index validation gap, unguarded raw write command, silent log-read skipping, and cleanup/error-handling weaknesses should be resolved before adding Phase 6 behavior on top.
