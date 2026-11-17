"""DDP parsing and credential helpers."""

from custom_components.playstation.console import (
    credential_from_regist_key,
    firmware,
    parse_ddp,
    psn_id_from_account,
)


def test_parse_ddp_standby() -> None:
    raw = b"HTTP/1.1 620 Server Standby\nhost-id:04F778000001\nhost-type:PS5\nhost-name:PS5 de Teste\nsystem-version:13420000\n"
    d = parse_ddp(raw)
    assert d["status"] == "repouso" and d["status_code"] == 620 and d["host-type"] == "PS5" and d["host-name"] == "PS5 de Teste"
    assert firmware(d["system-version"]) == "13.42"
    assert parse_ddp(b"garbage") is None
    assert parse_ddp(b"HTTP/1.1 200 Ok\nrunning-app-name:Jogo\n")["status"] == "ligado"


def test_ids() -> None:
    assert psn_id_from_account("1") == "AQAAAAAAAAA="
    # RegistKey is the hex of an ASCII hex string
    assert credential_from_regist_key("3031") == str(0x01)


async def test_standby_confirmed_by_ddp() -> None:
    """FW 14.x: no standby ack, but DDP shows rest mode → success."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from custom_components.playstation import console

    dev = MagicMock()
    dev.session.async_standby = AsyncMock(return_value=False)
    with patch.object(console, "rp_session", AsyncMock(return_value=dev)), patch.object(console, "ddp_query", AsyncMock(return_value={"h": {"status": "repouso"}})), patch.object(console.asyncio, "sleep", AsyncMock()):
        await console.rp_standby("h", "eu", "1", "AABB", "PS5", {})
    dev.disconnect.assert_called_once()

