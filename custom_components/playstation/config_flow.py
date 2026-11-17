"""Config flow: PSN account (NPSSO) or console (DDP scan, DHCP, discovery) + Remote Play pairing."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
import voluptuous as vol

from .console import credential_from_regist_key, ddp_query, rp_register
from .const import (
    CONF_ACCOUNT_ID,
    CONF_CREDENTIAL,
    CONF_HOST_ID,
    CONF_HOST_TYPE,
    CONF_KIND,
    CONF_NPSSO,
    CONF_ONLINE_ID,
    CONF_REGIST,
    DOMAIN,
    KIND_ACCOUNT,
    KIND_CONSOLE,
    KIND_PORTABLE,
)
from .psn import PSNAWPAuthenticationError, PSNAWPError, PsnClient

_LOGGER = logging.getLogger(__name__)
NPSSO_URL = "https://ca.account.sony.com/api/v1/ssocookie"


class PlayStationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Account or console."""

    VERSION = 1

    def __init__(self) -> None:  # noqa: D107
        self._found: dict[str, dict[str, Any]] = {}
        self._console: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose what to add."""
        return self.async_show_menu(step_id="user", menu_options=["account", "console", "portable"])

    # ---- PlayStation Portal / other Sony device (presence only) ---------------

    async def async_step_portable(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Device with no API (PS Portal): presence by ping, MAC from the ARP table."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            mac = await self._mac_of(host)
            if not mac:
                errors["base"] = "not_found"
            else:
                return await self._portable_found(host, mac, user_input.get("name") or "PlayStation Portal")
        return self.async_show_form(step_id="portable", data_schema=vol.Schema({vol.Required(CONF_HOST): str, vol.Optional("name", default="PlayStation Portal"): str}), errors=errors)

    async def _mac_of(self, host: str) -> str | None:
        from icmplib import async_ping

        try:
            await async_ping(host, count=1, timeout=2, privileged=False)
        except Exception:
            return None

        def arp() -> str | None:
            try:
                for line in open("/proc/net/arp", encoding="ascii").read().splitlines()[1:]:
                    f = line.split()
                    if f[0] == host and f[3] != "00:00:00:00:00:00":
                        return f[3].lower()
            except OSError:
                return None
            return None

        return await self.hass.async_add_executor_job(arp)

    async def _portable_found(self, host: str, mac: str, name: str, confirm: bool = False) -> ConfigFlowResult:
        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._console = {CONF_KIND: KIND_PORTABLE, CONF_HOST: host, "mac": mac, "name": name}
        self.context["title_placeholders"] = {"name": name}
        if confirm:
            return await self.async_step_confirm_portable()
        return self.async_create_entry(title=name, data=self._console)

    async def async_step_confirm_portable(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Sony device without DDP found by DHCP: most likely a PlayStation Portal."""
        if user_input is not None:
            return self.async_create_entry(title=user_input.get("name") or self._console["name"], data={**self._console, "name": user_input.get("name") or self._console["name"]})
        return self.async_show_form(step_id="confirm_portable", data_schema=vol.Schema({vol.Optional("name", default=self._console["name"]): str}), description_placeholders={"host": self._console[CONF_HOST]})

    # ---- account -------------------------------------------------------------

    async def async_step_account(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """NPSSO cookie (prefilled from the core PlayStation Network integration)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            npsso = user_input[CONF_NPSSO].strip()
            try:
                client = await self.hass.async_add_executor_job(PsnClient, npsso)
            except PSNAWPAuthenticationError:
                errors["base"] = "invalid_auth"
            except PSNAWPError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(client.account_id)
                data = {CONF_KIND: KIND_ACCOUNT, CONF_NPSSO: npsso}
                if self.source == "reauth":
                    return self.async_update_reload_and_abort(self._get_reauth_entry(), data_updates=data)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=client.online_id, data=data)
        known = next((e.data.get("npsso") for e in self.hass.config_entries.async_entries("playstation_network")), "")
        return self.async_show_form(
            step_id="account",
            data_schema=vol.Schema({vol.Required(CONF_NPSSO, default=known or ""): str}),
            errors=errors,
            description_placeholders={"url": NPSSO_URL, "signin_url": "https://www.playstation.com"},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """NPSSO expired."""
        return await self.async_step_account()

    # ---- console ---------------------------------------------------------------

    async def async_step_console(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Scan the LAN with DDP, or type the IP."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input.get("console") or user_input.get(CONF_HOST)
            info = self._found.get(host) or (await ddp_query(host, wait=2.0)).get(host)
            if info:
                return await self._console_found(host, info)
            errors["base"] = "not_found"
        self._found = await ddp_query(None, wait=2.0)
        known = {e.data.get(CONF_HOST_ID) for e in self._async_current_entries()}
        options = {h: f"{i.get('host-name')} ({i.get('host-type')}, {h})" for h, i in self._found.items() if i.get("host-id") not in known}
        schema = vol.Schema({vol.Optional("console"): vol.In(options)} if options else {}).extend({vol.Optional(CONF_HOST): str})
        return self.async_show_form(step_id="console", data_schema=schema, errors=errors)

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """Sony MAC/hostname seen on the network: check it speaks DDP."""
        info = (await ddp_query(discovery_info.ip, wait=2.0)).get(discovery_info.ip)
        if not info:
            # Sony MAC that does not speak DDP: PlayStation Portal (or a PS Vita); presence only
            mac = ":".join(discovery_info.macaddress[i : i + 2] for i in range(0, 12, 2)).lower()
            return await self._portable_found(discovery_info.ip, mac, "PlayStation Portal", confirm=True)
        return await self._console_found(discovery_info.ip, info, confirm=True)

    async def async_step_integration_discovery(self, discovery_info: dict[str, Any]) -> ConfigFlowResult:
        """Found by the account's periodic DDP broadcast."""
        return await self._console_found(discovery_info["host"], discovery_info, confirm=True)

    async def _console_found(self, host: str, info: dict[str, Any], confirm: bool = False) -> ConfigFlowResult:
        await self.async_set_unique_id(info["host-id"])
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._console = {CONF_KIND: KIND_CONSOLE, CONF_HOST: host, CONF_HOST_ID: info["host-id"], CONF_HOST_TYPE: info.get("host-type", "PS5"), "name": info.get("host-name") or info.get("host-type")}
        self.context["title_placeholders"] = {"name": self._console["name"]}
        if confirm:
            return await self.async_step_confirm()
        return self._create_console()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Confirm a discovered console."""
        if user_input is not None:
            return self._create_console()
        return self.async_show_form(step_id="confirm", description_placeholders={"name": self._console["name"], "host": self._console[CONF_HOST]})

    def _create_console(self) -> ConfigFlowResult:
        # reuse the wake credential of the ps5_local integration for the same console, if any
        cred = next((e.options.get("credential") for e in self.hass.config_entries.async_entries("ps5_local") if e.data.get(CONF_HOST) == self._console[CONF_HOST]), None)
        return self.async_create_entry(title=self._console["name"], data=self._console, options={CONF_CREDENTIAL: cred} if cred else {})

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:  # noqa: D102
        return ConsoleOptionsFlow()


class ConsoleOptionsFlow(OptionsFlow):
    """Pair Remote Play with the PIN shown on the console, or paste a wake credential."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:  # noqa: D102
        if self.config_entry.data.get(CONF_KIND) != KIND_CONSOLE:
            return self.async_abort(reason="nothing_to_configure")
        return self.async_show_menu(step_id="init", menu_options=["pair", "credential"])

    async def async_step_pair(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """PIN: Settings → System → Remote Play → Link Device on the console."""
        errors: dict[str, str] = {}
        account = next((e for e in self.hass.config_entries.async_entries(DOMAIN) if e.data.get(CONF_KIND) == KIND_ACCOUNT and hasattr(e, "runtime_data")), None)
        if user_input is not None:
            acc_id = user_input.get(CONF_ACCOUNT_ID) or (account.runtime_data.client.account_id if account else None)
            online = user_input.get(CONF_ONLINE_ID) or (account.runtime_data.client.online_id if account else "user")
            if not acc_id:
                errors["base"] = "need_account"
            else:
                d = self.config_entry.data
                try:
                    regist = await rp_register(self.hass, d[CONF_HOST], d.get(CONF_HOST_TYPE, "PS5"), acc_id, user_input["pin"].replace(" ", ""))
                except (ValueError, ConnectionError, OSError):
                    errors["base"] = "pair_failed"
                else:
                    key = regist[f"{d.get(CONF_HOST_TYPE, 'PS5')}-RegistKey"]
                    return self.async_create_entry(data={**self.config_entry.options, CONF_REGIST: regist, CONF_CREDENTIAL: credential_from_regist_key(key), CONF_ACCOUNT_ID: acc_id, CONF_ONLINE_ID: online})
        schema: dict[Any, Any] = {vol.Required("pin"): str}
        if not account:
            schema |= {vol.Required(CONF_ACCOUNT_ID): str, vol.Optional(CONF_ONLINE_ID): str}
        return self.async_show_form(step_id="pair", data_schema=vol.Schema(schema), errors=errors)

    async def async_step_credential(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Paste a wake credential (decimal) obtained elsewhere."""
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, CONF_CREDENTIAL: user_input[CONF_CREDENTIAL].strip()})
        return self.async_show_form(step_id="credential", data_schema=vol.Schema({vol.Required(CONF_CREDENTIAL, default=self.config_entry.options.get(CONF_CREDENTIAL, "")): str}))
