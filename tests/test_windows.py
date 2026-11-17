import pytest

from gridcast.windows import (
    TIMING_MATTERS_MIN_SPREAD_G_PER_KWH,
    Window,
    cleanest_window,
    dirtiest_window,
    timing_matters,
)


def test_cleanest_window_finds_lowest_mean() -> None:
    assert cleanest_window([9, 8, 1, 2, 9], 2) == Window(start=2, slots=2, mean=1.5)


def test_dirtiest_window_finds_highest_mean() -> None:
    assert dirtiest_window([1, 9, 8, 2, 1], 2) == Window(start=1, slots=2, mean=8.5)


def test_cleanest_window_picks_earliest_on_ties() -> None:
    assert cleanest_window([5, 1, 1, 5, 1, 1], 2).start == 1


def test_dirtiest_window_picks_earliest_on_ties() -> None:
    assert dirtiest_window([1, 5, 5, 1, 5, 5], 2).start == 1


def test_window_equal_to_whole_series() -> None:
    assert cleanest_window([3, 4, 8], 3) == Window(start=0, slots=3, mean=5.0)
    assert dirtiest_window([3, 4, 8], 3) == Window(start=0, slots=3, mean=5.0)


def test_single_slot_window() -> None:
    assert cleanest_window([4, 2, 7], 1).start == 1


def test_rejects_series_shorter_than_window() -> None:
    with pytest.raises(ValueError, match="at least 4 values, got 3"):
        cleanest_window([1, 2, 3], 4)


@pytest.mark.parametrize("slots", [0, -2])
def test_rejects_slots_below_one(slots: int) -> None:
    with pytest.raises(ValueError, match=f"got {slots}"):
        dirtiest_window([1, 2, 3], slots)


def test_timing_matters_at_exact_spread() -> None:
    spread = TIMING_MATTERS_MIN_SPREAD_G_PER_KWH
    assert timing_matters(Window(0, 2, 100.0), Window(4, 2, 100.0 + spread))


def test_timing_does_not_matter_just_below_spread() -> None:
    assert not timing_matters(Window(0, 2, 100.0), Window(4, 2, 119.9))
