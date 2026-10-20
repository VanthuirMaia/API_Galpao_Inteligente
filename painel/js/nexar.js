// Painel Nexar (index.html): início, galpão, histórico, alertas e configurações numa página só.
// As outras telas (diagnóstico, conta, administração) continuam em páginas próprias.
import { api, login } from "./api.js";
import { ambienteRotulo, CLASSIFICACAO, el, haQuanto, hora, horaMinuto, numero } from "./formato.js";
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
  $("theme-label").textContent = escuro ? "TEMA CLARO" : "TEMA ESCURO";
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
  const escuro = tema ? tema === "escuro" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  aplicarTema(escuro);
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
  home: { titulo: null, sub: "Veja aqui se está tudo bem com as aves." },
  barn: { titulo: "Ver galpão", sub: "Uma visão geral de como o galpão está agora." },
  history: { titulo: "Histórico", sub: "Como o galpão se comportou no último dia." },
  alerts: { titulo: "Alertas", sub: "O que precisa de atenção." },
  settings: { titulo: "Configurar", sub: "Deixe a tela do seu jeito." },
};
let paginaAtual = "home";

function irPara(nome, { foco = true } = {}) {
  if (!PAGINAS[nome]) nome = "home";
  paginaAtual = nome;
  for (const [id] of Object.entries(PAGINAS)) {
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

function atualizarTitulo() {
  const p = PAGINAS[paginaAtual];
  const disp = dispositivoAtual();
  const titulo = p.titulo || (disp ? disp.descricao || disp.id : "Galpão");
  $("page-title").textContent = titulo;
  $("page-subtitle").textContent = p.sub;
  document.title = `${titulo} — Nexar`;
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

function pintar(elemento, estado) {
  elemento.classList.remove(...ESTADOS);
  elemento.classList.add(estado);
}

function preencherCartao(id, { estado, valor, pill, acao, nota, rotuloValor }) {
  const c = $(id);
  pintar(c, estado);
  const v = c.querySelector('[data-campo="valor"]');
  v.textContent = valor;
  if (rotuloValor) v.setAttribute("aria-label", rotuloValor);
  else v.removeAttribute("aria-label");
  c.querySelector('[data-campo="pill"]').textContent = pill;
  c.querySelector('[data-campo="acao"]').textContent = acao;
  c.querySelector('[data-campo="nota"]').textContent = nota;
}

const ESTADO_DA_CLASSE = { conforto: "safe", alerta: "caution", critico: "danger", sem_faixa: "caution" };

/** "quente" | "frio" | null, comparando o ITGU com a faixa de conforto. */
function direcao(leitura, situacao) {
  const f = situacao && situacao.faixa;
  if (!f || situacao.classificacao === "conforto") return null;
  if (leitura.itgu > f.conforto_max) return "quente";
  if (leitura.itgu < f.conforto_min) return "frio";
  return null;
}

function textoTemperatura(classe, dir) {
  if (classe === "conforto") return { pill: "Boa", acao: "PODE MANTER COMO ESTÁ.", nota: "A temperatura está na faixa indicada." };
  if (classe === "sem_faixa") return { pill: "Sem faixa", acao: "DEFINA A FAIXA DO LOTE.", nota: "Sem faixa de ITGU, não dá para avaliar." };
  const forte = classe === "critico";
  if (dir === "frio") {
    return { pill: forte ? "Muito frio" : "Frio", acao: "CONFIRA O AQUECIMENTO.", nota: "Frio demais pode prejudicar as aves." };
  }
  return { pill: forte ? "Muito quente" : "Quente", acao: forte ? "LIGUE A VENTILAÇÃO." : "FIQUE DE OLHO NA VENTILAÇÃO.", nota: "Confira se o ar está circulando." };
}

function cartaoTemperatura(leitura, situacao) {
  const classe = situacao.classificacao || "sem_faixa";
  const t = textoTemperatura(classe, direcao(leitura, situacao));
  preencherCartao("m-temp", { estado: ESTADO_DA_CLASSE[classe], valor: `${numero(leitura.t_int, 1)} °C`, ...t });
}

function cartaoUmidade(leitura) {
  const ur = leitura.ur_int;
  let estado = "safe";
  let pill = "Boa";
  let acao = "PODE MANTER COMO ESTÁ.";
  let nota = "A umidade está na faixa indicada.";
  if (ur < UR_BOA[0] || ur > UR_BOA[1]) {
    const baixa = ur < UR_BOA[0];
    const critica = ur < UR_LIMITE[0] || ur > UR_LIMITE[1];
    estado = critica ? "danger" : "caution";
    pill = baixa ? (critica ? "Muito baixa" : "Baixa") : critica ? "Muito alta" : "Alta";
    acao = baixa ? "O AR ESTÁ SECO DEMAIS." : "O AR ESTÁ ÚMIDO DEMAIS.";
    nota = baixa ? "Ar seco levanta poeira e incomoda as aves." : "Ar úmido deixa a cama molhada.";
  }
  preencherCartao("m-umid", { estado, valor: `${numero(ur, 0)}%`, pill, acao, nota });
}

function cartaoExterna(leitura) {
  if (leitura.t_ext === null || leitura.t_ext === undefined) {
    preencherCartao("m-ext", {
      estado: "caution", valor: "-- °C", rotuloValor: "Sem leitura", pill: "Sem sinal",
      acao: "CONFIRA O SENSOR EXTERNO.", nota: "Não chegou uma leitura de fora.",
    });
    return;
  }
  const dif = leitura.t_int - leitura.t_ext;
  const nota = Math.abs(dif) < 0.5
    ? "Dentro e fora estão com a mesma temperatura."
    : `Dentro está ${numero(Math.abs(dif), 1)} °C ${dif > 0 ? "mais quente" : "mais frio"} que fora.`;
  preencherCartao("m-ext", { estado: "safe", valor: `${numero(leitura.t_ext, 1)} °C`, pill: "Lendo", acao: "SENSOR EXTERNO FUNCIONANDO.", nota });
}

function cartaoCalor(leitura, situacao) {
  const classe = situacao.classificacao || "sem_faixa";
  const dir = direcao(leitura, situacao);
  const info = CLASSIFICACAO[classe] || CLASSIFICACAO.sem_faixa;
  let valor = "NORMAL";
  let acao = "PODE MANTER COMO ESTÁ.";
  let nota = "O calor está dentro do esperado para as aves.";
  if (classe === "sem_faixa") {
    valor = "--";
    acao = "DEFINA A FAIXA DO LOTE.";
    nota = "Informe a data de alojamento do lote.";
  } else if (dir === "quente") {
    valor = "ALTO";
    acao = "MELHORE A VENTILAÇÃO.";
    nota = "Calor forte pode prejudicar as aves.";
  } else if (dir === "frio") {
    valor = "BAIXO";
    acao = "CONFIRA O AQUECIMENTO.";
    nota = "Frio forte pode prejudicar as aves.";
  }
  nota += ` ITGU ${numero(leitura.itgu, 1)}.`;
  preencherCartao("m-calor", {
    estado: ESTADO_DA_CLASSE[classe], valor,
    pill: classe === "critico" ? "Atenção urgente" : classe === "alerta" ? "Atenção" : info.texto.replace(/^\S+\s/, ""),
    acao, nota,
  });
}

function cartoesSemDado(offline) {
  const pill = offline ? "Sem sinal" : "Aguardando";
  const acao = offline ? "CONFIRA O EQUIPAMENTO." : "AGUARDANDO LEITURA.";
  const nota = offline ? "O galpão não envia leituras há um tempo." : "Ainda não chegou nenhuma leitura.";
  for (const id of ["m-temp", "m-umid", "m-ext", "m-calor"]) {
    preencherCartao(id, { estado: "sem-dado", valor: "--", rotuloValor: "Sem leitura", pill, acao, nota });
  }
}

function resumo(estado, titulo, texto) {
  const r = $("resumo");
  r.classList.remove("good", "caution");
  if (estado === "good") r.classList.add("good");
  if (estado === "caution") r.classList.add("caution");
  $("resumo-titulo").textContent = titulo;
  $("resumo-texto").textContent = texto;
}

function pintarCaixaSvg(id, estado, texto) {
  const g = $(id);
  g.classList.remove("danger", "caution");
  if (estado !== "safe") g.classList.add(estado === "danger" ? "danger" : "caution");
  g.querySelector("text:last-of-type").textContent = texto;
}

function mostrarInicio() {
  const d = dispositivoAtual();
  if (!d) {
    cartoesSemDado(false);
    resumo("caution", "NENHUM GALPÃO CADASTRADO", "Peça a um administrador para cadastrar um dispositivo.");
    return;
  }
  const u = ultimas[d.id];
  const leitura = u && u.leitura;
  if (!leitura) {
    cartoesSemDado(false);
    resumo("caution", "AGUARDANDO LEITURAS", "O galpão ainda não enviou nenhuma leitura.");
    pintarCaixaSvg("caixa-temp", "caution", "-- °C");
    pintarCaixaSvg("caixa-umid", "caution", "--%");
    return;
  }
  const situacao = u.situacao;
  cartaoTemperatura(leitura, situacao);
  cartaoUmidade(leitura);
  cartaoExterna(leitura);
  cartaoCalor(leitura, situacao);

  const classe = situacao.classificacao || "sem_faixa";
  const dir = direcao(leitura, situacao);
  const idade = `Última leitura ${haQuanto(leitura.ts)}.`;
  if (!d.online) {
    resumo("caution", "SEM SINAL DO GALPÃO", `${idade} Confira o equipamento e a internet.`);
  } else if (classe === "critico") {
    resumo("danger", "ALERTA: VERIFICAR O GALPÃO", dir === "frio" ? "Está muito frio. Confira o aquecimento agora." : "Está muito quente. Confira a ventilação agora.");
  } else if (classe === "alerta") {
    resumo("caution", "ATENÇÃO COM O GALPÃO", dir === "frio" ? "A temperatura está baixando. Acompanhe de perto." : "A temperatura está subindo. Acompanhe de perto.");
  } else if (classe === "sem_faixa") {
    resumo("caution", "FALTA DEFINIR A FAIXA", "Informe a data de alojamento do lote para avaliar o conforto.");
  } else {
    resumo("good", "TUDO BEM NO GALPÃO", "As aves estão em conforto. Pode manter como está.");
  }

  pintarCaixaSvg("caixa-temp", ESTADO_DA_CLASSE[classe], `${numero(leitura.t_int, 1)} °C`);
  const estadoUmid = $("m-umid").classList.contains("danger") ? "danger" : $("m-umid").classList.contains("caution") ? "caution" : "safe";
  pintarCaixaSvg("caixa-umid", estadoUmid, `${numero(leitura.ur_int, 0)}%`);
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
  svg.setAttribute("stroke-width", "2.5");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = tipo === "ok" ? ICONE_OK : ICONE_ALERTA; // constante do código, nunca dado da API
  const corpo = el("div", "alert-corpo");
  corpo.append(el("h3", null, titulo), el("p", null, texto));
  if (meta) corpo.append(el("p", "alert-meta", meta));
  linha.append(svg, corpo);
  return linha;
}

function montarAlertas() {
  const itens = [];
  for (const d of dispositivos.filter((x) => x.ativo)) {
    const nome = d.descricao || d.id;
    const u = ultimas[d.id];
    const leitura = u && u.leitura;
    if (!leitura) {
      itens.push({ peso: 1, linha: linhaAlerta("warning", `${nome}: sem leituras`, "Ainda não chegou nenhuma leitura deste galpão.", d.id) });
      continue;
    }
    const meta = `${d.id} · ${ambienteRotulo(d.ambiente)} · última leitura ${haQuanto(leitura.ts)}`;
    if (!d.online) {
      itens.push({ peso: 0, linha: linhaAlerta("danger", `${nome}: sem sinal`, "O galpão parou de enviar leituras. Confira o equipamento e a internet.", meta) });
    }
    const classe = u.situacao.classificacao;
    const dir = direcao(leitura, u.situacao);
    if (classe === "critico") {
      itens.push({ peso: 0, linha: linhaAlerta("danger", `${nome}: ${dir === "frio" ? "muito frio" : "muito quente"}`, dir === "frio" ? "Confira o aquecimento agora." : "Ligue a ventilação e confira se o ar está circulando.", `${meta} · ITGU ${numero(leitura.itgu, 1)}`) });
    } else if (classe === "alerta") {
      itens.push({ peso: 1, linha: linhaAlerta("warning", `${nome}: atenção com ${dir === "frio" ? "o frio" : "o calor"}`, "Acompanhe de perto nas próximas horas.", `${meta} · ITGU ${numero(leitura.itgu, 1)}`) });
    } else if (classe === "sem_faixa") {
      itens.push({ peso: 1, linha: linhaAlerta("warning", `${nome}: sem faixa de ITGU`, "Informe a data de alojamento do lote para avaliar o conforto.", meta) });
    }
    if (leitura.t_ext === null || leitura.t_ext === undefined) {
      itens.push({ peso: 1, linha: linhaAlerta("warning", `${nome}: sensor externo sem leitura`, "Confira o sensor de temperatura de fora.", meta) });
    }
    if (leitura.ur_int < UR_BOA[0] || leitura.ur_int > UR_BOA[1]) {
      const critica = leitura.ur_int < UR_LIMITE[0] || leitura.ur_int > UR_LIMITE[1];
      itens.push({ peso: critica ? 0 : 1, linha: linhaAlerta(critica ? "danger" : "warning", `${nome}: umidade ${leitura.ur_int < UR_BOA[0] ? "baixa" : "alta"}`, `Umidade em ${numero(leitura.ur_int, 0)}%.`, meta) });
    }
  }
  itens.sort((a, b) => a.peso - b.peso);
  const linhas = itens.map((i) => i.linha);
  if (linhas.length === 0) {
    linhas.push(linhaAlerta("ok", "Tudo certo por aqui", "Nenhum aviso no momento. Pode manter como está.", null));
  }
  $("lista-alertas").replaceChildren(...linhas);
}

// ---------- histórico ----------
let historicoDe = null; // "id|minuto" da última carga, para não repetir à toa

function el_svg(tag, attrs, texto) {
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

function desenharGrafico(itens) {
  const svg = $("grafico");
  const L = 56, R = 16, T = 16, B = 42, W = 760, H = 390;
  const pontos = itens.map((i) => ({ x: new Date(i.janela).getTime(), dentro: i.t_int, fora: i.t_ext }));
  const todos = pontos.flatMap((p) => [p.dentro, p.fora]).filter((v) => v !== null && v !== undefined);
  const nos = [];
  if (pontos.length < 2 || todos.length === 0) {
    svg.replaceChildren();
    return;
  }
  const xmin = pontos[0].x;
  const xmax = pontos[pontos.length - 1].x;
  const ymin = Math.floor(Math.min(...todos) - 1);
  const ymax = Math.ceil(Math.max(...todos) + 1);
  const px = (x) => L + ((x - xmin) / (xmax - xmin || 1)) * (W - L - R);
  const py = (y) => T + (1 - (y - ymin) / (ymax - ymin || 1)) * (H - T - B);

  const passo = Math.max(1, Math.ceil((ymax - ymin) / 6));
  for (let y = ymin; y <= ymax; y += passo) {
    nos.push(el_svg("line", { class: "grade", x1: L, x2: W - R, y1: py(y), y2: py(y) }));
    nos.push(el_svg("text", { class: "eixo-texto", x: L - 8, y: py(y) + 5, "text-anchor": "end" }, `${y}°`));
  }
  const horas = 4 * 3600 * 1000;
  for (let x = Math.ceil(xmin / horas) * horas; x <= xmax; x += horas) {
    nos.push(el_svg("line", { class: "grade", x1: px(x), x2: px(x), y1: T, y2: H - B }));
    nos.push(el_svg("text", { class: "eixo-texto", x: px(x), y: H - B + 22, "text-anchor": "middle" }, horaMinuto(x)));
  }
  // uma linha por série; trecho sem leitura (null) interrompe o traço
  for (const [chave, classe] of [["fora", "fora"], ["dentro", "dentro"]]) {
    let d = "";
    let aberto = false;
    for (const p of pontos) {
      const v = p[chave];
      if (v === null || v === undefined) {
        aberto = false;
        continue;
      }
      d += `${aberto ? "L" : "M"}${px(p.x).toFixed(1)} ${py(v).toFixed(1)} `;
      aberto = true;
    }
    if (d) nos.push(el_svg("path", { class: `serie ${classe}`, d: d.trim() }));
  }
  svg.replaceChildren(...nos);
}

function linhaTabela(nome, serie, casas, unidade) {
  const tr = el("tr");
  tr.append(el("th", null, nome));
  tr.firstChild.setAttribute("scope", "row");
  for (const k of ["min", "media", "max"]) tr.append(el("td", null, serie ? `${numero(serie[k], casas)} ${unidade}` : "—"));
  return tr;
}

async function carregarHistorico(forcar = false) {
  const d = dispositivoAtual();
  const vazio = $("grafico-vazio");
  if (!d) {
    vazio.textContent = "Nenhum galpão selecionado.";
    vazio.hidden = false;
    return;
  }
  const chave = `${d.id}|${Math.floor(Date.now() / INTERVALO_MS)}`;
  if (!forcar && chave === historicoDe) return;
  try {
    const r = await api("GET", `/leituras?device_id=${encodeURIComponent(d.id)}&agregacao=5min`);
    historicoDe = chave;
    const itens = r.itens;
    vazio.hidden = itens.length >= 2;
    vazio.textContent = "Ainda não há leituras suficientes nas últimas 24 horas.";
    desenharGrafico(itens);
    const dentro = resumoSerie(itens.map((i) => i.t_int));
    const fora = resumoSerie(itens.map((i) => i.t_ext));
    $("tabela").replaceChildren(
      linhaTabela("Temperatura dentro", dentro, 1, "°C"),
      linhaTabela("Temperatura de fora", fora, 1, "°C"),
      linhaTabela("Umidade do ar", resumoSerie(itens.map((i) => i.ur_int)), 0, "%"),
      linhaTabela("Calor para as aves (ITGU)", resumoSerie(itens.map((i) => i.itgu)), 1, ""),
    );
    if (dentro) {
      $("grafico").setAttribute("aria-label", `Gráfico da temperatura dentro e fora do galpão nas últimas 24 horas. Dentro: mínima ${numero(dentro.min, 1)}, máxima ${numero(dentro.max, 1)} °C.`);
    }
  } catch (e) {
    vazio.textContent = e instanceof TypeError ? "Sem conexão com o servidor." : e.message;
    vazio.hidden = false;
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
  $("rotulo-dispositivo").hidden = ativos.length < 2;
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
  } catch (e) {
    if (temDados) {
      $("status").textContent = "Não foi possível atualizar agora. Mostrando os últimos dados recebidos.";
    } else {
      $("status").textContent = e instanceof TypeError ? "Sem conexão com o servidor." : e.message;
      resumo("caution", "SEM CONEXÃO", "Não foi possível buscar as leituras agora.");
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
    botao.textContent = "ENTRANDO…";
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
      botao.textContent = "ENTRAR";
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
    if (paginaAtual === "history") carregarHistorico(true);
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
