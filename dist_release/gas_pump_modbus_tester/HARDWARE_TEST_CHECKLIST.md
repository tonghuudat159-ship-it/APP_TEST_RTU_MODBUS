# Hardware Test Checklist

## Stage 0 - Preparation

- Confirm firmware flashed.
- Confirm UART4 pins.
- Confirm USB-UART voltage level.
- Confirm common GND.
- Confirm pump is in safe state.
- Confirm current slave id.

## Stage 1 - Non-write Tests

```bash
python -m app.cli diagnose --port COM5 --slave 1 --debug --capture-txt output/diagnose_capture.txt
python -m app.cli ping --port COM5 --slave 1
python -m app.cli status --port COM5 --slave 1
python -m app.cli live --port COM5 --slave 1
python -m app.cli sensor --port COM5 --slave 1
python -m app.cli clock --port COM5 --slave 1
python -m app.cli fail --port COM5 --slave 1
```

## Stage 2 - Log Tests

```bash
python -m app.cli log-latest --port COM5 --slave 1
python -m app.cli log-dump --port COM5 --slave 1 --limit 10 --json output/logs.json --csv output/logs.csv
```

## Stage 3 - Auto Test

```bash
python -m app.cli test --port COM5 --slave 1 --out output/report.json --txt output/report.txt
```

## Stage 4 - Minimal Protected Write Test

Only if safe:

```bash
python -m app.cli config-status --port COM5 --slave 1
python -m app.cli config-unlock --port COM5 --slave 1 --password 1234
```

## Stage 5 - Optional Config Write Tests

Only if authorized:

```bash
python -m app.cli config-set-unit-price --port COM5 --slave 1 --password 1234 --value 23000
python -m app.cli config-set-hotkey-amount --port COM5 --slave 1 --password 1234 --key F1 --amount 10000
python -m app.cli config-set-hotkey-liters --port COM5 --slave 1 --password 1234 --key F1 --liters 1.000
```

## Stage 6 - High-risk Tests

These require explicit authorization:

```bash
python -m app.cli config-set-slave-id --port COM5 --slave 1 --password 1234 --new-id 2
python -m app.cli config-clear-daily --port COM5 --slave 1 --password 1234
python -m app.cli config-change-password --port COM5 --slave 1 --old-password 1234 --new-password 5678
```
