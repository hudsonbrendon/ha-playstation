"""Generate strings.json, translations/{en,pt-BR}.json, services.yaml, icons.json."""
import json
import pathlib

R = pathlib.Path(__file__).resolve().parents[1] / "custom_components/playstation"
E = {
 "sensor": {"status": ("Status", "Status"), "plataforma": ("Platform", "Plataforma"), "jogo_atual": ("Current game", "Jogo atual"), "ultima_vez_online": ("Last online", "Última vez online"),
  "nivel_de_trofeus": ("Trophy level", "Nível de troféus"), "progresso_do_nivel": ("Level progress", "Progresso do nível"), "pontos_de_trofeu": ("Trophy points", "Pontos de troféu"),
  "platinas": ("Platinum", "Platinas"), "ouros": ("Gold", "Ouros"), "pratas": ("Silver", "Pratas"), "bronzes": ("Bronze", "Bronzes"), "trofeus": ("Trophies", "Troféus"),
  "jogos_com_trofeus": ("Games with trophies", "Jogos com troféus"), "jogos_platinados": ("Platinum games", "Jogos platinados"), "jogos_completos": ("100% games", "Jogos 100%"),
  "conclusao_media": ("Average completion", "Conclusão média"), "ultimo_trofeu": ("Latest trophy", "Último troféu"), "jogos_na_biblioteca": ("Library games", "Jogos na biblioteca"),
  "tempo_total_jogado": ("Total playtime", "Tempo total jogado"), "ultimo_jogo": ("Last game", "Último jogo"), "jogo_mais_jogado": ("Most played", "Jogo mais jogado"),
  "jogos_comprados": ("Purchased games", "Jogos comprados"), "lista_de_desejos": ("Wishlist", "Lista de desejos"), "promocoes_na_lista_de_desejos": ("Wishlist sales", "Promoções na lista de desejos"), "amigos": ("Friends", "Amigos"), "amigos_online": ("Friends online", "Amigos online"), "amigos_jogando": ("Friends playing", "Amigos jogando"),
  "bloqueados": ("Blocked users", "Bloqueados"), "mensagens_novas": ("Chats with new messages", "Mensagens novas"), "dispositivos_vinculados": ("Linked devices", "Dispositivos vinculados"),
  "estado": ("Power state", "Estado"), "app_em_execucao": ("Running app", "App em execução"), "firmware": ("Firmware", "Firmware"), "ultima_vez_visto": ("Last seen", "Última vez visto"), "endereco_ip": ("IP address", "Endereço IP"), "latencia": ("Latency", "Latência"), "sinal_wifi": ("Wi-Fi signal", "Sinal Wi-Fi"), "banda_wifi": ("Wi-Fi band", "Banda Wi-Fi"), "velocidade_da_transmissao": ("Stream bitrate", "Velocidade da transmissão"), "velocidade_de_envio": ("Upload speed", "Velocidade de envio"), "dados_recebidos": ("Data received", "Dados recebidos"), "ativado_em": ("Activated on", "Ativado em")},
 "binary_sensor": {"ps_plus": ("PlayStation Plus", "PlayStation Plus"), "online": ("Online", "Online"), "jogando": ("Playing", "Jogando"), "verificado": ("Verified", "Verificado"),
  "ligado": ("Powered on", "Ligado"), "na_rede": ("On network", "Na rede"), "remote_play_pareado": ("Remote Play paired", "Remote Play pareado"), "pode_ligar": ("Wake available", "Pode ligar"), "transmitindo": ("Streaming", "Transmitindo")},
 "button": {"atualizar": ("Refresh", "Atualizar"), "ligar": ("Wake", "Ligar"), "modo_repouso": ("Rest mode", "Repouso")},
 "event": {"trofeus": ("Trophies", "Troféus"), "partidas": ("Sessions", "Partidas"), "presenca": ("Presence", "Presença"), "amigos_evento": ("Friends", "Amigos"), "mensagens": ("Messages", "Mensagens"), "promocoes": ("Sales", "Promoções"), "energia": ("Power", "Energia"), "apps": ("Apps", "Apps"), "transmissao": ("Streaming", "Transmissão")},
 "image": {"avatar": ("Avatar", "Avatar"), "capa_do_jogo": ("Game cover", "Capa do jogo")},
 "remote": {"controle": ("Controller", "Controle")},
 "media_player": {"console": ("Console", "Console")},
}
STATES = {"status": {"online": ("Online", "Online"), "offline": ("Offline", "Offline"), "jogando": ("Playing", "Jogando")},
          "estado": {"ligado": ("On", "Ligado"), "repouso": ("Rest mode", "Repouso"), "desligado": ("Off / unreachable", "Desligado"), "desconhecido": ("Unknown", "Desconhecido")}}
EVT = {"trofeu_conquistado": ("Trophy earned", "Troféu conquistado"), "jogo_iniciado": ("Game started", "Jogo iniciado"), "jogo_encerrado": ("Game stopped", "Jogo encerrado"), "ficou_online": ("Went online", "Ficou online"),
       "ficou_offline": ("Went offline", "Ficou offline"), "amigo_online": ("Friend online", "Amigo online"), "mensagem_nova": ("New message", "Mensagem nova"), "ligou": ("Powered on", "Ligou"),
       "entrou_em_repouso": ("Entered rest mode", "Entrou em repouso"), "app_mudou": ("App changed", "App mudou"), "promocao_na_lista_de_desejos": ("Wishlist item on sale", "Promoção na lista de desejos"), "transmissao_iniciada": ("Streaming started", "Transmissão iniciada"), "transmissao_encerrada": ("Streaming stopped", "Transmissão encerrada")}
FLOW = {
 "en": {"config": {"flow_title": "{name}", "step": {
   "user": {"title": "PlayStation", "menu_options": {"account": "PlayStation Network account", "console": "PS5 / PS4 console on this network", "portable": "PlayStation Portal (or another Sony device without an API)"}},
   "portable": {"title": "PlayStation Portal", "description": "The Portal has no API: Home Assistant tracks whether it is on the network (ping), its latency and when it was last seen. Type its IP address (see your router).", "data": {"host": "IP address", "name": "Name"}},
   "confirm_portable": {"title": "Sony device found", "description": "A Sony device at {host} does not answer the console protocol, so it is most likely a PlayStation Portal. Add it to track when it is on?", "data": {"name": "Name"}},
   "account": {"title": "PSN account", "description": "Paste your **NPSSO** (64 characters).\n\n1. Sign in at https://www.playstation.com in this browser.\n2. Open [{url}]({url}).\n3. Copy the value of `npsso` (without quotes).\n\nIf the core PlayStation Network integration is set up, its NPSSO is prefilled.", "data": {"npsso": "NPSSO"}},
   "console": {"title": "Console", "description": "Consoles answering on this network are listed. Turn the console on or put it in rest mode first, or type its IP.", "data": {"console": "Console found", "host": "IP address"}},
   "confirm": {"title": "PlayStation found", "description": "Add {name} ({host})?"}},
   "error": {"invalid_auth": "NPSSO rejected (expired or wrong)", "cannot_connect": "PSN unreachable", "not_found": "No console answered at that address"},
   "abort": {"already_configured": "Already configured", "reauth_successful": "Login renewed", "not_playstation": "Not a PlayStation"}},
  "options": {"step": {"init": {"title": "Remote Play", "menu_options": {"pair": "Pair Remote Play (PIN)", "credential": "Paste wake credential"}},
   "pair": {"title": "Pair Remote Play", "description": "On the console: **Settings → System → Remote Play → Link Device**. Type the 8-digit PIN shown (the console must be on). Pairing unlocks rest mode, every controller button and wake.", "data": {"pin": "PIN", "account_id": "PSN account id", "online_id": "Online ID"}},
   "credential": {"title": "Wake credential", "data": {"credential": "Credential"}}},
   "error": {"pair_failed": "Pairing refused: check the PIN (it changes every few minutes) and that the console is on", "need_account": "Add the PSN account first or type the account id"},
   "abort": {"nothing_to_configure": "Nothing to configure for the account"}}},
 "pt-BR": {"config": {"flow_title": "{name}", "step": {
   "user": {"title": "PlayStation", "menu_options": {"account": "Conta PlayStation Network", "console": "Console PS5 / PS4 nesta rede", "portable": "PlayStation Portal (ou outro aparelho Sony sem API)"}},
   "portable": {"title": "PlayStation Portal", "description": "O Portal não tem API: o Home Assistant acompanha se ele está na rede (ping), a latência e a última vez visto. Digite o IP dele (veja no roteador).", "data": {"host": "Endereço IP", "name": "Nome"}},
   "confirm_portable": {"title": "Aparelho Sony encontrado", "description": "Um aparelho Sony em {host} não responde o protocolo de console, então provavelmente é um PlayStation Portal. Adicionar para acompanhar quando ele está ligado?", "data": {"name": "Nome"}},
   "account": {"title": "Conta PSN", "description": "Cole o seu **NPSSO** (64 caracteres).\n\n1. Entre em https://www.playstation.com neste navegador.\n2. Abra [{url}]({url}).\n3. Copie o valor de `npsso` (sem aspas).\n\nSe a integração PlayStation Network do core estiver configurada, o NPSSO dela já vem preenchido.", "data": {"npsso": "NPSSO"}},
   "console": {"title": "Console", "description": "Aparecem os consoles que responderam nesta rede. Ligue o console ou deixe em modo repouso, ou digite o IP.", "data": {"console": "Console encontrado", "host": "Endereço IP"}},
   "confirm": {"title": "PlayStation encontrado", "description": "Adicionar {name} ({host})?"}},
   "error": {"invalid_auth": "NPSSO recusado (expirado ou errado)", "cannot_connect": "PSN inacessível", "not_found": "Nenhum console respondeu nesse endereço"},
   "abort": {"already_configured": "Já configurado", "reauth_successful": "Login renovado", "not_playstation": "Não é um PlayStation"}},
  "options": {"step": {"init": {"title": "Remote Play", "menu_options": {"pair": "Parear Remote Play (PIN)", "credential": "Colar credencial de wake"}},
   "pair": {"title": "Parear Remote Play", "description": "No console: **Configurações → Sistema → Remote Play → Vincular dispositivo**. Digite o PIN de 8 dígitos que aparece (o console precisa estar ligado). O pareamento libera modo repouso, todos os botões do controle e o ligar.", "data": {"pin": "PIN", "account_id": "ID da conta PSN", "online_id": "Online ID"}},
   "credential": {"title": "Credencial de wake", "data": {"credential": "Credencial"}}},
   "error": {"pair_failed": "Pareamento recusado: confira o PIN (ele muda a cada poucos minutos) e se o console está ligado", "need_account": "Adicione a conta PSN antes ou digite o ID da conta"},
   "abort": {"nothing_to_configure": "Nada para configurar na conta"}}},
}
SVC = {"enviar_mensagem": (("Send PSN message", "Sends a message to a friend (online id) or a group chat."), ("Enviar mensagem PSN", "Envia mensagem para um amigo (online id) ou grupo.")),
       "pressionar_botoes": (("Press controller buttons", "Presses DualSense buttons on a paired console via Remote Play."), ("Pressionar botões do controle", "Aperta botões do DualSense num console pareado via Remote Play."))}
FIELDS = {"device_id": (("Device", "PSN account or console"), ("Dispositivo", "Conta PSN ou console")), "mensagem": (("Message", "Text"), ("Mensagem", "Texto")),
          "online_id": (("Online ID", "Friend online id"), ("Online ID", "Online id do amigo")), "group_id": (("Group id", "Group chat id"), ("ID do grupo", "ID do chat em grupo")),
          "botoes": (("Buttons", "Sequence, e.g. PS, DOWN, CROSS"), ("Botões", "Sequência, ex.: PS, DOWN, CROSS")), "segurar": (("Hold (s)", "Hold each button"), ("Segurar (s)", "Tempo segurando cada botão"))}
E["sensor"].update({"armazenamento_livre": ("Free storage", "Armazenamento livre"), "armazenamento_total": ("Total storage", "Armazenamento total"), "armazenamento_usado": ("Storage used", "Armazenamento usado"),
                    "jogos_instalados": ("Installed games", "Jogos instalados"), "ultimo_jogo_aberto": ("Last opened game", "Último jogo aberto"), "nome_do_console": ("Console name", "Nome do console")})
E["button"].update({"ligar_pela_nuvem": ("Wake (cloud)", "Ligar pela nuvem"), "repouso_pela_nuvem": ("Rest mode (cloud)", "Repouso pela nuvem")})
E["event"]["instalacoes"] = ("Installs", "Instalações")
EVT.update({"jogo_instalado": ("Game installed", "Jogo instalado"), "jogo_removido": ("Game removed", "Jogo removido")})
SVC["abrir_jogo"] = (("Launch game", "Starts an installed game on the PS5 through PSN (works away from home)."), ("Abrir jogo", "Abre um jogo instalado no PS5 pela PSN (funciona fora de casa)."))
FIELDS["jogo"] = (("Game", "Name or title id of an installed game"), ("Jogo", "Nome ou title id de um jogo instalado"))
SVC_FIELDS = {"enviar_mensagem": ("device_id", "mensagem", "online_id", "group_id"), "pressionar_botoes": ("device_id", "botoes", "segurar"), "abrir_jogo": ("device_id", "jogo")}
for lang, i in (("en", 0), ("pt-BR", 1)):
    out = json.loads(json.dumps(FLOW[lang]))
    ent = {p: {k: {"name": v[i]} for k, v in d.items()} for p, d in E.items()}
    for k, st in STATES.items(): ent["sensor"][k]["state"] = {s: t[i] for s, t in st.items()}
    for k in ent["event"]: ent["event"][k]["state_attributes"] = {"event_type": {"state": {e: t[i] for e, t in EVT.items()}}}
    out["entity"] = ent
    out["services"] = {s: {"name": v[i][0], "description": v[i][1], "fields": {f: {"name": t[i][0], "description": t[i][1]} for f, t in FIELDS.items() if f in SVC_FIELDS[s]}} for s, v in SVC.items()}
    (R / "translations" / f"{lang}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    if lang == "en": (R / "strings.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
BTN = ["CROSS", "CIRCLE", "SQUARE", "TRIANGLE", "UP", "DOWN", "LEFT", "RIGHT", "L1", "R1", "L2", "R2", "L3", "R3", "OPTIONS", "SHARE", "PS", "TOUCHPAD"]
svc = ("enviar_mensagem:\n  fields:\n    device_id:\n      required: true\n      selector:\n        device:\n          integration: playstation\n    mensagem:\n      required: true\n      selector:\n        text:\n          multiline: true\n"
       "    online_id:\n      selector:\n        text:\n    group_id:\n      selector:\n        text:\n"
       "pressionar_botoes:\n  fields:\n    device_id:\n      required: true\n      selector:\n        device:\n          integration: playstation\n    botoes:\n      required: true\n      example: [PS, DOWN, CROSS]\n      selector:\n        select:\n          multiple: true\n          options:\n"
       + "".join(f"            - {b}\n" for b in BTN) + "    segurar:\n      default: 0\n      selector:\n        number:\n          min: 0\n          max: 10\n          step: 0.1\n          unit_of_measurement: s\n"
       "abrir_jogo:\n  fields:\n    device_id:\n      required: true\n      selector:\n        device:\n          integration: playstation\n    jogo:\n      required: true\n      example: Grand Theft Auto VI\n      selector:\n        text:\n")
(R / "services.yaml").write_text(svc)
ic = {"sensor": {"status": "mdi:sony-playstation", "plataforma": "mdi:gamepad-variant", "jogo_atual": "mdi:gamepad-variant", "ultima_vez_online": "mdi:clock-outline", "nivel_de_trofeus": "mdi:trophy-variant", "progresso_do_nivel": "mdi:progress-star",
      "pontos_de_trofeu": "mdi:star-four-points", "platinas": "mdi:trophy-award", "ouros": "mdi:trophy", "pratas": "mdi:trophy-outline", "bronzes": "mdi:trophy-broken", "trofeus": "mdi:trophy", "jogos_com_trofeus": "mdi:trophy-variant-outline",
      "jogos_platinados": "mdi:trophy-award", "jogos_completos": "mdi:check-decagram", "conclusao_media": "mdi:percent-circle", "ultimo_trofeu": "mdi:trophy", "jogos_na_biblioteca": "mdi:bookshelf", "tempo_total_jogado": "mdi:timer-sand",
      "ultimo_jogo": "mdi:history", "jogo_mais_jogado": "mdi:fire", "jogos_comprados": "mdi:cart", "lista_de_desejos": "mdi:heart", "promocoes_na_lista_de_desejos": "mdi:sale", "amigos": "mdi:account-multiple", "amigos_online": "mdi:account-multiple-check", "amigos_jogando": "mdi:account-multiple-plus",
      "bloqueados": "mdi:account-cancel", "mensagens_novas": "mdi:message-badge", "dispositivos_vinculados": "mdi:devices", "estado": "mdi:power", "app_em_execucao": "mdi:application", "firmware": "mdi:chip", "ultima_vez_visto": "mdi:eye-check", "endereco_ip": "mdi:ip-network", "latencia": "mdi:timer-outline", "sinal_wifi": "mdi:wifi", "banda_wifi": "mdi:wifi-settings", "velocidade_da_transmissao": "mdi:download-network", "velocidade_de_envio": "mdi:upload-network", "dados_recebidos": "mdi:download", "ativado_em": "mdi:calendar-check"},
      "binary_sensor": {"ps_plus": "mdi:plus-circle", "jogando": "mdi:gamepad-variant", "remote_play_pareado": "mdi:link-variant", "pode_ligar": "mdi:power-sleep", "transmitindo": "mdi:cast-connected"},
      "button": {"atualizar": "mdi:refresh", "ligar": "mdi:power", "modo_repouso": "mdi:power-sleep"},
      "event": {"trofeus": "mdi:trophy", "partidas": "mdi:gamepad-variant", "presenca": "mdi:account-clock", "amigos_evento": "mdi:account-multiple", "mensagens": "mdi:message", "promocoes": "mdi:sale", "energia": "mdi:power", "apps": "mdi:application", "transmissao": "mdi:cast"},
      "remote": {"controle": "mdi:controller"}}
ic["sensor"].update({"armazenamento_livre": "mdi:harddisk", "armazenamento_total": "mdi:harddisk", "armazenamento_usado": "mdi:harddisk-plus", "jogos_instalados": "mdi:download-box", "ultimo_jogo_aberto": "mdi:play-box", "nome_do_console": "mdi:label"})
ic["button"].update({"ligar_pela_nuvem": "mdi:cloud-check", "repouso_pela_nuvem": "mdi:cloud-off"})
ic["event"]["instalacoes"] = "mdi:download"
icons = {"entity": {p: {k: {"default": v} for k, v in d.items()} for p, d in ic.items()}, "services": {"enviar_mensagem": {"service": "mdi:message-text"}, "pressionar_botoes": {"service": "mdi:controller"}, "abrir_jogo": {"service": "mdi:play"}}}
(R / "icons.json").write_text(json.dumps(icons, indent=2) + "\n")
print("ok")
