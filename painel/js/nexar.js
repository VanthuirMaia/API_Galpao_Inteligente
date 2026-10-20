// Painel Nexar (index.html): início, galpão, histórico, alertas e configurações numa página só.
// As outras telas (diagnóstico, conta, administração) continuam em páginas próprias.
import { api, login } from "./api.js";
import { ambienteRotulo, dataCurta, diasRotulo, el, haQuanto, hojeRecifeISO, hora, horaMinuto, numero } from "./formato.js";
import { lerSessao, limparSessao, salvarSessao, sair } from "./sessao.js";

const INTERVALO_MS = 60000;
const NS = "http://www.w3.org/2000/svg";

// Referências de umidade relativa do ar (%). Ajustáveis: a API só classifica o ITGU.
const UR_BOA = [50, 70];
const UR_LIMITE = [40, 80];

const $ = (id) => document.getElementById(id);

// ---------- preferências da tela (tema e tamanho das letras) ----------
const PREF_TEMA = "nexar_tema";
const PREF_ESCALA = "nexar_escala";
const ESCALAS = [0.9, 1, 1.15, 1.3, 1.5];

function lerPref(chave) {
  try {
    return localStorage.getItem(chave);
  } catch {
    return null;
  }
}
function gravarPref(chave, valor) {
  try {
    localStorage.setItem(chave, valor);
  } catch {
    // armazenamento bloqueado: vale só até recarregar
  }
}

let escala = 1;

function aplicarTema(escuro) {
  document.body.classList.toggle("dark", escuro);
  const botao = $("theme-toggle");
  botao.setAttribute("aria-pressed", String(escuro));
  botao.setAttribute("aria-label", escuro ? "Ativar tema claro" : "Ativar tema escuro");
  $("theme-label").textContent = escuro ? "Tema claro" : "Tema escuro";
  document.querySelector('meta[name="color-scheme"]').content = escuro ? "dark" : "light";
}

function definirTema(escuro) {
  aplicarTema(escuro);
  gravarPref(PREF_TEMA, escuro ? "escuro" : "claro");
}

function aplicarEscala(valor) {
  escala = valor;
  document.documentElement.style.setProperty("--base-scale", String(valor));
}

function mudarEscala(passo) {
  const i = Math.max(0, Math.min(ESCALAS.length - 1, ESCALAS.indexOf(escala) + passo));
  aplicarEscala(ESCALAS[i]);
  gravarPref(PREF_ESCALA, String(ESCALAS[i]));
}

function iniciarPreferencias() {
  const tema = lerPref(PREF_TEMA);
  aplicarTema(tema ? tema === "escuro" : true); // padrão: tema escuro
  const salva = Number(lerPref(PREF_ESCALA));
  if (ESCALAS.includes(salva)) aplicarEscala(salva);

  $("theme-toggle").addEventListener("click", () => definirTema(!document.body.classList.contains("dark")));
  $("theme-light").addEventListener("click", () => definirTema(false));
  $("theme-dark").addEventListener("click", () => definirTema(true));
  $("font-up").addEventListener("click", () => mudarEscala(1));
  $("font-down").addEventListener("click", () => mudarEscala(-1));
  $("font-reset").addEventListener("click", () => {
    aplicarEscala(1);
    gravarPref(PREF_ESCALA, "1");
  });
}

// ---------- navegação entre as "páginas" ----------
const PAGINAS = {
  home: { titulo: "Monitoramento do galpão", sub: null },
  barn: { titulo: "Ver galpão", sub: "Uma visão geral de como o galpão está agora." },
  history: { titulo: "Histórico", sub: "Como o galpão se comportou no último dia." },
  alerts: { titulo: "Alertas", sub: "O que precisa de atenção." },
  settings: { titulo: "Configurações", sub: "Deixe a tela do seu jeito." },
};
let paginaAtual = "home";

function irPara(nome, { foco = true } = {}) {
  if (!PAGINAS[nome]) nome = "home";
  paginaAtual = nome;
  for (const id of Object.keys(PAGINAS)) {
    const secao = $(`page-${id}`);
    const ativa = id === nome;
    secao.hidden = !ativa;
    secao.classList.toggle("active", ativa);
  }
  document.querySelectorAll(".nav-button[data-page]").forEach((b) => {
    if (b.dataset.page === nome) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  if (location.hash !== `#${nome}`) history.replaceState(null, "", `#${nome}`);
  atualizarTitulo();
  if (nome === "history") carregarHistorico();
  if (foco) $("main").focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

function subtituloInicio() {
  const d = dispositivoAtual();
  if (!d) return "Acompanhe as condições das aves em tempo real.";
  const u = ultimas[d.id];
  const sit = (u && u.situacao) || d.situacao;
  const partes = [d.descricao || d.id];
  if (sit && sit.idade_dias !== null && sit.idade_dias !== undefined) partes.push(`lote com ${diasRotulo(sit.idade_dias)}`);
  if (sit && sit.faixa) partes.push(sit.faixa.nome);
  return partes.join(" · ");
}

function atualizarTitulo() {
  const p = PAGINAS[paginaAtual];
  $("page-title").textContent = p.titulo;
  $("page-subtitle").textContent = p.sub || subtituloInicio();
  document.title = `${p.titulo} — Nexar`;
}

function relogio() {
  $("topo-data").textContent = dataCurta(hojeRecifeISO());
  $("topo-hora").textContent = hora();
}

// ---------- estado ----------
let dispositivos = [];
let ultimas = {}; // id -> resposta de /ultima
let selecionado = null;
let emAndamento = false;
let temDados = false;

function dispositivoAtual() {
  return dispositivos.find((d) => d.id === selecionado) || null;
}

const ESTADOS = ["danger", "safe", "caution", "sem-dado"];
const ESTADO_DA_CLASSE = { conforto: "safe", alerta: "caution", critico: "danger", sem_faixa: "caution" };

/** Posições (em %) da faixa verde e do marcador numa escala azul-verde-amarelo-vermelho. */
function montarEscala(lo, hi, valor, confMin, confMax) {
  const pct = (x) => Math.max(0, Math.min(100, ((x - lo) / (hi - lo)) * 100));
  const p2 = pct(confMax);
  return { p1: pct(confMin), p2, p3: p2 + (100 - p2) / 2, pos: Math.max(2, Math.min(98, pct(valor))) };
}

function preencherLeitura(id, d) {
  const c = $(id);
  c.classList.remove(...ESTADOS);
  c.classList.add(d.estado);
  const campo = (nome) => c.querySelector(`[data-campo="${nome}"]`);
  const valor = campo("valor");
  valor.textContent = d.valor;
  if (d.unidade) valor.append(el("span", "unidade", d.unidade));
  if (d.rotuloValor) valor.setAttribute("aria-label", d.rotuloValor);
  else valor.removeAttribute("aria-label");
  campo("pill").textContent = d.pill;
  campo("faixa").textContent = d.faixa || "--";
  campo("extra").textContent = d.extra || "--";
  campo("acao").textContent = d.acao;
  campo("nota").textContent = d.nota || "";
  campo("legenda").textContent = d.legenda || "";
  const caixa = campo("escala");
  caixa.hidden = !d.escala;
  if (d.escala) {
    const barra = campo("barra");
    barra.style.setProperty("--p1", `${d.escala.p1.toFixed(1)}%`);
    barra.style.setProperty("--p2", `${d.escala.p2.toFixed(1)}%`);
    barra.style.setProperty("--p3", `${d.escala.p3.toFixed(1)}%`);
    campo("marca").style.left = `${d.escala.pos.toFixed(1)}%`;
  }
}

/** "quente" | "frio" | null, comparando o ITGU com a faixa de conforto. */
function direcao(leitura, situacao) {
  const f = situacao && situacao.faixa;
  if (!f || situacao.classificacao === "conforto") return null;
  if (leitura.itgu > f.conforto_max) return "quente";
  if (leitura.itgu < f.conforto_min) return "frio";
  return null;
}

function textoTemperatura(classe, dir) {
  if (classe === "conforto") return { pill: "Normal", acao: "Pode manter como está.", nota: "A temperatura está na faixa indicada." };
  if (classe === "sem_faixa") return { pill: "Sem faixa", acao: "Defina a faixa do lote.", nota: "Sem faixa de ITGU, não dá para avaliar." };
  const forte = classe === "critico";
  if (dir === "frio") {
    return { pill: forte ? "Muito frio" : "Frio", acao: "Confira o aquecimento.", nota: "Frio demais pode prejudicar as aves." };
  }
  return {
    pill: forte ? "Muito quente" : "Quente",
    acao: forte ? "Ligue a ventilação." : "Fique de olho na ventilação.",
    nota: "Calor forte pode prejudicar as aves. Confira se o ar está circulando.",
  };
}

function cartaoTemperatura(leitura, situacao) {
  const classe = situacao.classificacao || "sem_faixa";
  const t = textoTemperatura(classe, direcao(leitura, situacao));
  const f = situacao.faixa;
  let escalaTemp = null;
  if (f) {
    const folga = (f.critico_max - f.critico_min) * 0.4;
    escalaTemp = montarEscala(f.critico_min - folga, f.critico_max + folga, leitura.itgu, f.conforto_min, f.conforto_max);
  }
  const ext = leitura.t_ext === null || leitura.t_ext === undefined ? "Sem sinal" : `${numero(leitura.t_ext, 1)} °C`;
  preencherLeitura("m-temp", {
    estado: ESTADO_DA_CLASSE[classe],
    valor: numero(leitura.t_int, 1),
    unidade: "°C",
    faixa: f ? `${numero(f.conforto_min, 1)} – ${numero(f.conforto_max, 1)}` : "Sem faixa",
    extra: ext,
    escala: escalaTemp,
    legenda: `ITGU atual: ${numero(leitura.itgu, 1)}`,
    ...t,
  });
}

function cartaoUmidade(leitura) {
  const ur = leitura.ur_int;
  let estado = "safe";
  let pill = "Normal";
  let acao = "Pode manter como está.";
  let nota = "A umidade está na faixa indicada.";
  if (ur < UR_BOA[0] || ur > UR_BOA[1]) {
    const baixa = ur < UR_BOA[0];
    const critica = ur < UR_LIMITE[0] || ur > UR_LIMITE[1];
    estado = critica ? "danger" : "caution";
    pill = baixa ? (critica ? "Muito baixa" : "Baixa") : critica ? "Muito alta" : "Alta";
    acao = baixa ? "O ar está seco demais." : "O ar está úmido demais.";
    nota = baixa ? "Ar seco levanta poeira e incomoda as aves." : "Ar úmido deixa a cama molhada.";
  }
  preencherLeitura("m-umid", {
    estado, pill, acao, nota,
    valor: numero(ur, 0),
    unidade: "%",
    faixa: `${UR_BOA[0]} – ${UR_BOA[1]} %`,
    extra: `${UR_LIMITE[0]} – ${UR_LIMITE[1]} %`,
    escala: montarEscala(0, 100, ur, UR_BOA[0], UR_BOA[1]),
    legenda: `Umidade atual: ${numero(ur, 0)}%`,
  });
}

function leiturasSemDado(offline) {
  const pill = offline ? "Sem sinal" : "Aguardando";
  const acao = offline ? "Confira o equipamento." : "Aguardando leitura.";
  const nota = offline ? "O galpão não envia leituras há um tempo." : "Ainda não chegou nenhuma leitura.";
  for (const id of ["m-temp", "m-umid"]) {
    preencherLeitura(id, { estado: "sem-dado", valor: "--", rotuloValor: "Sem leitura", pill, acao, nota });
  }
}

const ICONE_ANEL_OK = '<path d="m6 12.5 4 4 8-9"/>';
const ICONE_ANEL_ALERTA = '<path d="M12 6.5v7m0 4h.01"/>';
const ICONE_BADGE_OK = '<circle cx="12" cy="12" r="9.5"/><path d="m7.5 12.5 3 3 6-6.5"/>';
const ICONE_BADGE_ALERTA = '<path d="M12 3 22 21H2L12 3Z"/><path d="M12 9v5m0 3h.01"/>';

/** Situação geral: selo do topo, anel e texto do painel lateral. estado: good | caution | danger. */
function situacaoGeral(estado, titulo, texto, rotuloAnel, descAnel) {
  const badge = $("resumo");
  badge.classList.remove("good", "caution", "danger");
  badge.classList.add(estado);
  $("resumo-titulo").textContent = titulo;
  $("resumo-texto").textContent = texto;
  // ícones: constantes do código, nunca dado da API
  badge.querySelector(".summary-icon").innerHTML = estado === "good" ? ICONE_BADGE_OK : ICONE_BADGE_ALERTA;

  const anel = $("anel");
  anel.classList.remove("good", "caution", "danger", "sem");
  anel.classList.add(estado === "caution" && rotuloAnel === "Sem sinal" ? "sem" : estado);
  anel.querySelector(".anel-icone").innerHTML = estado === "good" ? ICONE_ANEL_OK : ICONE_ANEL_ALERTA;
  $("anel-texto").textContent = rotuloAnel;
  $("anel-desc").textContent = descAnel;
}

function infoLateral(d, u) {
  const sit = (u && u.situacao) || d.situacao || {};
  const leitura = u && u.leitura;
  $("info-ambiente").textContent = ambienteRotulo(d.ambiente).replace(/^./, (c) => c.toUpperCase());
  $("info-idade").textContent = sit.idade_dias === null || sit.idade_dias === undefined ? "Não informada" : diasRotulo(sit.idade_dias);
  $("info-faixa").textContent = sit.faixa ? sit.faixa.nome : "Sem faixa";
  $("info-itgu").textContent = leitura ? numero(leitura.itgu, 1) : "--";
  $("info-ultima").textContent = leitura ? haQuanto(leitura.ts) : "--";
}

function mostrarInicio() {
  const d = dispositivoAtual();
  if (!d) {
    leiturasSemDado(false);
    situacaoGeral("caution", "Nenhum galpão", "Cadastre um dispositivo.", "Sem dados", "Peça a um administrador para cadastrar um dispositivo.");
    return;
  }
  const u = ultimas[d.id];
  infoLateral(d, u);
  const leitura = u && u.leitura;
  if (!leitura) {
    leiturasSemDado(false);
    situacaoGeral("caution", "Aguardando leituras", "O galpão ainda não enviou nada.", "Aguardando", "O galpão ainda não enviou nenhuma leitura.");
    return;
  }
  const situacao = u.situacao;
  cartaoTemperatura(leitura, situacao);
  cartaoUmidade(leitura);

  const classe = situacao.classificacao || "sem_faixa";
  const dir = direcao(leitura, situacao);
  if (!d.online) {
    situacaoGeral("caution", "Sem sinal do galpão", `Última leitura ${haQuanto(leitura.ts)}.`, "Sem sinal", `O galpão parou de enviar leituras (${haQuanto(leitura.ts)}). Confira o equipamento e a internet.`);
  } else if (classe === "critico") {
    const msg = dir === "frio" ? "Está muito frio. Confira o aquecimento agora." : "Está muito quente. Confira a ventilação agora.";
    situacaoGeral("danger", "Ambiente crítico", dir === "frio" ? "Confira o aquecimento" : "Confira a ventilação", "Crítico", msg);
  } else if (classe === "alerta") {
    const msg = dir === "frio" ? "A temperatura está baixando. Acompanhe de perto." : "A temperatura está subindo. Acompanhe de perto.";
    situacaoGeral("caution", "Atenção", "Acompanhe de perto", "Atenção", msg);
  } else if (classe === "sem_faixa") {
    situacaoGeral("caution", "Falta definir a faixa", "Informe a data de alojamento", "Sem faixa", "Informe a data de alojamento do lote para avaliar o conforto.");
  } else {
    situacaoGeral("good", "Ambiente normal", "Condições dentro da faixa ideal", "Normal", "Temperatura e umidade dentro das faixas recomendadas para as aves.");
  }
  // o desenho da aba "Ver galpão" usa as mesmas leituras
  pintarCaixaSvg("caixa-temp", ESTADO_DA_CLASSE[classe], `${numero(leitura.t_int, 1)} °C`);
  const umid = $("m-umid");
  const estadoUmid = umid.classList.contains("danger") ? "danger" : umid.classList.contains("caution") ? "caution" : "safe";
  pintarCaixaSvg("caixa-umid", estadoUmid, `${numero(leitura.ur_int, 0)}%`);
}

function pintarCaixaSvg(id, estado, texto) {
  const g = $(id);
  g.classList.remove("danger", "caution");
  if (estado !== "safe") g.classList.add(estado === "danger" ? "danger" : "caution");
  g.querySelector("text:last-of-type").textContent = texto;
}

// ---------- alertas (derivados das leituras; a API não guarda alertas) ----------
const ICONE_ALERTA = '<path d="M12 3 22 21H2L12 3Z" stroke-linejoin="round"/><path d="M12 9v5m0 3h.01" stroke-linecap="round"/>';
const ICONE_OK = '<path d="m4 12 5 5L20 6" stroke-linecap="round" stroke-linejoin="round"/>';

function linhaAlerta(tipo, titulo, texto, meta) {
  const linha = el("div", `alert-row${tipo === "warning" ? " warning" : tipo === "ok" ? " ok" : ""}`);
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.8");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = tipo === "ok" ? ICONE_OK : ICONE_ALERTA; // constante do código, nunca dado da API
  const corpo = el("div", "alert-corpo");
  corpo.append(el("h3", null, titulo), el("p", null, texto));
  if (meta) corpo.append(el("p", "alert-meta", meta));
  linha.append(svg, corpo);
  return linha;
}

function linhaTabelaAlerta(a) {
  const tr = el("tr");
  const status = el("td");
  const marca = el("span", `st ${a.estado}`);
  marca.append(el("i"), document.createTextNode(a.statusTexto));
  status.append(marca);
  tr.append(el("td", null, a.ts ? horaMinuto(new Date(a.ts).getTime()) : "—"), el("td", null, a.param), el("td", null, a.valor), status);
  return tr;
}

function montarAlertas() {
  const itens = [];
  const novo = (peso, tipo, titulo, texto, meta, linha) => itens.push({ peso, tipo, titulo, texto, meta, linha });

  for (const d of dispositivos.filter((x) => x.ativo)) {
    const nome = d.descricao || d.id;
    const u = ultimas[d.id];
    const leitura = u && u.leitura;
    if (!leitura) {
      novo(1, "warning", `${nome}: sem leituras`, "Ainda não chegou nenhuma leitura deste galpão.", d.id,
        { ts: null, param: nome, valor: "--", estado: "caution", statusTexto: "Sem leitura" });
      continue;
    }
    const meta = `${d.id} · ${ambienteRotulo(d.ambiente)} · última leitura ${haQuanto(leitura.ts)}`;
    if (!d.online) {
      novo(0, "danger", `${nome}: sem sinal`, "O galpão parou de enviar leituras. Confira o equipamento e a internet.", meta,
        { ts: leitura.ts, param: "Conexão", valor: haQuanto(leitura.ts), estado: "danger", statusTexto: "Sem sinal" });
    }
    const classe = u.situacao.classificacao;
    const dir = direcao(leitura, u.situacao);
    const temp = `${numero(leitura.t_int, 1)} °C`;
    if (classe === "critico") {
      novo(0, "danger", `${nome}: ${dir === "frio" ? "muito frio" : "muito quente"}`,
        dir === "frio" ? "Confira o aquecimento agora." : "Ligue a ventilação e confira se o ar está circulando.", `${meta} · ITGU ${numero(leitura.itgu, 1)}`,
        { ts: leitura.ts, param: "Temperatura", valor: temp, estado: "danger", statusTexto: "Crítico" });
    } else if (classe === "alerta") {
      novo(1, "warning", `${nome}: atenção com ${dir === "frio" ? "o frio" : "o calor"}`, "Acompanhe de perto nas próximas horas.", `${meta} · ITGU ${numero(leitura.itgu, 1)}`,
        { ts: leitura.ts, param: "Temperatura", valor: temp, estado: "caution", statusTexto: "Atenção" });
    } else if (classe === "sem_faixa") {
      novo(1, "warning", `${nome}: sem faixa de ITGU`, "Informe a data de alojamento do lote para avaliar o conforto.", meta,
        { ts: leitura.ts, param: "Faixa de ITGU", valor: "--", estado: "caution", statusTexto: "Sem faixa" });
    }
    if (leitura.t_ext === null || leitura.t_ext === undefined) {
      novo(1, "warning", `${nome}: sensor externo sem leitura`, "Confira o sensor de temperatura de fora.", meta,
        { ts: leitura.ts, param: "Sensor externo", valor: "--", estado: "caution", statusTexto: "Sem leitura" });
    }
    if (leitura.ur_int < UR_BOA[0] || leitura.ur_int > UR_BOA[1]) {
      const critica = leitura.ur_int < UR_LIMITE[0] || leitura.ur_int > UR_LIMITE[1];
      novo(critica ? 0 : 1, critica ? "danger" : "warning", `${nome}: umidade ${leitura.ur_int < UR_BOA[0] ? "baixa" : "alta"}`, `Umidade em ${numero(leitura.ur_int, 0)}%.`, meta,
        { ts: leitura.ts, param: "Umidade", valor: `${numero(leitura.ur_int, 0)}%`, estado: critica ? "danger" : "caution", statusTexto: critica ? "Crítico" : "Atenção" });
    }
  }
  itens.sort((a, b) => a.peso - b.peso);

  const linhas = itens.map((i) => linhaAlerta(i.tipo, i.titulo, i.texto, i.meta));
  if (linhas.length === 0) linhas.push(linhaAlerta("ok", "Tudo certo por aqui", "Nenhum aviso no momento. Pode manter como está.", null));
  $("lista-alertas").replaceChildren(...linhas);

  const tabela = itens.slice(0, 5).map((i) => linhaTabelaAlerta(i.linha));
  if (tabela.length === 0) {
    const tr = el("tr");
    const td = el("td", "vazio", "Nenhum alerta ativo no momento.");
    td.colSpan = 4;
    tr.append(td);
    tabela.push(tr);
  }
  $("tabela-alertas").replaceChildren(...tabela);
}

// ---------- gráficos ----------
function elSvg(tag, attrs, texto) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, String(v));
  if (texto !== undefined) e.textContent = texto;
  return e;
}

function resumoSerie(valores) {
  const v = valores.filter((x) => x !== null && x !== undefined);
  if (v.length === 0) return null;
  return { min: Math.min(...v), media: v.reduce((a, b) => a + b, 0) / v.length, max: Math.max(...v) };
}

/** Temperatura (eixo esquerdo, °C) e umidade (eixo direito, %), 5 faixas de grade alinhadas. */
function desenharGrafico(svg, itens) {
  const [, , W, H] = svg.getAttribute("viewBox").split(" ").map(Number);
  const L = 46, R = 48, T = 14, B = 34;
  const pontos = itens.map((i) => ({ x: new Date(i.janela).getTime(), temp: i.t_int, fora: i.t_ext, umid: i.ur_int }));
  const temps = pontos.flatMap((p) => [p.temp, p.fora]).filter((v) => v !== null && v !== undefined);
  const umids = pontos.map((p) => p.umid).filter((v) => v !== null && v !== undefined);
  if (pontos.length < 2 || temps.length === 0 || umids.length === 0) {
    svg.replaceChildren();
    return;
  }
  const nos = [];
  const xmin = pontos[0].x;
  const xmax = pontos[pontos.length - 1].x;
  const tmin = Math.floor(Math.min(...temps) - 1);
  const tpasso = Math.max(1, Math.ceil((Math.max(...temps) + 1 - tmin) / 5));
  const tmax = tmin + 5 * tpasso;
  const umin = Math.max(0, Math.floor((Math.min(...umids) - 3) / 5) * 5);
  const upasso = Math.max(5, Math.ceil((Math.max(...umids) + 3 - umin) / 25) * 5);
  const umax = umin + 5 * upasso;
  const px = (x) => L + ((x - xmin) / (xmax - xmin || 1)) * (W - L - R);
  const py = (v, lo, hi) => T + (1 - (v - lo) / (hi - lo || 1)) * (H - T - B);

  for (let i = 0; i <= 5; i++) {
    const y = py(i, 0, 5);
    nos.push(elSvg("line", { class: "grade", x1: L, x2: W - R, y1: y, y2: y }));
    nos.push(elSvg("text", { class: "eixo-texto", x: L - 8, y: y + 4, "text-anchor": "end" }, String(tmin + i * tpasso)));
    nos.push(elSvg("text", { class: "eixo-texto", x: W - R + 8, y: y + 4, "text-anchor": "start" }, String(umin + i * upasso)));
  }
  nos.push(elSvg("text", { class: "eixo-unidade", x: L - 8, y: H - 8, "text-anchor": "end" }, "°C"));
  nos.push(elSvg("text", { class: "eixo-unidade", x: W - R + 8, y: H - 8, "text-anchor": "start" }, "%"));
  const horas = 4 * 3600 * 1000;
  for (let x = Math.ceil(xmin / horas) * horas; x <= xmax; x += horas) {
    nos.push(elSvg("text", { class: "eixo-texto", x: px(x), y: H - 8, "text-anchor": "middle" }, horaMinuto(x)));
  }
  // uma linha por série; trecho sem leitura (null) interrompe o traço
  const series = [
    ["fora", "fora", (p) => p.fora, tmin, tmax],
    ["umid", "umid", (p) => p.umid, umin, umax],
    ["temp", "temp", (p) => p.temp, tmin, tmax],
  ];
  for (const [, classe, valor, lo, hi] of series) {
    let d = "";
    let aberto = false;
    for (const p of pontos) {
      const v = valor(p);
      if (v === null || v === undefined) {
        aberto = false;
        continue;
      }
      d += `${aberto ? "L" : "M"}${px(p.x).toFixed(1)} ${py(v, lo, hi).toFixed(1)} `;
      aberto = true;
    }
    if (d) nos.push(elSvg("path", { class: `serie ${classe}`, d: d.trim() }));
  }
  svg.replaceChildren(...nos);
}

function linhaTabela(nome, serie, casas, unidade) {
  const tr = el("tr");
  const th = el("th", null, nome);
  th.setAttribute("scope", "row");
  tr.append(th);
  for (const k of ["min", "media", "max"]) tr.append(el("td", null, serie ? `${numero(serie[k], casas)} ${unidade}`.trim() : "—"));
  return tr;
}

let historicoDe = null; // "id|minuto" da última carga, para não repetir à toa

async function carregarHistorico(forcar = false) {
  const d = dispositivoAtual();
  const avisos = [$("grafico-vazio"), $("grafico-home-vazio")];
  const mostrarAviso = (texto) => avisos.forEach((a) => { a.textContent = texto; a.hidden = !texto; });
  if (!d) {
    mostrarAviso("Nenhum galpão selecionado.");
    return;
  }
  const chave = `${d.id}|${Math.floor(Date.now() / INTERVALO_MS)}`;
  if (!forcar && chave === historicoDe) return;
  try {
    const r = await api("GET", `/leituras?device_id=${encodeURIComponent(d.id)}&agregacao=5min`);
    historicoDe = chave;
    const itens = r.itens;
    mostrarAviso(itens.length >= 2 ? "" : "Ainda não há leituras suficientes nas últimas 24 horas.");
    desenharGrafico($("grafico"), itens);
    desenharGrafico($("grafico-home"), itens);
    const dentro = resumoSerie(itens.map((i) => i.t_int));
    $("tabela").replaceChildren(
      linhaTabela("Temperatura dentro", dentro, 1, "°C"),
      linhaTabela("Temperatura de fora", resumoSerie(itens.map((i) => i.t_ext)), 1, "°C"),
      linhaTabela("Umidade do ar", resumoSerie(itens.map((i) => i.ur_int)), 0, "%"),
      linhaTabela("Calor para as aves (ITGU)", resumoSerie(itens.map((i) => i.itgu)), 1, ""),
    );
    if (dentro) {
      const rotulo = `Gráfico de temperatura e umidade nas últimas 24 horas. Temperatura dentro: mínima ${numero(dentro.min, 1)}, máxima ${numero(dentro.max, 1)} °C.`;
      $("grafico").setAttribute("aria-label", rotulo);
      $("grafico-home").setAttribute("aria-label", rotulo);
    }
  } catch (e) {
    mostrarAviso(e instanceof TypeError ? "Sem conexão com o servidor." : e.message);
  }
}

// ---------- carga de dados ----------
function montarSeletor() {
  const ativos = dispositivos.filter((d) => d.ativo);
  const sel = $("dispositivo");
  if (!ativos.some((d) => d.id === selecionado)) selecionado = ativos.length ? ativos[0].id : null;
  sel.replaceChildren(...ativos.map((d) => {
    const o = el("option", null, d.descricao || d.id);
    o.value = d.id;
    o.selected = d.id === selecionado;
    return o;
  }));
}

async function atualizar() {
  if (emAndamento) return;
  emAndamento = true;
  try {
    dispositivos = await api("GET", "/dispositivos");
    const ativos = dispositivos.filter((d) => d.ativo);
    const respostas = await Promise.all(ativos.map((d) => api("GET", `/dispositivos/${encodeURIComponent(d.id)}/ultima`)));
    ultimas = Object.fromEntries(ativos.map((d, i) => [d.id, respostas[i]]));
    montarSeletor();
    mostrarInicio();
    montarAlertas();
    atualizarTitulo();
    temDados = true;
    $("status").textContent = `Atualizado às ${hora()}.`;
    carregarHistorico(true);
  } catch (e) {
    if (temDados) {
      $("status").textContent = "Não foi possível atualizar agora. Mostrando os últimos dados recebidos.";
    } else {
      $("status").textContent = e instanceof TypeError ? "Sem conexão com o servidor." : e.message;
      situacaoGeral("caution", "Sem conexão", "Não foi possível buscar as leituras.", "Sem sinal", "Não foi possível buscar as leituras agora.");
    }
  } finally {
    emAndamento = false;
  }
}

// ---------- entrada ----------
function mostrarApp(sessao) {
  $("login").hidden = true;
  $("app").hidden = false;
  document.querySelectorAll(".so-admin").forEach((a) => { a.hidden = sessao.perfil !== "admin"; });
  $("usuario-logado").textContent = `${sessao.nome} (${sessao.perfil})`;
  relogio();
  setInterval(relogio, 15000);
  const hash = location.hash.slice(1);
  irPara(PAGINAS[hash] ? hash : "home", { foco: false });
  atualizar();
  setInterval(() => { if (!document.hidden) atualizar(); }, INTERVALO_MS);
}

function iniciarLogin() {
  $("login").hidden = false;
  $("app").hidden = true;
  const form = $("form-login");
  const erro = $("erro-login");
  const botao = form.querySelector("button[type=submit]");
  $("usuario").focus();
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    erro.textContent = "";
    const email = $("usuario").value.trim();
    const senha = $("senha").value;
    if (!email || !senha) {
      erro.textContent = "Informe e-mail e senha.";
      return;
    }
    botao.disabled = true;
    botao.textContent = "Entrando…";
    try {
      const r = await login(email, senha);
      const sessao = { token: r.access_token, nome: r.nome, perfil: r.perfil };
      salvarSessao(sessao);
      $("senha").value = "";
      mostrarApp(sessao);
    } catch (e) {
      erro.textContent = e instanceof TypeError ? "Sem conexão com o servidor." : e.message;
    } finally {
      botao.disabled = false;
      botao.textContent = "Entrar";
    }
  });
}

function iniciar() {
  iniciarPreferencias();
  document.querySelectorAll(".nav-button[data-page]").forEach((b) => b.addEventListener("click", () => irPara(b.dataset.page)));
  document.querySelectorAll("[data-goto]").forEach((b) => b.addEventListener("click", () => irPara(b.dataset.goto)));
  $("dispositivo").addEventListener("change", (ev) => {
    selecionado = ev.target.value;
    historicoDe = null;
    mostrarInicio();
    atualizarTitulo();
    carregarHistorico(true);
  });
  $("sair").addEventListener("click", sair);
  window.addEventListener("hashchange", () => {
    const h = location.hash.slice(1);
    if (PAGINAS[h] && h !== paginaAtual) irPara(h, { foco: false });
  });

  const sessao = lerSessao();
  if (sessao) mostrarApp(sessao);
  else {
    limparSessao();
    iniciarLogin();
  }
}

iniciar();
