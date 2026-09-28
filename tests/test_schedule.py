"""Tests for FirstView window and interval helpers."""

from datetime import time

from custom_components.firstview.config_flow import (
    _apply_preset,
    _intervals_valid,
    _normalize_hhmm,
    _window_valid,
)
from custom_components.firstview.const import (
    CONF_AM_ENABLED,
    CONF_AM_END,
    CONF_AM_START,
    CONF_DAILY_INTERVAL_HOURS,
    CONF_HOURLY_INTERVAL_MINUTES,
    CONF_PM_ENABLED,
    CONF_PM_END,
    CONF_PM_START,
    CONF_PRESET,
    PRESET_CUSTOM,
    PRESET_SCHOOL_DEFAULT,
)
from custom_components.firstview.coordinator import _parse_hhmm


def test_window_accepts_two_hours() -> None:
    """A two-hour window is inside the 4-hour cap."""
    assert _window_valid("06:00", "08:00") is True


def test_window_rejects_more_than_four_hours() -> None:
    """Windows longer than 4 hours are rejected."""
    assert _window_valid("06:00", "10:01") is False


def test_window_rejects_end_before_start() -> None:
    """A window that does not move forward is rejected."""
    assert _window_valid("08:00", "06:00") is False


def test_normalize_hhmm_truncates_seconds() -> None:
    """Selectors sometimes return HH:MM:SS."""
    assert _normalize_hhmm("06:00:00") == "06:00"


def test_school_default_preset_overwrites_windows() -> None:
    """The school preset forces the standard AM/PM windows."""
    data = _apply_preset(
        {
            CONF_PRESET: PRESET_SCHOOL_DEFAULT,
            CONF_AM_ENABLED: False,
            CONF_AM_START: "05:00:00",
            CONF_AM_END: "09:00",
            CONF_PM_ENABLED: False,
            CONF_PM_START: "12:00",
            CONF_PM_END: "18:00",
        }
    )

    assert data[CONF_AM_ENABLED] is True
    assert data[CONF_AM_START] == "06:00"
    assert data[CONF_AM_END] == "08:00"
    assert data[CONF_PM_ENABLED] is True
    assert data[CONF_PM_START] == "13:00"
    assert data[CONF_PM_END] == "15:00"


def test_custom_preset_keeps_windows() -> None:
    """Custom preset only normalizes the clock strings."""
    data = _apply_preset(
        {
            CONF_PRESET: PRESET_CUSTOM,
            CONF_AM_START: "07:15:00",
            CONF_AM_END: "09:15",
            CONF_PM_START: "14:00",
            CONF_PM_END: "16:00",
        }
    )

    assert data[CONF_AM_START] == "07:15"
    assert data[CONF_AM_END] == "09:15"


def test_intervals_respect_bounds() -> None:
    """Daily and frequent refresh intervals stay inside the allowed range."""
    assert _intervals_valid(
        {CONF_DAILY_INTERVAL_HOURS: 24, CONF_HOURLY_INTERVAL_MINUTES: 60}
    )
    assert not _intervals_valid(
        {CONF_DAILY_INTERVAL_HOURS: 1, CONF_HOURLY_INTERVAL_MINUTES: 60}
    )
    assert not _intervals_valid(
        {CONF_DAILY_INTERVAL_HOURS: 24, CONF_HOURLY_INTERVAL_MINUTES: 1}
    )


def test_parse_hhmm() -> None:
    """Clock strings become time objects for the coordinator."""
    assert _parse_hhmm("06:05") == time(6, 5)
