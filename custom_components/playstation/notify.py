"""One notify entity per PSN group chat (incl. 1:1 chats)."""

from __future__ import annotations

from homeassistant.components.notify import NotifyEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PlayStationConfigEntry
from .coordinator import AccountCoordinator
from .entity import PlayStationEntity
from .psn import PSNAWPError


async def async_setup_entry(hass: HomeAssistant, entry: PlayStationConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    """Groups come with the slow snapshot; add them as they appear."""
    co: AccountCoordinator = entry.runtime_data
    seen: set[str] = set()

    def check() -> None:
        new = []
        for g in (co.data or {}).get("groups") or []:
            if g["groupId"] not in seen:
                seen.add(g["groupId"])
                new.append(GroupNotify(co, g))
        if new:
            add(new)

    check()
    entry.async_on_unload(co.async_add_listener(check))


class GroupNotify(PlayStationEntity, NotifyEntity):
    """Send a PSN message to a group/chat."""

    def __init__(self, co: AccountCoordinator, group: dict) -> None:  # noqa: D107
        self.group_id = group["groupId"]
        names = [m.get("onlineId") for m in group.get("members", []) if m.get("onlineId") and m.get("onlineId") != co.client.online_id]
        label = (group.get("groupName") or {}).get("value") or ", ".join(names[:3]) or self.group_id[:8]
        super().__init__(co, f"grupo_{self.group_id}", name=f"Mensagem {label}")

    async def async_send_message(self, message: str, title: str | None = None) -> None:  # noqa: D102
        try:
            await self.hass.async_add_executor_job(self.coordinator.client.send_message, message, None, self.group_id)
        except PSNAWPError as err:
            raise HomeAssistantError(str(err)) from err
