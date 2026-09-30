#!/bin/sh
# Uso: scripts/criar_usuario_mqtt.sh <usuario> <senha>
# Cria/atualiza o usuário em mosquitto/config/passwd (criando o arquivo se não existir).
# O passwd fica com dono 1883:1883 (usuário mosquitto da imagem) e permissão 0600.
set -e
[ $# -eq 2 ] || { echo "uso: $0 <usuario> <senha>" >&2; exit 1; }

cfg="$(cd "$(dirname "$0")/../mosquitto/config" && pwd)"
[ -f "$cfg/passwd" ] && flag="-b" || flag="-c -b"

MSYS_NO_PATHCONV=1 docker run --rm -v "$cfg:/mosquitto/config" eclipse-mosquitto:2 \
    sh -c 'mosquitto_passwd "$@" && chown 1883:1883 /mosquitto/config/passwd && chmod 0600 /mosquitto/config/passwd' \
    sh $flag /mosquitto/config/passwd "$1" "$2"
echo "usuário '$1' gravado em mosquitto/config/passwd"
