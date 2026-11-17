"""Local console control: DDP (discovery, status, wake) and Remote Play (standby, buttons).

DDP (Device Discovery Protocol) answers without any pairing:
- PS5: UDP 9302, protocol 00030010; PS4: UDP 987, protocol 00020020.
- ``SRCH`` -> ``HTTP/1.1 200 Ok`` (on) / ``620 Server Standby`` (rest) + headers.
- ``WAKEUP`` with ``user-credential`` = Remote Play RegistKey as decimal.
Remote Play (pyremoteplay) needs a one-time PIN registration and opens a session
to send standby or DualSense button input.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import socket
import struct
from typing import Any

_LOGGER = logging.getLogger(__name__)

PORTS = {"PS5": (9302, "00030010"), "PS4": (987, "00020020")}
STATUS = {200: "ligado", 620: "repouso"}
BUTTONS = [
    "CROSS", "CIRCLE", "SQUARE", "TRIANGLE", "UP", "DOWN", "LEFT", "RIGHT",
    "L1", "R1", "L2", "R2", "L3", "R3", "OPTIONS", "SHARE", "PS", "TOUCHPAD",
]


def parse_ddp(data: bytes) -> dict[str, Any] | None:
    """Parse a DDP reply into a dict (status_code, status, host-* headers)."""
    lines = data.decode(errors="replace").replace("\r", "").split("\n")
    if not lines[0].startswith("HTTP/1.1"):
        return None
    parts = lines[0].split(" ", 2)
    out: dict[str, Any] = {"status_code": int(parts[1])}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    out["status"] = STATUS.get(out["status_code"], "desconhecido")
    return out


def firmware(system_version: str | None) -> str | None:
    """13420000 -> 13.42."""
    if not system_version or len(system_version) < 4:
        return None
    return f"{int(system_version[:2])}.{system_version[2:4]}"


class _Collector(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.replies: dict[str, dict[str, Any]] = {}

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if parsed := parse_ddp(data):
            parsed["host"] = addr[0]
            self.replies[addr[0]] = parsed


async def ddp_query(host: str | None, wait: float = 2.0, tries: int = 2) -> dict[str, dict[str, Any]]:
    """Send SRCH to one host (or broadcast when None); return replies by IP."""
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", 0))
    transport, proto = await loop.create_datagram_endpoint(_Collector, sock=sock)
    try:
        for _ in range(tries):
            for port, ver in PORTS.values():
                msg = f"SRCH * HTTP/1.1\ndevice-discovery-protocol-version:{ver}\n".encode()
                transport.sendto(msg, (host or "255.255.255.255", port))
            await asyncio.sleep(wait)
            if host and host in proto.replies:
                break
    finally:
        transport.close()
    return proto.replies


async def ddp_wakeup(host: str, host_type: str, credential: str) -> None:
    """Wake a console from rest mode (credential = RegistKey as decimal)."""
    port, ver = PORTS.get(host_type, PORTS["PS5"])
    msg = (
        "WAKEUP * HTTP/1.1\nclient-type:vr\nauth-type:R\nmodel:w\napp-type:r\n"
        f"user-credential:{credential}\ndevice-discovery-protocol-version:{ver}\n"
    ).encode()
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    transport, _ = await loop.create_datagram_endpoint(asyncio.DatagramProtocol, sock=sock)
    try:
        for _ in range(3):
            transport.sendto(msg, (host, port))
            await asyncio.sleep(0.2)
    finally:
        transport.close()


def psn_id_from_account(account_id: str | int) -> str:
    """Remote Play user id = base64 of the PSN account id (little endian u64)."""
    return base64.b64encode(struct.pack("<Q", int(account_id))).decode()


def credential_from_regist_key(regist_key: str) -> str:
    """RegistKey (hex of an ASCII hex string) -> decimal wake credential, as the PS app does."""
    return str(int.from_bytes(bytes.fromhex(bytes.fromhex(regist_key).decode()), "big"))


def _register_blocking(host: str, host_type: str, psn_id: str, pin: str) -> dict[str, Any]:
    from pyremoteplay.const import RP_PORT
    from pyremoteplay.register import _get_regist_cipher_headers_payload, _regist_init

    if not _regist_init(host, host_type, 5):
        raise ConnectionError("console did not answer the registration search")
    cipher, headers, payload = _get_regist_cipher_headers_payload(host_type, psn_id, pin)
    # pyremoteplay splits the binary body on CRLF and corrupts it; read it whole
    with socket.create_connection((host, RP_PORT), timeout=5) as s:
        s.sendall(headers + payload)
        resp = b""
        while True:
            if b"\r\n\r\n" in resp:
                head, body = resp.split(b"\r\n\r\n", 1)
                hdrs = dict(line.split(b": ", 1) for line in head.split(b"\r\n")[1:] if b": " in line)
                if len(body) >= int(hdrs.get(b"Content-Length", 0)):
                    break
            chunk = s.recv(4096)
            if not chunk:
                break
            resp += chunk
    head, body = resp.split(b"\r\n\r\n", 1)
    if b"200 OK" not in head.split(b"\r\n")[0]:
        raise ValueError(f"registration refused: {head.split(b'\r\n')[0].decode(errors='replace')}")
    return dict(line.split(": ", 1) for line in cipher.decrypt(body).decode().split("\r\n") if ": " in line)


async def rp_register(hass: Any, host: str, host_type: str, account_id: str, pin: str) -> dict[str, Any]:
    """Register this HA as a Remote Play device using the PIN shown on the console."""
    info = await hass.async_add_executor_job(_register_blocking, host, host_type, psn_id_from_account(account_id), pin)
    if not info.get(f"{host_type}-RegistKey") or not info.get("RP-Key"):
        raise ValueError(f"incomplete registration: {sorted(info)}")
    return info


def _profiles(online_id: str, account_id: str, mac: str, host_type: str, regist: dict[str, Any]) -> Any:
    from pyremoteplay.profile import Profiles

    data = {k.replace(f"{host_type}-", ""): v for k, v in regist.items()}
    return Profiles({online_id: {"id": psn_id_from_account(account_id), "hosts": {mac: {"type": host_type, "data": data}}}})


async def rp_session(host: str, online_id: str, account_id: str, mac: str, host_type: str, regist: dict[str, Any]) -> Any:
    """Open a Remote Play session; caller must ``device.disconnect()``."""
    from pyremoteplay.device import RPDevice

    device = RPDevice(host)
    if not await device.async_get_status():
        raise ConnectionError("console did not answer")
    if not device.is_on:
        raise ConnectionError("console is in rest mode")
    profiles = _profiles(online_id, account_id, mac, host_type, regist)
    if not device.create_session(online_id, profiles=profiles, resolution="360p", fps="low", quality="very_low"):
        raise ConnectionError("could not create session")
    if not await device.connect() or not await device.async_wait_for_session():
        device.disconnect()
        raise ConnectionError("Remote Play session failed")
    return device


async def rp_standby(*args: Any) -> None:
    """Put the console in rest mode through Remote Play.

    PS5 firmware 14.x enters rest mode but never sends the standby ack pyremoteplay
    waits for, so success is confirmed by DDP (620 Server Standby) instead.
    """
    host = args[0]
    device = await rp_session(*args)
    try:
        await device.session.async_standby()
    finally:
        device.disconnect()
    for _ in range(15):
        await asyncio.sleep(2)
        if (await ddp_query(host, wait=1.5, tries=1)).get(host, {}).get("status") == "repouso":
            return
    raise ConnectionError("console did not enter rest mode")


async def rp_buttons(*args: Any, buttons: list[str], hold: float = 0.0) -> None:
    """Tap (or hold) DualSense buttons in sequence."""
    device = await rp_session(*args)
    try:
        await asyncio.sleep(0.5)
        for b in buttons:
            if hold:
                await device.controller.async_button(b, "press")
                await asyncio.sleep(hold)
                await device.controller.async_button(b, "release")
            else:
                await device.controller.async_button(b, "tap")
            await asyncio.sleep(0.35)
    finally:
        device.disconnect()
