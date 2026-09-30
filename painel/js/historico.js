// Histórico: gráficos de ITGU, temperaturas e umidade, resumo e exportação CSV.
import { api, baixarArquivo } from "./api.js";
import {
  classificar, dataHoraCompleta, deInputLocal, diaHora, el, horaMinuto, numero, paraInputLocal,
} from "./formato.js";
import { montarLayout } from "./layout.js";
import { exigirLogin } from "./sessao.js";

exigirLogin();
montarLayout();

const CHAVE_DISPOSITIVO = "galpao_ultimo_dispositivo";
const HORA_MS = 3600 * 1000;
const PERIODOS_MS = { "6h": 6 * HORA_MS, "24h": 24 * HORA_MS, "7d": 7 * 24 * HORA_MS, "30d": 30 * 24 * HORA_MS };
const LIMITE_MS = 31 * 24 * HORA_MS; // a API aceita no máximo 31 dias
const LACUNA_FATOR = 3; // mais que 3x o intervalo esperado = lacuna

// agregação automática: até 24 h bruto, até 7 dias 15 min, acima disso 1 h
const AGREGACOES = {
  bruto: { rotulo: "dados brutos (1 leitura por minuto)", esperadoMs: 60 * 1000 },
  "15min": { rotulo: "médias de 15 min", esperadoMs: 15 * 60 * 1000 },
  "1h": { rotulo: "médias de 1 h", esperadoMs: HORA_MS },
  "5min": { rotulo: "médias de 5 min", esperadoMs: 5 * 60 * 1000 }, // só para o CSV agregado de períodos curtos
};

// cores consistentes entre os gráficos (interna = laranja, externa = azul, globo = roxo)
const COR = {
  itgu: "#1f2933", interna: "#e8590c", globo: "#862e9c", externa: "#1c7ed6",
  conforto: "#2f9e44", critico: "#c92a2a",
};

const principal = document.getElementById("principal");
const selectDispositivo = document.getElementById("dispositivo");
const botoesPeriodo = document.querySelectorAll("[data-periodo]");
const blocoPersonalizado = document.getElementById("personalizado");
const campoInicio = document.getElementById("inicio");
const campoFim = document.getElementById("fim");
const agregacaoEl = document.getElementById("agregacao");
const carregandoEl = document.getElementById("carregando");
const erroEl = document.getElementById("erro");
const vazioEl = document.getElementById("vazio");
const blocoDados = document.getElementById("conteudo-dados");
const resumoEl = document.getElementById("resumo");
const notaResumo = document.getElementById("nota-resumo");
const avisoFaixa = document.getElementById("aviso-faixa");
const botaoBruto = document.getElementById("csv-bruto");
const botaoAgregado = document.getElementById("csv-agregado");
const erroCsv = document.getElementById("erro-csv");

const graficos = {}; // id do canvas -> instância do Chart
let periodo = "24h";
let consulta = null; // {deviceId, inicio, fim, agregacao} da tela atual (usado pelo CSV)
let numeroPedido = 0; // descarta respostas de pedidos antigos (filtros trocados rápido)

// ---------- estado da tela ----------

function definirEstado(estado, mensagem = "") {
  principal.dataset.estado = estado;
  carregandoEl.hidden = estado !== "carregando";
  vazioEl.hidden = estado !== "vazio";
  erroEl.hidden = estado !== "erro";
  blocoDados.hidden = estado !== "ok";
  if (estado === "erro") erroEl.textContent = mensagem;
}

// ---------- filtros ----------

/** Período atual em ms: [inicio, fim] ou null se o personalizado for inválido. */
function intervalo() {
  if (periodo !== "custom") {
    const fim = Date.now();
    return { inicio: fim - PERIODOS_MS[periodo], fim };
  }
  const inicio = deInputLocal(campoInicio.value);
  const fim = deInputLocal(campoFim.value);
  if (!inicio || !fim) return { erro: "Informe o início e o fim do período." };
  if (fim <= inicio) return { erro: "O fim deve ser depois do início." };
  if (fim - inicio > LIMITE_MS) return { erro: "O período máximo é de 31 dias." };
  return { inicio: inicio.getTime(), fim: fim.getTime() };
}

function agregacaoPara(duracaoMs) {
  if (duracaoMs <= PERIODOS_MS["24h"]) return "bruto";
  if (duracaoMs <= PERIODOS_MS["7d"]) return "15min";
  return "1h";
}

function marcarPeriodo(novo) {
  periodo = novo;
  botoesPeriodo.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.periodo === novo)));
  blocoPersonalizado.hidden = novo !== "custom";
}

function lembrarDispositivo(id) {
  try {
    localStorage.setItem(CHAVE_DISPOSITIVO, id);
  } catch {
    // sem armazenamento: só não lembra
  }
}

function dispositivoLembrado() {
  try {
    return localStorage.getItem(CHAVE_DISPOSITIVO);
  } catch {
    return null;
  }
}

// ---------- dados: lacunas, resumo ----------

/**
 * Linhas do gráfico em ordem de tempo, com um marcador {lacuna: true} entre duas leituras
 * separadas por mais de 3x o intervalo esperado (a linha quebra em vez de ligar os pontos).
 */
function comLacunas(itens, esperadoMs) {
  const linhas = [];
  let anterior = null;
  for (const item of itens) {
    const x = Date.parse(item.ts || item.janela);
    if (anterior !== null && x - anterior > LACUNA_FATOR * esperadoMs) {
      linhas.push({ x: anterior + esperadoMs, lacuna: true });
    }
    linhas.push({ x, dado: item });
    anterior = x;
  }
  return linhas;
}

/** Maior tempo sem dados, em minutos (intervalo entre pontos menos o intervalo esperado). */
function maiorLacunaMin(itens, esperadoMs) {
  let maior = 0;
  for (let i = 1; i < itens.length; i++) {
    const dt = Date.parse(itens[i].ts || itens[i].janela) - Date.parse(itens[i - 1].ts || itens[i - 1].janela);
    maior = Math.max(maior, dt - esperadoMs);
  }
  return Math.round(maior / 60000);
}

/** ITGU mínimo, médio e máximo, e contagem de leituras (no agregado, a média é ponderada por n). */
function estatisticas(itens, agregado) {
  let n = 0;
  let soma = 0;
  let min = Infinity;
  let max = -Infinity;
  for (const i of itens) {
    const peso = agregado ? i.n : 1;
    n += peso;
    soma += i.itgu * peso;
    min = Math.min(min, agregado ? i.itgu_min : i.itgu);
    max = Math.max(max, agregado ? i.itgu_max : i.itgu);
  }
  return { n, media: soma / n, min, max };
}

/** % do tempo em cada classe, sobre os pontos do gráfico, com a faixa vigente hoje. */
function percentuais(itens, agregado, faixa) {
  const total = { conforto: 0, alerta: 0, critico: 0 };
  let soma = 0;
  for (const i of itens) {
    const peso = agregado ? i.n : 1;
    total[classificar(i.itgu, faixa)] += peso;
    soma += peso;
  }
  return Object.fromEntries(Object.entries(total).map(([k, v]) => [k, (100 * v) / soma]));
}

function itemResumo(rotulo, valor, classe = "") {
  const caixa = el("div", `resumo-item ${classe}`.trim());
  caixa.append(el("div", "rotulo", rotulo), el("div", "valor", valor));
  return caixa;
}

function montarResumo(itens, agregado, faixa, esperadoMs) {
  const est = estatisticas(itens, agregado);
  const lacuna = maiorLacunaMin(itens, esperadoMs);
  const cartoes = [
    itemResumo("ITGU mínimo", numero(est.min, 1)),
    itemResumo("ITGU médio", numero(est.media, 1)),
    itemResumo("ITGU máximo", numero(est.max, 1)),
    itemResumo("Leituras", new Intl.NumberFormat("pt-BR").format(est.n)),
    itemResumo("Maior lacuna sem dados", lacuna > 0 ? `${lacuna} min` : "nenhuma"),
  ];
  if (faixa) {
    const p = percentuais(itens, agregado, faixa);
    cartoes.push(
      itemResumo("% do tempo em conforto", `${numero(p.conforto, 0)}%`, "conforto"),
      itemResumo("% do tempo em alerta", `${numero(p.alerta, 0)}%`, "alerta"),
      itemResumo("% do tempo em crítico", `${numero(p.critico, 0)}%`, "critico"),
    );
    notaResumo.textContent =
      `Percentuais estimados no navegador sobre os pontos do gráfico, usando a faixa vigente hoje (${faixa.nome}).`;
  } else {
    notaResumo.textContent = "Sem faixa definida: não há percentuais de conforto para este dispositivo.";
  }
  resumoEl.replaceChildren(...cartoes);
}

// ---------- gráficos ----------

function opcoesBase(unidade, rotuloY, inicio, fim, duracaoMs) {
  const rotuloTick = duracaoMs <= PERIODOS_MS["24h"] ? horaMinuto : diaHora;
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { mode: "nearest", axis: "x", intersect: false },
    scales: {
      x: {
        type: "linear", min: inicio, max: fim,
        ticks: { maxTicksLimit: 6, maxRotation: 0, callback: (v) => rotuloTick(v) },
      },
      y: { title: { display: true, text: rotuloY } },
    },
    plugins: {
      legend: {
        display: true,
        labels: { filter: (item, dados) => !dados.datasets[item.datasetIndex].ocultarNaLegenda },
      },
      tooltip: {
        filter: (item) => !item.dataset.ocultarNoTooltip,
        callbacks: {
          title: (itens) => dataHoraCompleta(itens[0].parsed.x),
          label: (item) => `${item.dataset.label}: ${numero(item.parsed.y, 1)} ${unidade}`,
        },
      },
    },
  };
}

/** Série de um campo, com y null nas lacunas para a linha quebrar. */
function serie(linhas, campo, rotulo, cor, agregado) {
  return {
    label: rotulo,
    data: linhas.map((l) => ({ x: l.x, y: l.lacuna ? null : l.dado[campo] ?? null })),
    borderColor: cor,
    backgroundColor: cor,
    borderWidth: 2,
    pointRadius: agregado ? 1 : 0,
    pointHoverRadius: 4,
    spanGaps: false,
  };
}

function desenhar(id, datasets, opcoes) {
  if (graficos[id]) graficos[id].destroy(); // evita vazar memória a cada troca de filtro
  graficos[id] = new Chart(document.getElementById(id), { type: "line", data: { datasets }, options: opcoes });
}

/** Datasets extras da faixa de conforto: área verde e linhas críticas tracejadas (sem plugin). */
function datasetsFaixa(faixa, inicio, fim) {
  const reta = (y) => [{ x: inicio, y }, { x: fim, y }];
  const auxiliar = { pointRadius: 0, pointHoverRadius: 0, spanGaps: false, ocultarNoTooltip: true };
  return [
    { ...auxiliar, label: "conforto mínimo", data: reta(faixa.conforto_min), borderWidth: 0, ocultarNaLegenda: true },
    {
      ...auxiliar, label: `Conforto: faixa vigente hoje (${faixa.nome})`, data: reta(faixa.conforto_max),
      borderColor: "rgba(47, 158, 68, 0.6)", borderWidth: 1, backgroundColor: "rgba(47, 158, 68, 0.18)", fill: "-1",
    },
    {
      ...auxiliar, label: `Limites críticos (${numero(faixa.critico_min, 1)} e ${numero(faixa.critico_max, 1)})`,
      data: reta(faixa.critico_min), borderColor: COR.critico, borderDash: [6, 4], borderWidth: 1.5,
    },
    { ...auxiliar, label: "limite crítico superior", data: reta(faixa.critico_max), borderColor: COR.critico, borderDash: [6, 4], borderWidth: 1.5, ocultarNaLegenda: true },
  ];
}

function desenharGraficos(linhas, agregado, faixa, inicio, fim) {
  const duracao = fim - inicio;
  const itgu = serie(linhas, "itgu", agregado ? "ITGU (média)" : "ITGU", COR.itgu, agregado);
  itgu.borderWidth = 2.5;
  const dsItgu = faixa ? [itgu, ...datasetsFaixa(faixa, inicio, fim)] : [itgu];
  desenhar("grafico-itgu", dsItgu, opcoesBase("", "ITGU", inicio, fim, duracao));

  desenhar("grafico-temp", [
    serie(linhas, "t_int", "Temperatura interna", COR.interna, agregado),
    serie(linhas, "t_globo", "Temperatura de globo", COR.globo, agregado),
    serie(linhas, "t_ext", "Temperatura externa", COR.externa, agregado),
  ], opcoesBase("°C", "°C", inicio, fim, duracao));

  desenhar("grafico-ur", [
    serie(linhas, "ur_int", "Umidade interna", COR.interna, agregado),
    serie(linhas, "ur_ext", "Umidade externa", COR.externa, agregado),
  ], opcoesBase("%", "% de umidade relativa", inicio, fim, duracao));
}

// ---------- carga ----------

function consultaDe(deviceId, inicio, fim, agregacao) {
  const p = new URLSearchParams({
    device_id: deviceId,
    inicio: new Date(inicio).toISOString(),
    fim: new Date(fim).toISOString(),
    agregacao,
  });
  return p.toString();
}

async function carregar() {
  const meu = ++numeroPedido;
  const janela = intervalo();
  if (janela.erro) {
    definirEstado("erro", janela.erro);
    return;
  }
  const deviceId = selectDispositivo.value;
  if (!deviceId) return;

  const { inicio, fim } = janela;
  const agregacao = agregacaoPara(fim - inicio);
  const info = AGREGACOES[agregacao];
  agregacaoEl.textContent = `Mostrando ${info.rotulo}.`;
  definirEstado("carregando");
  try {
    const [dados, ultima] = await Promise.all([
      api("GET", `/leituras?${consultaDe(deviceId, inicio, fim, agregacao)}${agregacao === "bruto" ? "&limite=20000" : ""}`),
      api("GET", `/dispositivos/${encodeURIComponent(deviceId)}/ultima`),
    ]);
    if (meu !== numeroPedido) return; // o usuário já mudou o filtro

    consulta = { deviceId, inicio, fim, agregacao };
    if (dados.itens.length === 0) {
      Object.values(graficos).forEach((g) => g.destroy());
      Object.keys(graficos).forEach((k) => delete graficos[k]);
      definirEstado("vazio");
      return;
    }

    const faixa = ultima.situacao.faixa;
    const agregado = agregacao !== "bruto";
    const linhas = comLacunas(dados.itens, info.esperadoMs);
    definirEstado("ok"); // o bloco precisa estar visível antes de desenhar
    montarResumo(dados.itens, agregado, faixa, info.esperadoMs);
    avisoFaixa.hidden = Boolean(faixa);
    desenharGraficos(linhas, agregado, faixa, inicio, fim);
    botaoAgregado.textContent = `Dados agregados (${agregado ? info.rotulo : AGREGACOES["5min"].rotulo})`;
  } catch (e) {
    if (meu !== numeroPedido) return;
    definirEstado("erro", e instanceof TypeError ? "Sem conexão com o servidor." : e.message);
  }
}

// ---------- exportação CSV ----------

async function exportar(agregacao, botao) {
  erroCsv.hidden = true;
  if (!consulta) return;
  botao.disabled = true;
  try {
    const { blob, nome } = await baixarArquivo(
      `/leituras/csv?${consultaDe(consulta.deviceId, consulta.inicio, consulta.fim, agregacao)}`,
    );
    const url = URL.createObjectURL(blob);
    const link = el("a");
    link.href = url;
    link.download = nome; // nome vindo do Content-Disposition
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  } catch (e) {
    erroCsv.textContent = e.message;
    erroCsv.hidden = false;
  } finally {
    botao.disabled = false;
  }
}

// ---------- inicialização ----------

async function iniciar() {
  try {
    const dispositivos = (await api("GET", "/dispositivos")).filter((d) => d.ativo);
    if (dispositivos.length === 0) {
      definirEstado("erro", "Nenhum dispositivo ativo.");
      return;
    }
    const opcoes = dispositivos.map((d) => {
      const o = el("option", null, `${d.descricao || d.id} (${d.id})`);
      o.value = d.id;
      return o;
    });
    selectDispositivo.replaceChildren(...opcoes);
    const lembrado = dispositivoLembrado();
    if (lembrado && dispositivos.some((d) => d.id === lembrado)) selectDispositivo.value = lembrado;
  } catch (e) {
    definirEstado("erro", e instanceof TypeError ? "Sem conexão com o servidor." : e.message);
    return;
  }

  const agora = new Date();
  campoFim.value = paraInputLocal(agora);
  campoInicio.value = paraInputLocal(new Date(agora.getTime() - PERIODOS_MS["24h"]));

  selectDispositivo.addEventListener("change", () => {
    lembrarDispositivo(selectDispositivo.value);
    carregar();
  });
  botoesPeriodo.forEach((b) =>
    b.addEventListener("click", () => {
      marcarPeriodo(b.dataset.periodo);
      if (b.dataset.periodo !== "custom") carregar(); // o personalizado espera o "Aplicar"
    }),
  );
  document.getElementById("aplicar").addEventListener("click", carregar);
  botaoBruto.addEventListener("click", () => exportar("bruto", botaoBruto));
  botaoAgregado.addEventListener("click", () => exportar(consulta && consulta.agregacao !== "bruto" ? consulta.agregacao : "5min", botaoAgregado));

  carregar();
}

iniciar();
