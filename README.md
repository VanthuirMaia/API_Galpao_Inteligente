# Galpão Inteligente - API

## Produção

### Usuários MQTT (Mosquitto)

O arquivo `mosquitto/config/passwd` precisa pertencer ao uid 1883 (usuário `mosquitto` da imagem oficial) com permissão `0600`. Os scripts `scripts/criar_usuario_mqtt.sh` e `scripts/criar_usuario_mqtt.ps1` já fazem isso (`chown 1883:1883` + `chmod 0600`, no mesmo container do `mosquitto_passwd`). Não use `chmod 0644`: o Mosquitto 2.x avisa sobre arquivos legíveis por outros usuários e versões futuras podem recusá-los.

Na VPS, o mesmo vale para o `acl` (dono 1883, permissão 0600).

Projeto desenvolvido no Espaço CRIA da ETEGEC com apoio da Fundação de Amparo à Ciência e Tecnologia do Estado de Pernambuco (FACEPE), processo ARC-0572-1.03/26.
