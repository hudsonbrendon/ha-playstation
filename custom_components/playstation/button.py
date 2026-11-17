"""Buttons: refresh (account); power and every DualSense button (console, via Remote Play)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PlayStationConfigEntry
from .console import BUTTONS, ddp_wakeup, rp_buttons, rp_standby
from .const import CONF_CREDENTIAL, CONF_HOST_TYPE, CONF_KIND, KIND_ACCOUNT
from .coordinator import AccountCoordinator, ConsoleCoordinator
from .entity import PlayStationEntity, rp_args

BUTTON_NAMES = {
    "CROSS": "Botão X", "CIRCLE": "Botão Círculo", "SQUARE": "Botão Quadrado", "TRIANGLE": "Botão Triângulo",
    "UP": "Direcional cima", "DOWN": "Direcional baixo", "LEFT": "Direcional esquerda", "RIGHT": "Direcional direita",
    "L1": "L1", "R1": "R1", "L2": "L2", "R2": "R2", "L3": "L3", "R3": "R3",
    "OPTIONS": "Options", "SHARE": "Create", "PS": "Botão PS", "TOUCHPAD": "Touchpad",
}


async def async_setup_entry(hass: HomeAssistant, entry: PlayStationConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    """Add buttons."""
    co = entry.runtime_data
    if entry.data.get(CONF_KIND) == KIND_ACCOUNT:
        add([RefreshButton(co)])
        seen: set[str] = set()

        def cloud() -> None:
            new = [CloudButton(co, c["duid"], k) for c in (co.data or {}).get("clients") or [] if c.get("duid") and c["duid"] not in seen for k in CLOUD_COMMANDS]
            seen.update(b.duid for b in new)
            if new:
                add(new)

        cloud()
        entry.async_on_unload(co.async_add_listener(cloud))
        return
    add([WakeButton(co), RestButton(co), *(PadButton(co, b) for b in BUTTONS)])


CLOUD_COMMANDS = {"ligar_pela_nuvem": "enterWorkingMode", "repouso_pela_nuvem": "enterRestMode"}


class CloudButton(PlayStationEntity, ButtonEntity):
    """Power command queued through PSN (works away from home, no Remote Play pairing)."""

    def __init__(self, co: AccountCoordinator, duid: str, key: str) -> None:  # noqa: D107
        from .entity import platform_device

        super().__init__(co, key)
        self.duid = duid
        self._attr_unique_id = f"{co.client.account_id}_{duid}_{key}"
        self._attr_device_info = platform_device(co, "PS5", "PlayStation 5")

    async def async_press(self) -> None:  # noqa: D102
        try:
            await self.hass.async_add_executor_job(self.coordinator.client.command, self.duid, CLOUD_COMMANDS[self._attr_translation_key])
        except Exception as err:
            raise HomeAssistantError(f"PSN: {err}") from err


class RefreshButton(PlayStationEntity, ButtonEntity):
    """Reload trophies, library, friends now."""

    def __init__(self, co: AccountCoordinator) -> None:  # noqa: D107
        super().__init__(co, "atualizar")

    async def async_press(self) -> None:  # noqa: D102
        self.coordinator._snap_at = 0
        await self.coordinator.async_request_refresh()


class WakeButton(PlayStationEntity, ButtonEntity):
    """Wake from rest mode (DDP)."""

    def __init__(self, co: ConsoleCoordinator) -> None:  # noqa: D107
        super().__init__(co, "ligar")

    @property
    def available(self) -> bool:  # noqa: D102
        return bool(self.coordinator.config_entry.options.get(CONF_CREDENTIAL))

    async def async_press(self) -> None:  # noqa: D102
        e = self.coordinator.config_entry
        await ddp_wakeup(e.data["host"], e.data.get(CONF_HOST_TYPE, "PS5"), e.options[CONF_CREDENTIAL])


class RestButton(PlayStationEntity, ButtonEntity):
    """Enter rest mode (Remote Play)."""

    def __init__(self, co: ConsoleCoordinator) -> None:  # noqa: D107
        super().__init__(co, "modo_repouso")

    async def async_press(self) -> None:  # noqa: D102
        try:
            await rp_standby(*rp_args(self.coordinator.config_entry))
        except (ConnectionError, ValueError, OSError) as err:
            raise HomeAssistantError(f"Remote Play: {err}") from err
        await self.coordinator.async_request_refresh()


class PadButton(PlayStationEntity, ButtonEntity):
    """One DualSense button through Remote Play."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, co: ConsoleCoordinator, button: str) -> None:  # noqa: D107
        self.button = button
        super().__init__(co, f"botao_{button.lower()}", name=BUTTON_NAMES[button])

    async def async_press(self) -> None:  # noqa: D102
        try:
            await rp_buttons(*rp_args(self.coordinator.config_entry), buttons=[self.button])
        except (ConnectionError, ValueError, OSError) as err:
            raise HomeAssistantError(f"Remote Play: {err}") from err
