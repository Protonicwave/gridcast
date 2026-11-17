"""Cleanest and dirtiest contiguous windows of a carbon intensity series."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

TIMING_MATTERS_MIN_SPREAD_G_PER_KWH = 20.0


@dataclass(frozen=True, slots=True)
class Window:
    """A run of `slots` consecutive values starting at index `start`."""

    start: int
    slots: int
    mean: float


def cleanest_window(values: Sequence[int], slots: int) -> Window:
    """Window with the lowest mean, earliest on ties. Raises ValueError on a bad size."""
    return _best_window(values, slots, lambda candidate, best: candidate < best)


def dirtiest_window(values: Sequence[int], slots: int) -> Window:
    """Window with the highest mean, earliest on ties. Raises ValueError on a bad size."""
    return _best_window(values, slots, lambda candidate, best: candidate > best)


def timing_matters(cleanest: Window, dirtiest: Window) -> bool:
    """True when the gap between the dirtiest and cleanest window is worth acting on."""
    return dirtiest.mean - cleanest.mean >= TIMING_MATTERS_MIN_SPREAD_G_PER_KWH


def _best_window(
    values: Sequence[int], slots: int, is_better: Callable[[int, int], bool]
) -> Window:
    if slots < 1:
        raise ValueError(f"expected slots of at least 1, got {slots}")
    if len(values) < slots:
        raise ValueError(f"expected at least {slots} values, got {len(values)}")
    # Integer sums keep ties exact, which float means would not.
    total = sum(values[:slots])
    best_total = total
    best_start = 0
    for start in range(1, len(values) - slots + 1):
        total += values[start + slots - 1] - values[start - 1]
        if is_better(total, best_total):
            best_total = total
            best_start = start
    return Window(start=best_start, slots=slots, mean=best_total / slots)
