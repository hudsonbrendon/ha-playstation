"""Events derived between polls."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PlayStationConfigEntry
from .const import (
    CONF_KIND,
    EVENT_APP,
    EVENT_FRIEND_ONLINE,
    EVENT_GAME_STARTED,
    EVENT_GAME_STOPPED,
    EVENT_INSTALLED,
    EVENT_NEW_MESSAGE,
    EVENT_OFFLINE,
    EVENT_ONLINE,
    EVENT_POWER_ON,
    EVENT_REMOVED,
    EVENT_REST,
    EVENT_SALE,
    EVENT_STREAM_START,
    EVENT_STREAM_STOP,
    EVENT_TROPHY,
    KIND_ACCOUNT,
)
from .coordinator import AccountCoordinator, ConsoleCoordinator
from .entity import PlayStationEntity

ACCOUNT = {"trofeus": [EVENT_TROPHY], "partidas": [EVENT_GAME_STARTED, EVENT_GAME_STOPPED], "presenca": [EVENT_ONLINE, EVENT_OFFLINE], "amigos_evento": [EVENT_FRIEND_ONLINE], "mensagens": [EVENT_NEW_MESSAGE], "promocoes": [EVENT_SALE], "instalacoes": [EVENT_INSTALLED, EVENT_REMOVED]}
CONSOLE = {"energia": [EVENT_POWER_ON, EVENT_REST], "apps": [EVENT_APP]}


async def async_setup_entry(hass: HomeAssistant, entry: PlayStationConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    """Add event entities."""
    kind = entry.data.get(CONF_KIND)
    kinds = ACCOUNT if kind == KIND_ACCOUNT else {"presenca": [EVENT_ONLINE, EVENT_OFFLINE], "transmissao": [EVENT_STREAM_START, EVENT_STREAM_STOP]} if kind == "portable" else CONSOLE
    add(PSEvent(entry.runtime_data, k, t) for k, t in kinds.items())


class PSEvent(PlayStationEntity, EventEntity):
    """Fires coordinator events of its types."""

    def __init__(self, co: AccountCoordinator | ConsoleCoordinator, key: str, types: list[str]) -> None:  # noqa: D107
        super().__init__(co, key)
        self._attr_event_types = types

    def _handle_coordinator_update(self) -> None:
        for kind, data in self.coordinator.events:
            if kind in self._attr_event_types:
                self._trigger_event(kind, data)
        super()._handle_coordinator_update()
