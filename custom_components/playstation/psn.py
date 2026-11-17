"""PlayStation Network client (sync, run in the executor) on top of PSNAWP auth.

Endpoints validated live in November 2026 (see REVERSE_ENGINEERING.md).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from psnawp_api import PSNAWP
from psnawp_api.core.psnawp_exceptions import PSNAWPAuthenticationError, PSNAWPError

_LOGGER = logging.getLogger(__name__)
M = "https://m.np.playstation.com/api"
GQL = f"{M}/graphql/v1/op"
CAN = f"{M}/cloudAssistedNavigation/v2/users/me"
PURCHASED_HASH = "2c045408b0a4d0264bb5a3edfed4efd49fb4749cf8d216be9043768adff905e2"
WISHLIST_HASH = "1fa88dd6c70279e3d914f7ba535b2558a7e45821d030cb2a63a8e450963d12c3"  # captured from store.playstation.com/wishlist
PROFILE_FIELDS = (
    "npId,onlineId,accountId,avatarUrls,plus,aboutMe,languagesUsed,"
    "trophySummary(@default,level,progress,earnedTrophies),isOfficiallyVerified,"
    "personalDetail(@default,profilePictureUrls),primaryOnlineStatus,"
    "presences(@default,@titleInfo,platform,lastOnlineDate,hasBroadcastData)"
)

__all__ = ["PSNAWPAuthenticationError", "PSNAWPError", "PsnClient"]


class PsnClient:
    """Read the whole account; every method is blocking."""

    def __init__(self, npsso: str) -> None:
        """Log in with the NPSSO cookie (valid ~2 months)."""
        self.psn = PSNAWP(npsso)
        self.me = self.psn.me()
        self.account_id = str(self.me.account_id)
        self.online_id = self.me.online_id

    def _get(self, url: str, **params: Any) -> Any:
        return self.psn.authenticator.get(url=url, params=params or None).json()

    def _safe(self, fn: Any, default: Any = None) -> Any:
        try:
            return fn()
        except PSNAWPAuthenticationError:
            raise
        except (PSNAWPError, ValueError, KeyError) as err:
            _LOGGER.debug("PSN call failed: %s", err)
            return default

    # ---- fast (presence) ---------------------------------------------------

    def presences(self, account_ids: list[str]) -> dict[str, Any]:
        """Primary presence (status, platform, game) for up to 100 accounts."""
        out: dict[str, Any] = {}
        for i in range(0, len(account_ids), 100):
            chunk = ",".join(account_ids[i : i + 100])
            d = self._safe(lambda c=chunk: self._get(f"{M}/userProfile/v1/internal/users/basicPresences", type="primary", accountIds=c), {})
            for p in d.get("basicPresences", []):
                out[str(p["accountId"])] = p
        return out

    def legacy_presences(self) -> list[dict[str, Any]]:
        """Per-platform presences (the only source that reports PS Vita / PS3 sessions)."""
        d = self._safe(lambda: self._get(f"https://us-prof.np.community.playstation.net/userProfile/v1/users/{self.online_id}/profile2", fields="presences(@default,@titleInfo,platform,lastOnlineDate,hasBroadcastData)"), {})
        return (d.get("profile") or {}).get("presences") or []

    # ---- slow ----------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Everything that changes slowly."""
        a = self.account_id
        data: dict[str, Any] = {"account_id": a, "online_id": self.online_id}
        data["profile"] = self._safe(lambda: self._get(f"https://us-prof.np.community.playstation.net/userProfile/v1/users/{self.online_id}/profile2", fields=PROFILE_FIELDS)["profile"], {})
        data["trophy_summary"] = self._safe(lambda: self._get(f"{M}/trophy/v1/users/{a}/trophySummary"), {})
        data["trophy_titles"] = self._safe(lambda: self._get(f"{M}/trophy/v1/users/{a}/trophyTitles", limit=800).get("trophyTitles", []), [])
        games: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self._safe(lambda o=offset: self._get(f"{M}/gamelist/v2/users/{a}/titles", categories="ps4_game,ps5_native_game,pspc_game,unknown", limit=200, offset=o), {})
            games += page.get("titles", [])
            if not page.get("nextOffset") or len(games) >= int(page.get("totalItemCount", 0)):
                break
            offset = page["nextOffset"]
        data["games"] = games
        data["purchased"] = self._safe(self.purchased, [])
        data["wishlist"] = self._safe(self.wishlist)
        friends = self._safe(lambda: self._get(f"{M}/userProfile/v1/internal/users/{a}/friends", limit=1000).get("friends", []), [])
        data["friend_ids"] = [str(f) for f in friends]
        data["friend_profiles"] = self._safe(lambda: self.profiles(data["friend_ids"]), {}) if friends else {}
        data["blocked"] = self._safe(lambda: self._get(f"{M}/userProfile/v1/internal/users/me/blocks").get("blockList", []), [])
        data["groups"] = self._safe(lambda: self._get(f"{M}/gamingLoungeGroups/v1/members/me/groups", includeFields="groupName,members,mainThread,joinedTimestamp,modifiedTimestamp,isFavorite,existsNewArrival,partySessions").get("groups", []), [])
        data["devices"] = self._safe(lambda: self._get("https://dms.api.playstation.com/api/v1/devices/accounts/me").get("accountDevices", []), [])
        recent = max(data["trophy_titles"], key=lambda t: t.get("lastUpdatedDateTime", ""), default=None)
        data["latest_trophy"] = self._safe(lambda: self.latest_trophy(recent)) if recent else None
        return data

    def profiles(self, account_ids: list[str]) -> dict[str, Any]:
        """Online id + avatar for many accounts."""
        out: dict[str, Any] = {}
        for i in range(0, len(account_ids), 100):
            chunk = ",".join(account_ids[i : i + 100])
            d = self._get(f"{M}/userProfile/v1/internal/users/profiles", accountIds=chunk)
            for aid, p in zip(account_ids[i : i + 100], d.get("profiles", []), strict=False):
                out[aid] = p
        return out

    def _gql(self, op: str, sha: str, variables: dict[str, Any]) -> dict[str, Any]:
        return self.psn.authenticator.get(
            url=GQL,
            headers={"x-apollo-operation-name": op, "apollo-require-preflight": "true", "content-type": "application/json"},
            params={"operationName": op, "variables": json.dumps(variables), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": sha}})},
        ).json().get("data") or {}

    def wishlist(self) -> list[dict[str, Any]]:
        """Store wishlist with price and discount."""
        out = []
        for p in self._gql("storeRetrieveWishlist", WISHLIST_HASH, {}).get("storeWishlistSecure") or []:
            price = p.get("price") or {}
            out.append({"id": p.get("id"), "jogo": p.get("name"), "plataformas": p.get("platforms"), "preco": price.get("discountedPrice"),
                        "preco_original": price.get("basePrice"), "desconto": price.get("discountText"), "gratis": price.get("isFree"),
                        "capa": (p.get("boxArt") or {}).get("url"), "url": f"https://store.playstation.com/pt-br/product/{p.get('id')}"})
        return out

    def purchased(self) -> list[dict[str, Any]]:
        """Purchased + PS Plus games (GraphQL, same query as library.playstation.com)."""
        games: list[dict[str, Any]] = []
        start = 0
        while True:
            variables = {"isActive": True, "platform": ["ps4", "ps5"], "size": 200, "start": start, "sortBy": "ACTIVE_DATE", "sortDirection": "desc"}
            r = self.psn.authenticator.get(
                url=GQL,
                headers={"x-apollo-operation-name": "getPurchasedGameList", "apollo-require-preflight": "true", "content-type": "application/json"},
                params={"operationName": "getPurchasedGameList", "variables": json.dumps(variables), "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": PURCHASED_HASH}})},
            ).json()
            block = (r.get("data") or {}).get("purchasedTitlesRetrieve") or {}
            games += block.get("games", [])
            page = block.get("pageInfo") or {}
            if not page or page.get("isLast", True) or not block.get("games"):
                break
            start += 200
        return games

    def latest_trophy(self, title: dict[str, Any]) -> dict[str, Any] | None:
        """Most recent earned trophy of a trophy title, with name and rarity."""
        cid = title["npCommunicationId"]
        svc = title.get("npServiceName", "trophy2")
        earned = self._get(f"{M}/trophy/v1/users/{self.account_id}/npCommunicationIds/{cid}/trophyGroups/all/trophies", npServiceName=svc).get("trophies", [])
        got = [t for t in earned if t.get("earned")]
        if not got:
            return None
        last = max(got, key=lambda t: t.get("earnedDateTime", ""))
        meta = {t["trophyId"]: t for t in self._get(f"{M}/trophy/v1/npCommunicationIds/{cid}/trophyGroups/all/trophies", npServiceName=svc).get("trophies", [])}
        info = meta.get(last["trophyId"], {})
        return {
            "jogo": title.get("trophyTitleName"),
            "trofeu": info.get("trophyName"),
            "descricao": info.get("trophyDetail"),
            "tipo": last.get("trophyType"),
            "raridade": last.get("trophyEarnedRate"),
            "conquistado_em": last.get("earnedDateTime"),
            "icone": info.get("trophyIconUrl"),
        }

    # ---- cloud device control (PS App "cloudAssistedNavigation", see REVERSE_ENGINEERING.md) ----

    def clients(self) -> list[dict[str, Any]]:
        """Consoles linked to the PS App: name, wake modes, storage, installed titles."""
        d = self._get(f"{CAN}/clients", platform="PS5", includeFields="device,systemData")
        return d.get("clients", [])

    def command(self, duid: str, command_type: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        """Queue a command on a console through PSN (it runs when the console polls)."""
        detail: dict[str, Any] = {"platform": "PS5", "duid": duid, "commandType": command_type}
        if parameters:
            detail["parameters"] = parameters
        r = self.psn.authenticator.post(url=f"{CAN}/commands", json={"commandDetail": detail})
        return r.json() if r.content else {}

    # ---- actions ---------------------------------------------------------------

    def send_message(self, text: str, online_id: str | None = None, group_id: str | None = None) -> None:
        """Send a PSN message to a friend (by online id) or to an existing group."""
        group = self.psn.group(group_id=group_id) if group_id else self.psn.group(users_list=[self.psn.user(online_id=online_id)])
        group.send_message(text)
