from pathlib import Path

from scripts.build_release import build_release


def test_release_script_creates_folder_and_zip(tmp_path) -> None:
    release_dir = build_release(tmp_path / "dist_release", build_exe=False)
    zip_files = list((tmp_path / "dist_release").glob("gas_pump_modbus_tester_v*.zip"))

    assert release_dir.exists()
    assert (release_dir / "README.md").exists()
    assert (release_dir / "USER_MANUAL.md").exists()
    assert (release_dir / "HARDWARE_TEST_CHECKLIST.md").exists()
    assert (release_dir / "config.example.json").exists()
    assert (release_dir / "app").exists()
    assert (release_dir / "scripts").exists()
    assert zip_files


def test_handoff_files_exist() -> None:
    for path in (
        "USER_MANUAL.md",
        "HARDWARE_TEST_CHECKLIST.md",
        "config.example.json",
    ):
        assert Path(path).exists()
