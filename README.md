# PlayStation for Home Assistant

A custom integration (`playstation`) that covers far more than the core *PlayStation Network* integration. It handles the PSN account, plus the PS5/PS4 on your network: auto-discovery, wake, rest mode, and every controller button through Remote Play.

## Add it

*Settings → Devices & services → Add integration → PlayStation*, then pick:

- **PlayStation Network account**: paste your NPSSO. If the core integration is configured, its NPSSO is prefilled.
- **Console on this network**: consoles answering DDP are listed. Consoles are also discovered automatically (DHCP plus a DDP broadcast every 10 minutes).

To unlock rest mode, the buttons and wake, open the console's **Configure → Pair Remote Play** and type the PIN shown on the console (*Settings → System → Remote Play → Link Device*).

## What you get

**Account**

- **Presence:** status, platform, current game (with cover), last online.
- **Trophies:** trophy level, level progress, points, platinum/gold/silver/bronze/total, games with trophies (and the in-progress list), platinum games, 100% games, average completion, latest trophy (name, rarity, icon).
- **Library:** games played, total playtime, last game, most played (top 10 with hours), purchased games (PS Plus share).
- **Friends:** friends, online, playing, plus one sensor per friend.
- **Other:** blocked users, chats with new messages, linked devices, PS Plus, online, playing, verified.
- **Images:** avatar, game cover.
- **Events:** trophy earned, game started/stopped, online/offline, friend online, new message.
- **Messages:** one `notify` entity per chat, plus the `playstation.enviar_mensagem` action to message any friend.

**One device per platform** (PS5, PS4, PS3, PS Vita, PC, whichever appear on the account): playing now (PS Vita and PS3 included), current game, games with trophies, trophies, platinum, average completion, library games, total playtime, last game, activation date. Game start/stop events per platform.

**PS5 through the PSN cloud** (the same API the PS App uses; no pairing, works away from home), on the PlayStation 5 device: free, total and used storage (per drive: internal SSD, M.2, USB), installed games (version, size, disc or digital, last opened), last opened game, console name and wake modes; *Wake (cloud)* and *Rest mode (cloud)* buttons; the `playstation.abrir_jogo` action (name or title id of an installed game); game installed/removed events.

**PlayStation Portal** (or another Sony device without an API, found by DHCP from its Sony MAC): online, latency, last seen, IP. If a router integration tracks its MAC, it also shows Wi-Fi signal and band, stream bitrate, upload speed, data received, and *Streaming* (Remote Play active, ≥ 2 Mbit/s), with streaming started/stopped events. The Portal exposes nothing else; its battery is only shown on its own screen.

**Console**

- **Media player:** on / rest mode / off, running app with cover, turn on (wake) and turn off (rest mode).
- **Remote:** `remote.send_command` with CROSS, CIRCLE, SQUARE, TRIANGLE, UP, DOWN, LEFT, RIGHT, L1, R1, L2, R2, L3, R3, OPTIONS, SHARE, PS, TOUCHPAD; supports hold and repeat.
- **Buttons:** wake, rest mode, and one per controller button.
- **Sensors:** power state, running app, firmware, last seen, IP.
- **Binary sensors:** on, on network, Remote Play paired, wake available.
- **Events:** powered on, entered rest mode, app changed.
- **Action:** `playstation.pressionar_botoes`, which sends a button sequence with hold.

How each piece was found and verified: [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md).
