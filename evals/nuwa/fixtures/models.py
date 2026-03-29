from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Record:
    id: int
    name: str
    email: str
    role: str
    active: bool
