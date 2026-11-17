"""Cloud (PS App cloudAssistedNavigation): storage, installed games, power, launch."""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.playstation.const import DOMAIN, EVENT_INSTALLED, EVENT_REMOVED
from custom_components.playstation.coordinator import diff_installed

from .conftest import CLOUD, ME
from .test_init import _setup, st


def test_diff_installed() -> None:
    new = copy.deepcopy(CLOUD)
    new[0]["systemData"]["installedTitles"]["titles"] = [{"comment": "Jogo Z", "npTitleId": "PPSA00009_00"}]
    assert sorted(k for k, _ in diff_installed(CLOUD, new)) == sorted([EVENT_INSTALLED, EVENT_REMOVED])


async def test_cloud(hass: HomeAssistant, account_entry: MockConfigEntry, client: Any) -> None:
    await _setup(hass, account_entry)
    fake = client["c"]
    assert st(hass, "sensor", f"{ME}_D1_armazenamento_usado").state == "50.0"
    assert st(hass, "sensor", f"{ME}_D1_jogos_instalados").state == "1"
    assert st(hass, "sensor", f"{ME}_D1_nome_do_console").state == "PS5-Teste"
    await hass.services.async_call("button", "press", {"entity_id": st(hass, "button", f"{ME}_D1_ligar_pela_nuvem").entity_id}, blocking=True)
    assert ("cmd", "D1", "enterWorkingMode", None) in fake.sent
    dev = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, f"{ME}_PS5"), account_entry.entry_id)
    await hass.services.async_call(DOMAIN, "abrir_jogo", {"device_id": dev.id, "jogo": "jogo a"}, blocking=True)
    assert ("cmd", "D1", "launchTitle", {"titleIds": ["PPSA00001"]}) in fake.sent
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "abrir_jogo", {"device_id": dev.id, "jogo": "nao existe"}, blocking=True)
