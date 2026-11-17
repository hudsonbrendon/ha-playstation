"""PlayStation: PSN account + local consoles (DDP discovery/wake, Remote Play standby and buttons)."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .console import BUTTONS, rp_buttons
from .const import (
    ACCOUNT_PLATFORMS,
    CONF_KIND,
    CONF_NPSSO,
    CONSOLE_PLATFORMS,
    DOMAIN,
    KIND_ACCOUNT,
    KIND_PORTABLE,
    PORTABLE_PLATFORMS,
)
from .coordinator import AccountCoordinator, ConsoleCoordinator, PortableCoordinator
from .psn import PSNAWPAuthenticationError, PSNAWPError, PsnClient

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type PlayStationConfigEntry = ConfigEntry[AccountCoordinator | ConsoleCoordinator]


def _platforms(entry: ConfigEntry) -> list[Any]:
    kind = entry.data.get(CONF_KIND)
    return ACCOUNT_PLATFORMS if kind == KIND_ACCOUNT else PORTABLE_PLATFORMS if kind == KIND_PORTABLE else CONSOLE_PLATFORMS


def _entry_for_device(hass: HomeAssistant, device_id: str) -> ConfigEntry:
    dev = dr.async_get(hass).async_get(device_id)
    entry = hass.config_entries.async_get_entry(dev.config_entry_id) if dev else None
    if entry and entry.domain == DOMAIN and hasattr(entry, "runtime_data"):
        return entry
    raise ServiceValidationError("Dispositivo PlayStation não encontrado")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Actions: send PSN message, press DualSense buttons."""

    async def send_message(call: ServiceCall) -> None:
        entry = _entry_for_device(hass, call.data["device_id"])
        if entry.data.get(CONF_KIND) != KIND_ACCOUNT:
            raise ServiceValidationError("Escolha o dispositivo da conta PSN")
        try:
            await hass.async_add_executor_job(entry.runtime_data.client.send_message, call.data["mensagem"], call.data.get("online_id"), call.data.get("group_id"))
        except PSNAWPError as err:
            raise HomeAssistantError(str(err)) from err

    async def press(call: ServiceCall) -> None:
        entry = _entry_for_device(hass, call.data["device_id"])
        from .entity import rp_args

        try:
            await rp_buttons(*rp_args(entry), buttons=call.data["botoes"], hold=call.data.get("segurar", 0))
        except (ConnectionError, ValueError, OSError) as err:
            raise HomeAssistantError(f"Remote Play: {err}") from err

    async def launch(call: ServiceCall) -> None:
        entry = _entry_for_device(hass, call.data["device_id"])
        if entry.data.get(CONF_KIND) != KIND_ACCOUNT:
            raise ServiceValidationError("Escolha a conta PSN ou o dispositivo PlayStation 5 dela")
        from .coordinator import installed

        want = call.data["jogo"].strip().lower()
        for c in (entry.runtime_data.data or {}).get("clients") or []:
            for tid, t in installed(c).items():
                if want in (str(tid).lower(), str(t.get("titleId", "")).lower()) or want in str(t.get("comment", "")).lower():
                    try:
                        await hass.async_add_executor_job(entry.runtime_data.client.command, c["duid"], "launchTitle", {"titleIds": [t.get("titleId") or tid]})
                    except Exception as err:
                        raise HomeAssistantError(f"PSN: {err}") from err
                    return
        raise ServiceValidationError(f"Jogo não instalado: {call.data['jogo']}")

    hass.services.async_register(DOMAIN, "abrir_jogo", launch, vol.Schema({vol.Required("device_id"): cv.string, vol.Required("jogo"): cv.string}))
    hass.services.async_register(DOMAIN, "enviar_mensagem", send_message, vol.Schema({
        vol.Required("device_id"): cv.string, vol.Required("mensagem"): cv.string,
        vol.Exclusive("online_id", "destino"): cv.string, vol.Exclusive("group_id", "destino"): cv.string,
    }))
    hass.services.async_register(DOMAIN, "pressionar_botoes", press, vol.Schema({
        vol.Required("device_id"): cv.string,
        vol.Required("botoes"): vol.All(cv.ensure_list, [vol.All(vol.Upper, vol.In(BUTTONS))]),
        vol.Optional("segurar", default=0): vol.All(vol.Coerce(float), vol.Range(min=0, max=10)),
    }))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PlayStationConfigEntry) -> bool:
    """Set up a PSN account or a console."""
    if entry.data.get(CONF_KIND) == KIND_ACCOUNT:
        try:
            client = await hass.async_add_executor_job(PsnClient, entry.data[CONF_NPSSO])
        except PSNAWPAuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PSNAWPError as err:
            raise ConfigEntryNotReady(str(err)) from err
        co: AccountCoordinator | ConsoleCoordinator = AccountCoordinator(hass, entry, client)
    elif entry.data.get(CONF_KIND) == KIND_PORTABLE:
        co = PortableCoordinator(hass, entry)
    else:
        co = ConsoleCoordinator(hass, entry)
    await co.async_config_entry_first_refresh()
    entry.runtime_data = co
    entry.async_on_unload(entry.add_update_listener(lambda h, e: h.config_entries.async_reload(e.entry_id)))
    await hass.config_entries.async_forward_entry_setups(entry, _platforms(entry))
    if isinstance(co, AccountCoordinator):
        co.start_snapshot()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PlayStationConfigEntry) -> bool:
    """Unload."""
    return await hass.config_entries.async_unload_platforms(entry, _platforms(entry))
