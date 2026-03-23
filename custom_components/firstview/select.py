"""Select entities for FirstView actions."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FirstViewCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: FirstViewCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            FirstViewNotificationIdSelect(coordinator, entry.entry_id),
            FirstViewNotificationStatusSelect(coordinator, entry.entry_id),
        ]
    )


class _FirstViewSelect(CoordinatorEntity[FirstViewCoordinator], SelectEntity):
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


class FirstViewNotificationIdSelect(_FirstViewSelect):
    def __init__(self, coordinator: FirstViewCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "notification_id", "Notification ID")

    @property
    def options(self) -> list[str]:
        return (self.coordinator.data or {}).get("notification_ids", [])

    @property
    def current_option(self) -> str | None:
        return (self.coordinator.data or {}).get("selected_notification_id")

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_selected_notification_id(option)


class FirstViewNotificationStatusSelect(_FirstViewSelect):
    _attr_options = ["CREATED", "READ"]

    def __init__(self, coordinator: FirstViewCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "notification_status", "Notification Status")

    @property
    def current_option(self) -> str | None:
        return (self.coordinator.data or {}).get("selected_notification_status", "READ")

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_selected_notification_status(option)
