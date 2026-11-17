"""Images: avatar and current/last game cover."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import PlayStationConfigEntry
from .coordinator import AccountCoordinator, game_of
from .entity import PlayStationEntity
from .sensor import _last_game, _me

IMAGES: dict[str, Callable[[dict[str, Any]], str | None]] = {
    "avatar": lambda d: next((a.get("avatarUrl") for a in (d.get("profile") or {}).get("avatarUrls", [])), None),
    "capa_do_jogo": lambda d: (game_of(_me(d)) or {}).get("conceptIconUrl") or (_last_game(d) or {}).get("imageUrl"),
}


async def async_setup_entry(hass: HomeAssistant, entry: PlayStationConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    """Account only."""
    if isinstance(entry.runtime_data, AccountCoordinator):
        add(PSImage(hass, entry.runtime_data, k) for k in IMAGES)


class PSImage(PlayStationEntity, ImageEntity):
    """Remote image following coordinator data."""

    def __init__(self, hass: HomeAssistant, co: AccountCoordinator, key: str) -> None:  # noqa: D107
        PlayStationEntity.__init__(self, co, key)
        ImageEntity.__init__(self, hass)
        self._fn = IMAGES[key]
        self._attr_image_url = self._fn(co.data or {})
        self._attr_image_last_updated = dt_util.utcnow()

    def _handle_coordinator_update(self) -> None:
        url = self._fn(self.coordinator.data or {})
        if url != self._attr_image_url:
            self._attr_image_url = url
            self._cached_image = None
            self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()
