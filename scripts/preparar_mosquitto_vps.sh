#!/bin/sh
# Rodar na VPS (Linux), na raiz do repositório: sudo sh scripts/preparar_mosquitto_vps.sh
# Ajusta dono (uid/gid 1883 = usuário mosquitto da imagem) e permissão 0600 do passwd e do acl.
set -e
cfg="mosquitto/config"

[ -f "$cfg/passwd" ] || {
    echo "ERRO: $cfg/passwd não existe. Crie os usuários antes (scripts/criar_usuario_mqtt.sh)." >&2
    exit 1
}
[ -f "$cfg/acl" ] || { echo "ERRO: $cfg/acl não existe." >&2; exit 1; }

chown 1883:1883 "$cfg/passwd" "$cfg/acl"
chmod 0600 "$cfg/passwd" "$cfg/acl"
echo "ok: passwd e acl com dono 1883:1883 e permissão 0600"
