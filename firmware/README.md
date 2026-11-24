# Firmware do ESP32 (Galpão Inteligente)

Lê a temperatura e a umidade do galpão, controla localmente o ventilador (fan) e a bomba e envia as leituras por MQTT para o servidor (ver o `README.md` da raiz).

## Autoria

O firmware (`firmware.ino`, antes `sketch_oct19a.ino`) foi desenvolvido pelos alunos **Axl Henrique, Vitor Duan, Taylon Ramon e Maysa Siqueira**, no Espaço CRIA da ETEGEC, para o projeto Galpão Inteligente (placa Wemos D1 R32). Esta documentação descreve o código deles; a lógica não foi alterada. A única mudança no código foi mover o IP do broker para o `secrets.h` (ver [Segredos](#segredos-secretsh)).

## Hardware

| Item | Detalhe |
|---|---|
| Placa | Wemos D1 R32 (ESP32) |
| Sensores | 3 × SHT40 (temperatura e umidade, I2C, endereço `0x44`): **interno**, **externo** e **globo** |
| Atuadores | 2 relés: ventilador (fan) e bomba. Acionados em nível **baixo** (`LOW` liga, `HIGH` desliga) |

Os três SHT40 têm o mesmo endereço (`0x44`). Por isso **não há multiplexador (TCA9548A)**: cada sensor fica num barramento próprio. Dois usam os controladores I2C do ESP32 e o terceiro (globo) usa I2C por software.

## Ligação (pinagem)

| Função | Barramento | SDA | SCL |
|---|---|---|---|
| SHT40 **interno** → `interno.t`, `interno.ur` | I2C hardware 0 | GPIO 18 | GPIO 19 |
| SHT40 **externo** → `externo.t`, `externo.ur` | I2C hardware 1 | GPIO 25 | GPIO 26 |
| SHT40 **globo** → `globo.t`, `globo.ur` | I2C por software | GPIO 23 | GPIO 16 |

| Relé | GPIO |
|---|---|
| Ventilador (fan) | 27 |
| Bomba | 14 |

Alimente os SHT40 com 3,3 V e confira se os módulos têm resistores de pull-up nas linhas SDA/SCL (o firmware só habilita o pull-up interno do ESP32).

## Bibliotecas e versões

| Biblioteca | Para quê | Versão |
|---|---|---|
| Core **esp32** (Espressif), via Gerenciador de Placas | `WiFi`, `Wire`, FreeRTOS, `time.h` | 3.3.11 (instalada na máquina de documentação) |
| **MQTT** (Joel Gaehwiler, `arduino-mqtt`) | cliente MQTT (`MQTT.h`) | a registrar |
| **ArduinoJson** (Benoit Blanchon) | montar o JSON (`StaticJsonDocument`, API 6.x) | a registrar |
| **Adafruit SHT4x Library** | sensores interno e externo | a registrar |
| Adafruit BusIO | dependência da SHT4x | a registrar |
| Adafruit Unified Sensor | dependência da SHT4x | 1.1.15 (instalada na máquina de documentação) |

"A registrar": as versões usadas pelos alunos na compilação não foram anotadas, e essas bibliotecas não estavam instaladas na máquina onde isto foi documentado. Ao compilar, preencha a coluna com as versões do Gerenciador de Bibliotecas. O sketch usa `StaticJsonDocument`, da API 6.x do ArduinoJson; não foi testado com a 7.x.

## Segredos (`secrets.h`)

Rede Wi-Fi, senha MQTT e endereço do broker **não ficam no código**: ficam em `firmware/secrets.h`, que está no `.gitignore` e nunca deve ser commitado.

1. Copie `firmware/secrets_exemplo.h` para `firmware/secrets.h`.
2. Troque os valores:

| Definição | O que é |
|---|---|
| `WIFI_SSID`, `WIFI_PASS` | rede Wi-Fi do galpão (2,4 GHz) |
| `MQTT_BROKER` | IP ou domínio do Mosquitto na VPS |
| `MQTT_PASS` | senha do usuário MQTT deste ESP, criada com `scripts/criar_usuario_mqtt.sh <device_id> <senha>` |

O usuário MQTT e o `client id` são o `DEVICE_ID` (`const char* DEVICE_ID = "esp01"` no sketch). Cada ESP precisa de um `DEVICE_ID` diferente, cadastrado no painel (Dispositivos) e com usuário no Mosquitto.

## Compilar e gravar (Arduino IDE)

1. Instale o core **esp32** (Espressif) e as bibliotecas da tabela acima.
2. Placa: **WEMOS D1 R32** (`esp32:esp32:d1_uno32`). Porta: a COM do ESP32. Velocidade do monitor serial: **115200**.
3. Abra `firmware/firmware.ino` (a pasta e o arquivo têm o mesmo nome, como o Arduino IDE exige). O `secrets.h` precisa estar na mesma pasta. Também compila com `arduino-cli compile --fqbn esp32:esp32:d1_uno32 firmware`.
4. **Verificar** (compilar) e **Carregar** (gravar).
5. No Monitor Serial devem aparecer `[SHT40 INTERNO] OK`, `[SHT40 EXTERNO] OK`, `[MQTT] CONECTADO` e, a cada minuto, `[MQTT] DADOS ENVIADOS` com o JSON.

## Funcionamento

- Lê os sensores a cada **3 s** (`INTERVALO_LEITURA`) e envia ao servidor a cada **60 s** (`INTERVALO_ENVIO`); a primeira mensagem sai assim que o MQTT conecta.
- O controle dos relés roda numa tarefa separada, então uma falha de Wi-Fi ou MQTT não interrompe o controle local.
- O envio é cancelado se o sensor interno ou o globo estiverem inválidos, ou se a leitura tiver mais de 10 s.

### Controle local dos relés

Decidido no ESP, com a temperatura e a umidade **internas** (não usa o ITGU nem o servidor):

| Atuador | Liga | Desliga |
|---|---|---|
| Ventilador (fan) | temperatura interna ≥ 30,0 °C | temperatura interna ≤ 28,0 °C |
| Bomba | umidade interna < 60 % (pulso de 2 s, no mínimo 60 s entre pulsos) | umidade interna ≥ 65 % (fim da demanda) |

- Os dois nunca ficam ligados juntos; o ventilador tem prioridade, com pausa de 2 s na troca.
- Sem leitura interna válida (falha do sensor ou leitura com mais de 10 s), os dois relés desligam.
- Os limites ficam no começo do sketch (`TEMP_LIGAR_FAN`, `UMIDADE_LIGAR_BOMBA` etc.) e podem ser ajustados.

## Mensagem MQTT

- **Tópico:** `galpao/<device_id>/leituras` (ex.: `galpao/esp01/leituras`), QoS 1, sem retain.
- **Conexão:** porta 1883 (sem TLS), usuário e client id = `device_id`. O ACL do Mosquitto só deixa cada ESP publicar no próprio tópico.

```json
{
  "device_id": "esp01",
  "ts": 1795478400,
  "interno": { "t": 29.4, "ur": 68.2 },
  "globo": { "t": 30.1, "ur": 62.0 },
  "externo": { "t": 27.0, "ur": 70.5 },
  "rssi": -61,
  "atuadores": { "fan": false, "bomba": false, "automatico": true }
}
```

| Campo | Regra |
|---|---|
| `device_id` | obrigatório; igual ao do tópico |
| `ts` | opcional; segundos Unix (UTC), enviado só depois de sincronizar o relógio por NTP (`a.st1.ntp.br`, `pool.ntp.org`). É a hora do envio, não a da leitura (que pode ter até 10 s). Sem `ts`, o servidor usa a hora em que recebeu a mensagem |
| `interno.t`, `interno.ur` | obrigatórios |
| `globo.t` | obrigatório (o ITGU é calculado no servidor com a temperatura de globo); `globo.ur` é enviado, mas não é usado |
| `externo` | opcional; se existir, `externo.t` é obrigatório e `externo.ur` é opcional. Omitido se o sensor externo falhar |
| `rssi` | opcional (sinal Wi-Fi, dBm) |
| `atuadores` | estado dos relés; o servidor guarda, mas não valida |

O servidor (`ingestor/validacao.py`) rejeita temperatura fora de -10 a 70 °C e umidade interna fora de (0, 100]. O ponto de orvalho e o ITGU não vêm do ESP: são calculados no servidor.

## Melhorias futuras

Pontos encontrados na revisão do código. Nenhum foi alterado: o firmware é dos alunos e fica como está até que eles decidam.

1. **TLS no MQTT.** A conexão usa a porta 1883 sem criptografia, então o usuário e a senha MQTT trafegam em texto pela internet. Dá para usar a porta 8883 com TLS no Mosquitto e `WiFiClientSecure` no ESP.
2. **Watchdog.** Não há *watchdog*: se a tarefa de controle travar, os relés ficam no último estado (por exemplo, o ventilador ligado). Dá para registrar a tarefa no watchdog do ESP32 para reiniciar a placa, que sobe com os relés desligados.
3. **Reconexão do Wi-Fi.** O sketch chama `WiFi.begin` a cada 10 s e também liga o `setAutoReconnect(true)`. Os dois mecanismos juntos podem atrapalhar a reconexão. Basta deixar só um (por exemplo, `WiFi.reconnect()` a cada 10 s).
4. **Umidade interna igual a 0 %.** O ESP aceita 0 % como leitura válida, mas o servidor rejeita (`ingestor/validacao.py` exige umidade interna maior que 0). Deve-se alinhar os dois lados, e na prática 0 % indica falha do sensor.
5. **GPIO 14 (relé da bomba) na partida.** Em alguns ESP32 o GPIO 14 emite um pulso ao ligar, o que pode dar um clique na bomba. Se incomodar, dá para trocar o pino do relé ou usar um resistor de pull-up no módulo.
6. **Nome do sketch.** O arquivo `sketch_oct19a.ino` não batia com o nome da pasta `firmware/`, e o Arduino IDE e o `arduino-cli` exigem que batam. **Resolvido:** o arquivo foi renomeado para `firmware.ino`.
7. **Estado de conexão (LWT) e sessão persistente.** O MQTT não define *Last Will* nem sessão persistente. Sem o LWT, o painel só percebe que o ESP caiu pela falta de leituras; sem sessão persistente, o que for publicado durante uma queda se perde. Dá para publicar um estado `online`/`offline` com *retain* e usar sessão persistente (`cleanSession = false`).
