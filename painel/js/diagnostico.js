// Diagnóstico: situação dos dispositivos e mensagens rejeitadas (para quem cuida do firmware).
import { api } from "./api.js";
import { dataHora, dispositivoDoTopico, el, haQuanto, hora, motivoAmigavel, sinalWifi } from "./formato.js";
import { montarLayout } from "./layout.js";
import { exigirLogin } from "./sessao.js";

exigirLogin();
montarLayout();

const INTERVALO_MS = 30000;
const LIMITE_ERROS = 50;

const principal = document.getElementById("principal");
const listaSituacao = document.getElementById("lista-situacao");
const filtro = document.getElementById("filtro-dispositivo");
const auto = document.getElementById("auto");
const tabela = document.getElementById("tabela-erros");
const corpoErros = document.getElementById("corpo-erros");
const semErros = document.getElementById("sem-erros");
const avisoEl = document.getElementById("aviso");
const erroEl = document.getElementById("erro");
const atualizadoEl = document.getElementById("atualizado");

let temDados = false;
let horaUltima = null;
let emAndamento = false;

function mostrar(elemento, texto) {
  elemento.textContent = texto;
  elemento.hidden = !texto;
}

function chip(info) {
  return el("span", `chip ${info.css}`, info.texto);
}

function linha(rotulo, ...conteudo) {
  const p = el("p", "linha-diag");
  p.append(el("span", "sub", `${rotulo}:`), ...conteudo);
  return p;
}

// ---------- situação dos dispositivos ----------

function cartaoSituacao(d, leitura) {
  const card = el("article", "card");
  card.dataset.id = d.id;

  const titulo = el("div");
  titulo.append(el("h3", null, d.descricao || d.id), el("p", "sub", d.id));
  const topo = el("div", "card-topo");
  topo.append(titulo, el("span", `selo ${d.online ? "online" : "offline"}`, d.online ? "Online" : "Offline"));
  card.append(topo);

  card.append(
    linha("Última leitura", el("span", null, d.ultima_leitura_em ? `${haQuanto(d.ultima_leitura_em)} (${dataHora(d.ultima_leitura_em)})` : "nunca recebida")),
  );

  const rssi = leitura ? leitura.rssi : null;
  const detalheRssi = rssi === null || rssi === undefined ? "" : `${rssi} dBm`;
  card.append(linha("Sinal Wi-Fi", chip(sinalWifi(rssi)), el("span", "sub", detalheRssi)));

  if (leitura && leitura.ts_origem === "servidor") {
    card.append(el("p", "msg aviso", "O ESP não está enviando horário válido (verifique o NTP). O horário das leituras vem do servidor."));
  } else if (leitura) {
    card.append(linha("Horário das leituras", el("span", null, "enviado pelo ESP")));
  }
  return card;
}

// ---------- mensagens rejeitadas ----------

function celula(rotulo, ...conteudo) {
  const td = el("td");
  td.dataset.rotulo = rotulo; // usado pelo CSS para rotular o cartão no celular
  td.append(...conteudo);
  return td;
}

function linhaErro(e) {
  const motivo = el("span", null, motivoAmigavel(e.motivo));
  const codigo = el("span", "codigo", e.motivo);

  const detalhes = el("details");
  detalhes.append(el("summary", null, "Ver mensagem"), el("pre", "payload", e.payload || "(vazia)"));

  const tr = el("tr");
  tr.append(
    celula("Hora", el("span", null, dataHora(e.recebido_em))),
    celula("Dispositivo", el("span", null, dispositivoDoTopico(e.topico))),
    celula("Motivo", motivo, codigo),
    celula("Mensagem", detalhes),
  );
  return tr;
}

/** Preserva os <details> abertos entre atualizações (chave: hora + motivo + payload). */
function chaveErro(e) {
  return `${e.recebido_em}|${e.motivo}|${e.payload}`;
}

async function atualizar() {
  if (emAndamento) return;
  emAndamento = true;
  try {
    const dispositivos = await api("GET", "/dispositivos");
    const ativos = dispositivos.filter((d) => d.ativo);
    const parametro = filtro.value ? `&device_id=${encodeURIComponent(filtro.value)}` : "";
    const [ultimas, erros] = await Promise.all([
      Promise.all(ativos.map((d) => api("GET", `/dispositivos/${encodeURIComponent(d.id)}/ultima`))),
      api("GET", `/erros?limite=${LIMITE_ERROS}${parametro}`),
    ]);

    // lista do filtro: todos os dispositivos cadastrados (um inativo também pode ter enviado erros)
    if (filtro.options.length !== dispositivos.length + 1) {
      const atual = filtro.value;
      const opcoes = dispositivos.map((d) => {
        const o = el("option", null, d.id);
        o.value = d.id;
        return o;
      });
      const todos = el("option", null, "Todos");
      todos.value = "";
      filtro.replaceChildren(todos, ...opcoes);
      filtro.value = atual;
    }

    const abertos = new Set(
      [...corpoErros.querySelectorAll("details[open]")].map((d) => d.closest("tr").dataset.chave),
    );
    listaSituacao.replaceChildren(...ativos.map((d, i) => cartaoSituacao(d, ultimas[i].leitura)));
    if (ativos.length === 0) listaSituacao.replaceChildren(el("p", "sub", "Nenhum dispositivo ativo."));

    const linhas = erros.map((e) => {
      const tr = linhaErro(e);
      tr.dataset.chave = chaveErro(e);
      if (abertos.has(tr.dataset.chave)) tr.querySelector("details").open = true;
      return tr;
    });
    corpoErros.replaceChildren(...linhas);
    tabela.hidden = linhas.length === 0;
    semErros.hidden = linhas.length !== 0;

    temDados = true;
    horaUltima = hora();
    mostrar(avisoEl, "");
    mostrar(erroEl, "");
    mostrar(atualizadoEl, `atualizado às ${horaUltima}`);
    principal.dataset.estado = "ok";
  } catch (e) {
    if (temDados) {
      mostrar(avisoEl, `Não foi possível atualizar agora. Exibindo os dados de ${horaUltima}.`);
    } else {
      mostrar(erroEl, e instanceof TypeError ? "Sem conexão com o servidor." : e.message);
      principal.dataset.estado = "erro";
    }
  } finally {
    emAndamento = false;
  }
}

filtro.addEventListener("change", atualizar);
setInterval(() => {
  if (auto.checked) atualizar();
}, INTERVALO_MS);
atualizar();
