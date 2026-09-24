"""Locate the LPC1343 boot ROM dump for tests. The image is not in the repo."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

FULL_DUMP_SHA256 = "f9888cc2459c184e67f84878271e2c12373e2887531f6e29a948efba01fe6dcb"


def rom_path() -> Path | None:
    candidates: list[Path] = []
    env = os.environ.get("LPC1343_ROM")
    if env:
        candidates.append(Path(env))
    here = Path(__file__).resolve().parents[1]
    candidates.append(here.parent / "LPC-ROP" / "LPC1343_bootloader_dump.bin")
    for path in candidates:
        if path.is_file():
            return path
    return None


def load_rom() -> bytes | None:
    path = rom_path()
    if path is None:
        return None
    data = path.read_bytes()
    if len(data) == 32768:
        digest = hashlib.sha256(data).hexdigest()
        if digest != FULL_DUMP_SHA256:
            raise AssertionError(f"{path} sha256 {digest} != {FULL_DUMP_SHA256}")
    return data
