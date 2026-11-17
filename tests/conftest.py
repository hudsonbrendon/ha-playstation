"""Fixtures with invented data."""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.playstation.const import (
    CONF_HOST_ID,
    CONF_HOST_TYPE,
    CONF_KIND,
    CONF_NPSSO,
    DOMAIN,
    KIND_ACCOUNT,
    KIND_CONSOLE,
)

ME = "1000000000000000001"
FRIEND = "1000000000000000002"
HOST = "192.0.2.50"
HOST_ID = "AABBCCDDEEFF"

SNAP: dict[str, Any] = {
    "account_id": ME, "online_id": "eu",
    "profile": {"plus": 1, "avatarUrls": [{"avatarUrl": "https://example.invalid/a.png"}], "isOfficiallyVerified": False},
    "trophy_summary": {"trophyLevel": 32, "progress": 25, "tier": 1, "trophyPoint": 1875, "trophyLevelNextPoint": 1920, "earnedTrophies": {"bronze": 71, "silver": 15, "gold": 4, "platinum": 1}},
    "trophy_titles": [{"npCommunicationId": "NPWR1", "trophyTitleName": "Jogo A", "trophyTitlePlatform": "PS5", "progress": 100, "earnedTrophies": {"bronze": 10, "silver": 2, "gold": 1, "platinum": 1}, "lastUpdatedDateTime": "2026-07-01T00:00:00Z"},
                      {"npCommunicationId": "NPWR2", "trophyTitleName": "Jogo B", "trophyTitlePlatform": "PSVITA", "progress": 20, "earnedTrophies": {"bronze": 3, "silver": 0, "gold": 0, "platinum": 0}, "lastUpdatedDateTime": "2026-06-01T00:00:00Z"}],
    "games": [{"titleId": "PPSA00001_00", "name": "Jogo A", "playDuration": "PT24H30M", "playCount": 10, "lastPlayedDateTime": "2026-07-16T00:00:00Z", "imageUrl": "https://example.invalid/a.jpg", "category": "ps5_native_game"},
              {"titleId": "CUSA00002_00", "name": "Jogo B", "playDuration": "PT1H", "playCount": 1, "lastPlayedDateTime": "2026-01-01T00:00:00Z"}],
    "purchased": [{"name": "Jogo A", "subscriptionService": "NONE"}, {"name": "Jogo C", "subscriptionService": "PS_PLUS"}],
    "friend_ids": [FRIEND], "friend_profiles": {FRIEND: {"onlineId": "amigo"}}, "blocked": [], "devices": [{"deviceName": "PS5", "deviceType": "PS5", "activationDate": "2024-04-17T06:40:34Z"}],
    "groups": [{"groupId": "g1", "groupName": {"value": ""}, "members": [{"onlineId": "eu"}, {"onlineId": "amigo"}], "existsNewArrival": False, "modifiedTimestamp": "1"}],
    "latest_trophy": {"jogo": "Jogo A", "trofeu": "Platina", "tipo": "platinum"},
    "wishlist": [{"id": "EP1-X", "jogo": "Jogo W", "preco": "R$ 100", "desconto": None}],
}
PRES: dict[str, Any] = {
    ME: {"accountId": ME, "availability": "availableToPlay", "primaryPlatformInfo": {"onlineStatus": "online", "platform": "PS5", "lastOnlineDate": "2026-07-16T00:00:00Z"},
         "gameTitleInfoList": [{"npTitleId": "PPSA00001_00", "titleName": "Jogo A", "launchPlatform": "PS5", "conceptIconUrl": "https://example.invalid/c.png"}]},
    FRIEND: {"accountId": FRIEND, "availability": "unavailable", "primaryPlatformInfo": {"onlineStatus": "offline", "platform": "PS4"}},
}
CLOUD: list[dict[str, Any]] = [{"duid": "D1", "platform": "PS5", "device": {"name": "PS5-Teste", "wakeupEnabledPowerModes": ["networkStandby"]},
    "systemData": {"storage": {"embedded": {"freeSize": 300_000_000_000, "totalSize": 600_000_000_000}},
                   "installedTitles": {"titles": [{"comment": "Jogo A", "npTitleId": "PPSA00001_00", "titleId": "PPSA00001", "size": 50_000_000_000, "storage": "embedded", "disc": "inapplicable", "lastAccessDateTime": "2026-07-16T00:00:00Z", "version": "01.000.000"}]}}}]
DDP_ON = {"status_code": 200, "status": "ligado", "host": HOST, "host-id": HOST_ID, "host-type": "PS5", "host-name": "PS5 Teste", "system-version": "13420000", "running-app-titleid": "PPSA00001", "running-app-name": "Jogo A"}


class FakeClient:
    """PsnClient replacement."""

    def __init__(self, npsso: str = "x") -> None:
        if npsso == "bad":
            from custom_components.playstation.psn import PSNAWPAuthenticationError
            raise PSNAWPAuthenticationError("bad")
        self.account_id, self.online_id = ME, "eu"
        self.snap, self.pres = copy.deepcopy(SNAP), copy.deepcopy(PRES)
        self.sent: list[tuple] = []
        self.cloud = copy.deepcopy(CLOUD)

    def presences(self, ids: list[str]) -> dict[str, Any]:
        return {i: copy.deepcopy(self.pres[i]) for i in ids if i in self.pres}

    def legacy_presences(self) -> list[dict[str, Any]]:
        return [{"onlineStatus": "online", "platform": "PSVITA", "titleName": "Jogo Vita", "npTitleId": "PCSE00001_00"}]

    def clients(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self.cloud)

    def command(self, duid: str, command_type: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        self.sent.append(("cmd", duid, command_type, parameters))
        return {}

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.snap)

    def latest_trophy(self, title: dict[str, Any]) -> dict[str, Any]:
        return {"jogo": title["trophyTitleName"], "trofeu": "Novo", "tipo": "gold"}

    def send_message(self, text: str, online_id: str | None = None, group_id: str | None = None) -> None:
        self.sent.append((text, online_id, group_id))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/."""


@pytest.fixture
def client() -> Any:
    holder: dict[str, FakeClient] = {}

    def make(npsso: str) -> FakeClient:
        holder["c"] = holder.get("c") or FakeClient(npsso)
        return holder["c"]

    with patch("custom_components.playstation.PsnClient", side_effect=make), patch("custom_components.playstation.config_flow.PsnClient", side_effect=FakeClient), \
         patch("custom_components.playstation.coordinator.ddp_query", return_value={}):
        yield holder


@pytest.fixture
def ddp() -> Any:
    state = {"reply": copy.deepcopy(DDP_ON)}

    async def query(host: str | None, wait: float = 2.0, tries: int = 2) -> dict[str, Any]:
        return {HOST: copy.deepcopy(state["reply"])} if state["reply"] else {}

    with patch("custom_components.playstation.coordinator.ddp_query", side_effect=query), patch("custom_components.playstation.config_flow.ddp_query", side_effect=query):
        yield state


@pytest.fixture
def account_entry() -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, unique_id=ME, title="eu", data={CONF_KIND: KIND_ACCOUNT, CONF_NPSSO: "x"})


@pytest.fixture
def console_entry() -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, unique_id=HOST_ID, title="PS5 Teste", data={CONF_KIND: KIND_CONSOLE, "host": HOST, CONF_HOST_ID: HOST_ID, CONF_HOST_TYPE: "PS5"},
                           options={"credential": "123", "regist": {"PS5-RegistKey": "aa", "RP-Key": "bb"}, "account_id": ME, "online_id": "eu"})
