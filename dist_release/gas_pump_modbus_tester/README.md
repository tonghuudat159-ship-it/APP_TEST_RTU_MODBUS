# Gas Pump Modbus Tester

`gas-pump-modbus-tester` is a Python Modbus RTU tester for gas pump firmware. It supports real serial hardware, an offline simulator, raw TX/RX capture, automated reports, protected config writes, and release packaging.

See [USER_MANUAL.md](USER_MANUAL.md) for operator instructions and [HARDWARE_TEST_CHECKLIST.md](HARDWARE_TEST_CHECKLIST.md) for staged hardware validation.

## Quick Start

1. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

2. Run the simulator smoke test:

```bash
python -m app.cli smoke-test
```

3. Run real-hardware diagnose before other hardware commands:

```bash
python -m app.cli diagnose --port COM5 --slave 1 --debug
```

4. Read status, live data, and logs:

```bash
python -m app.cli status --port COM5 --slave 1
python -m app.cli live --port COM5 --slave 1
python -m app.cli log-latest --port COM5 --slave 1
```

5. Run the non-destructive auto test:

```bash
python -m app.cli test --port COM5 --slave 1 --out output/report.json --txt output/report.txt
```

6. Protected config writes require extra care.

These commands write to device configuration. Use only when the pump is safe to configure, double-check COM port and slave id, and do not expose manager passwords in screenshots or logs. Changing slave id requires using the new id afterward. Clearing daily total cannot be undone.

## Simulator Mode

Simulator mode does not open a COM port and is safe for development:

```bash
python -m app.cli ping --simulate --slave 1
python -m app.cli live --simulate --slave 1
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

## Version And Release QA

```bash
python -m app.cli version
python -m app.cli --version
python scripts/run_tests.py
python scripts/build_release.py
```

## Hardware Wiring

```text
PC USB-UART TX  -> STM32 UART4_RX / PC11
PC USB-UART RX  -> STM32 UART4_TX / PC10
GND             -> GND
Serial          -> 9600 8N1
```

Use `diagnose` and raw capture files when comparing PC-side frames with firmware debug output.
