"""Sensors: PSN account (presence, trophies, library, friends...) and console (DDP)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PlayStationConfigEntry
from .console import firmware
from .const import CONF_KIND, KIND_ACCOUNT
from .coordinator import AccountCoordinator, ConsoleCoordinator, game_of, iso_hours
from .entity import PlayStationEntity

D = dict[str, Any]


def _ts(v: Any) -> datetime | None:
    if not v:
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, UTC)
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def _me(d: D) -> D:
    return (d.get("presences") or {}).get(d.get("account_id") or "", {}) or next(iter((d.get("presences") or {}).values()), {})


def _status(p: D) -> str | None:
    if not p:
        return None
    if game_of(p):
        return "jogando"
    return "online" if p.get("availability") == "availableToPlay" else "offline"


def _titles(d: D) -> list[D]:
    return d.get("trophy_titles") or []


def _earned(d: D, kind: str) -> int | None:
    e = (d.get("trophy_summary") or {}).get("earnedTrophies")
    return e.get(kind) if e else None


def _games(d: D) -> list[D]:
    return d.get("games") or []


def _last_game(d: D) -> D | None:
    return max(_games(d), key=lambda g: g.get("lastPlayedDateTime", ""), default=None)


def _top_game(d: D) -> D | None:
    return max(_games(d), key=lambda g: iso_hours(g.get("playDuration")), default=None)


def _friends(d: D, pred: Callable[[D], bool]) -> list[str]:
    pres, prof = d.get("presences") or {}, d.get("friend_profiles") or {}
    return [prof.get(a, {}).get("onlineId", a) for a in d.get("friend_ids", []) if pred(pres.get(a, {}))]


def _plat(t: D) -> bool:
    return bool((t.get("earnedTrophies") or {}).get("platinum"))


@dataclass(frozen=True, kw_only=True)
class PSDescription(SensorEntityDescription):
    """Value/attrs from coordinator data."""

    value: Callable[[D], Any]
    attrs: Callable[[D], D | None] = lambda d: None
    picture: Callable[[D], str | None] = lambda d: None


ACCOUNT: tuple[PSDescription, ...] = (
    PSDescription(key="status", device_class=SensorDeviceClass.ENUM, options=["online", "offline", "jogando"], value=lambda d: _status(_me(d)),
                  attrs=lambda d: {"disponibilidade": _me(d).get("availability"), "plataforma": (_me(d).get("primaryPlatformInfo") or {}).get("platform")}),
    PSDescription(key="plataforma", value=lambda d: (_me(d).get("primaryPlatformInfo") or {}).get("platform")),
    PSDescription(key="jogo_atual", value=lambda d: (game_of(_me(d)) or {}).get("titleName"),
                  attrs=lambda d: {"title_id": (game_of(_me(d)) or {}).get("npTitleId"), "plataforma": (game_of(_me(d)) or {}).get("launchPlatform"), "formato": (game_of(_me(d)) or {}).get("format")},
                  picture=lambda d: (game_of(_me(d)) or {}).get("conceptIconUrl") or (game_of(_me(d)) or {}).get("npTitleIconUrl")),
    PSDescription(key="ultima_vez_online", device_class=SensorDeviceClass.TIMESTAMP, value=lambda d: _ts((_me(d).get("primaryPlatformInfo") or {}).get("lastOnlineDate") or _me(d).get("lastAvailableDate"))),
    PSDescription(key="nivel_de_trofeus", state_class=SensorStateClass.MEASUREMENT, value=lambda d: (d.get("trophy_summary") or {}).get("trophyLevel"),
                  attrs=lambda d: {"tier": (d.get("trophy_summary") or {}).get("tier")}),
    PSDescription(key="progresso_do_nivel", native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT, value=lambda d: (d.get("trophy_summary") or {}).get("progress")),
    PSDescription(key="pontos_de_trofeu", state_class=SensorStateClass.TOTAL_INCREASING, value=lambda d: (d.get("trophy_summary") or {}).get("trophyPoint"),
                  attrs=lambda d: {"pontos_para_proximo_nivel": ((d.get("trophy_summary") or {}).get("trophyLevelNextPoint") or 0) - ((d.get("trophy_summary") or {}).get("trophyPoint") or 0)}),
    PSDescription(key="platinas", state_class=SensorStateClass.TOTAL_INCREASING, value=lambda d: _earned(d, "platinum")),
    PSDescription(key="ouros", state_class=SensorStateClass.TOTAL_INCREASING, value=lambda d: _earned(d, "gold")),
    PSDescription(key="pratas", state_class=SensorStateClass.TOTAL_INCREASING, value=lambda d: _earned(d, "silver")),
    PSDescription(key="bronzes", state_class=SensorStateClass.TOTAL_INCREASING, value=lambda d: _earned(d, "bronze")),
    PSDescription(key="trofeus", state_class=SensorStateClass.TOTAL_INCREASING, value=lambda d: sum((d.get("trophy_summary") or {}).get("earnedTrophies", {}).values()) if d.get("trophy_summary") else None),
    PSDescription(key="jogos_com_trofeus", state_class=SensorStateClass.MEASUREMENT, value=lambda d: len(_titles(d)) if d.get("trophy_titles") is not None else None,
                  attrs=lambda d: {"em_andamento": [{"jogo": t.get("trophyTitleName"), "progresso": t.get("progress"), "plataforma": t.get("trophyTitlePlatform")} for t in sorted(_titles(d), key=lambda t: t.get("lastUpdatedDateTime", ""), reverse=True)[:15]]}),
    PSDescription(key="jogos_platinados", state_class=SensorStateClass.MEASUREMENT, value=lambda d: sum(1 for t in _titles(d) if _plat(t)) if d.get("trophy_titles") is not None else None,
                  attrs=lambda d: {"jogos": [t.get("trophyTitleName") for t in _titles(d) if _plat(t)]}),
    PSDescription(key="jogos_completos", state_class=SensorStateClass.MEASUREMENT, value=lambda d: sum(1 for t in _titles(d) if t.get("progress") == 100) if d.get("trophy_titles") is not None else None),
    PSDescription(key="conclusao_media", native_unit_of_measurement=PERCENTAGE, suggested_display_precision=1, state_class=SensorStateClass.MEASUREMENT,
                  value=lambda d: (sum(t.get("progress", 0) for t in _titles(d)) / len(_titles(d))) if _titles(d) else None),
    PSDescription(key="ultimo_trofeu", value=lambda d: (d.get("latest_trophy") or {}).get("trofeu"), attrs=lambda d: d.get("latest_trophy"), picture=lambda d: (d.get("latest_trophy") or {}).get("icone")),
    PSDescription(key="jogos_na_biblioteca", state_class=SensorStateClass.MEASUREMENT, value=lambda d: len(_games(d)) if d.get("games") is not None else None,
                  attrs=lambda d: {"mais_jogados": [{"jogo": g.get("name"), "horas": iso_hours(g.get("playDuration")), "vezes": g.get("playCount")} for g in sorted(_games(d), key=lambda g: -iso_hours(g.get("playDuration")))[:10]]}),
    PSDescription(key="tempo_total_jogado", device_class=SensorDeviceClass.DURATION, native_unit_of_measurement=UnitOfTime.HOURS, state_class=SensorStateClass.TOTAL_INCREASING, suggested_display_precision=1,
                  value=lambda d: round(sum(iso_hours(g.get("playDuration")) for g in _games(d)), 1) if d.get("games") is not None else None),
    PSDescription(key="ultimo_jogo", value=lambda d: (_last_game(d) or {}).get("name"),
                  attrs=lambda d: {"jogado_em": (_last_game(d) or {}).get("lastPlayedDateTime"), "horas": iso_hours((_last_game(d) or {}).get("playDuration")), "plataforma": (_last_game(d) or {}).get("category")},
                  picture=lambda d: (_last_game(d) or {}).get("imageUrl")),
    PSDescription(key="jogo_mais_jogado", value=lambda d: (_top_game(d) or {}).get("name"), attrs=lambda d: {"horas": iso_hours((_top_game(d) or {}).get("playDuration")), "vezes": (_top_game(d) or {}).get("playCount")}, picture=lambda d: (_top_game(d) or {}).get("imageUrl")),
    PSDescription(key="jogos_comprados", state_class=SensorStateClass.MEASUREMENT, value=lambda d: len(d["purchased"]) if d.get("purchased") is not None else None,
                  attrs=lambda d: {"ps_plus": sum(1 for g in d.get("purchased") or [] if g.get("subscriptionService") not in (None, "NONE")), "jogos": [g.get("name") for g in (d.get("purchased") or [])[:30]]}),
    PSDescription(key="lista_de_desejos", state_class=SensorStateClass.MEASUREMENT, value=lambda d: len(d["wishlist"]) if d.get("wishlist") is not None else None,
                  attrs=lambda d: {"jogos": d.get("wishlist") or []}),
    PSDescription(key="promocoes_na_lista_de_desejos", state_class=SensorStateClass.MEASUREMENT, value=lambda d: sum(1 for w in d["wishlist"] if w.get("desconto")) if d.get("wishlist") is not None else None,
                  attrs=lambda d: {"jogos": [w for w in d.get("wishlist") or [] if w.get("desconto")]}),
    PSDescription(key="amigos", state_class=SensorStateClass.MEASUREMENT, value=lambda d: len(d["friend_ids"]) if "friend_ids" in d else None),
    PSDescription(key="amigos_online", state_class=SensorStateClass.MEASUREMENT, value=lambda d: len(_friends(d, lambda p: p.get("availability") == "availableToPlay")) if "friend_ids" in d else None,
                  attrs=lambda d: {"amigos": _friends(d, lambda p: p.get("availability") == "availableToPlay")}),
    PSDescription(key="amigos_jogando", state_class=SensorStateClass.MEASUREMENT, value=lambda d: len(_friends(d, lambda p: bool(game_of(p)))) if "friend_ids" in d else None,
                  attrs=lambda d: {"amigos": _friends(d, lambda p: bool(game_of(p)))}),
    PSDescription(key="bloqueados", entity_category=EntityCategory.DIAGNOSTIC, value=lambda d: len(d["blocked"]) if d.get("blocked") is not None else None),
    PSDescription(key="mensagens_novas", state_class=SensorStateClass.MEASUREMENT, value=lambda d: sum(1 for g in d.get("groups") or [] if g.get("existsNewArrival")) if d.get("groups") is not None else None,
                  attrs=lambda d: {"grupos": len(d.get("groups") or [])}),
    PSDescription(key="dispositivos_vinculados", entity_category=EntityCategory.DIAGNOSTIC, value=lambda d: len(d["devices"]) if d.get("devices") is not None else None,
                  attrs=lambda d: {"dispositivos": [{"nome": x.get("deviceName"), "tipo": x.get("deviceType"), "ativado_em": x.get("activationDate")} for x in d.get("devices") or []]}),
)

CONSOLE: tuple[PSDescription, ...] = (
    PSDescription(key="estado", device_class=SensorDeviceClass.ENUM, options=["ligado", "repouso", "desligado", "desconhecido"], value=lambda d: d.get("status")),
    PSDescription(key="app_em_execucao", value=lambda d: d.get("running-app-name") if d.get("status") == "ligado" else None, attrs=lambda d: {"title_id": d.get("running-app-titleid")}),
    PSDescription(key="firmware", entity_category=EntityCategory.DIAGNOSTIC, value=lambda d: firmware(d.get("system-version"))),
    PSDescription(key="ultima_vez_visto", device_class=SensorDeviceClass.TIMESTAMP, entity_category=EntityCategory.DIAGNOSTIC, value=lambda d: _ts(d.get("last_seen"))),
    PSDescription(key="endereco_ip", entity_category=EntityCategory.DIAGNOSTIC, value=lambda d: d.get("host")),
)


PORTABLE: tuple[PSDescription, ...] = (
    PSDescription(key="latencia", native_unit_of_measurement="ms", state_class=SensorStateClass.MEASUREMENT, value=lambda d: d.get("latency")),
    PSDescription(key="sinal_wifi", native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT, value=lambda d: (d.get("router") or {}).get("signal") or None,
                  attrs=lambda d: {"qualidade": (d.get("router") or {}).get("signal_quality"), "banda": (d.get("router") or {}).get("band"), "nome_na_rede": (d.get("router") or {}).get("host_name")}),
    PSDescription(key="banda_wifi", value=lambda d: (d.get("router") or {}).get("band") or None),
    PSDescription(key="velocidade_da_transmissao", device_class=SensorDeviceClass.DATA_RATE, native_unit_of_measurement="B/s", suggested_unit_of_measurement="Mbit/s", suggested_display_precision=1, state_class=SensorStateClass.MEASUREMENT,
                  value=lambda d: (d.get("router") or {}).get("download_speed") if d.get("router") else None),
    PSDescription(key="velocidade_de_envio", device_class=SensorDeviceClass.DATA_RATE, native_unit_of_measurement="B/s", suggested_unit_of_measurement="kbit/s", suggested_display_precision=0, state_class=SensorStateClass.MEASUREMENT,
                  value=lambda d: (d.get("router") or {}).get("upload_speed") if d.get("router") else None),
    PSDescription(key="dados_recebidos", device_class=SensorDeviceClass.DATA_SIZE, native_unit_of_measurement="B", suggested_unit_of_measurement="GB", suggested_display_precision=2, state_class=SensorStateClass.TOTAL_INCREASING,
                  value=lambda d: (d.get("router") or {}).get("download_total") if d.get("router") else None),
    PSDescription(key="ultima_vez_visto", device_class=SensorDeviceClass.TIMESTAMP, value=lambda d: _ts(d.get("last_seen"))),
    PSDescription(key="endereco_ip", entity_category=EntityCategory.DIAGNOSTIC, value=lambda d: d.get("host")),
)


async def async_setup_entry(hass: HomeAssistant, entry: PlayStationConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    """Add sensors; friends appear when the slow snapshot lists them."""
    co = entry.runtime_data
    if entry.data.get(CONF_KIND) == "portable":
        add(PSSensor(co, d) for d in PORTABLE)
        return
    if entry.data.get(CONF_KIND) != KIND_ACCOUNT:
        add(PSSensor(co, d) for d in CONSOLE)
        return
    add(PSSensor(co, d) for d in ACCOUNT)
    seen: set[str] = set()

    @callback
    def friends() -> None:
        from .platforms import summarize

        new: list[SensorEntity] = [FriendSensor(co, a) for a in (co.data or {}).get("friend_ids", []) if a not in seen]
        seen.update(f.account for f in new)
        for c in (co.data or {}).get("clients") or []:
            if (duid := c.get("duid")) and f"c:{duid}" not in seen:
                seen.add(f"c:{duid}")
                new += [CloudSensor(co, d, duid) for d in CLOUD]
        for p in summarize(co.data or {}):
            if f"p:{p}" not in seen:
                seen.add(f"p:{p}")
                new += [PlatformSensor(co, d, p) for d in PLATFORM]
        if new:
            add(new)

    friends()
    entry.async_on_unload(co.async_add_listener(friends))


class PSSensor(PlayStationEntity, SensorEntity):
    """Description-driven sensor."""

    entity_description: PSDescription

    def __init__(self, co: AccountCoordinator | ConsoleCoordinator, desc: PSDescription) -> None:  # noqa: D107
        super().__init__(co, desc.key)
        self.entity_description = desc

    @property
    def native_value(self) -> Any:  # noqa: D102
        return self.entity_description.value(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> D | None:  # noqa: D102
        return self.entity_description.attrs(self.coordinator.data or {})

    @property
    def entity_picture(self) -> str | None:  # noqa: D102
        return self.entity_description.picture(self.coordinator.data or {})


class FriendSensor(PlayStationEntity, SensorEntity):
    """Presence of one friend."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["online", "offline", "jogando"]

    def __init__(self, co: AccountCoordinator, account: str) -> None:  # noqa: D107
        self.account = account
        name = ((co.data or {}).get("friend_profiles") or {}).get(account, {}).get("onlineId", account)
        super().__init__(co, f"amigo_{account}", name=f"Amigo {name}")

    @property
    def _p(self) -> D:
        return ((self.coordinator.data or {}).get("presences") or {}).get(self.account, {})

    @property
    def native_value(self) -> str | None:  # noqa: D102
        return _status(self._p)

    @property
    def extra_state_attributes(self) -> D:  # noqa: D102
        g = game_of(self._p) or {}
        return {"jogo": g.get("titleName"), "plataforma": (self._p.get("primaryPlatformInfo") or {}).get("platform"), "ultima_vez_online": (self._p.get("primaryPlatformInfo") or {}).get("lastOnlineDate")}


PLATFORM: tuple[PSDescription, ...] = (
    PSDescription(key="jogo_atual", value=lambda s: (s.get("jogando") or {}).get("jogo"), attrs=lambda s: {"title_id": (s.get("jogando") or {}).get("title_id")}, picture=lambda s: (s.get("jogando") or {}).get("capa")),
    PSDescription(key="jogos_com_trofeus", state_class=SensorStateClass.MEASUREMENT, value=lambda s: s.get("jogos_com_trofeus")),
    PSDescription(key="trofeus", state_class=SensorStateClass.TOTAL_INCREASING, value=lambda s: s.get("trofeus")),
    PSDescription(key="platinas", state_class=SensorStateClass.TOTAL_INCREASING, value=lambda s: s.get("platinas")),
    PSDescription(key="conclusao_media", native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT, value=lambda s: s.get("conclusao_media")),
    PSDescription(key="jogos_na_biblioteca", state_class=SensorStateClass.MEASUREMENT, value=lambda s: s.get("jogos_jogados"), attrs=lambda s: {"mais_jogados": s.get("mais_jogados")}),
    PSDescription(key="tempo_total_jogado", device_class=SensorDeviceClass.DURATION, native_unit_of_measurement=UnitOfTime.HOURS, state_class=SensorStateClass.TOTAL_INCREASING, value=lambda s: s.get("horas")),
    PSDescription(key="ultimo_jogo", value=lambda s: s.get("ultimo_jogo"), attrs=lambda s: {"jogado_em": s.get("ultimo_jogo_em")}, picture=lambda s: s.get("capa_ultimo_jogo")),
    PSDescription(key="ativado_em", device_class=SensorDeviceClass.TIMESTAMP, entity_category=EntityCategory.DIAGNOSTIC, value=lambda s: _ts(s.get("ativado_em"))),
)


class PlatformSensor(PSSensor):
    """Sensor of one platform (device per platform under the account)."""

    def __init__(self, co: AccountCoordinator, desc: PSDescription, platform: str) -> None:  # noqa: D107
        from .entity import platform_device
        from .platforms import PLATFORMS

        super().__init__(co, desc)
        self.ps_platform = platform
        self._attr_unique_id = f"{co.client.account_id}_{platform}_{desc.key}"
        self._attr_device_info = platform_device(co, platform, PLATFORMS[platform])

    @property
    def _s(self) -> D:
        from .platforms import summarize

        return summarize(self.coordinator.data or {}).get(self.ps_platform, {})

    @property
    def native_value(self) -> Any:  # noqa: D102
        return self.entity_description.value(self._s)

    @property
    def extra_state_attributes(self) -> D | None:  # noqa: D102
        return self.entity_description.attrs(self._s)

    @property
    def entity_picture(self) -> str | None:  # noqa: D102
        return self.entity_description.picture(self._s)



def _storages(c: D) -> D:
    return {k: v for k, v in ((c.get("systemData") or {}).get("storage") or {}).items() if isinstance(v, dict)}


def _sum(c: D, field: str) -> int | None:
    vals = [v.get(field) for v in _storages(c).values() if v.get(field) is not None]
    return sum(vals) if vals else None


def _installed(c: D) -> list[D]:
    return ((c.get("systemData") or {}).get("installedTitles") or {}).get("titles") or []


CLOUD: tuple[PSDescription, ...] = (
    PSDescription(key="armazenamento_livre", device_class=SensorDeviceClass.DATA_SIZE, native_unit_of_measurement="B", suggested_unit_of_measurement="GB", suggested_display_precision=1, state_class=SensorStateClass.MEASUREMENT,
                  value=lambda c: _sum(c, "freeSize"), attrs=lambda c: {k: {"livre_gb": round(v.get("freeSize", 0) / 1e9, 1), "total_gb": round(v.get("totalSize", 0) / 1e9, 1)} for k, v in _storages(c).items()}),
    PSDescription(key="armazenamento_total", device_class=SensorDeviceClass.DATA_SIZE, native_unit_of_measurement="B", suggested_unit_of_measurement="GB", suggested_display_precision=1, entity_category=EntityCategory.DIAGNOSTIC,
                  value=lambda c: _sum(c, "totalSize")),
    PSDescription(key="armazenamento_usado", native_unit_of_measurement=PERCENTAGE, suggested_display_precision=1, state_class=SensorStateClass.MEASUREMENT,
                  value=lambda c: round(100 * (1 - _sum(c, "freeSize") / t), 1) if (t := _sum(c, "totalSize")) else None),
    PSDescription(key="jogos_instalados", state_class=SensorStateClass.MEASUREMENT, value=lambda c: len(_installed(c)) if c.get("systemData") else None,
                  attrs=lambda c: {"jogos": [{"jogo": t.get("comment"), "title_id": t.get("npTitleId"), "versao": t.get("version"), "tamanho_gb": round((t.get("size") or 0) / 1e9, 1), "local": t.get("storage"), "midia": "disco" if t.get("disc") == "available" else "digital", "plataforma": t.get("psPlatform"), "ultimo_acesso": t.get("lastAccessDateTime")}
                                             for t in sorted(_installed(c), key=lambda t: t.get("lastAccessDateTime") or "", reverse=True)]}),
    PSDescription(key="ultimo_jogo_aberto", value=lambda c: (max(_installed(c), key=lambda t: t.get("lastAccessDateTime") or "", default=None) or {}).get("comment"),
                  attrs=lambda c: {"aberto_em": (max(_installed(c), key=lambda t: t.get("lastAccessDateTime") or "", default=None) or {}).get("lastAccessDateTime")}),
    PSDescription(key="nome_do_console", entity_category=EntityCategory.DIAGNOSTIC, value=lambda c: (c.get("device") or {}).get("name"),
                  attrs=lambda c: {"modos_de_ligar": (c.get("device") or {}).get("wakeupEnabledPowerModes"), "recursos": (c.get("device") or {}).get("enabledFeatures"), "idioma": (c.get("device") or {}).get("language"), "atualizado_em": c.get("updatedDateTime")}),
)


class CloudSensor(PSSensor):
    """Console data from the PS App cloud API (storage, installed games)."""

    def __init__(self, co: AccountCoordinator, desc: PSDescription, duid: str) -> None:  # noqa: D107
        from .entity import platform_device
        from .platforms import PLATFORMS

        super().__init__(co, desc)
        self.duid = duid
        self._attr_unique_id = f"{co.client.account_id}_{duid}_{desc.key}"
        self._attr_device_info = platform_device(co, "PS5", PLATFORMS["PS5"])

    @property
    def _c(self) -> D:
        return next((c for c in (self.coordinator.data or {}).get("clients") or [] if c.get("duid") == self.duid), {})

    @property
    def available(self) -> bool:  # noqa: D102
        return super().available and bool(self._c)

    @property
    def native_value(self) -> Any:  # noqa: D102
        return self.entity_description.value(self._c)

    @property
    def extra_state_attributes(self) -> D | None:  # noqa: D102
        return self.entity_description.attrs(self._c)

    @property
    def entity_picture(self) -> str | None:  # noqa: D102
        return None
