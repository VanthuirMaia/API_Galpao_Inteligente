// Formatação de datas, números e rótulos. A API manda UTC; aqui tudo vira hora de Recife, pt-BR.

const FUSO = "America/Recife";
const fmtDataHora = new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO, dateStyle: "short", timeStyle: "short" });
const fmtHora = new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO, hour: "2-digit", minute: "2-digit" });

/** Cria um elemento sem innerHTML: el("p", "classe", "texto"). Dados da API só entram como texto. */
export function el(tag, classe, texto) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texto !== undefined && texto !== null) e.textContent = texto;
  return e;
}

export function dataHora(iso) {
  return iso ? fmtDataHora.format(new Date(iso)) : "—";
}

export function hora(data = new Date()) {
  return fmtHora.format(data);
}

/** Número com vírgula decimal; "—" se não houver valor. */
export function numero(valor, casas = 1) {
  if (valor === null || valor === undefined) return "—";
  return new Intl.NumberFormat("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }).format(valor);
}

/** "há 3 min", "há 2 h 5 min", "há 4 dias". */
export function haQuanto(iso, agora = Date.now()) {
  const min = Math.floor((agora - new Date(iso).getTime()) / 60000);
  if (min < 1) return "há menos de 1 min";
  if (min < 60) return `há ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `há ${h} h ${min % 60} min`;
  const d = Math.floor(h / 24);
  return `há ${d} ${d === 1 ? "dia" : "dias"}`;
}

/** Classificação: texto sempre presente (a cor não pode ser a única informação). */
export const CLASSIFICACAO = {
  conforto: { css: "conforto", texto: "✔ Conforto" },
  alerta: { css: "alerta", texto: "⚠ Alerta" },
  critico: { css: "critico", texto: "✖ Crítico" },
  sem_faixa: { css: "sem_faixa", texto: "? Sem faixa definida" },
};

export function ambienteRotulo(ambiente) {
  return ambiente === "modelo" ? "galpão-modelo" : "galpão real";
}

export function diasRotulo(n) {
  return `${n} ${n === 1 ? "dia" : "dias"}`;
}

// ---------- datas para gráficos (eixo x em milissegundos) ----------
const fmtHoraMin = new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO, hour: "2-digit", minute: "2-digit" });
const fmtDiaHora = new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const fmtCompleta = new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO, dateStyle: "short", timeStyle: "medium" });
// "sv-SE" formata como 2026-10-01 13:05, que é o formato do <input type="datetime-local"> (com "T")
const fmtInputLocal = new Intl.DateTimeFormat("sv-SE", {
  timeZone: FUSO, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

export const horaMinuto = (ms) => fmtHoraMin.format(new Date(ms));
export const diaHora = (ms) => fmtDiaHora.format(new Date(ms));
export const dataHoraCompleta = (ms) => fmtCompleta.format(new Date(ms));

/** Date -> valor de <input type="datetime-local"> em horário de Recife. */
export function paraInputLocal(data) {
  return fmtInputLocal.format(data).replace(" ", "T");
}

/**
 * Valor de <input type="datetime-local"> (horário de Recife) -> Date.
 * Pernambuco não tem horário de verão, então o deslocamento é sempre -03:00.
 */
export function deInputLocal(texto) {
  const data = new Date(`${texto}:00-03:00`);
  return Number.isNaN(data.getTime()) ? null : data;
}

/** Mesma regra do servidor (app/classificacao.py), usada para estimar % de tempo nos gráficos. */
export function classificar(itgu, faixa) {
  if (!faixa) return "sem_faixa";
  if (itgu >= faixa.conforto_min && itgu <= faixa.conforto_max) return "conforto";
  if (itgu < faixa.critico_min || itgu > faixa.critico_max) return "critico";
  return "alerta";
}

// ---------- diagnóstico ----------

/** Sinal Wi-Fi a partir do RSSI (dBm): > -67 bom, -67 a -80 regular, < -80 fraco. */
export function sinalWifi(rssi) {
  if (rssi === null || rssi === undefined) return { css: "sem_faixa", texto: "não informado" };
  if (rssi > -67) return { css: "conforto", texto: "bom" };
  if (rssi >= -80) return { css: "alerta", texto: "regular" };
  return { css: "critico", texto: "fraco" };
}

// Motivos de rejeição do ingestor em linguagem simples. O código original continua visível na tela.
export const MOTIVOS = {
  json_invalido: "O texto enviado não é um JSON válido",
  topico_invalido: "Tópico MQTT fora do padrão galpao/<id>/leituras",
  device_divergente: "O device_id do JSON é diferente do tópico",
  device_desconhecido: "Dispositivo não cadastrado ou desativado",
  erro_calculo: "Erro no servidor ao processar",
  erro_interno: "Erro no servidor ao processar",
};

// Motivos com sufixo ":<campo>"
export const MOTIVOS_COM_CAMPO = {
  campo_ausente: (campo) => `Faltou o campo ${campo}`,
  valor_invalido: (campo) => `O campo ${campo} não é um número válido`,
  fora_da_faixa: (campo) => `O campo ${campo} está fora da faixa aceita`,
};

/** Traduz o código do motivo; se não conhecer, devolve o código como veio. */
export function motivoAmigavel(codigo) {
  if (MOTIVOS[codigo]) return MOTIVOS[codigo];
  const i = codigo.indexOf(":");
  if (i > 0) {
    const traduz = MOTIVOS_COM_CAMPO[codigo.slice(0, i)];
    if (traduz) return traduz(codigo.slice(i + 1));
  }
  return codigo;
}

/** Id do dispositivo a partir do tópico galpao/<id>/leituras; senão o próprio tópico. */
export function dispositivoDoTopico(topico) {
  const m = /^galpao\/([^/]+)\/leituras$/.exec(topico || "");
  return m ? m[1] : topico || "—";
}
