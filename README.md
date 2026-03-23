# FirstView Home Assistant Integration (HACS)

Custom Home Assistant integration for FirstView monitoring.

## Features

- Config flow asks for:
  - Email
  - Password
  - Preset (`custom` or `school_default`)
  - AM enabled checkbox
  - Morning websocket window start/end
  - PM enabled checkbox
  - Afternoon websocket window start/end
  - Daily refresh interval (hours)
  - Frequent refresh interval (minutes)
  - Weekday checkboxes (`M T W R F Sat Sun`; `R` = Thursday)
- Window validation enforces max 2 hours per window.
- Automatic monitoring:
  - Daily checks: students + trips
  - Hourly checks: trips progress, notifications, recent location
- Websocket:
  - Connects only during configured AM/PM windows and enabled weekdays
  - Auto-retries with backoff
  - Re-subscribes with trip IDs + vehicle IDs
  - Reuses last successful subscriptions during startup before first poll
  - Jittered reconnect backoff with diagnostics
  - Fires HA event `firstview_live_event` for automations
- Entities:
  - Sensors for counts + websocket status
  - Device trackers per student bus (best-effort student-to-vehicle mapping, with confidence attribute)
  - Device trackers per bus/vehicle for map view and diagnostics
  - Bus telemetry attributes on tracker (vehicle ID, device ID, heading, speed, odometer, ignition/motion/door)
  - Supports options flow to update AM/PM windows without re-adding integration
  - Device-page button: **Toggle Websocket** (manual on/off override; still constrained by enabled days/windows and 2-hour window settings)
  - Action entities:
    - Mark all notifications read
    - Select notification ID + status (`READ`/`CREATED`) and apply
    - Delete selected notification (double-press confirm)
    - Delete all notifications (double-press confirm)

## Runtime stability behavior

- Cognito refresh/login uses retry + exponential backoff with jitter.
- On transient auth/network/API errors, coordinator serves last-good cached data to reduce unavailable flapping.
- Repeated auth failures create a persistent Home Assistant notification; it is cleared automatically after successful recovery.

## Installation

1. Copy `custom_components/firstview` into your Home Assistant `custom_components/`.
2. Restart Home Assistant.
3. Add integration from **Settings -> Devices & Services -> Add Integration**.
4. Search for `FirstView`.

## Notes

- Uses Cognito SRP login via `pycognito`.
