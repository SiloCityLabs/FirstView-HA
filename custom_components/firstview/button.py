"""Button entities for FirstView."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DELETE_CONFIRM_WINDOW_SECONDS, DOMAIN
from .coordinator import FirstViewCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: FirstViewCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            FirstViewToggleSocketButton(coordinator, entry.entry_id),
            FirstViewMarkAllReadButton(coordinator, entry.entry_id),
            FirstViewApplyNotificationStatusButton(coordinator, entry.entry_id),
            FirstViewDeleteSelectedNotificationButton(coordinator, entry.entry_id),
            FirstViewDeleteAllNotificationsButton(coordinator, entry.entry_id),
        ]
    )


class FirstViewToggleSocketButton(CoordinatorEntity[FirstViewCoordinator], ButtonEntity):
    """Toggle websocket on/off from device page."""

    _attr_has_entity_name = True
    _attr_name = "Toggle Websocket"

    def __init__(self, coordinator: FirstViewCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_toggle_websocket"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="FirstView",
            manufacturer="FirstView",
            model="Cloud Integration",
        )

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return {
            "socket_enabled": data.get("socket_enabled", True),
            "websocket_connected": data.get("websocket_connected", False),
        }

    async def async_press(self) -> None:
        await self.coordinator.async_toggle_socket_enabled()


class _FirstViewActionButton(CoordinatorEntity[FirstViewCoordinator], ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: FirstViewCoordinator, entry_id: str, unique: str, name: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_{unique}"
        self._attr_name = name

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="FirstView",
            manufacturer="FirstView",
            model="Cloud Integration",
        )


class FirstViewMarkAllReadButton(_FirstViewActionButton):
    def __init__(self, coordinator: FirstViewCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "mark_all_read", "Mark All Notifications Read")

    async def async_press(self) -> None:
        await self.coordinator.async_mark_all_notifications_read()


class FirstViewApplyNotificationStatusButton(_FirstViewActionButton):
    def __init__(self, coordinator: FirstViewCoordinator, entry_id: str) -> None:
        super().__init__(
            coordinator, entry_id, "apply_notification_status", "Apply Selected Notification Status"
        )

    async def async_press(self) -> None:
        await self.coordinator.async_update_selected_notification_status()


class FirstViewDeleteSelectedNotificationButton(_FirstViewActionButton):
    def __init__(self, coordinator: FirstViewCoordinator, entry_id: str) -> None:
        super().__init__(
            coordinator, entry_id, "delete_selected_notification", "Delete Selected Notification"
        )
        self._last_press: str | None = None

    async def async_press(self) -> None:
        now = dt_util.utcnow()
        if self._last_press:
            previous = dt_util.parse_datetime(self._last_press)
            if previous and now - previous <= timedelta(seconds=DELETE_CONFIRM_WINDOW_SECONDS):
                self._last_press = None
                await self.coordinator.async_delete_selected_notification()
                return
        self._last_press = now.isoformat()
        _LOGGER.warning(
            "FirstView delete-selected requires second press within %ss",
            DELETE_CONFIRM_WINDOW_SECONDS,
        )


class FirstViewDeleteAllNotificationsButton(_FirstViewActionButton):
    def __init__(self, coordinator: FirstViewCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "delete_all_notifications", "Delete All Notifications")
        self._last_press: str | None = None

    async def async_press(self) -> None:
        now = dt_util.utcnow()
        if self._last_press:
            previous = dt_util.parse_datetime(self._last_press)
            if previous and now - previous <= timedelta(seconds=DELETE_CONFIRM_WINDOW_SECONDS):
                self._last_press = None
                await self.coordinator.async_delete_all_notifications()
                return
        self._last_press = now.isoformat()
        _LOGGER.warning(
            "FirstView delete-all requires second press within %ss",
            DELETE_CONFIRM_WINDOW_SECONDS,
        )
