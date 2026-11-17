"""Per-platform summary (PS5, PS4, PS3, PS Vita, PC) built from account data."""

from __future__ import annotations

from typing import Any

from .coordinator import game_of, iso_hours

PLATFORMS = {"PS5": "PlayStation 5", "PS4": "PlayStation 4", "PS3": "PlayStation 3", "PSVITA": "PlayStation Vita", "PSPC": "PlayStation PC"}
CATEGORY = {"ps5_native_game": "PS5", "ps4_game": "PS4", "pspc_game": "PSPC"}
PREFIX = (("PPSA", "PS5"), ("CUSA", "PS4"), ("PCS", "PSVITA"), ("NP", "PS3"), ("BL", "PS3"), ("BC", "PS3"))


def game_platform(game: dict[str, Any]) -> str | None:
    """Platform of a gamelist title (category first, title id prefix as fallback)."""
    if p := CATEGORY.get(game.get("category", "")):
        return p
    tid = str(game.get("titleId") or "")
    return next((p for pre, p in PREFIX if tid.startswith(pre)), None)


def summarize(d: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """{platform: stats}; only platforms with any trace on the account."""
    out: dict[str, dict[str, Any]] = {}

    def slot(p: str) -> dict[str, Any]:
        return out.setdefault(p, {"titulos": [], "jogos": [], "ativado_em": None, "jogando": None})

    for t in d.get("trophy_titles") or []:
        for p in str(t.get("trophyTitlePlatform") or "").split(","):
            if p in PLATFORMS:
                slot(p)["titulos"].append(t)
    for g in d.get("games") or []:
        if (p := game_platform(g)) in PLATFORMS:
            slot(p)["jogos"].append(g)
    for dev in d.get("devices") or []:
        if (p := {"PSVita": "PSVITA", "PSVITA": "PSVITA"}.get(dev.get("deviceType"), dev.get("deviceType"))) in PLATFORMS:
            s = slot(p)
            s["ativado_em"] = min(filter(None, [s["ativado_em"], dev.get("activationDate")]), default=None)
    me = (d.get("presences") or {}).get(d.get("account_id") or "", {})
    if (g := game_of(me)) and (p := str(g.get("launchPlatform") or "").upper()) in PLATFORMS:
        slot(p)["jogando"] = {"jogo": g.get("titleName"), "title_id": g.get("npTitleId"), "capa": g.get("conceptIconUrl") or g.get("npTitleIconUrl")}
    for pr in d.get("legacy_presences") or []:
        p = str(pr.get("platform") or "").upper().replace("PSVITA", "PSVITA")
        if pr.get("onlineStatus") == "online" and p in PLATFORMS and pr.get("titleName"):
            slot(p)["jogando"] = slot(p)["jogando"] or {"jogo": pr.get("titleName"), "title_id": pr.get("npTitleId"), "capa": None}
    for s in out.values():
        titles, games = s.pop("titulos"), s.pop("jogos")
        earned = [t.get("earnedTrophies") or {} for t in titles]
        last = max(games, key=lambda g: g.get("lastPlayedDateTime", ""), default=None)
        s |= {
            "jogos_com_trofeus": len(titles),
            "trofeus": sum(sum(e.values()) for e in earned),
            "platinas": sum(e.get("platinum", 0) for e in earned),
            "conclusao_media": round(sum(t.get("progress", 0) for t in titles) / len(titles), 1) if titles else None,
            "jogos_jogados": len(games),
            "horas": round(sum(iso_hours(g.get("playDuration")) for g in games), 1),
            "ultimo_jogo": (last or {}).get("name"),
            "ultimo_jogo_em": (last or {}).get("lastPlayedDateTime"),
            "capa_ultimo_jogo": (last or {}).get("imageUrl"),
            "mais_jogados": [{"jogo": g.get("name"), "horas": iso_hours(g.get("playDuration"))} for g in sorted(games, key=lambda g: -iso_hours(g.get("playDuration")))[:5]],
        }
    return out
