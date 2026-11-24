#include <WiFi.h>
#include <Wire.h>
#include <MQTT.h>
#include <ArduinoJson.h>
#include <Adafruit_SHT4x.h>
#include <time.h>
#include <math.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include "secrets.h"

// Projeto Galpão Inteligente - Wemos D1 R32
// Axl Henrique, Vitor Duan, Taylon Ramon e Maysa Siqueira

// Configurações do servidor que recebe as leituras do galpão.
const char* DEVICE_ID = "esp01";
const char* BROKER = MQTT_BROKER;  // definido em secrets.h
const int PORTA_MQTT = 1883;
char TOPICO[40];
WiFiClient rede;
MQTTClient mqtt(1024);

// Cada SHT40 usa seu próprio barramento, pois os três têm o mesmo endereço.
#define SDA_1 18
#define SCL_1 19
#define SDA_2 25
#define SCL_2 26
#define SDA_3 23
#define SCL_3 16
#define ENDERECO_SHT40 0x44
#define RELE_FAN 27
#define RELE_BOMBA 14

// Os seletores dos relés estão em L: LOW liga e HIGH desliga.
const uint8_t RELE_LIGADO = LOW;
const uint8_t RELE_DESLIGADO = HIGH;

// Podemos ajustar estes limites conforme as necessidades do galpão.
// Usamos dois limites para evitar que os relés fiquem oscilando.
const float TEMP_LIGAR_FAN = 30.0;
const float TEMP_DESLIGAR_FAN = 28.0;
const float UMIDADE_LIGAR_BOMBA = 60.0;
const float UMIDADE_PARAR_BOMBA = 65.0;
const unsigned long INTERVALO_LEITURA = 3000UL;
const unsigned long INTERVALO_ENVIO = 60000UL;
const unsigned long TEMPO_BOMBA = 2000UL;
const unsigned long INTERVALO_BOMBA = 60000UL;
const unsigned long PAUSA_FAN_BOMBA = 2000UL;
const unsigned long PAUSA_BOMBA_FAN = 2000UL;
const unsigned long INTERVALO_WIFI = 10000UL;
const unsigned long INTERVALO_MQTT = 5000UL;
const unsigned long LIMITE_LEITURA = 10000UL;

TwoWire I2C_1(0), I2C_2(1);
Adafruit_SHT4x sht40_1, sht40_2;
bool sht1OK = false, sht2OK = false;

// A fila permite enviar uma cópia das leituras para a tarefa de comunicação.
// Assim, uma falha de internet não precisa interromper o controle local.
struct DadosGalpao {
  float tInterna, urInterna, tExterna, urExterna, tGlobo, urGlobo;
  bool internaOK, externaOK, globoOK;
  bool fanLigada, bombaLigada, automatico;
  unsigned long instanteLeitura;
};
DadosGalpao dados = {};
QueueHandle_t filaDados = nullptr;
bool demandaFan = false, demandaBomba = false;
bool bombaJaAcionada = false;
unsigned long inicioBomba = 0, ultimoInicioBomba = 0;
unsigned long ultimaFanDesligada = 0, ultimaBombaDesligada = 0;
unsigned long ultimaLeituraValida = 0;
unsigned long ultimaPublicacao = 0, ultimaTentativaWiFi = 0;
unsigned long ultimaTentativaMQTT = 0;
bool primeiraPublicacao = true;

bool temperaturaValida(float t) { return isfinite(t) && t >= -10 && t <= 70; }
bool umidadeValida(float ur) { return isfinite(ur) && ur >= 0 && ur <= 100; }

void desligarFan() {
  digitalWrite(RELE_FAN, RELE_DESLIGADO);
  if (dados.fanLigada) {
    dados.fanLigada = false;
    ultimaFanDesligada = millis();
    Serial.println("[FAN] DESLIGADA");
  }
}
void desligarBomba() {
  digitalWrite(RELE_BOMBA, RELE_DESLIGADO);
  if (dados.bombaLigada) {
    dados.bombaLigada = false;
    ultimaBombaDesligada = millis();
    Serial.println("[BOMBA] PULSO FINALIZADO");
  }
}
void desligarTudo() { desligarFan(); desligarBomba(); }
void ligarFan() {
  if (dados.fanLigada || dados.bombaLigada) return;
  digitalWrite(RELE_BOMBA, RELE_DESLIGADO);
  digitalWrite(RELE_FAN, RELE_LIGADO);
  dados.fanLigada = true;
  Serial.println("[FAN] LIGADA");
}
void ligarBomba() {
  if (dados.bombaLigada || dados.fanLigada) return;
  Serial.println("[BOMBA] INICIANDO PULSO");
  digitalWrite(RELE_FAN, RELE_DESLIGADO);
  digitalWrite(RELE_BOMBA, RELE_LIGADO);
  dados.bombaLigada = true;
  bombaJaAcionada = true;
  inicioBomba = ultimoInicioBomba = millis();
}

// O ESP32 tem dois controladores I2C. Para o terceiro sensor, usamos I2C por software.
void softSDA(bool alto) {
  if (alto) pinMode(SDA_3, INPUT_PULLUP);
  else { digitalWrite(SDA_3, LOW); pinMode(SDA_3, OUTPUT); }
}
void softSCL(bool alto) {
  if (alto) pinMode(SCL_3, INPUT_PULLUP);
  else { digitalWrite(SCL_3, LOW); pinMode(SCL_3, OUTPUT); }
}
void softDelay() { delayMicroseconds(5); }
void softStart() {
  softSDA(true); softSCL(true); softDelay();
  softSDA(false); softDelay(); softSCL(false);
}
void softStop() {
  softSDA(false); softSCL(true); softDelay(); softSDA(true); softDelay();
}
bool softWrite(uint8_t valor) {
  for (int i = 7; i >= 0; i--) {
    softSDA((valor >> i) & 1); softDelay();
    softSCL(true); softDelay(); softSCL(false);
  }
  softSDA(true); softDelay(); softSCL(true); softDelay();
  bool ack = digitalRead(SDA_3) == LOW;
  softSCL(false); return ack;
}
uint8_t softRead(bool enviarACK) {
  uint8_t valor = 0;
  softSDA(true);
  for (int i = 7; i >= 0; i--) {
    softSCL(true); softDelay();
    if (digitalRead(SDA_3)) valor |= (1 << i);
    softSCL(false); softDelay();
  }
  softSDA(!enviarACK); softDelay(); softSCL(true); softDelay();
  softSCL(false); softSDA(true); return valor;
}

// O CRC ajuda a identificar dados corrompidos durante a leitura do globo.
uint8_t calcularCRC(const uint8_t* bytes) {
  uint8_t crc = 0xFF;
  for (int i = 0; i < 2; i++) {
    crc ^= bytes[i];
    for (int b = 0; b < 8; b++)
      crc = (crc & 0x80) ? (crc << 1) ^ 0x31 : crc << 1;
  }
  return crc;
}
bool lerGlobo(float &t, float &ur) {
  uint8_t bytes[6];
  softStart();
  if (!softWrite(ENDERECO_SHT40 << 1) || !softWrite(0xFD)) {
    softStop(); return false;
  }
  softStop(); delay(10); softStart();
  if (!softWrite((ENDERECO_SHT40 << 1) | 1)) { softStop(); return false; }
  for (int i = 0; i < 6; i++) bytes[i] = softRead(i < 5);
  softStop();
  if (calcularCRC(bytes) != bytes[2] || calcularCRC(bytes + 3) != bytes[5]) return false;
  uint16_t rawT = ((uint16_t)bytes[0] << 8) | bytes[1];
  uint16_t rawUR = ((uint16_t)bytes[3] << 8) | bytes[4];
  t = -45.0f + 175.0f * rawT / 65535.0f;
  ur = -6.0f + 125.0f * rawUR / 65535.0f;
  if (ur < 0) ur = 0;
  if (ur > 100) ur = 100;
  return temperaturaValida(t) && umidadeValida(ur);
}

bool iniciarSHT(Adafruit_SHT4x &sensor, TwoWire &bus) {
  if (!sensor.begin(&bus)) return false;
  sensor.setPrecision(SHT4X_HIGH_PRECISION);
  sensor.setHeater(SHT4X_NO_HEATER);
  return true;
}
void iniciarSensores() {
  I2C_1.begin(SDA_1, SCL_1, 100000);
  I2C_2.begin(SDA_2, SCL_2, 100000);
  I2C_1.setTimeOut(50); I2C_2.setTimeOut(50);
  sht1OK = iniciarSHT(sht40_1, I2C_1);
  sht2OK = iniciarSHT(sht40_2, I2C_2);
  Serial.println(sht1OK ? "[SHT40 INTERNO] OK" : "[SHT40 INTERNO] FALHA");
  Serial.println(sht2OK ? "[SHT40 EXTERNO] OK" : "[SHT40 EXTERNO] FALHA");
  pinMode(SDA_3, INPUT_PULLUP); pinMode(SCL_3, INPUT_PULLUP);
}

// Se um sensor perder a comunicação, tentamos inicializá-lo novamente na próxima leitura.
bool lerSHT(Adafruit_SHT4x &sensor, TwoWire &bus, bool &ok, float &t, float &ur) {
  t = ur = NAN;
  if (!ok) ok = iniciarSHT(sensor, bus);
  if (!ok) return false;
  sensors_event_t u = {}, temp = {};
  if (!sensor.getEvent(&u, &temp)) { ok = false; return false; }
  t = temp.temperature; ur = u.relative_humidity;
  return true;
}
void lerSensores() {
  dados.internaOK = lerSHT(sht40_1, I2C_1, sht1OK, dados.tInterna, dados.urInterna)
      && temperaturaValida(dados.tInterna) && umidadeValida(dados.urInterna);
  // O sensor interno é a referência dos motores. Sem ele, paramos o controle.
  if (dados.internaOK) ultimaLeituraValida = millis();
  else desligarTudo();
  dados.externaOK = lerSHT(sht40_2, I2C_2, sht2OK, dados.tExterna, dados.urExterna)
      && temperaturaValida(dados.tExterna);
  dados.tGlobo = dados.urGlobo = NAN;
  dados.globoOK = lerGlobo(dados.tGlobo, dados.urGlobo);
  dados.instanteLeitura = millis();
}
void atualizarDemandas() {
  if (!dados.internaOK) { demandaFan = demandaBomba = false; return; }
  if (dados.tInterna >= TEMP_LIGAR_FAN) demandaFan = true;
  else if (dados.tInterna <= TEMP_DESLIGAR_FAN) demandaFan = false;
  if (dados.urInterna < UMIDADE_LIGAR_BOMBA) demandaBomba = true;
  else if (dados.urInterna >= UMIDADE_PARAR_BOMBA) demandaBomba = false;
}

// A fan tem prioridade. Nunca acionamos os dois motores ao mesmo tempo.
void controlarAmbiente() {
  unsigned long agora = millis();
  if (!dados.automatico || !dados.internaOK || agora - ultimaLeituraValida >= LIMITE_LEITURA) {
    desligarTudo(); return;
  }
  if (dados.bombaLigada && agora - inicioBomba >= TEMPO_BOMBA) desligarBomba();
  if (demandaFan) {
    desligarBomba();
    if (millis() - ultimaBombaDesligada >= PAUSA_BOMBA_FAN) ligarFan();
    return;
  }
  desligarFan();
  if (!demandaBomba) { desligarBomba(); return; }
  // Esperamos a fan parar e damos tempo para a umidade se estabilizar entre pulsos.
  if (millis() - ultimaFanDesligada < PAUSA_FAN_BOMBA) return;
  if (bombaJaAcionada && millis() - ultimoInicioBomba < INTERVALO_BOMBA) return;
  if (!dados.bombaLigada) ligarBomba();
}
void mostrarRelatorio() {
  Serial.println("\n========== GALPAO INTELIGENTE ==========");
  if (dados.internaOK) Serial.printf("INTERNO: %.2f C | %.2f %%\n", dados.tInterna, dados.urInterna);
  else Serial.println("INTERNO: FALHA");
  if (dados.externaOK) Serial.printf("EXTERNO: %.2f C | %.2f %%\n", dados.tExterna, dados.urExterna);
  else Serial.println("EXTERNO: FALHA");
  if (dados.globoOK) Serial.printf("GLOBO: %.2f C | %.2f %%\n", dados.tGlobo, dados.urGlobo);
  else Serial.println("GLOBO: FALHA");
  Serial.printf("FAN: %s | BOMBA: %s\n", dados.fanLigada ? "LIGADA" : "DESLIGADA", dados.bombaLigada ? "LIGADA" : "DESLIGADA");
  if (!dados.internaOK) Serial.println("[CONTROLE] BLOQUEADO: FALHA NO SENSOR");
  else if (demandaFan && demandaBomba) Serial.println("[CONTROLE] PRIORIDADE PARA VENTILACAO");
  else if (demandaFan) Serial.println("[CONTROLE] TEMPERATURA ELEVADA");
  else if (demandaBomba) Serial.println("[CONTROLE] UMIDADE BAIXA");
  else Serial.println("[CONTROLE] CONDICOES ADEQUADAS");
}

// Esta tarefa cuida dos sensores e dos motores, sem esperar a conexão MQTT.
void tarefaControle(void* parametro) {
  iniciarSensores(); lerSensores(); atualizarDemandas();
  ultimaFanDesligada = ultimaBombaDesligada = millis();
  xQueueOverwrite(filaDados, &dados);
  Serial.println("[SISTEMA] CONTROLE AUTOMATICO ATIVADO");
  for (;;) {
    controlarAmbiente();
    // Evitamos iniciar uma leitura enquanto a bomba está ligada.
    if (!dados.bombaLigada && millis() - dados.instanteLeitura >= INTERVALO_LEITURA) {
      lerSensores(); atualizarDemandas(); mostrarRelatorio(); controlarAmbiente();
    }
    xQueueOverwrite(filaDados, &dados);
    vTaskDelay(pdMS_TO_TICKS(10));
  }
}
void verificarWiFi() {
  if (WiFi.status() == WL_CONNECTED || millis() - ultimaTentativaWiFi < INTERVALO_WIFI) return;
  ultimaTentativaWiFi = millis();
  Serial.println("[WI-FI] RECONECTANDO...");
  WiFi.begin(WIFI_SSID, WIFI_PASS);
}
void verificarMQTT() {
  if (WiFi.status() != WL_CONNECTED || mqtt.connected() || millis() - ultimaTentativaMQTT < INTERVALO_MQTT) return;
  ultimaTentativaMQTT = millis();
  if (mqtt.connect(DEVICE_ID, DEVICE_ID, MQTT_PASS)) Serial.println("[MQTT] CONECTADO");
  else Serial.printf("[MQTT] FALHA: %d / %d\n", (int)mqtt.lastError(), (int)mqtt.returnCode());
}

// Mantemos o formato JSON e o tópico usados pelo site do galpão.
bool publicarDados() {
  if (WiFi.status() != WL_CONNECTED || !mqtt.connected()) return false;
  DadosGalpao copia;
  if (xQueuePeek(filaDados, &copia, 0) != pdTRUE) return false;
  if (!copia.internaOK || !copia.globoOK || millis() - copia.instanteLeitura >= LIMITE_LEITURA) {
    Serial.println("[MQTT] ENVIO CANCELADO: DADOS INVALIDOS"); return false;
  }
  StaticJsonDocument<768> doc;
  doc["device_id"] = DEVICE_ID;
  if (time(nullptr) > 1700000000) doc["ts"] = (uint32_t)time(nullptr);
  doc["interno"]["t"] = copia.tInterna;
  doc["interno"]["ur"] = copia.urInterna;
  doc["globo"]["t"] = copia.tGlobo;
  doc["globo"]["ur"] = copia.urGlobo;
  if (copia.externaOK) {
    doc["externo"]["t"] = copia.tExterna;
    if (umidadeValida(copia.urExterna)) doc["externo"]["ur"] = copia.urExterna;
  }
  doc["rssi"] = WiFi.RSSI();
  doc["atuadores"]["fan"] = copia.fanLigada;
  doc["atuadores"]["bomba"] = copia.bombaLigada;
  doc["atuadores"]["automatico"] = copia.automatico;
  char buffer[768];
  if (doc.overflowed() || measureJson(doc) >= sizeof(buffer)) return false;
  serializeJson(doc, buffer, sizeof(buffer));
  if (!mqtt.publish(TOPICO, buffer, false, 1)) { Serial.println("[MQTT] FALHA NO ENVIO"); return false; }
  Serial.println("[MQTT] DADOS ENVIADOS"); Serial.println(buffer); return true;
}
void setup() {
  // Começamos com os relés desligados e só liberamos o controle após ler os sensores.
  digitalWrite(RELE_FAN, RELE_DESLIGADO); digitalWrite(RELE_BOMBA, RELE_DESLIGADO);
  pinMode(RELE_FAN, OUTPUT); pinMode(RELE_BOMBA, OUTPUT);
  desligarTudo(); Serial.begin(115200); delay(1000);
  dados.automatico = true;
  snprintf(TOPICO, sizeof(TOPICO), "galpao/%s/leituras", DEVICE_ID);
  filaDados = xQueueCreate(1, sizeof(DadosGalpao));
  if (!filaDados) { Serial.println("[ERRO] FILA"); desligarTudo(); while (true) delay(1000); }
  if (xTaskCreatePinnedToCore(tarefaControle, "ControleAmbiental", 8192, nullptr, 2, nullptr, 1) != pdPASS) {
    Serial.println("[ERRO] TAREFA"); desligarTudo(); while (true) delay(1000);
  }
  WiFi.mode(WIFI_STA); WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS); ultimaTentativaWiFi = millis();
  mqtt.begin(BROKER, PORTA_MQTT, rede); mqtt.setTimeout(1000);
  configTime(0, 0, "a.st1.ntp.br", "pool.ntp.org");
  ultimaPublicacao = millis();
}
void loop() {
  // A comunicação fica aqui. O controle ambiental roda na tarefa separada.
  verificarWiFi(); verificarMQTT();
  if (mqtt.connected()) {
    mqtt.loop();
    static unsigned long ultimaTentativaEnvio = 0;
    unsigned long agora = millis();
    if ((primeiraPublicacao || agora - ultimaPublicacao >= INTERVALO_ENVIO) && agora - ultimaTentativaEnvio >= 3000UL) {
      ultimaTentativaEnvio = agora;
      if (publicarDados()) { primeiraPublicacao = false; ultimaPublicacao = millis(); }
    }
  }
  delay(10);
}