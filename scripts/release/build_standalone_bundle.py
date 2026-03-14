#!/usr/bin/env python3
"""
Build standalone release bundles in one command.

Usage:
  python scripts/release/build_standalone_bundle.py
  python scripts/release/build_standalone_bundle.py --skip-build
  python scripts/release/build_standalone_bundle.py --format both
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.version import APP_NAME, APP_VERSION  # noqa: E402


def run_command(cmd: list[str]) -> None:
    print(f"[cmd] {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def detect_platform() -> tuple[str, str, str]:
    if sys.platform.startswith("win"):
        return "windows", f"{APP_NAME}.exe", "install-web-rooter.bat"
    if sys.platform == "darwin":
        return "macos", APP_NAME, "install-web-rooter.sh"
    return "linux", APP_NAME, "install-web-rooter.sh"


def normalize_format(fmt: str, platform_key: str) -> str:
    lowered = fmt.strip().lower()
    if lowered in {"zip", "tar.gz", "both"}:
        return lowered
    if platform_key == "windows":
        return "zip"
    return "tar.gz"


def create_archive(source_dir: Path, output_file: Path, fmt: str) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if output_file.exists():
        output_file.unlink()

    if fmt == "zip":
        with zipfile.ZipFile(output_file, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for item in source_dir.rglob("*"):
                if item.is_file():
                    zf.write(item, arcname=item.relative_to(source_dir))
        return

    if fmt == "tar.gz":
        with tarfile.open(output_file, "w:gz") as tf:
            for item in source_dir.rglob("*"):
                tf.add(item, arcname=item.relative_to(source_dir))
        return

    raise ValueError(f"Unsupported archive format: {fmt}")


def build_bundle(skip_build: bool, archive_format: str) -> list[Path]:
    platform_key, binary_name, installer_name = detect_platform()

    dist_dir = ROOT / "dist"
    binary_path = dist_dir / binary_name
    if not skip_build:
        run_command([sys.executable, "-m", "pip", "install", "-U", "pyinstaller"])
        run_command(["pyinstaller", "web-rooter.spec", "--clean"])

    if not binary_path.exists():
        raise FileNotFoundError(
            f"Binary not found: {binary_path}. "
            f"Run without --skip-build or check pyinstaller output."
        )

    installer_src = ROOT / "packaging" / "standalone" / ("windows" if platform_key == "windows" else "unix") / installer_name
    readme_src = ROOT / "packaging" / "standalone" / "README.txt"
    if not installer_src.exists():
        raise FileNotFoundError(f"Installer template not found: {installer_src}")
    if not readme_src.exists():
        raise FileNotFoundError(f"Standalone README not found: {readme_src}")

    bundle_root = dist_dir / "standalone" / platform_key
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    bundle_root.mkdir(parents=True, exist_ok=True)

    shutil.copy2(binary_path, bundle_root / binary_name)
    shutil.copy2(installer_src, bundle_root / installer_name)
    shutil.copy2(readme_src, bundle_root / "README.txt")
    if (ROOT / "LICENSE").exists():
        shutil.copy2(ROOT / "LICENSE", bundle_root / "LICENSE")

    if platform_key != "windows":
        (bundle_root / binary_name).chmod(0o755)
        (bundle_root / installer_name).chmod(0o755)

    tag = f"{APP_NAME}-standalone-v{APP_VERSION}-{platform_key}"
    out_dir = dist_dir / "release"
    created: list[Path] = []

    if archive_format in {"zip", "both"}:
        zip_path = out_dir / f"{tag}.zip"
        create_archive(bundle_root, zip_path, "zip")
        created.append(zip_path)

    if archive_format in {"tar.gz", "both"}:
        tgz_path = out_dir / f"{tag}.tar.gz"
        create_archive(bundle_root, tgz_path, "tar.gz")
        created.append(tgz_path)

    print("[ok] bundle directory:", bundle_root)
    for artifact in created:
        print("[ok] archive:", artifact)
    return created


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build standalone release bundle")
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip pyinstaller build and only package existing dist binary.",
    )
    parser.add_argument(
        "--format",
        default="auto",
        choices=["auto", "zip", "tar.gz", "both"],
        help="Archive format. auto: zip on Windows, tar.gz on Unix.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    platform_key, _, _ = detect_platform()
    archive_format = normalize_format(args.format, platform_key)
    build_bundle(skip_build=args.skip_build, archive_format=archive_format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
