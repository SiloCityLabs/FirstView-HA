# FirstView Home Assistant Integration (HACS)

Custom Home Assistant integration for FirstView monitoring.

## Features

- Config flow asks for:
  - Email
  - Password
  - Morning websocket window start/end
  - Afternoon websocket window start/end
- Window validation enforces max 2 hours per window.
- Automatic monitoring:
  - Daily checks: students + trips
  - Hourly checks: trips progress, notifications, recent location
- Websocket:
  - Connects only during configured AM/PM windows
  - Auto-retries with backoff
  - Re-subscribes with trip IDs + vehicle IDs
  - Fires HA event `firstview_live_event` for automations
- Entities:
  - Sensors for counts + websocket status
  - Device trackers per student bus (best-effort student-to-vehicle mapping, with last-known vehicle fallback)
  - Bus telemetry attributes on tracker (vehicle ID, device ID, heading, speed, odometer, ignition/motion/door)
  - Supports options flow to update AM/PM windows without re-adding integration

## Installation

1. Copy `custom_components/firstview` into your Home Assistant `custom_components/`.
2. Restart Home Assistant.
3. Add integration from **Settings -> Devices & Services -> Add Integration**.
4. Search for `FirstView`.

## Notes

- Uses Cognito SRP login via `pycognito`.
