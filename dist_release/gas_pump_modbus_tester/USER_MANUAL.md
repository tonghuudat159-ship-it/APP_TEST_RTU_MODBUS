# Gas Pump Modbus Tester User Manual

## Overview

`gas-pump-modbus-tester` is a Python CLI for testing gas pump firmware over Modbus RTU. It supports real serial hardware, raw TX/RX capture, offline simulator mode, automated reports, and protected configuration writes.

## Install Python

Install Python 3.11 or newer from https://www.python.org/downloads/. On Windows, enable "Add python.exe to PATH" during installation.

## Install Dependencies

```bash
python -m pip install -r requirements.txt
```

## Run Tests

```bash
python -m pytest
```

## Run Simulator

```bash
python -m app.cli smoke-test
python -m app.cli sim-demo
python -m app.cli ping --simulate --slave 1
```

Simulator mode does not open a COM port and is safe for development.

## Real Hardware Wiring

```text
PC USB-UART TX  -> STM32 UART4_RX / PC11
PC USB-UART RX  -> STM32 UART4_TX / PC10
GND             -> GND
Serial          -> 9600 8N1
```

Modbus data uses UART4. Firmware debug text is not Modbus payload.

## First Real Hardware Commands

```bash
python -m app.cli diagnose --port COM5 --slave 1 --debug
python -m app.cli ping --port COM5 --slave 1
python -m app.cli status --port COM5 --slave 1
python -m app.cli live --port COM5 --slave 1
```

## Log Reading

```bash
python -m app.cli log-latest --port COM5 --slave 1
python -m app.cli log-dump --port COM5 --slave 1 --limit 100 --json output/logs.json --csv output/logs.csv
```

## Auto Test

```bash
python -m app.cli test --port COM5 --slave 1 --out output/report.json --txt output/report.txt
```

## Capture Files

```bash
python -m app.cli diagnose --port COM5 --slave 1 --capture-txt output/capture.txt
```

Capture files are useful when comparing PC-side Modbus frames with firmware debug logs.

## Protected Config Writes

Do not run config-write commands on a real pump unless the pump is safe to configure. Changing slave id requires using the new id afterward. Clearing daily total cannot be undone. Do not expose manager password in screenshots/logs.

Examples:

```bash
python -m app.cli config-unlock --port COM5 --slave 1 --password 1234
python -m app.cli config-set-unit-price --port COM5 --slave 1 --password 1234 --value 23000
python -m app.cli config-set-hotkey-amount --port COM5 --slave 1 --password 1234 --key F1 --amount 10000
python -m app.cli config-clear-daily --port COM5 --slave 1 --password 1234
```

Every protected config command asks for confirmation unless `--yes` is provided.

## Troubleshooting

| Symptom | Likely cause | What to check |
| --- | --- | --- |
| COM open failed | Wrong COM/busy port | Device Manager, close serial monitor |
| Timeout | Wrong slave id, wiring, no GND | TX/RX, GND, 9600 8N1 |
| CRC mismatch | Noise, wrong serial config | wires, baudrate, RS485 |
| Illegal address | Wrong register | register map |
| Illegal value | invalid config/password/clock | value range, unlock |
