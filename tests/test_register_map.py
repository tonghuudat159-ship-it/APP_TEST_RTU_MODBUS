from app import register_map as reg


def test_register_block_definitions() -> None:
    assert reg.QUICK_STATUS_START == 0x0000
    assert reg.QUICK_STATUS_COUNT == 8
    assert reg.LOG_WINDOW_START == 0x0028
    assert reg.LOG_WINDOW_COUNT == 20
    assert reg.CLOCK_START == 0x003C
    assert reg.CLOCK_COUNT == 3
    assert reg.SENSOR_START == 0x003F
    assert reg.SENSOR_COUNT == 4
    assert reg.FAIL_EVENT_START == 0x0049
    assert reg.FAIL_EVENT_COUNT == 2


def test_register_maps() -> None:
    assert reg.NOZZLE_STATUS_TEXT[0] == "nozzle placed / idle"
    assert reg.STATUS_FLAG_BITS[0x0004] == "storage_ready"
    assert reg.LOG_STATUS_BITS[0x0004] == "payload_loaded"
    assert reg.SENSOR_STATUS_BITS[0x0001] == "ambient_valid"
    assert reg.FAIL_CODE_TEXT[0x0402] == "MODBUS_CRC_MISMATCH"
    assert reg.REGISTER_MAP["LOG_SELECT"] == 0x002A
