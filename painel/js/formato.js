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
