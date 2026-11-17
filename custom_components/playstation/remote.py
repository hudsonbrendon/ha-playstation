"""Remote: send any DualSense button sequence (remote.send_command)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    ATTR_HOLD_SECS,
    RemoteEntity,
    RemoteEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PlayStationConfigEntry
from .console import BUTTONS, ddp_wakeup, rp_buttons, rp_standby
from .const import CONF_CREDENTIAL, CONF_HOST_TYPE
from .coordinator import ConsoleCoordinator
from .entity import PlayStationEntity, rp_args


async def async_setup_entry(hass: HomeAssistant, entry: PlayStationConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    """Console only."""
    add([PSRemote(entry.runtime_data)])


class PSRemote(PlayStationEntity, RemoteEntity):
    """Commands: CROSS CIRCLE SQUARE TRIANGLE UP DOWN LEFT RIGHT L1 R1 L2 R2 L3 R3 OPTIONS SHARE PS TOUCHPAD."""

    _attr_supported_features = RemoteEntityFeature(0)

    def __init__(self, co: ConsoleCoordinator) -> None:  # noqa: D107
        super().__init__(co, "controle")

    @property
    def is_on(self) -> bool:  # noqa: D102
        return (self.coordinator.data or {}).get("status") == "ligado"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:  # noqa: D102
        return {"comandos": BUTTONS}

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: D102
        e = self.coordinator.config_entry
        if not e.options.get(CONF_CREDENTIAL):
            raise HomeAssistantError("Pareie o Remote Play primeiro (Configurar)")
        await ddp_wakeup(e.data["host"], e.data.get(CONF_HOST_TYPE, "PS5"), e.options[CONF_CREDENTIAL])

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: D102
        try:
            await rp_standby(*rp_args(self.coordinator.config_entry))
        except (ConnectionError, ValueError, OSError) as err:
            raise HomeAssistantError(f"Remote Play: {err}") from err

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:  # noqa: D102
        cmds = [c.upper() for c in command]
        if bad := [c for c in cmds if c not in BUTTONS]:
            raise ServiceValidationError(f"Comandos inválidos: {bad}. Válidos: {BUTTONS}")
        repeats = int(kwargs.get("num_repeats", 1))
        try:
            await rp_buttons(*rp_args(self.coordinator.config_entry), buttons=cmds * repeats, hold=float(kwargs.get(ATTR_HOLD_SECS) or 0))
        except (ConnectionError, ValueError, OSError) as err:
            raise HomeAssistantError(f"Remote Play: {err}") from err
        _ = kwargs.get(ATTR_DELAY_SECS)
