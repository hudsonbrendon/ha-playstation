"""Binary sensors: PS Plus, online, playing (account); on, Remote Play paired (console)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PlayStationConfigEntry
from .const import CONF_CREDENTIAL, CONF_KIND, CONF_REGIST, KIND_ACCOUNT
from .coordinator import AccountCoordinator, ConsoleCoordinator, game_of
from .entity import PlayStationEntity
from .sensor import _me


@dataclass(frozen=True, kw_only=True)
class PSBinaryDescription(BinarySensorEntityDescription):
    """``value(data, entry)``."""

    value: Callable[[dict[str, Any], Any], bool | None]


ACCOUNT = (
    PSBinaryDescription(key="ps_plus", value=lambda d, e: bool((d.get("profile") or {}).get("plus")) if d.get("profile") else None),
    PSBinaryDescription(key="online", device_class=BinarySensorDeviceClass.CONNECTIVITY, value=lambda d, e: _me(d).get("availability") == "availableToPlay" if _me(d) else None),
    PSBinaryDescription(key="jogando", value=lambda d, e: bool(game_of(_me(d))) if _me(d) else None),
    PSBinaryDescription(key="verificado", entity_category=EntityCategory.DIAGNOSTIC, value=lambda d, e: (d.get("profile") or {}).get("isOfficiallyVerified")),
)
PORTABLE = (
    PSBinaryDescription(key="online", device_class=BinarySensorDeviceClass.CONNECTIVITY, value=lambda d, e: d.get("online")),
    PSBinaryDescription(key="transmitindo", value=lambda d, e: d.get("streaming")),
)
CONSOLE = (
    PSBinaryDescription(key="ligado", device_class=BinarySensorDeviceClass.POWER, value=lambda d, e: d.get("status") == "ligado"),
    PSBinaryDescription(key="na_rede", device_class=BinarySensorDeviceClass.CONNECTIVITY, entity_category=EntityCategory.DIAGNOSTIC, value=lambda d, e: d.get("status") in ("ligado", "repouso")),
    PSBinaryDescription(key="remote_play_pareado", entity_category=EntityCategory.DIAGNOSTIC, value=lambda d, e: bool(e.options.get(CONF_REGIST))),
    PSBinaryDescription(key="pode_ligar", entity_category=EntityCategory.DIAGNOSTIC, value=lambda d, e: bool(e.options.get(CONF_CREDENTIAL))),
)


async def async_setup_entry(hass: HomeAssistant, entry: PlayStationConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    """Add binary sensors."""
    kind = entry.data.get(CONF_KIND)
    descs = ACCOUNT if kind == KIND_ACCOUNT else PORTABLE if kind == "portable" else CONSOLE
    co = entry.runtime_data
    add(PSBinary(co, d) for d in descs)
    if entry.data.get(CONF_KIND) != KIND_ACCOUNT:
        return
    seen: set[str] = set()

    @callback
    def platforms() -> None:
        from .platforms import summarize

        new = [PlatformPlaying(co, p) for p in summarize(co.data or {}) if p not in seen]
        seen.update(x.ps_platform for x in new)
        if new:
            add(new)

    platforms()
    entry.async_on_unload(co.async_add_listener(platforms))


class PlatformPlaying(PlayStationEntity, BinarySensorEntity):
    """Playing on this platform right now (PS Vita/PS3 included, via legacy presence)."""

    def __init__(self, co: AccountCoordinator, platform: str) -> None:  # noqa: D107
        from .entity import platform_device
        from .platforms import PLATFORMS

        super().__init__(co, "jogando")
        self.ps_platform = platform
        self._attr_unique_id = f"{co.client.account_id}_{platform}_jogando"
        self._attr_device_info = platform_device(co, platform, PLATFORMS[platform])

    @property
    def is_on(self) -> bool:  # noqa: D102
        from .platforms import summarize

        return bool(summarize(self.coordinator.data or {}).get(self.ps_platform, {}).get("jogando"))


class PSBinary(PlayStationEntity, BinarySensorEntity):
    """Description-driven binary sensor."""

    entity_description: PSBinaryDescription

    def __init__(self, co: AccountCoordinator | ConsoleCoordinator, desc: PSBinaryDescription) -> None:  # noqa: D107
        super().__init__(co, desc.key)
        self.entity_description = desc

    @property
    def is_on(self) -> bool | None:  # noqa: D102
        return self.entity_description.value(self.coordinator.data or {}, self.coordinator.config_entry)
