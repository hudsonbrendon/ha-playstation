"""Constants for PlayStation."""

from homeassistant.const import Platform

DOMAIN = "playstation"
MANUFACTURER = "Sony Interactive Entertainment"
CONF_KIND = "kind"
KIND_ACCOUNT = "account"
KIND_CONSOLE = "console"
KIND_PORTABLE = "portable"
CONF_NPSSO = "npsso"
CONF_HOST_TYPE = "host_type"
CONF_HOST_ID = "host_id"
CONF_CREDENTIAL = "credential"
CONF_REGIST = "regist"
CONF_ACCOUNT_ID = "account_id"
CONF_ONLINE_ID = "online_id"

ACCOUNT_PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.EVENT, Platform.IMAGE, Platform.NOTIFY, Platform.SENSOR]
PORTABLE_PLATFORMS = [Platform.BINARY_SENSOR, Platform.EVENT, Platform.SENSOR]
CONSOLE_PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.EVENT, Platform.MEDIA_PLAYER, Platform.REMOTE, Platform.SENSOR]

PRESENCE_INTERVAL = 60
SNAPSHOT_INTERVAL = 1800
CONSOLE_INTERVAL = 10
DISCOVERY_INTERVAL = 600
CLOUD_INTERVAL = 300

EVENT_TROPHY = "trofeu_conquistado"
EVENT_GAME_STARTED = "jogo_iniciado"
EVENT_GAME_STOPPED = "jogo_encerrado"
EVENT_ONLINE = "ficou_online"
EVENT_OFFLINE = "ficou_offline"
EVENT_FRIEND_ONLINE = "amigo_online"
EVENT_NEW_MESSAGE = "mensagem_nova"
EVENT_SALE = "promocao_na_lista_de_desejos"
EVENT_POWER_ON = "ligou"
EVENT_REST = "entrou_em_repouso"
EVENT_APP = "app_mudou"
EVENT_STREAM_START = "transmissao_iniciada"
EVENT_STREAM_STOP = "transmissao_encerrada"
EVENT_INSTALLED = "jogo_instalado"
EVENT_REMOVED = "jogo_removido"
