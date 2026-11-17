# PlayStation — how each piece was found (November 2026)

## PlayStation Network (cloud)

Auth: the NPSSO cookie → OAuth tokens (PSNAWP 3.0.3, the same library the core integration uses). Endpoints validated live with a real account:

| Data | Endpoint |
|---|---|
| Presence (status, platform, game) for up to 100 accounts | `m.np.playstation.com/api/userProfile/v1/internal/users/basicPresences?type=primary&accountIds=…` |
| Profile (PS Plus flag, avatar, verified) | `us-prof.np.community.playstation.net/userProfile/v1/users/{onlineId}/profile2?fields=…` |
| Trophy level / points / counts | `…/trophy/v1/users/{accountId}/trophySummary` |
| Per-game trophy progress | `…/trophy/v1/users/{accountId}/trophyTitles?limit=800` |
| Latest trophy (name, rarity, icon) | `…/trophy/v1/users/{id}/npCommunicationIds/{cid}/trophyGroups/all/trophies` + the same path without `users/{id}` for names |
| Played games with playtime (ISO 8601 `playDuration`), play count, first/last played | `…/gamelist/v2/users/{accountId}/titles?categories=ps4_game,ps5_native_game,pspc_game,unknown` |
| Purchased + PS Plus games | GraphQL `getPurchasedGameList` (persisted hash `2c0454…05e2`) |
| Friends, blocked users | `…/userProfile/v1/internal/users/{id}/friends`, `…/me/blocks` |
| Group chats (new-message flag) | `…/gamingLoungeGroups/v1/members/me/groups` |
| Devices linked to the account | `dms.api.playstation.com/api/v1/devices/accounts/me` |

GraphQL notes:

- `m.np.playstation.com/api/graphql/v1/op` only runs queries on its allow-list, identified by the sha256 of the query text. Arbitrary queries (even those found in the store's JS bundles) get "Query not whitelisted".
- Allow-listed hashes also require Apollo's CSRF headers (`x-apollo-operation-name`, `apollo-require-preflight: true`). Without them the server answers "blocked as a potential CSRF".
- `friends/receivedRequests` returns 403 with this OAuth scope.

## Consoles on the LAN

- **DDP** (Device Discovery Protocol): UDP 9302 (PS5, `00030010`) and 987 (PS4, `00020020`). `SRCH` answers without any pairing: `200 Ok` (on) or `620 Server Standby` (rest mode), plus host-id (MAC), host-type, host-name, system-version (13420000 → 13.42), host-request-port, and `running-app-titleid/name` while on. Broadcasting to 255.255.255.255 finds every console; this is the auto-discovery, alongside the DHCP matchers for Sony MAC prefixes and `ps5-*`/`ps4-*` hostnames.
- **WAKEUP**: same port, with `user-credential` = the Remote Play RegistKey as a decimal. The RegistKey is hex of an ASCII hex string, so the conversion is `int(bytes.fromhex(bytes.fromhex(k).decode()))`.
- **Remote Play** (pyremoteplay 0.7.6): registration with the 8-digit PIN from *Settings → System → Remote Play → Link Device*, using `psn_id` = base64(little-endian u64 account id). pyremoteplay's parser corrupts the binary registration response (it splits on CRLF), so the body is read whole and decrypted directly. A session gives standby and every DualSense button.
- pyremoteplay imports fine against the protobuf 7.36 that HA pins.

## Per-platform devices (PS5, PS4, PS3, PS Vita, PC)

- Built from trophy titles (`trophyTitlePlatform` can list several, e.g. `PS3,PSVITA,PS4`), gamelist (`category`, else title-id prefix: PPSA=PS5, CUSA=PS4, PCS*=Vita, NP*/BL*/BC*=PS3), account devices (`activationDate`) and presences.
- Only the legacy `profile2` presence (`presences(@titleInfo,platform)`) reports sessions on PS Vita and PS3. `basicPresences` reports only the primary platform. It is polled every minute, and game start/stop events are emitted per platform.
- The account device list (`dms.api…/accountDevices`) did not include the PS Vita on this account, even though there are 18 Vita trophy lists.

## Researched and not possible (November 2026)

- **PlayStation Portal**: verified live on this LAN. Its MAC is Sony Interactive (9C:37:CB, which is in the DHCP matchers); it answers ping (Wi-Fi power save, 0.1-1 s), and it has no DDP and no open TCP ports. The integration tracks it by ping. It has no local or PSN API. It talks only Remote Play to the PS5, and the PSN does not list it as a device unless cloud streaming is used. Its sessions appear as the PS5.
- **DualSense battery / firmware**: neither PSN nor Remote Play exposes them. They exist only in the controller's HID reports: the status byte (battery 0-10, charging) and feature report 0x20 (firmware at offset 28, hardware at offset 24), as read by Linux `hid-playstation`. The HA OS kernel (6.18-haos) ships `hid-sony` (DualShock 3/4) but not `hid-playstation`, and pairing the DualSense to the HA host would unpair it from the PS5. On the console itself this would need a jailbreak payload calling `libScePad`, which the public PS5 payload SDK has no headers for.
- **PS Plus tier/expiry** (`getProfileOracle`) and **PS5 remote downloads** (`GetRemoteDownloadList` needs a `duid` the API rejects for PS5) do not work with the integration's Bearer token. The wishlist (`storeRetrieveWishlist`) does work.


## PSN cloud device control (PS App, November 2026)

Found by decompiling the PS App Hermes bundle (`hermes-dec`) and confirmed live with the NPSSO Bearer token.

- `GET https://m.np.playstation.com/api/cloudAssistedNavigation/v2/users/me/clients?platform=PS5&includeFields=device,systemData`
  returns, per console (`duid`), `device` (name, language, `wakeupEnabledPowerModes`, `enabledFeatures`) and `systemData` (`storage.{embedded,m2Extended,mounted}.{freeSize,totalSize}` and `installedTitles.titles[]` with `comment` (name), `npTitleId`, `titleId`, `size`, `version`, `storage`, `disc`, `lastAccessDateTime`).
- `GET .../v2/users/me/commands` lists recent commands with `commandStatus`/`commandResult`. `.../actions` returns 403.
- `POST .../v2/users/me/commands` with `{"commandDetail": {"platform": "PS5", "duid", "commandType", "parameters"}}`. Command types in the app: `launchTitle {titleIds}`, `sendGameIntent {gameIntent}`, `enterWorkingMode`, `enterRestMode`, `keepMainOnStandby`, `prepareForRemotePlay` (with `subCommands`), `storageManagement {operation: "delete", titles}`, `downloadProgress`/`downloadErrorReason {entitlementId}`, plus party commands.
- Not exposed: the delete command (destructive). DualSense and Portal battery are not in this API. The battery fields in the app (`swDevice*BatteryLevel`) belong to PULSE earbuds and the PlayStation Link adapter, which the phone reads over Bluetooth.
