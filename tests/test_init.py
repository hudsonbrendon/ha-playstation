"""Account and console setup, events, commands."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.playstation.const import DOMAIN

from .conftest import HOST_ID, ME


def st(hass: HomeAssistant, domain: str, uid: str) -> Any:
    eid = er.async_get(hass).async_get_entity_id(domain, DOMAIN, uid)
    assert eid, uid
    return hass.states.get(eid)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_account(hass: HomeAssistant, account_entry: MockConfigEntry, client: Any, freezer: FrozenDateTimeFactory) -> None:
    await _setup(hass, account_entry)
    assert st(hass, "sensor", f"{ME}_status").state == "jogando"
    assert st(hass, "sensor", f"{ME}_jogo_atual").state == "Jogo A"
    assert st(hass, "sensor", f"{ME}_nivel_de_trofeus").state == "32"
    assert st(hass, "sensor", f"{ME}_trofeus").state == "91"
    assert st(hass, "sensor", f"{ME}_jogos_platinados").state == "1"
    assert st(hass, "sensor", f"{ME}_tempo_total_jogado").state == "25.5"
    assert st(hass, "sensor", f"{ME}_jogo_mais_jogado").state == "Jogo A"
    assert st(hass, "sensor", f"{ME}_jogos_comprados").attributes["ps_plus"] == 1
    assert st(hass, "sensor", f"{ME}_ultimo_trofeu").state == "Platina"
    assert st(hass, "binary_sensor", f"{ME}_ps_plus").state == "on"
    assert st(hass, "sensor", f"{ME}_amigo_1000000000000000002").state == "offline"
    assert hass.states.get("notify.psn_eu_mensagem_amigo") is not None

    c = client["c"]
    assert st(hass, "sensor", f"{ME}_lista_de_desejos").state == "1"
    assert st(hass, "sensor", f"{ME}_PSVITA_jogo_atual").state == "Jogo Vita"
    assert st(hass, "binary_sensor", f"{ME}_PSVITA_jogando").state == "on"
    assert st(hass, "sensor", f"{ME}_PSVITA_jogos_com_trofeus").state == "1"
    assert st(hass, "sensor", f"{ME}_PS5_tempo_total_jogado").state == "24.5"
    assert st(hass, "sensor", f"{ME}_PS4_tempo_total_jogado").state == "1.0"
    assert st(hass, "sensor", f"{ME}_PS5_ativado_em").state.startswith("2024-04-17")
    vita = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, f"{ME}_PSVITA"), account_entry.entry_id)
    assert vita and vita.name == "PlayStation Vita" and vita.via_device_id
    c.snap["trophy_titles"][1]["earnedTrophies"]["gold"] = 1
    c.snap["wishlist"][0]["desconto"] = "-50%"
    c.pres[ME]["gameTitleInfoList"] = []
    c.pres["1000000000000000002"]["availability"] = "availableToPlay"
    await hass.services.async_call("button", "press", {"entity_id": st(hass, "button", f"{ME}_atualizar").entity_id}, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert st(hass, "event", f"{ME}_trofeus").attributes["trofeu"] == "Novo"
    assert st(hass, "event", f"{ME}_promocoes").attributes["jogo"] == "Jogo W"
    assert st(hass, "sensor", f"{ME}_promocoes_na_lista_de_desejos").state == "1"
    freezer.tick(61)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert st(hass, "event", f"{ME}_partidas").attributes["event_type"] == "jogo_encerrado"
    assert st(hass, "event", f"{ME}_amigos_evento").attributes["amigo"] == "amigo"

    dev = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, ME), account_entry.entry_id)
    await hass.services.async_call(DOMAIN, "enviar_mensagem", {"device_id": dev.id, "mensagem": "oi", "online_id": "amigo"}, blocking=True)
    await hass.services.async_call("notify", "send_message", {"entity_id": "notify.psn_eu_mensagem_amigo", "message": "grupo"}, blocking=True)
    assert ("oi", "amigo", None) in c.sent and ("grupo", None, "g1") in c.sent


async def test_console(hass: HomeAssistant, console_entry: MockConfigEntry, ddp: Any, freezer: FrozenDateTimeFactory) -> None:
    await _setup(hass, console_entry)
    mp = st(hass, "media_player", f"{HOST_ID}_console")
    assert mp.state == "playing" and mp.attributes["media_title"] == "Jogo A"
    assert st(hass, "sensor", f"{HOST_ID}_firmware").state == "13.42"
    assert st(hass, "binary_sensor", f"{HOST_ID}_remote_play_pareado").state == "on"
    dev = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, HOST_ID), console_entry.entry_id)
    assert dev.sw_version == "13.42" and dev.model == "PS5"

    with patch("custom_components.playstation.remote.rp_buttons", new=AsyncMock()) as rb, patch("custom_components.playstation.media_player.rp_standby", new=AsyncMock()) as sb, \
         patch("custom_components.playstation.media_player.ddp_wakeup", new=AsyncMock()) as wk, patch("custom_components.playstation.rp_buttons", new=AsyncMock()) as svc:
        await hass.services.async_call("remote", "send_command", {"entity_id": st(hass, "remote", f"{HOST_ID}_controle").entity_id, "command": ["ps", "down", "cross"]}, blocking=True)
        await hass.services.async_call("media_player", "turn_off", {"entity_id": mp.entity_id}, blocking=True)
        await hass.services.async_call("media_player", "turn_on", {"entity_id": mp.entity_id}, blocking=True)
        await hass.services.async_call(DOMAIN, "pressionar_botoes", {"device_id": dev.id, "botoes": ["options"]}, blocking=True)
    assert rb.await_args.kwargs["buttons"] == ["PS", "DOWN", "CROSS"]
    assert sb.await_count == 1 and wk.await_args.args == ("192.0.2.50", "PS5", "123") and svc.await_args.kwargs["buttons"] == ["OPTIONS"]

    ddp["reply"]["status"], ddp["reply"]["status_code"] = "repouso", 620
    freezer.tick(11)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert st(hass, "media_player", f"{HOST_ID}_console").state == "off"
    assert st(hass, "sensor", f"{HOST_ID}_estado").state == "repouso"
    assert st(hass, "event", f"{HOST_ID}_energia").attributes["event_type"] == "entrou_em_repouso"

