"""Config flows: account, console scan, DHCP, pairing."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from custom_components.playstation.const import DOMAIN

from .conftest import HOST, HOST_ID, ME


async def test_account_flow(hass: HomeAssistant, client: Any) -> None:
    with patch("custom_components.playstation.async_setup_entry", return_value=True):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"next_step_id": "account"})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"npsso": "bad"})
        assert r["errors"] == {"base": "invalid_auth"}
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"npsso": "good"})
    assert r["type"] is FlowResultType.CREATE_ENTRY and r["result"].unique_id == ME


async def test_console_scan_and_dhcp(hass: HomeAssistant, ddp: Any) -> None:
    with patch("custom_components.playstation.async_setup_entry", return_value=True):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"next_step_id": "console"})
        assert r["step_id"] == "console"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"console": HOST})
        assert r["type"] is FlowResultType.CREATE_ENTRY and r["result"].unique_id == HOST_ID
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DhcpServiceInfo(ip=HOST, hostname="ps5-x", macaddress="aabbccddeeff"))
        assert r["type"] is FlowResultType.ABORT and r["reason"] == "already_configured"


async def test_pairing(hass: HomeAssistant, console_entry: Any, ddp: Any) -> None:
    console_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(console_entry.entry_id)
    await hass.async_block_till_done()
    regist = {"PS5-RegistKey": "3031", "RP-Key": "cc"}
    with patch("custom_components.playstation.config_flow.rp_register", new=AsyncMock(return_value=regist)):
        r = await hass.config_entries.options.async_init(console_entry.entry_id)
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "pair"})
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"pin": "1234 5678", "account_id": ME})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert console_entry.options["regist"] == regist and console_entry.options["credential"] == "1"


async def test_portable_dhcp_and_ping(hass: HomeAssistant) -> None:
    """Sony MAC without DDP → PlayStation Portal entry tracked by ping."""
    from types import SimpleNamespace

    async def no_ddp(host: str | None, wait: float = 2.0, tries: int = 2) -> dict:
        return {}

    alive = {"v": True}

    async def ping(*a: Any, **k: Any) -> Any:
        return SimpleNamespace(is_alive=alive["v"], avg_rtt=57.0)

    hass.states.async_set("device_tracker.portal_router", "home", {"mac": "9C:37:CB:00:00:01", "signal": 82, "signal_quality": "good", "band": "5G", "download_speed": 1_500_000, "upload_speed": 20_000, "download_total": 9_000_000_000})
    with patch("custom_components.playstation.config_flow.ddp_query", side_effect=no_ddp), patch("icmplib.async_ping", side_effect=ping):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DhcpServiceInfo(ip="192.0.2.53", hostname="", macaddress="9c37cb000001"))
        assert r["step_id"] == "confirm_portable"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"name": "PlayStation Portal"})
        assert r["type"] is FlowResultType.CREATE_ENTRY and r["result"].unique_id == "9c:37:cb:00:00:01"
        await hass.async_block_till_done()
        assert hass.states.get("binary_sensor.playstation_portal_online").state == "on"
        assert hass.states.get("sensor.playstation_portal_latency").state == "57.0"
        assert hass.states.get("sensor.playstation_portal_wi_fi_signal").state == "82"
        assert hass.states.get("binary_sensor.playstation_portal_streaming").state == "on"  # 12 Mbit/s
