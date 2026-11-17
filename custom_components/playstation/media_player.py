"""Console as a media player: on/standby/off, running app with cover, wake and rest."""

from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PlayStationConfigEntry
from .console import ddp_wakeup, rp_standby
from .const import (
    CONF_CREDENTIAL,
    CONF_HOST_TYPE,
    CONF_KIND,
    CONF_REGIST,
    DOMAIN,
    KIND_ACCOUNT,
)
from .coordinator import ConsoleCoordinator
from .entity import PlayStationEntity, rp_args


async def async_setup_entry(hass: HomeAssistant, entry: PlayStationConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    """Console only."""
    add([PSConsolePlayer(entry.runtime_data)])


class PSConsolePlayer(PlayStationEntity, MediaPlayerEntity):
    """State from DDP; cover from the PSN library when an account is configured."""

    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_media_content_type = MediaType.GAME
    def __init__(self, co: ConsoleCoordinator) -> None:  # noqa: D107
        super().__init__(co, "console")

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:  # noqa: D102
        o = self.coordinator.config_entry.options
        f = MediaPlayerEntityFeature(0)
        if o.get(CONF_CREDENTIAL):
            f |= MediaPlayerEntityFeature.TURN_ON
        if o.get(CONF_REGIST):
            f |= MediaPlayerEntityFeature.TURN_OFF
        return f

    @property
    def state(self) -> MediaPlayerState:  # noqa: D102
        s = (self.coordinator.data or {}).get("status")
        if s == "ligado":
            return MediaPlayerState.PLAYING if self.media_title else MediaPlayerState.ON
        return MediaPlayerState.OFF  # rest mode vs fully off is in the "Estado" sensor

    @property
    def media_title(self) -> str | None:  # noqa: D102
        d = self.coordinator.data or {}
        return d.get("running-app-name") if d.get("status") == "ligado" else None

    @property
    def media_content_id(self) -> str | None:  # noqa: D102
        return (self.coordinator.data or {}).get("running-app-titleid")

    @property
    def media_image_url(self) -> str | None:  # noqa: D102
        tid = self.media_content_id
        if not tid or not self.media_title:
            return None
        for e in self.hass.config_entries.async_entries(DOMAIN):
            if e.data.get(CONF_KIND) == KIND_ACCOUNT and hasattr(e, "runtime_data"):
                for g in (e.runtime_data.data or {}).get("games") or []:
                    if str(g.get("titleId", "")).startswith(tid):
                        return g.get("imageUrl")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:  # noqa: D102
        d = self.coordinator.data or {}
        return {"host_id": d.get("host-id"), "tipo": d.get("host-type"), "porta_remote_play": d.get("host-request-port")}

    async def async_turn_on(self) -> None:  # noqa: D102
        e = self.coordinator.config_entry
        await ddp_wakeup(e.data["host"], e.data.get(CONF_HOST_TYPE, "PS5"), e.options[CONF_CREDENTIAL])

    async def async_turn_off(self) -> None:  # noqa: D102
        try:
            await rp_standby(*rp_args(self.coordinator.config_entry))
        except (ConnectionError, ValueError, OSError) as err:
            raise HomeAssistantError(f"Remote Play: {err}") from err
        await self.coordinator.async_request_refresh()
