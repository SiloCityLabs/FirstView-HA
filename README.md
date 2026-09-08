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
- Window validation enforces max 4 hours per window.
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
  - Device-page button: **Toggle Websocket** (manual on/off override; still constrained by enabled days/windows and 4-hour window settings)
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

## Example: bus near-home notifications (Rodriguez household)

Real setup used with this integration in Amherst, NY (Home Assistant map + notify). Alert on **buses/routes**, not students — Delilah and Genevieve share one bus, so kid-level trackers would double-notify.

| Route | Riders | Typical device name |
|-------|--------|---------------------|
| `AH-84` | Delilah, Genevieve | `AH-84 (PCUJ6246)` (vehicle ID changes day to day) |
| `AH-91` | Luzellie | `AH-91 (PCUJ6413)` |

Supporting pieces:

- Passive zone `zone.bus_alert` at home, radius **610 m (~2000 ft)**, icon `mdi:bus-school` (passive so it does not affect person home/away)
- Automations match FirstView `device_tracker` entities by the `route` attribute (`AH-84` / `AH-91`), so changing `vehicleId`s still work
- 20-second debounce; skipped when `input_boolean.vacation_mode` is on
- Notifies `notify.luis_phone` and `notify.pixel_9_pro`

Example automation for route **AH-84** (duplicate and change `AH-84` → `AH-91` for Luzellie’s bus):

```yaml
alias: "FirstView: AH-84 bus near home"
id: firstview_bus_ah84_near_home
description: >
  Notify when FirstView route AH-84 bus is within 2000 ft of home.
  Matches by route so vehicle ID changes still work; one alert per bus (not per kid).
mode: single
max_exceeded: silent
triggers:
  - trigger: template
    id: near
    for:
      seconds: 20
    value_template: >
      {% set thresh_km = 2000 / 3280.84 %}
      {% set ns = namespace(near=false) %}
      {% for s in states.device_tracker
            if state_attr(s.entity_id, 'route') == 'AH-84'
            and state_attr(s.entity_id, 'latitude') is not none %}
        {% set d = distance(s.entity_id, 'zone.home') %}
        {% if d is not none and d <= thresh_km %}
          {% set ns.near = true %}
        {% endif %}
      {% endfor %}
      {{ ns.near }}
conditions:
  - condition: state
    entity_id: input_boolean.vacation_mode
    state: "off"
actions:
  - action: notify.send_message
    target:
      entity_id:
        - notify.luis_phone
        - notify.pixel_9_pro
    data:
      title: "School bus nearby (AH-84)"
      message: >
        {% set thresh_km = 2000 / 3280.84 %}
        {% set ns = namespace(name='Bus AH-84', students='') %}
        {% for s in states.device_tracker
              if state_attr(s.entity_id, 'route') == 'AH-84'
              and state_attr(s.entity_id, 'latitude') is not none %}
          {% set d = distance(s.entity_id, 'zone.home') %}
          {% if d is not none and d <= thresh_km %}
            {% set ns.name = state_attr(s.entity_id, 'friendly_name') or 'Bus AH-84' %}
            {% set kids = state_attr(s.entity_id, 'students') %}
            {% if kids %}{% set ns.students = kids | join(', ') %}{% endif %}
          {% endif %}
        {% endfor %}
        {{ ns.name }}{% if ns.students %} ({{ ns.students }}){% endif %} is within 2000 ft of home.
```

Suggested websocket windows for three staggered routes (max 4 hours each): e.g. AM `06:00`–`10:00`, PM `13:00`–`17:00`.

## Notes

- Uses Cognito SRP login via `pycognito`.
