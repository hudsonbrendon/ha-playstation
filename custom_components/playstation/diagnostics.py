"""Diagnostics with secrets and personal ids redacted."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import PlayStationConfigEntry
from .const import CONF_CREDENTIAL, CONF_NPSSO, CONF_REGIST

REDACT = {CONF_NPSSO, CONF_CREDENTIAL, CONF_REGIST, "accountId", "account_id", "npId", "onlineId", "online_id", "firstName", "lastName", "deviceId", "host-id", "host_id", "friend_ids", "friend_profiles", "aboutMe", "members", "RP-Key", "RegistKey"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: PlayStationConfigEntry) -> dict[str, Any]:
    """Entry + coordinator snapshot."""
    data = dict(entry.runtime_data.data or {})
    for big in ("games", "purchased", "trophy_titles"):
        if big in data:
            data[big] = f"{len(data[big])} items"
    return {"entry": async_redact_data({"data": dict(entry.data), "options": dict(entry.options)}, REDACT), "data": async_redact_data(data, REDACT)}
