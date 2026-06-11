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
python -m pytest
```

Bare `pytest` may not be available on PATH in some environments, even when the
package is installed for the active Python interpreter.

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

## Troubleshooting real hardware

Modbus data goes through UART4 on the STM32:

```text
PC USB-UART TX  -> STM32 UART4_RX / PC11
PC USB-UART RX  -> STM32 UART4_TX / PC10
GND             -> GND
Serial          -> 9600 8N1
```

Firmware debug `printf` text is not Modbus payload. If debug ASCII is mixed
into the same serial line as binary Modbus RTU frames, the Modbus frame may be
corrupted or fail CRC validation.

Use `diagnose` first when hardware does not respond:

```bash
python -m app.cli diagnose --port COM5 --slave 1 --debug
```

Capture PC-side raw TX/RX frames for comparison with firmware debug output:

```bash
python -m app.cli diagnose --port COM5 --slave 1 \
  --capture-jsonl output/capture.jsonl \
  --capture-txt output/capture.txt
```

Try a range of slave ids without writing to the device:

```bash
python -m app.cli diagnose --port COM5 --slave 1 --try-slaves 1-20
```

Existing commands can also export raw captures:

```bash
python -m app.cli ping --port COM5 --slave 1 \
  --capture-txt output/ping_capture.txt
```

## Offline simulator mode

Simulator mode does not open a COM port. It is safe for development and
no-hardware testing, but it is not a replacement for final hardware validation.
Real hardware should still be tested with `diagnose`, `ping`, and `status`
before protected config writes.

Run normal read/test workflows without hardware:

```bash
python -m app.cli ping --simulate --slave 1
python -m app.cli status --simulate --slave 1
python -m app.cli live --simulate --slave 1
python -m app.cli sensor --simulate --slave 1
python -m app.cli clock --simulate --slave 1
python -m app.cli log-latest --simulate --slave 1
python -m app.cli log-dump --simulate --slave 1 --limit 3
python -m app.cli test --simulate --slave 1
python -m app.cli sim-demo
```

Try simulator profiles:

```bash
python -m app.cli test --simulate --sim-profile no-logs --slave 1
python -m app.cli test --simulate --sim-profile sensor-invalid --slave 1
python -m app.cli test --simulate --sim-profile bad-protocol --slave 1
python -m app.cli test --simulate --sim-profile fail-event --slave 1
```

Protected config writes can also be tested safely in simulator mode:

```bash
python -m app.cli config-set-unit-price --simulate --slave 1 \
  --password 1234 --value 25000 --yes

python -m app.cli config-set-slave-id --simulate --slave 1 \
  --password 1234 --new-id 2 --yes
```

## Protected config writes

These commands write to device configuration. Use only when the pump is safe to
configure, double-check the slave id and COM port, and do not expose the manager
password in screenshots or logs. Changing the slave id requires using the new id
afterward. Clearing the daily total cannot be undone.

Unlock protected writes:

```bash
python -m app.cli config-unlock --port COM5 --slave 1 --password 1234
```

Set unit price:

```bash
python -m app.cli config-set-unit-price --port COM5 --slave 1 \
  --password 1234 --value 23000
```

Set slave id:

```bash
python -m app.cli config-set-slave-id --port COM5 --slave 1 \
  --password 1234 --new-id 2
```

Set hotkey amount:

```bash
python -m app.cli config-set-hotkey-amount --port COM5 --slave 1 \
  --password 1234 --key F1 --amount 10000
```

Set hotkey liters:

```bash
python -m app.cli config-set-hotkey-liters --port COM5 --slave 1 \
  --password 1234 --key F1 --liters 1.000
```

Clear daily total:

```bash
python -m app.cli config-clear-daily --port COM5 --slave 1 \
  --password 1234
```

Change manager password:

```bash
python -m app.cli config-change-password --port COM5 --slave 1 \
  --old-password 1234 --new-password 5678
```

All protected config commands ask for confirmation unless `--yes` is provided.

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
