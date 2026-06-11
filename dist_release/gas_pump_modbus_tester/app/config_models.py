"""Dataclasses for protected configuration write operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WriteResult:
    name: str
    success: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConfigWritePlan:
    title: str
    warning: str
    writes: list[tuple[int, int]]
    readback_registers: tuple[int, int] | None = None
    expected_readback_value: int | None = None
