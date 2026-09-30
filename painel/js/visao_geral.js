// Visão geral: um card por dispositivo, atualizado a cada 60 s.
import { api } from "./api.js";
import { CLASSIFICACAO, ambienteRotulo, dataHora, diasRotulo, el, haQuanto, hora, numero } from "./formato.js";
import { montarLayout } from "./layout.js";
import { exigirLogin } from "./sessao.js";

exigirLogin();
montarLayout();

const INTERVALO_MS = 60000;

const listaAtivos = document.getElementById("lista-ativos");
const listaInativos = document.getElementById("lista-inativos");
const blocoInativos = document.getElementById("inativos");
const resumoInativos = document.getElementById("resumo-inativos");
const carregando = document.getElementById("carregando");
const avisoEl = document.getElementById("aviso");
const erroEl = document.getElementById("erro");
const atualizadoEl = document.getElementById("atualizado");

let emAndamento = false;
let temDados = false;
let horaUltimaAtualizacao = null;

/** Uma medida do card: rótulo + valor com unidade. */
function medida(rotulo, valor, unidade) {
  const caixa = el("div", "medida");
  const dt = el("dt", null, rotulo);
  const dd = el("dd", null, valor === "—" ? "—" : `${valor} ${unidade}`);
  caixa.append(dt, dd);
  return caixa;
}

function selo(online) {
  return el("span", `selo ${online ? "online" : "offline"}`, online ? "Online" : "Offline");
}

function topoDoCard(d) {
  const titulo = el("div");
  titulo.append(el("h3", null, d.descricao || d.id), el("p", "sub", `${d.id} · ${ambienteRotulo(d.ambiente)}`));
  const topo = el("div", "card-topo");
  topo.append(titulo, selo(d.online));
  return topo;
}

/** Bloco do ITGU: valor grande + classificação (cor e texto). */
function blocoItgu(leitura, situacao) {
  const info = CLASSIFICACAO[situacao.classificacao] || CLASSIFICACAO.sem_faixa;
  const bloco = el("div", `itgu ${info.css}`);
  bloco.append(
    el("span", "itgu-valor", numero(leitura.itgu, 1)),
    el("span", "itgu-rotulo", "ITGU"),
    el("span", "itgu-texto", info.texto),
  );
  return bloco;
}

function linhaFaixa(situacao) {
  const partes = [];
  partes.push(situacao.idade_dias === null ? "Idade do lote não informada" : `Lote com ${diasRotulo(situacao.idade_dias)}`);
  if (situacao.faixa) {
    const f = situacao.faixa;
    const manual = situacao.origem_faixa === "manual" ? " (escolhida manualmente)" : "";
    partes.push(`Faixa: ${f.nome}${manual}`);
    partes.push(`Conforto: ${numero(f.conforto_min, 1)} a ${numero(f.conforto_max, 1)}`);
  } else {
    partes.push("Faixa: sem faixa definida");
  }
  return el("p", "faixa", partes.join(" · "));
}

/** Card de um dispositivo ativo, com a última leitura. */
function montarCard(d, ultima) {
  const card = el("article", "card");
  card.dataset.id = d.id;
  card.append(topoDoCard(d));

  const leitura = ultima.leitura;
  if (!leitura) {
    card.append(el("p", "aguardando", "Aguardando primeira leitura"));
    return card;
  }

  const medidas = el("dl", "medidas");
  medidas.append(
    medida("Temperatura interna", numero(leitura.t_int, 1), "°C"),
    medida("Umidade interna", numero(leitura.ur_int, 0), "%"),
    medida("Temperatura de globo", numero(leitura.t_globo, 1), "°C"),
    medida("Temperatura externa", numero(leitura.t_ext, 1), "°C"),
  );
  card.append(
    blocoItgu(leitura, ultima.situacao),
    medidas,
    linhaFaixa(ultima.situacao),
    el("p", "sub", `Última leitura ${haQuanto(leitura.ts)} (${dataHora(leitura.ts)})`),
  );
  return card;
}

/** Card compacto de dispositivo inativo. */
function montarCardInativo(d) {
  const card = el("article", "card inativo");
  card.dataset.id = d.id;
  card.append(topoDoCard(d));
  card.append(el("p", "sub", d.ultima_leitura_em ? `Última leitura em ${dataHora(d.ultima_leitura_em)}` : "Nunca enviou leituras"));
  return card;
}

function mostrar(elemento, texto) {
  elemento.textContent = texto;
  elemento.hidden = !texto;
}

async function atualizar() {
  if (emAndamento) return;
  emAndamento = true;
  try {
    const dispositivos = await api("GET", "/dispositivos");
    const ativos = dispositivos.filter((d) => d.ativo);
    const inativos = dispositivos.filter((d) => !d.ativo);
    // última leitura de cada ativo, em paralelo
    const ultimas = await Promise.all(ativos.map((d) => api("GET", `/dispositivos/${encodeURIComponent(d.id)}/ultima`)));

    const cards = ativos.map((d, i) => montarCard(d, ultimas[i]));
    if (cards.length === 0) cards.push(el("p", "sub", "Nenhum dispositivo ativo."));
    listaAtivos.replaceChildren(...cards);

    listaInativos.replaceChildren(...inativos.map(montarCardInativo));
    blocoInativos.hidden = inativos.length === 0;
    resumoInativos.textContent = `Dispositivos inativos (${inativos.length})`;

    temDados = true;
    horaUltimaAtualizacao = hora();
    mostrar(avisoEl, "");
    mostrar(erroEl, "");
    mostrar(atualizadoEl, `atualizado às ${horaUltimaAtualizacao}`);
  } catch (e) {
    if (temDados) {
      // mantém o que já está na tela e avisa de forma discreta
      mostrar(avisoEl, `Não foi possível atualizar agora. Exibindo os dados de ${horaUltimaAtualizacao}.`);
    } else {
      mostrar(erroEl, e instanceof TypeError ? "Sem conexão com o servidor." : e.message);
    }
  } finally {
    carregando.hidden = true;
    emAndamento = false;
  }
}

atualizar();
setInterval(atualizar, INTERVALO_MS);
