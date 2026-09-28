"""Tests for FirstView trip and map-marker helpers."""

from datetime import datetime, timedelta, timezone

from custom_components.firstview.coordinator import (
    _as_int,
    _build_student_stops,
    _build_vehicle_meta,
    _build_vehicle_stops,
    _collect_trip_ids,
    _collect_vehicle_ids,
    _fresh_vehicle_ids,
    _status_rank,
    _trip_students,
)
from custom_components.firstview.device_tracker import _coords_visible


def _live_trip() -> dict:
    return {
        "id": 10,
        "status": "LIVE",
        "direction": "AM",
        "name": "RT-12",
        "vehicleId": "bus-1",
        "vehicleLp": "BUS1",
        "runs": [
            {
                "id": 999,
                "students": [
                    {"id": 7, "firstName": "Ada", "pickupStopId": 3},
                    {"id": 7, "firstName": "Ada", "pickupStopId": 3},
                ],
                "stops": [
                    {"id": 1, "order": 1, "addressType": "SCHOOL"},
                    {
                        "id": 3,
                        "order": 4,
                        "addressType": "STUDENT",
                        "addressName": "Home",
                    },
                ],
            }
        ],
    }


def test_trip_students_dedupes_nested_and_top_level() -> None:
    """The same student is not counted twice across payload shapes."""
    trip = _live_trip()
    trip["followedStudents"] = [
        {"id": 7, "firstName": "Ada"},
        {"id": 8, "firstName": "Bea"},
    ]

    students = _trip_students(trip)

    assert [student["id"] for student in students] == [7, 8]


def test_status_rank_prefers_live() -> None:
    """LIVE outranks upcoming and completed trips."""
    assert _status_rank("LIVE") > _status_rank("UPCOMING") > _status_rank("COMPLETED")


def test_vehicle_meta_keeps_live_trip() -> None:
    """A later completed payload does not replace the live bus label."""
    completed = {
        "id": 11,
        "status": "COMPLETED",
        "name": "RT-12",
        "vehicleId": "bus-1",
        "vehicleLp": "OLD",
    }

    meta = _build_vehicle_meta([completed, _live_trip()])

    assert meta["bus-1"]["status"] == "LIVE"
    assert meta["bus-1"]["vehicle_lp"] == "BUS1"
    assert meta["bus-1"]["student_names"] == ["Ada"]


def test_collect_trip_ids_ignores_non_integers() -> None:
    """Only integer trip ids are sent to the progress API."""
    assert _collect_trip_ids([_live_trip(), {"id": "run-1"}, {"id": 4}]) == [4, 10]


def test_as_int_rejects_bools() -> None:
    """Bool is a subclass of int and must not become a stop id."""
    assert _as_int(True) is None
    assert _as_int(3.0) == 3
    assert _as_int("4") is None


def test_stops_left_until_house() -> None:
    """stops_left is house-stop order minus the last visited stop."""
    stats = _build_student_stops(
        [_live_trip()],
        {10: {"lastVisitedStop": 2, "totalStopsCount": 8}},
    )

    assert stats["7"]["stops_left"] == 2
    assert stats["7"]["target_kind"] == "pickup"
    assert stats["7"]["stop_name"] == "Home"
    assert stats["7"]["route"] == "RT-12"

    rolled = _build_vehicle_stops(stats)
    assert rolled["bus-1"]["stops_left"] == 2
    assert rolled["bus-1"]["students"] == {"Ada": 2}


def test_collect_vehicle_ids_is_unique_and_sorted() -> None:
    """Vehicle ids are gathered from trips, locations, and progress."""
    ids = _collect_vehicle_ids(
        [_live_trip(), {"previousVehicleId": "bus-2"}],
        [{"vehicleId": "bus-3"}],
        [{"vehicleId": "bus-1"}],
    )

    assert ids == ["bus-1", "bus-2", "bus-3"]


def test_fresh_vehicle_ids_skip_completed_trips() -> None:
    """A recent fix on a completed trip does not count as live."""
    now = datetime.now(tz=timezone.utc).isoformat()
    locations = {
        "bus-1": {"latitude": 1.0, "longitude": 2.0, "eventTimestamp": now},
        "bus-2": {"latitude": 1.0, "longitude": 2.0, "eventTimestamp": now},
    }
    meta = {"bus-2": {"status": "COMPLETED"}}

    assert _fresh_vehicle_ids(locations, meta) == {"bus-1"}


def test_fresh_vehicle_ids_skip_old_fixes() -> None:
    """Fixes older than the freshness window are dropped."""
    old = (datetime.now(tz=timezone.utc) - timedelta(hours=2)).isoformat()
    locations = {"bus-1": {"latitude": 1.0, "longitude": 2.0, "eventTimestamp": old}}

    assert _fresh_vehicle_ids(locations, {}) == set()


def test_coords_visible_follows_live_and_status() -> None:
    """Map markers stay up for a websocket bus and hide completed routes."""
    assert _coords_visible({"ws_live_vehicle_ids": ["bus-1"]}, "bus-1") is True
    assert _coords_visible({"live_vehicle_ids": ["other"]}, "bus-1") is False
    assert (
        _coords_visible({"vehicle_meta": {"bus-1": {"status": "COMPLETED"}}}, "bus-1")
        is False
    )
    assert (
        _coords_visible({"vehicle_meta": {"bus-1": {"status": "LIVE"}}}, "bus-1")
        is True
    )
