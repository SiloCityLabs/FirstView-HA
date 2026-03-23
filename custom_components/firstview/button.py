"""Button entities for FirstView."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    async_add_entities([FirstViewToggleSocketButton(coordinator, entry.entry_id)])


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
