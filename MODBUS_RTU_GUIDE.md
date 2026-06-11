# Modbus RTU Guide

Tai lieu nay mo ta giao tiep Modbus RTU qua `UART4` cua firmware `GASPUMP_GEN1`, cach doi `slave id` bang ban phim, va cach doc log bom tu EEPROM.

## 1. Cau hinh giao tiep

- UART data channel: `UART4`
- Pin: `PC10 = TX`, `PC11 = RX`
- Serial: `9600 8N1`
- Modbus RTU frame gap: `5 ms`
- Function code ho tro:
  - `0x03`: Read Holding Registers
  - `0x04`: Read Input Registers
  - `0x06`: Write Single Register

Luu y:

- Duong UART data di thang vao Modbus parser, khong di qua `uart_protocol` text command.
- `printf` debug khong phai la payload Modbus.

### Bat debug Modbus

Bat/tat trong `Config/app_config.h`:

```c
#define MODBUS_DEBUG 1U
```

- `0U`: tat `printf` debug Modbus
- `1U`: bat debug cho raw frame, request da parse, log refresh, clock write/commit, exception

Khi bat debug, firmware se in cac dong theo dang:

```text
[MODBUS] rx frame len=8 01 03 00 28 00 14 C5 CD
[MODBUS] req slave=1 fn=0x03(read_holding) start=0x0028 count=20
[MODBUS] read start=0x0028 count=20
[MODBUS] tx read len=45 01 03 ...

[MODBUS] rx frame len=8 01 06 00 3C 1A 04 43 65
[MODBUS] req slave=1 fn=0x06(write_single) reg=0x003C(CLOCK_YEAR_MONTH) value=0x1A04(6660)
[MODBUS] write clock year_month=0x1A04 year=26 month=4
[MODBUS] tx write len=8 01 06 00 3C 1A 04 43 65
```

Sau khi ghi du 3 register clock, firmware se in them:

```text
[MODBUS] clock commit ok 2026-04-24 15:30:45
```

Clock duoc luu vao EEPROM khi commit thanh cong. Firmware cung tu luu software
clock dinh ky theo `TIME_SERVICE_EEPROM_SAVE_INTERVAL_MS`, nen reset/power cycle
se restore lai lan clock gan nhat da luu.

## 2. Slave ID

`Slave id` chinh la id cua voi/tru bom.

- Mac dinh sau khi khoi tao: `1`
- Range hop le: `1..247`
- Duoc luu trong EEPROM cung cac setting khac
- Flow doi bang ban phim nam trong `Services/pump_keypad_controller.c`
- Modbus parser lay id hien tai tu `pump_service_get_modbus_slave_address()`

### Doi slave id bang ban phim

Nhap tren ban phim:

```text
P -> 9 9 9 0 3 2 -> E -> <id_moi> -> E
```

Vi du:

```text
P-999032-E-2-E
P-999032-E-15-E
```

Neu hop le:

- firmware luu `slave id` moi
- man hinh se hien thong bao `IDOK`
- Modbus se chi tra loi frame gui toi `slave id` moi

Neu gia tri ngoai range `1..247`:

- firmware bao `BADID`

## 3. Byte order

Moi register Modbus la 16-bit:

- high byte truoc
- low byte sau

Moi gia tri 32-bit duoc tach thanh 2 register:

- `*_HI`: 16 bit cao
- `*_LO`: 16 bit thap

Vi du:

```text
HI = 0x0000
LO = 0x3A98
=> value = 0x00003A98 = 15000
```

## 4. Register map

### 4.1 Pump data

- `0x0000`: protocol version
- `0x0001`: slave address hien tai
- `0x0002`: status flags
- `0x0003`: pump mode
- `0x0004`: key mode
- `0x0005`: screen
- `0x0006`: selected field
- `0x0007`: nozzle status
- `0x0008-0x0027`: amount, liters, unit price, target, daily, total, hotkey

`protocol version` hien la `7` cho map co them fail event registers.

`NOZZLE_STATUS` la register 16-bit bieu dien trang thai co bom:

- `0`: gac co bom
- `1`: nhac co bom, chua bat dau bom
- `2`: nhac co bom va bat dau/dang bom

Trong source hien tai, khi PA0 chuyen sang trang thai nhac co, firmware se goi `pump_service_start_transaction()` va `NOZZLE_STATUS` se chuyen len `2`.

`STATUS_FLAGS` van giu dang bitmask chan doan:

- `0x0001`: transaction active
- `0x0002`: nozzle lifted
- `0x0004`: storage ready

### 4.2 EEPROM log window

- `0x0028-0x0029`: `LOG_COUNT` 32-bit
- `0x002A`: `LOG_SELECT`
- `0x002B`: `LOG_STATUS`
- `0x002C`: `LOG_ID_PUMP`
- `0x002D`: `LOG_YEAR_MONTH`
- `0x002E`: `LOG_DAY_HOUR`
- `0x002F`: `LOG_MINUTE_SECOND`
- `0x0030-0x0031`: `LOG_SEQUENCE`
- `0x0032-0x0033`: `LOG_AMOUNT`
- `0x0034-0x0035`: `LOG_LITERS_X1000`
- `0x0036-0x0037`: `LOG_UNIT_PRICE`
- `0x0038-0x0039`: `LOG_TOTAL_LITERS_X1000`
- `0x003A-0x003B`: `LOG_CHECKSUM`

### 4.3 Current clock registers

- `0x003C`: `CLOCK_YEAR_MONTH`
- `0x003D`: `CLOCK_DAY_HOUR`
- `0x003E`: `CLOCK_MINUTE_SECOND`

Dang dong goi:
- `YEAR_MONTH`: high byte = `year`, low byte = `month`
- `DAY_HOUR`: high byte = `day`, low byte = `hour`
- `MINUTE_SECOND`: high byte = `minute`, low byte = `second`

`year` la nam offset tu `2000`.

Vi du:
- `year = 26` => nam `2026`

### 4.4 Sensor registers

- `0x003F`: `SENSOR_STATUS`
- `0x0040`: `MCU_TEMP_C_X100`
- `0x0041`: `AMBIENT_TEMP_C_X100`
- `0x0042`: `HUMIDITY_X100`

`SENSOR_STATUS` la bitmask 16-bit:

- `0x0001`: cam bien moi truong doc OK, `AMBIENT_TEMP_C_X100` va `HUMIDITY_X100`
  hop le

`MCU_TEMP_C_X100` va `AMBIENT_TEMP_C_X100` la so co dau 16-bit, don vi `C * 100`.
Master can giai ma theo `int16_t`:

```text
0x09E4 -> 2532 -> 25.32C
0xFF9C -> -100 -> -1.00C
```

`HUMIDITY_X100` la so khong dau 16-bit, don vi `%RH * 100`:

```text
0x1996 -> 6550 -> 65.50%
```

Neu `SENSOR_STATUS bit0 = 0`, firmware chua co du lieu moi truong hop le. Khi do
`AMBIENT_TEMP_C_X100` va `HUMIDITY_X100` se la `0`.

### 4.5 Configuration write registers

- `0x0043`: `CONFIG_STATUS`
- `0x0044`: `CONFIG_UNLOCK_PASSWORD_HI`
- `0x0045`: `CONFIG_UNLOCK_PASSWORD_LO`
- `0x0046`: `CONFIG_NEW_PASSWORD_HI`
- `0x0047`: `CONFIG_NEW_PASSWORD_LO`
- `0x0048`: `CONFIG_CLEAR_DAILY`

`CONFIG_STATUS` la bitmask 16-bit:

- `0x0001`: Modbus config da unlock bang password quan ly

Unlock het han sau 60 giay. Cac register password la write-only ve logic; khi
doc se tra `0`.

De unlock, ghi password quan ly 32-bit theo thu tu:

```text
0x0044 = PASSWORD_HI
0x0045 = PASSWORD_LO
```

Vi du password `123456 = 0x0001E240`:

```text
ghi 0x0044 = 0x0001
ghi 0x0045 = 0xE240
```

Sau khi unlock, cac setting sau co the ghi bang function `0x06`:

- `0x0001`: `SLAVE_ADDRESS`, range `1..247`
- `0x000C-0x000D`: `UNIT_PRICE`
- `0x0018-0x001F`: hotkey tien `F1..F4`
- `0x0020-0x0027`: hotkey lit `F1..F4`, don vi `liters_x1000`
- `0x0046-0x0047`: doi password quan ly moi, range `0..999999`
- `0x0048`: xoa daily total neu ghi magic `0xC1EA`

Voi gia tri 32-bit, ghi `_HI` truoc roi ghi `_LO`. Firmware chi commit va luu
EEPROM khi ghi `_LO`. Neu gia tri nho hon `65536`, co the chi ghi `_LO` neu
high-word hien tai dang la `0`.

Vi du doi don gia thanh `23000 = 0x000059D8`:

```text
ghi 0x000C = 0x0000
ghi 0x000D = 0x59D8
```

Neu doi `SLAVE_ADDRESS`, firmware ACK bang slave id cu cho frame ghi hien tai;
cac frame sau phai gui toi slave id moi.

Ba cau hinh van hanh sau hien doi bang keypad va luu EEPROM, chua expose thanh
Modbus register:

- `P -> 800001 -> E -> <delay_ms> -> E`: delay tung buoc mo valve/motor.
- `P -> 800002 -> E -> <liters_x1000> -> E`: nguong slowdown.
- `P -> 800003 -> E -> <liters_x1000> -> E`: nguong giao dich hop le.

### 4.6 Last fail event registers

- `0x0049`: `LAST_FAIL_CODE`
- `0x004A`: `LAST_FAIL_SEQUENCE`

Hai register nay chi luu trong RAM. Khi boot moi, `LAST_FAIL_CODE = 0` va
`LAST_FAIL_SEQUENCE = 0`. Moi lan firmware ghi nhan mot fail event moi,
`LAST_FAIL_CODE` duoc cap nhat theo bang ma ben duoi va `LAST_FAIL_SEQUENCE`
tang them 1. Sequence la 16-bit nen sau `0xFFFF` se loop ve `0x0000`.

Master nen poll ca 2 register. Neu `LAST_FAIL_SEQUENCE` doi so voi lan doc truoc
thi `LAST_FAIL_CODE` la fail event moi nhat. Text hien thi/SCADA tu tra bang ma,
firmware khong truyen message ASCII qua Modbus.

Bang ma fail event hien tai:

```text
0x0000 NONE
0x0101 POWER_FAIL_VOLTAGE_DETECTOR_TRIGGER
0x0103 POWER_FAIL_VOLUME_TOO_SMALL
0x0104 POWER_FAIL_EMERGENCY_SAVE_FAILED
0x0105 POWER_FAIL_LOG_APPEND_FAILED
0x0106 POWER_FAIL_MARK_PROCESSED_FAILED
0x0107 POWER_FAIL_RECOVERY_FAILED
0x0201 SETTINGS_SAVE_FAILED
0x0202 COUNTERS_SAVE_FAILED
0x0203 RUNTIME_CONFIG_SAVE_FAILED
0x0204 LOG_APPEND_FAILED
0x0401 UART_ERROR
0x0402 MODBUS_CRC_MISMATCH
0x0403 MODBUS_ILLEGAL_FUNCTION
0x0404 MODBUS_ILLEGAL_ADDRESS
0x0405 MODBUS_ILLEGAL_VALUE
0x0406 MODBUS_UNLOCK_DENIED
0x0407 MODBUS_CLOCK_INVALID
0x0501 KEYPAD_BAD_ID
0x0502 KEYPAD_BAD_PRICE
0x0503 KEYPAD_PASSWORD_DENIED
0x0504 KEYPAD_BUSY
0x0505 KEYPAD_RESET_FAILED
0x0506 KEYPAD_UNSUPPORTED
```

## 5. Y nghia log

### `LOG_SELECT`

`LOG_SELECT` la chi so log tinh tu moi nhat:

- `0`: log moi nhat
- `1`: log ngay truoc do
- `2`: log cu hon nua

Firmware chi ghi log khi phien ket thuc dat nguong runtime
`PUMP_MIN_VALID_TRANSACTION_LITERS_X1000`, co the doi bang keypad code `800003`.
Cac xung nho do nhac/gac co hoac cang ong khong cap nhat amount/liters live qua
Modbus va khong lam tang `log_count`. Khi da vuot nguong, live register va log
van dung du toan bo liters cua phien, khong tru phan nguong.

Firmware ghi log bang co che write + read-back verify. Neu mot slot EEPROM ghi
khong khop sau cac lan retry, firmware skip slot do va thu slot ke tiep. Khi doc
qua Modbus, firmware quet lui theo `last_log_sequence` va chi expose record co
`magic/version/length/end_marker/log_epoch/CRC32` hop le, nen slot skip hoac data
cu con sot lai se khong duoc tinh la log hop le.

Neu MCP130 bao power-fail trong luc dang bom, EXTI2 chi set co nghi ngo. Firmware
doi `PUMP_POWER_FAIL_CONFIRM_MS` trong super-loop roi doc lai PE2 active-low; neu
tin hieu da ve high thi bo qua spike, neu van low va phien da dat nguong hop le
thi ghi emergency record truoc roi chot thanh log chinh thuc trong super-loop
hoac trong lan boot ke tiep. Modbus van thay giao dich nay nhu mot log binh
thuong; register map khong them flag rieng cho nguyen nhan power-fail.

### `LOG_STATUS`

Bitmask 16-bit:

- `0x0001`: co log trong EEPROM
- `0x0002`: `LOG_SELECT` hop le
- `0x0004`: log da duoc load vao cache thanh cong

Gia tri thuong gap:

- `0x0000`: khong co log hoac storage chua san sang
- `0x0001`: co log nhung `LOG_SELECT` sai range
- `0x0007`: co log, `LOG_SELECT` hop le, payload hop le

Neu `LOG_SELECT` vuot qua so log hien co:

- lenh `0x06` van duoc ACK
- nhung `LOG_STATUS` se khong du `0x0007`
- payload log doc ra se la `0`

## 6. Trinh tu doc log dung

Trinh tu khuyen nghi:

1. Doc `LOG_COUNT`
2. Ghi `LOG_SELECT = N`
3. Doc `LOG_STATUS` hoac doc ca block log
4. Chi dung payload khi `LOG_STATUS == 0x0007`

## 7. Cac lenh dung nhieu nhat

Tat ca vi du ben duoi gia su `slave id = 1`.

Neu ban da doi `slave id`, hay thay byte dau tien cho dung.

### 7.1 Doc so luong log hien co

Request:

```text
01 03 00 28 00 02 44 03
```

Y nghia:

- slave `01`
- function `03`
- start address `0x0028`
- quantity `2` register

Neu hien tai co `7` log, response se co dang:

```text
01 03 04 00 00 00 07 BB F1
```

### 7.2 Chon log moi nhat

Request:

```text
01 06 00 2A 00 00 A8 02
```

Y nghia:

- ghi `0` vao `LOG_SELECT`
- `0` la log moi nhat

Response echo:

```text
01 06 00 2A 00 00 A8 02
```

### 7.3 Chon log thu 2 tinh tu moi nhat

Request:

```text
01 06 00 2A 00 01 69 C2
```

Response echo:

```text
01 06 00 2A 00 01 69 C2
```

### 7.4 Doc toan bo cua so log

Request:

```text
01 03 00 28 00 14 C5 CD
```

Request nay doc 20 register tu `0x0028` den `0x003B`.

Y nghia tung byte request:

- `01`: slave id
- `03`: Read Holding Registers
- `00 28`: start address = `0x0028`
- `00 14`: quantity = `20` register
- `C5 CD`: CRC16 Modbus RTU

Thu tu payload trong response:

1. `LOG_COUNT`
2. `LOG_SELECT`
3. `LOG_STATUS`
4. `LOG_ID_PUMP`
5. `LOG_YEAR_MONTH`
6. `LOG_DAY_HOUR`
7. `LOG_MINUTE_SECOND`
8. `LOG_SEQUENCE`
9. `LOG_AMOUNT`
10. `LOG_LITERS_X1000`
11. `LOG_UNIT_PRICE`
12. `LOG_TOTAL_LITERS_X1000`
13. `LOG_CHECKSUM`

### 7.5 Doc rieng payload log da chon

Request:

```text
01 03 00 2C 00 10 85 CF
```

Request nay bo qua `LOG_COUNT`, `LOG_SELECT`, `LOG_STATUS`, chi doc payload tu `LOG_ID_PUMP` tro di, kem theo `LOG_CHECKSUM`.

Request nay doc `16` register:

- `0x002C`: `LOG_ID_PUMP`
- `0x002D`: `LOG_YEAR_MONTH`
- `0x002E`: `LOG_DAY_HOUR`
- `0x002F`: `LOG_MINUTE_SECOND`
- `0x0030-0x0031`: `LOG_SEQUENCE`
- `0x0032-0x0033`: `LOG_AMOUNT`
- `0x0034-0x0035`: `LOG_LITERS_X1000`
- `0x0036-0x0037`: `LOG_UNIT_PRICE`
- `0x0038-0x0039`: `LOG_TOTAL_LITERS_X1000`
- `0x003A-0x003B`: `LOG_CHECKSUM`

Neu muon kiem tra rieng trang thai log truoc khi doc payload:

```text
01 03 00 2B 00 01 F4 02
```

Lenh nay chi doc 1 register `LOG_STATUS`.

### 7.6 Doc trang thai co bom

Request:

```text
01 03 00 07 00 01 35 CB
```

Response mau khi dang bom:

```text
01 03 02 00 02 39 85
```

Giai nghia:

- `00 00`: gac co bom
- `00 01`: nhac co bom, chua bat dau bom
- `00 02`: nhac co bom va bat dau/dang bom

### 7.7 Doc dong ho hien tai cua tru bom

Request:

```text
01 03 00 3C 00 03 C5 C7
```

Response tra ve:
- `CLOCK_YEAR_MONTH`
- `CLOCK_DAY_HOUR`
- `CLOCK_MINUTE_SECOND`

Vi du neu dong ho dang la `2026-04-24 15:30:45`, 3 register se duoc giai ma nhu sau:

- `CLOCK_YEAR_MONTH = 0x1A04` => `year=26`, `month=4`
- `CLOCK_DAY_HOUR = 0x180F` => `day=24`, `hour=15`
- `CLOCK_MINUTE_SECOND = 0x1E2D` => `minute=30`, `second=45`

### 7.8 Ghi dong ho hien tai cua tru bom

Can ghi 3 register:

```text
0x003C = YEAR_MONTH
0x003D = DAY_HOUR
0x003E = MINUTE_SECOND
```

Vi du set thoi gian `2026-04-24 15:30:45`:

- `year = 26`
- `month = 4`
- `day = 24`
- `hour = 15`
- `minute = 30`
- `second = 45`

Gia tri register:

```text
YEAR_MONTH    = 0x1A04
DAY_HOUR      = 0x180F
MINUTE_SECOND = 0x1E2D
```

Khuyen nghi:
1. ghi `CLOCK_YEAR_MONTH`
2. ghi `CLOCK_DAY_HOUR`
3. ghi `CLOCK_MINUTE_SECOND`

Firmware se commit gia tri moi sau khi nhan du ca 3 register.

Frame RTU day du:

1. Ghi `CLOCK_YEAR_MONTH = 0x1A04`

```text
01 06 00 3C 1A 04 43 65
```

2. Ghi `CLOCK_DAY_HOUR = 0x180F`

```text
01 06 00 3D 18 0F 52 02
```

3. Ghi `CLOCK_MINUTE_SECOND = 0x1E2D`

```text
01 06 00 3E 1E 2D 21 BB
```

Moi lenh `0x06` se duoc echo lai y chang neu hop le.

Luu y:

- Neu moi ghi 1 hoac 2 register, firmware moi chi stage tam thoi, chua commit clock moi
- Chi sau register thu 3, firmware moi validate va commit toan bo `year/month/day/hour/minute/second`
- Neu bo 3 register tao thanh ngay gio khong hop le, firmware se tra exception `0x86 0x03`

## 8. Cach parse 32-bit

Pseudo code:

```c
uint32_t modbus_u32(uint16_t hi, uint16_t lo)
{
    return ((uint32_t)hi << 16) | lo;
}
```

PC co the tu tinh lai `CRC32` cua payload log va so sanh voi `LOG_CHECKSUM`.

Thu tu field cua payload khi tinh `CRC32`:

1. `pump_id`
2. `datetime.year`
3. `datetime.month`
4. `datetime.day`
5. `datetime.hour`
6. `datetime.minute`
7. `datetime.second`
8. `sequence`
9. `amount`
10. `liters_x1000`
11. `unit_price`
12. `total_liters_x1000`

Luu y quan trong:
- `CRC32` trong firmware duoc tinh tren raw payload trong EEPROM
- `pump_id` duoc dua vao CRC32 bang 1 byte
- 6 truong `year/month/day/hour/minute/second` moi truong duoc dua vao CRC32 bang 1 byte
- `LOG_ID_PUMP` doc qua Modbus van nam trong 1 register 16-bit, nhung khi tinh CRC32 chi lay 1 byte gia tri `pump_id`
- cac truong `uint32_t` trong payload duoc luu little-endian tren STM32
- vi vay khi PC tinh lai `CRC32`, can serialize `pump_id` + `datetime` theo tung byte, roi den tung field `uint32_t` theo little-endian

Vi du:

```text
amount = 12345 = 0x00003039
bytes dua vao CRC32 phai la: 39 30 00 00
```

Vi du:

```text
00 00 30 39 -> 12345
00 00 02 18 -> 536
00 00 59 D8 -> 23000
```

## 9. Giai nghia mot response mau

Response schematic:

```text
01 03 28
[LOG_COUNT 4 bytes]
[LOG_SELECT 2 bytes]
[LOG_STATUS 2 bytes]
[LOG_ID_PUMP 2 bytes]
[LOG_YEAR_MONTH 2 bytes]
[LOG_DAY_HOUR 2 bytes]
[LOG_MINUTE_SECOND 2 bytes]
[LOG_SEQUENCE 4 bytes]
[LOG_AMOUNT 4 bytes]
[LOG_LITERS_X1000 4 bytes]
[LOG_UNIT_PRICE 4 bytes]
[LOG_TOTAL_LITERS_X1000 4 bytes]
[LOG_CHECKSUM 4 bytes]
[CRC16 2 bytes]
```

Giai nghia:

- `LOG_COUNT = 7`
- `LOG_SELECT = 0`
- `LOG_STATUS = 0x0007`
- `LOG_ID_PUMP = 1`
- `LOG_YEAR_MONTH = nam/thang`
- `LOG_DAY_HOUR = ngay/gio`
- `LOG_MINUTE_SECOND = phut/giay`
- `LOG_SEQUENCE = 7`
- `LOG_AMOUNT = 12345`
- `LOG_LITERS_X1000 = 536`
- `LOG_UNIT_PRICE = 23000`
- `LOG_TOTAL_LITERS_X1000 = tong lit luy ke sau giao dich nay`
- `LOG_CHECKSUM = <CRC32 cua payload>`

## 10. Test nhanh bang PC

Neu dung USB-UART hoac USB-RS485:

1. Noi vao `UART4`
2. Dat cong serial `9600 8N1`
3. Dung `slave id` hien tai cua voi bom
4. Gui cac frame can test ben duoi

Tat ca vi du trong muc nay gia su:

- `slave id = 1`
- password quan ly hien tai la `1234 = 0x000004D2`
- cac frame da co san CRC16 Modbus RTU o 2 byte cuoi, thu tu `CRC_LO CRC_HI`

### 10.1 Doc nhanh trang thai

Doc protocol version, slave id, status, mode, key mode, screen, selected field,
nozzle status:

```text
01 03 00 00 00 08 44 0C
```

Doc amount/liters/unit price/target/daily/total/hotkey:

```text
01 03 00 08 00 20 C5 D0
```

`TARGET_AMOUNT` va `TARGET_LITERS` la target cua phien preset hien tai. Sau khi
gac co ket thuc mot phien bom, firmware xoa target ve `0` de phien ke tiep mac
dinh quay lai bom tu do neu khong co preset moi.

Doc sensor snapshot: `SENSOR_STATUS`, nhiet do STM32, nhiet do moi truong, do am:

```text
01 03 00 3F 00 04 74 05
```

Doc config unlock status:

```text
01 03 00 43 00 01 75 DE
```

Doc last fail code va sequence:

```text
01 03 00 49 00 02 15 DD
```

### 10.2 Unlock config truoc khi ghi setting

Ghi password `1234 = 0x000004D2`:

```text
01 06 00 44 00 00 C9 DF
01 06 00 45 04 D2 1A 82
```

Sau khi unlock thanh cong, doc `CONFIG_STATUS` se co bit `0x0001`:

```text
01 03 00 43 00 01 75 DE
```

Unlock het han sau 60 giay. Neu password sai, firmware tra exception
`0x86 0x03`.

### 10.3 Doi don gia

Vi du doi don gia thanh `23000 = 0x000059D8`.

Can unlock truoc bang password, sau do ghi:

```text
01 06 00 0C 00 00 49 C9
01 06 00 0D 59 D8 22 03
```

Doc lai `UNIT_PRICE_HI/LO`:

```text
01 03 00 0C 00 02 04 08
```

### 10.4 Doi slave id

Vi du doi slave id tu `1` sang `2`. Can unlock truoc:

```text
01 06 00 01 00 02 59 CB
```

Frame tren se duoc ACK bang slave id cu `1`. Sau do cac frame tiep theo phai
gui toi slave id moi `2`.

### 10.5 Doi hotkey F1

Vi du set hotkey tien F1 = `10000 = 0x00002710`. Can unlock truoc:

```text
01 06 00 18 00 00 09 CD
01 06 00 19 27 10 42 31
```

Vi du set hotkey lit F1 = `1000 liters_x1000 = 1.000L`. Can unlock truoc:

```text
01 06 00 20 00 00 88 00
01 06 00 21 03 E8 D9 7E
```

### 10.6 Clear daily total va doi password

Clear daily total. Can unlock truoc, magic value la `0xC1EA`:

```text
01 06 00 48 C1 EA D9 C3
```

Doi password quan ly thanh `5678 = 0x0000162E`. Can unlock bang password cu
truoc:

```text
01 06 00 46 00 00 68 1F
01 06 00 47 16 2E B7 A3
```

Sau khi doi password, lan unlock tiep theo phai dung password moi.

### 10.7 Doc log EEPROM

Doc so log:

```text
01 03 00 28 00 02 44 03
```

Chon log moi nhat:

```text
01 06 00 2A 00 00 A8 02
```

Doc `LOG_STATUS`:

```text
01 03 00 2B 00 01 F4 02
```

Doc full log window:

```text
01 03 00 28 00 14 C5 CD
```

### 10.8 Doc/ghi clock

Doc clock hien tai:

```text
01 03 00 3C 00 03 C5 C7
```

Set clock thanh `2026-04-24 15:30:45`:

```text
01 06 00 3C 1A 04 43 65
01 06 00 3D 18 0F 52 02
01 06 00 3E 1E 2D 21 BB
```

Neu ban da doi `slave id`, phai doi byte dau va tinh lai CRC. Vi du cac frame
ben tren chi copy dung ngay khi `slave id = 1`:

```text
02 03 00 28 00 02 ...
02 06 00 2A 00 00 ...
02 03 00 28 00 14 ...
02 03 00 3C 00 03 ...
```

## 11. Exception

Firmware se tra exception khi:

- function code khong duoc ho tro
- dia chi register sai
- quantity sai

Vi du:

- `0x83 0x02`: read sai dia chi
- `0x86 0x02`: write sai dia chi

## 12. Ghi chu van hanh

- firmware hien tai dung software clock, khong phai RTC hardware
- clock duoc restore tu EEPROM sau reset/power cycle neu da tung duoc set va luu
- trong thoi gian mat dien, clock khong tu chay tiep neu khong co RTC hardware co backup
- `MODBUS_DEBUG` co the bat/tat trong `Config/app_config.h`
- Quet man hinh 7 doan hien da duoc tach sang timer interrupt rieng, khong con phu thuoc `super-loop`
