"""Coordinators: PSN account (presence fast, snapshot slow) and local console (DDP)."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import re
import time
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import discovery_flow
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .console import ddp_query
from .const import (
    CLOUD_INTERVAL,
    CONF_HOST_ID,
    CONSOLE_INTERVAL,
    DISCOVERY_INTERVAL,
    DOMAIN,
    EVENT_APP,
    EVENT_FRIEND_ONLINE,
    EVENT_GAME_STARTED,
    EVENT_GAME_STOPPED,
    EVENT_INSTALLED,
    EVENT_NEW_MESSAGE,
    EVENT_OFFLINE,
    EVENT_ONLINE,
    EVENT_POWER_ON,
    EVENT_REMOVED,
    EVENT_REST,
    EVENT_SALE,
    EVENT_STREAM_START,
    EVENT_STREAM_STOP,
    EVENT_TROPHY,
    PRESENCE_INTERVAL,
    SNAPSHOT_INTERVAL,
)
from .psn import PSNAWPAuthenticationError, PSNAWPError, PsnClient

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


def iso_hours(duration: str | None) -> float:
    """ISO 8601 duration (PT24H37M31S) -> hours."""
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?", duration or "")
    if not m:
        return 0.0
    d, h, mi, s = (float(x or 0) for x in m.groups())
    return round(d * 24 + h + mi / 60 + s / 3600, 2)


def game_of(presence: dict[str, Any]) -> dict[str, Any] | None:
    """First game in a basicPresence."""
    info = presence.get("gameTitleInfoList") or []
    return info[0] if info else None


def installed(client: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Installed titles of one cloud client by npTitleId."""
    return {t.get("npTitleId") or t.get("titleId"): t for t in ((client.get("systemData") or {}).get("installedTitles") or {}).get("titles") or []}


def diff_installed(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """Game installed/removed events between two cloud polls."""
    ev: list[tuple[str, dict[str, Any]]] = []
    before = {c.get("duid"): installed(c) for c in old}
    for c in new:
        if (was := before.get(c.get("duid"))) is None:
            continue
        now = installed(c)
        ev += [(EVENT_INSTALLED, {"jogo": now[k].get("comment"), "title_id": k, "console": (c.get("device") or {}).get("name")}) for k in now.keys() - was.keys()]
        ev += [(EVENT_REMOVED, {"jogo": was[k].get("comment"), "title_id": k, "console": (c.get("device") or {}).get("name")}) for k in was.keys() - now.keys()]
    return ev


class AccountCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One PSN account: presence every minute, everything else every 30 min."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: PsnClient) -> None:  # noqa: D107
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN}_account", update_interval=timedelta(seconds=PRESENCE_INTERVAL))
        self.client = client
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.snapshot: dict[str, Any] = {}
        self._presence: dict[str, Any] | None = None
        self._snap_at = 0.0
        self._snap_task: asyncio.Task[None] | None = None
        self._scan_at = 0.0
        self._cloud_at = 0.0
        self._clients: list[dict[str, Any]] | None = None

    # ponytail: data = latest snapshot + latest presence, so neither refresh overwrites the other
    @property
    def data(self) -> dict[str, Any] | None:  # type: ignore[override]
        """Snapshot (slow) merged with presence (fast)."""
        return None if self._presence is None else {**self.snapshot, **self._presence}

    @data.setter
    def data(self, value: dict[str, Any] | None) -> None:
        self._presence = value

    async def _async_update_data(self) -> dict[str, Any]:
        ids = [self.client.account_id, *self.snapshot.get("friend_ids", [])]
        try:
            presences = await self.hass.async_add_executor_job(self.client.presences, ids)
            legacy = await self.hass.async_add_executor_job(self.client.legacy_presences)
        except PSNAWPAuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PSNAWPError as err:
            raise UpdateFailed(str(err)) from err
        prev = self._presence or {}
        events_cloud: list[tuple[str, dict[str, Any]]] = []
        if time.time() - self._cloud_at > CLOUD_INTERVAL:
            self._cloud_at = time.time()
            try:
                clients = await self.hass.async_add_executor_job(self.client.clients)
            except PSNAWPAuthenticationError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except (PSNAWPError, ValueError) as err:
                _LOGGER.debug("PSN cloud clients failed: %s", err)
                clients = self._clients
            if self._clients is not None and clients is not None:
                events_cloud = diff_installed(self._clients, clients)
            self._clients = clients
        data = {"presences": presences, "legacy_presences": legacy, "clients": self._clients}
        events = self._diff_presence(prev.get("presences", {}), presences) if prev else []
        if prev:
            def playing(lst: list[dict[str, Any]]) -> dict[str, str]:
                return {str(p.get("platform")).upper(): p["titleName"] for p in lst or [] if p.get("onlineStatus") == "online" and p.get("titleName") and str(p.get("platform")).upper() in ("PSVITA", "PS3")}
            was, now = playing(prev.get("legacy_presences")), playing(legacy)
            for plat in set(was) | set(now):
                if was.get(plat) != now.get(plat):
                    if was.get(plat):
                        events.append((EVENT_GAME_STOPPED, {"jogo": was[plat], "plataforma": plat}))
                    if now.get(plat):
                        events.append((EVENT_GAME_STARTED, {"jogo": now[plat], "plataforma": plat}))
        if prev and time.time() - self._snap_at > SNAPSHOT_INTERVAL:
            self.start_snapshot()
        if time.time() - self._scan_at > DISCOVERY_INTERVAL:
            self._scan_at = time.time()
            self.config_entry.async_create_background_task(self.hass, self._discover_consoles(), f"{DOMAIN}_ddp_scan")
        self.events = events + events_cloud  # published together with this update (no await below)
        return data

    def start_snapshot(self) -> None:
        """Refresh the slow data in the background (first one right after setup)."""
        if not (self._snap_task and not self._snap_task.done()):
            self._snap_task = self.config_entry.async_create_background_task(self.hass, self._refresh_snapshot(), f"{DOMAIN}_snapshot")

    async def _refresh_snapshot(self) -> None:
        try:
            snap = await self.hass.async_add_executor_job(self.client.snapshot)
        except PSNAWPAuthenticationError:
            self.config_entry.async_start_reauth(self.hass)
            return
        except PSNAWPError as err:
            _LOGGER.warning("PSN snapshot failed: %s", err)
            return
        self._snap_at = time.time()
        old = self.snapshot
        events = await self._diff_snapshot(old, snap) if old else []
        self.snapshot = snap
        have = (self._presence or {}).get("presences", {})
        if missing := [a for a in snap.get("friend_ids", []) if a not in have]:
            try:
                extra = await self.hass.async_add_executor_job(self.client.presences, missing)
            except PSNAWPError:
                extra = {}
            self._presence = {**(self._presence or {}), "presences": {**have, **extra}}
        self.events = events
        self.async_update_listeners()

    def _diff_presence(self, old: dict[str, Any], new: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        ev: list[tuple[str, dict[str, Any]]] = []
        me = self.client.account_id
        o, n = old.get(me, {}), new.get(me, {})
        if o.get("availability") != n.get("availability"):
            ev.append((EVENT_ONLINE if n.get("availability") == "availableToPlay" else EVENT_OFFLINE, {"plataforma": (n.get("primaryPlatformInfo") or {}).get("platform")}))
        og, ng = game_of(o), game_of(n)
        if (og or {}).get("npTitleId") != (ng or {}).get("npTitleId"):
            if og:
                ev.append((EVENT_GAME_STOPPED, {"jogo": og.get("titleName"), "title_id": og.get("npTitleId")}))
            if ng:
                ev.append((EVENT_GAME_STARTED, {"jogo": ng.get("titleName"), "title_id": ng.get("npTitleId"), "plataforma": ng.get("launchPlatform")}))
        for aid, p in new.items():
            if aid != me and p.get("availability") == "availableToPlay" and old.get(aid, {}).get("availability") != "availableToPlay":
                prof = self.snapshot.get("friend_profiles", {}).get(aid, {})
                ev.append((EVENT_FRIEND_ONLINE, {"amigo": prof.get("onlineId", aid), "jogo": (game_of(p) or {}).get("titleName")}))
        return ev

    async def _diff_snapshot(self, old: dict[str, Any], new: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        ev: list[tuple[str, dict[str, Any]]] = []
        before = {t["npCommunicationId"]: t.get("earnedTrophies", {}) for t in old.get("trophy_titles", [])}
        for t in new.get("trophy_titles", []):
            b = before.get(t["npCommunicationId"])
            if b is not None and sum(t.get("earnedTrophies", {}).values()) > sum(b.values()):
                info = await self.hass.async_add_executor_job(self.client.latest_trophy, t)
                if info:
                    ev.append((EVENT_TROPHY, info))
        seen = {g["groupId"]: g.get("modifiedTimestamp") for g in old.get("groups", [])}
        for g in new.get("groups", []):
            if g.get("existsNewArrival") and seen.get(g["groupId"]) != g.get("modifiedTimestamp"):
                ev.append((EVENT_NEW_MESSAGE, {"grupo": (g.get("groupName") or {}).get("value") or g["groupId"], "group_id": g["groupId"]}))
        was = {w["id"]: w.get("desconto") for w in old.get("wishlist") or []}
        for w in new.get("wishlist") or []:
            if w.get("desconto") and was.get(w["id"]) != w["desconto"] and w["id"] in was:
                ev.append((EVENT_SALE, w))
        return ev

    async def _discover_consoles(self) -> None:
        """Broadcast DDP and offer any console not configured yet."""
        try:
            found = await ddp_query(None, wait=2.0)
        except OSError as err:
            _LOGGER.debug("DDP scan failed: %s", err)
            return
        known = {e.data.get(CONF_HOST_ID) for e in self.hass.config_entries.async_entries(DOMAIN)}
        for host, info in found.items():
            if info.get("host-id") and info["host-id"] not in known:
                discovery_flow.async_create_flow(self.hass, DOMAIN, {"source": "integration_discovery"}, {"host": host, **info})


class ConsoleCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """DDP status of one console every 10 s."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:  # noqa: D107
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN}_console", update_interval=timedelta(seconds=CONSOLE_INTERVAL))
        self.host: str = entry.data["host"]
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def _async_update_data(self) -> dict[str, Any]:
        self.events = []
        replies = await ddp_query(self.host, wait=1.5)
        new = replies.get(self.host) or {"status": "desligado", "status_code": None}
        old = self.data or {}
        if old:
            if old.get("status") != "ligado" and new["status"] == "ligado":
                self.events.append((EVENT_POWER_ON, {}))
            if old.get("status") == "ligado" and new["status"] == "repouso":
                self.events.append((EVENT_REST, {}))
            if old.get("running-app-titleid") != new.get("running-app-titleid") and new["status"] == "ligado":
                self.events.append((EVENT_APP, {"app": new.get("running-app-name"), "title_id": new.get("running-app-titleid")}))
        if new["status"] != "desligado":
            new["last_seen"] = time.time()
        elif old.get("last_seen"):
            new["last_seen"] = old["last_seen"]
        return new


class PortableCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """PlayStation Portal (or any Sony device without an API): presence by ping every 30 s."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:  # noqa: D107
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN}_portable", update_interval=timedelta(seconds=30))
        self.host: str = entry.data["host"]
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def _async_update_data(self) -> dict[str, Any]:
        from icmplib import async_ping

        try:
            r = await async_ping(self.host, count=3, interval=0.5, timeout=3, privileged=False)
            alive, rtt = r.is_alive, (round(r.avg_rtt, 1) if r.is_alive else None)
        except Exception as err:  # icmplib raises its own hierarchy
            _LOGGER.debug("ping %s failed: %s", self.host, err)
            alive, rtt = False, None
        old = self.data or {}
        events: list[tuple[str, dict[str, Any]]] = []
        if old and old.get("online") != alive:
            events.append((EVENT_ONLINE if alive else EVENT_OFFLINE, {}))
        router = self._router()
        streaming = (router.get("download_speed") or 0) * 8 >= 2_000_000  # bytes/s → >= 2 Mbit/s
        if old and old.get("streaming") is not None and old.get("streaming") != streaming:
            events.append((EVENT_STREAM_START if streaming else EVENT_STREAM_STOP, {}))
        self.events = events
        return {"online": alive or router.get("state") == "home", "latency": rtt, "host": self.host,
                "last_seen": time.time() if alive else old.get("last_seen"), "router": router, "streaming": streaming if router else None}

    def _router(self) -> dict[str, Any]:
        """Wi-Fi data of this MAC from any router integration's device tracker (signal, band, speeds)."""
        mac = self.config_entry.data["mac"].lower()
        for st in self.hass.states.async_all("device_tracker"):
            if str(st.attributes.get("mac", "")).lower() == mac:
                return {"state": st.state, **st.attributes}
        return {}
