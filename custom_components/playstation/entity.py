"""Base entities and device info."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceEntryType,
    DeviceInfo,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .console import firmware
from .const import (
    CONF_ACCOUNT_ID,
    CONF_HOST_ID,
    CONF_HOST_TYPE,
    CONF_ONLINE_ID,
    CONF_REGIST,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import AccountCoordinator, ConsoleCoordinator, PortableCoordinator


def account_device(co: AccountCoordinator) -> DeviceInfo:
    """The PSN account as a service device."""
    return DeviceInfo(
        identifiers={(DOMAIN, co.client.account_id)},
        manufacturer=MANUFACTURER,
        model="PlayStation Network",
        name=f"PSN {co.client.online_id}",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=f"https://psnprofiles.com/{co.client.online_id}",
    )


def platform_device(co: AccountCoordinator, platform: str, name: str) -> DeviceInfo:
    """One device per platform seen on the account (PS5, PS4, PS3, PS Vita, PC)."""
    info = DeviceInfo(
        identifiers={(DOMAIN, f"{co.client.account_id}_{platform}")},
        manufacturer=MANUFACTURER,
        model=name,
        name=name,
        entry_type=DeviceEntryType.SERVICE,
    )
    if acct := dr.async_get(co.hass).async_get_device_by_identifier((DOMAIN, co.client.account_id), co.config_entry.entry_id):
        info["via_device_id"] = acct.id
    return info


def portable_device(co: PortableCoordinator) -> DeviceInfo:
    """PlayStation Portal (or another Sony device) known only by MAC/IP."""
    e = co.config_entry
    return DeviceInfo(
        identifiers={(DOMAIN, e.data["mac"])},
        connections={(CONNECTION_NETWORK_MAC, e.data["mac"])},
        manufacturer=MANUFACTURER,
        model=e.data.get("model", "PlayStation Portal"),
        name=e.title,
    )


def console_device(co: ConsoleCoordinator) -> DeviceInfo:
    """A PS5/PS4 on the LAN."""
    e = co.config_entry
    host_id = e.data[CONF_HOST_ID]
    mac = ":".join(host_id[i : i + 2] for i in range(0, 12, 2)).lower()
    return DeviceInfo(
        identifiers={(DOMAIN, host_id)},
        connections={(CONNECTION_NETWORK_MAC, mac)},
        manufacturer=MANUFACTURER,
        model=e.data.get(CONF_HOST_TYPE, "PlayStation"),
        name=e.title,
        sw_version=firmware((co.data or {}).get("system-version")),
    )


def rp_args(entry: ConfigEntry) -> tuple[Any, ...]:
    """Arguments for console.rp_* from a paired console entry."""
    regist = entry.options.get(CONF_REGIST)
    if not regist:
        raise ValueError("console not paired for Remote Play (Configurar → Parear)")
    return (entry.data["host"], entry.options[CONF_ONLINE_ID], entry.options[CONF_ACCOUNT_ID], entry.data[CONF_HOST_ID], entry.data.get(CONF_HOST_TYPE, "PS5"), regist)


class PlayStationEntity(CoordinatorEntity[AccountCoordinator | ConsoleCoordinator | PortableCoordinator]):
    """Unique id = <account id|host id>_<key>."""

    _attr_has_entity_name = True

    def __init__(self, co: AccountCoordinator | ConsoleCoordinator | PortableCoordinator, key: str, name: str | None = None) -> None:  # noqa: D107
        super().__init__(co)
        if isinstance(co, AccountCoordinator):
            base = co.client.account_id
            self._attr_device_info = account_device(co)
        elif isinstance(co, PortableCoordinator):
            base = co.config_entry.data["mac"].replace(":", "")
            self._attr_device_info = portable_device(co)
        else:
            base = co.config_entry.data[CONF_HOST_ID]
            self._attr_device_info = console_device(co)
        self._attr_unique_id = f"{base}_{key}"
        if name is None:
            self._attr_translation_key = key
        else:
            self._attr_name = name
