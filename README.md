# Gas Pump Modbus Tester

`gas_pump_modbus_tester` is a small Python CLI foundation for testing gas pump firmware that communicates with a PC over Modbus RTU serial.

The app implements manual Modbus RTU frame construction, CRC16 verification, response parsing, raw serial transport, register decoders, live-data reads, clock writes, and log export helpers.

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run Tests

```bash
pytest
```

## CLI Examples

Read 8 holding registers from slave `1` on `COM5`:

```bash
python -m app.cli read --port COM5 --slave 1 --addr 0x0000 --count 8
```

Read input registers with function `0x04`:

```bash
python -m app.cli read --port COM5 --slave 1 --function 4 --addr 0 --count 8 --debug
```

Write register `0x002A` to `0`:

```bash
python -m app.cli write --port COM5 --slave 1 --addr 0x002A --value 0
```

Check whether the device responds:

```bash
python -m app.cli ping --port COM5 --slave 1
```

Read decoded live pump values:

```bash
python -m app.cli live --port COM5 --slave 1
```

Read decoded status, sensor, clock, fail-event, and config status blocks:

```bash
python -m app.cli status --port COM5 --slave 1
python -m app.cli sensor --port COM5 --slave 1
python -m app.cli clock --port COM5 --slave 1
python -m app.cli fail --port COM5 --slave 1
python -m app.cli config-status --port COM5 --slave 1
```

Set the pump clock from an explicit timestamp:

```bash
python -m app.cli clock-set --port COM5 --slave 1 --datetime "2026-04-24 15:30:45"
```

Set the pump clock from local system time:

```bash
python -m app.cli clock-set-now --port COM5 --slave 1
```

Dump logs to JSON and CSV:

```bash
python -m app.cli log-dump --port COM5 --slave 1 --limit 100 --json output/logs.json --csv output/logs.csv
```

## Auto Test Runner

Run the non-destructive automated diagnostic suite:

```bash
python -m app.cli test --port COM5 --slave 1
```

Write structured JSON and human-readable TXT reports:

```bash
python -m app.cli test --port COM5 --slave 1 --out output/report.json --txt output/report.txt
```

Enable the optional wrong-slave timeout test:

```bash
python -m app.cli test --port COM5 --slave 1 --include-slow-tests
```

The default auto test is mostly read-only. It writes only `LOG_SELECT` when `LOG_COUNT > 0` so it can inspect the latest log window. It does not change unit price, password, slave id, configuration, or clock. `--include-slow-tests` may wait for a serial timeout while checking behavior for a wrong slave id.

Warning: `write`, `clock-set`, `clock-set-now`, `log-latest`, `log-read`, and `log-dump` may write `LOG_SELECT` or other registers. Write commands can change device state. Use them only when the firmware and hardware are in a safe test condition.
