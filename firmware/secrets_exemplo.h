// Modelo do secrets.h. Copie este arquivo para firmware/secrets.h e troque os valores.
// O secrets.h NÃO vai para o Git (está no .gitignore). Nunca coloque senha real neste arquivo de exemplo.
#pragma once

// Rede Wi-Fi do galpão (2,4 GHz)
#define WIFI_SSID "nome-da-rede-wifi"
#define WIFI_PASS "senha-da-rede-wifi"

// Servidor MQTT (Mosquitto na VPS): IP ou domínio do broker
#define MQTT_BROKER "mqtt.etenexus.tech"
// Senha do usuário MQTT deste ESP (o usuário é o DEVICE_ID, ex.: esp01); criada com scripts/criar_usuario_mqtt.sh
#define MQTT_PASS "senha-mqtt-do-esp"
