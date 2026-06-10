from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CadernoRange:
    inicio: int
    page_size: int
    position_start: int
    position_end: int
    is_last: bool


def build_caderno_ranges(*, expected_total: int, page_size: int) -> list[CadernoRange]:
    if expected_total <= 0:
        raise ValueError("expected_total must be > 0")
    if page_size <= 0:
        raise ValueError("page_size must be > 0")

    ranges: list[CadernoRange] = []
    for inicio in range(0, expected_total, page_size):
        position_start = inicio + 1
        position_end = min(inicio + page_size, expected_total)
        ranges.append(
            CadernoRange(
                inicio=inicio,
                page_size=page_size,
                position_start=position_start,
                position_end=position_end,
                is_last=position_end == expected_total,
            )
        )
    return ranges
