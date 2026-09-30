import logging
import os
import signal
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import psycopg

from db import conectar, registrar_erro
from processamento import novo_cache, processar_mensagem

log = logging.getLogger("ingestor")

ERRO_INTERNO = "erro_interno"


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        log.error("falha ao conectar no broker: %s", reason_code)
        return
    # assina a cada (re)conexão
    topico = os.environ.get("MQTT_TOPICO", "galpao/+/leituras")
    client.subscribe(topico, qos=1)
    log.info("conectado ao broker (session_present=%s); assinando %s", flags.session_present, topico)


def on_disconnect(client, userdata, flags, reason_code, properties):
    log.warning("desconectado do broker: %s", reason_code)


def on_message(client, userdata, msg):
    """Nunca deixa exceção escapar. Se o banco cair, bloqueia até reconectar e repete a mensagem."""
    agora = datetime.now(timezone.utc)
    while True:
        try:
            resultado = processar_mensagem(
                userdata["conn"], userdata["cache"], msg.topic, msg.payload, agora, userdata["ttl"]
            )
            break
        except (psycopg.OperationalError, psycopg.InterfaceError) as e:
            log.warning("banco indisponível (%s); reconectando", e)
            try:
                userdata["conn"].close()
            except Exception:
                pass
            userdata["conn"] = conectar(userdata["url"])
        except Exception:
            log.exception("erro inesperado processando %s", msg.topic)
            try:
                registrar_erro(userdata["conn"], msg.topic, msg.payload, ERRO_INTERNO)
            except Exception:
                log.exception("falha ao registrar %s", ERRO_INTERNO)
            return

    if resultado == "gravada":
        log.info("%s gravada", msg.topic)
    elif resultado == "duplicada":
        log.debug("%s duplicada", msg.topic)
    else:
        log.warning("%s %s", msg.topic, resultado)


def main():
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    host = os.environ["MQTT_HOST"]
    porta = int(os.environ.get("MQTT_PORT", "1883"))
    topico = os.environ.get("MQTT_TOPICO", "galpao/+/leituras")
    url = os.environ["DATABASE_URL"]

    # banco antes do MQTT
    conn = conectar(url)
    estado = {
        "conn": conn,
        "cache": novo_cache(),
        "url": url,
        "ttl": int(os.environ.get("CACHE_TTL_S", "300")),
    }

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=os.environ.get("MQTT_CLIENT_ID", "galpao-ingestor"),
        clean_session=False,
        protocol=mqtt.MQTTv311,
        userdata=estado,
    )
    client.username_pw_set(os.environ["MQTT_USER"], os.environ["MQTT_PASS"])
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    def encerrar(signum, frame):
        client.disconnect()

    signal.signal(signal.SIGTERM, encerrar)
    signal.signal(signal.SIGINT, encerrar)

    log.info("iniciando: broker %s:%s, tópico %s", host, porta, topico)
    client.connect_async(host, porta)
    client.loop_forever(retry_first_connection=True)

    try:
        estado["conn"].close()
    except Exception:
        pass
    log.info("ingestor encerrado")


if __name__ == "__main__":
    main()
