"""Build a Windows-friendly source release package."""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.version import APP_VERSION


PACKAGE_NAME = "gas_pump_modbus_tester"


def build_release(output_root: str | Path = "dist_release", build_exe: bool = True) -> Path:
    output_root = Path(output_root)
    release_dir = output_root / PACKAGE_NAME
    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True, exist_ok=True)

    for filename in (
        "README.md",
        "USER_MANUAL.md",
        "HARDWARE_TEST_CHECKLIST.md",
        "config.example.json",
        "requirements.txt",
        "pyproject.toml",
        "app_cli_entry.py",
    ):
        shutil.copy2(PROJECT_ROOT / filename, release_dir / filename)

    _copy_tree(PROJECT_ROOT / "app", release_dir / "app")
    _copy_tree(PROJECT_ROOT / "scripts", release_dir / "scripts")
    if (PROJECT_ROOT / "examples").exists():
        _copy_tree(PROJECT_ROOT / "examples", release_dir / "examples")

    zip_path = output_root / f"{PACKAGE_NAME}_v{APP_VERSION}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in release_dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(output_root))

    if build_exe:
        _try_build_exe(release_dir)
    return release_dir


def main() -> int:
    release_dir = build_release()
    print(f"Release folder: {release_dir}")
    print(f"Release zip: {release_dir.parent / f'{PACKAGE_NAME}_v{APP_VERSION}.zip'}")
    return 0


def _copy_tree(source: Path, destination: Path) -> None:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
    shutil.copytree(source, destination, ignore=ignore)


def _try_build_exe(release_dir: Path) -> None:
    pyinstaller = shutil.which("pyinstaller")
    if pyinstaller is None:
        print("PyInstaller not installed; skipping executable build.")
        print("To build manually:")
        print("python -m pip install pyinstaller")
        print("pyinstaller --onefile --name gas-pump-modbus-tester app_cli_entry.py")
        return
    subprocess.run(
        [
            pyinstaller,
            "--onefile",
            "--name",
            "gas-pump-modbus-tester",
            "app_cli_entry.py",
        ],
        cwd=release_dir,
        check=False,
    )


if __name__ == "__main__":
    raise SystemExit(main())
