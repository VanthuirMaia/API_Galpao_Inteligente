// Administração de dispositivos: lista, novo, editar (alojamento, faixa manual, ativo).
import { api } from "./api.js";
import {
  abrirDialogo, configurarDialogo, copiar, erroNoDialogo, fecharDialogo, linhaInfo, mostrarAviso,
  mostrarErroDialogo, mostrarErroPagina, pedirConfirmacao, semPermissao, textoDoErro,
} from "./admin.js";
import { ambienteRotulo, dataCurta, diasRotulo, el, haQuanto, hojeRecifeISO, idadeEmDias } from "./formato.js";
import { montarLayout } from "./layout.js";
import { exigirAdmin } from "./sessao.js";

exigirAdmin();
montarLayout();

const REGRA_ID = /^[a-z0-9_-]{3,32}$/; // a mesma da API (o id também é usuário MQTT e parte do tópico)

const principal = document.getElementById("principal");
const lista = document.getElementById("lista");
const carregando = document.getElementById("carregando");
const dlgNovo = document.getElementById("dlg-novo");
const dlgCriado = document.getElementById("dlg-criado");
const dlgEditar = document.getElementById("dlg-editar");
[dlgNovo, dlgCriado, dlgEditar].forEach(configurarDialogo);

let dispositivos = [];
let editando = null; // dispositivo aberto no diálogo de edição

// ---------- lista ----------

function cartao(d) {
  const card = el("article", d.ativo ? "card" : "card inativo");
  card.dataset.id = d.id;

  const titulo = el("div");
  titulo.append(el("h3", null, d.descricao || d.id), el("p", "sub", `${d.id} · ${ambienteRotulo(d.ambiente)}`));
  const selos = el("div");
  selos.append(el("span", `selo ${d.online ? "online" : "offline"}`, d.online ? "Online" : "Offline"));
  if (!d.ativo) selos.append(" ", el("span", "chip inativo", "Inativo"));
  const topo = el("div", "card-topo");
  topo.append(titulo, selos);
  card.append(topo);

  const sit = d.situacao;
  const lote = d.data_alojamento
    ? `alojado em ${dataCurta(d.data_alojamento)} (${diasRotulo(sit.idade_dias)})`
    : "lote não informado";
  let faixa = "sem faixa definida";
  if (sit.faixa) faixa = `${sit.faixa.nome} (${sit.origem_faixa === "manual" ? "escolhida à mão" : "pela idade"})`;
  card.append(
    linhaInfo("Última leitura", d.ultima_leitura_em ? haQuanto(d.ultima_leitura_em) : "nunca recebida"),
    linhaInfo("Lote", lote),
    linhaInfo("Faixa em uso", faixa),
  );

  const editar = el("button", "botao-simples claro pequeno", "Editar");
  editar.type = "button";
  editar.dataset.acao = "editar";
  editar.addEventListener("click", () => abrirEdicao(d));
  const acoes = el("div", "acoes-card");
  acoes.append(editar);
  card.append(acoes);
  return card;
}

async function carregar() {
  try {
    dispositivos = await api("GET", "/dispositivos");
    lista.replaceChildren(...dispositivos.map(cartao));
    mostrarErroPagina("");
    principal.dataset.estado = "ok";
  } catch (e) {
    if (e.status === 403) return semPermissao();
    mostrarErroPagina(textoDoErro(e));
    principal.dataset.estado = "erro";
  } finally {
    carregando.hidden = true;
  }
}

// ---------- novo dispositivo ----------

document.getElementById("btn-novo").addEventListener("click", () => {
  document.getElementById("form-novo").reset();
  abrirDialogo(dlgNovo);
  document.getElementById("novo-id").focus();
});

document.getElementById("form-novo").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const id = document.getElementById("novo-id").value.trim();
  const ambiente = document.getElementById("novo-ambiente").value;
  const descricao = document.getElementById("novo-descricao").value.trim();

  if (!REGRA_ID.test(id)) {
    mostrarErroDialogo(dlgNovo, "Id inválido: use 3 a 32 caracteres, só letras minúsculas, números, - e _.");
    return;
  }
  try {
    const criado = await api("POST", "/dispositivos", { id, ambiente, descricao: descricao || null });
    fecharDialogo(dlgNovo);
    document.getElementById("criado-aviso").textContent = criado.aviso;
    document.getElementById("criado-comando").textContent = `sh scripts/criar_usuario_mqtt.sh ${criado.id} <senha>`;
    abrirDialogo(dlgCriado);
    carregar();
  } catch (e) {
    erroNoDialogo(dlgNovo, e);
  }
});

document.getElementById("copiar-comando").addEventListener("click", (evento) => {
  copiar(document.getElementById("criado-comando").textContent, evento.currentTarget);
});

// ---------- editar ----------

function atualizarPrevia() {
  const data = document.getElementById("ed-data").value;
  const previa = document.getElementById("ed-previa");
  if (!data) {
    previa.textContent = "Lote não informado: sem data, a faixa pela idade não pode ser escolhida.";
  } else if (data > hojeRecifeISO()) {
    previa.textContent = "A data de alojamento não pode ser futura.";
  } else {
    previa.textContent = `Com esta data, o lote tem ${diasRotulo(idadeEmDias(data))} hoje.`;
  }
}

async function abrirEdicao(d) {
  editando = d;
  document.getElementById("editar-id").textContent = `${d.id}`;
  document.getElementById("ed-descricao").value = d.descricao || "";
  document.getElementById("ed-ambiente").value = d.ambiente;
  document.getElementById("ed-ativo").checked = d.ativo;
  const campoData = document.getElementById("ed-data");
  campoData.max = hojeRecifeISO();
  campoData.value = d.data_alojamento || "";
  atualizarPrevia();

  // faixas ativas para a escolha manual
  const select = document.getElementById("ed-faixa");
  const automatica = el("option", null, "Automática pela idade do lote");
  automatica.value = "";
  select.replaceChildren(automatica);
  try {
    const faixas = (await api("GET", "/faixas")).filter((f) => f.ativo);
    for (const f of faixas) {
      const o = el("option", null, `${f.nome} (${f.idade_inicio_dias} a ${f.idade_fim_dias} dias)`);
      o.value = String(f.id);
      select.append(o);
    }
  } catch (e) {
    if (e.status === 403) return semPermissao();
  }
  select.value = d.faixa_manual_id === null ? "" : String(d.faixa_manual_id);
  abrirDialogo(dlgEditar);
}

document.getElementById("ed-data").addEventListener("input", atualizarPrevia);

document.getElementById("encerrar-lote").addEventListener("click", async () => {
  if (!editando.data_alojamento) {
    mostrarErroDialogo(dlgEditar, "Este dispositivo não tem lote informado.");
    return;
  }
  const confirmou = await pedirConfirmacao(
    dlgEditar,
    "Encerrar o lote apaga a data de alojamento. Sem ela, a faixa pela idade deixa de valer e o dispositivo aparece como 'sem faixa definida' (a menos que tenha faixa escolhida à mão).",
  );
  if (!confirmou) return;
  try {
    await api("PATCH", `/dispositivos/${encodeURIComponent(editando.id)}`, { data_alojamento: null });
    fecharDialogo(dlgEditar);
    mostrarAviso("Lote encerrado.");
    carregar();
  } catch (e) {
    erroNoDialogo(dlgEditar, e);
  }
});

document.getElementById("form-editar").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const d = editando;
  const descricao = document.getElementById("ed-descricao").value.trim();
  const ambiente = document.getElementById("ed-ambiente").value;
  const ativo = document.getElementById("ed-ativo").checked;
  const data = document.getElementById("ed-data").value || null;
  const faixa = document.getElementById("ed-faixa").value;

  if (data && data > hojeRecifeISO()) {
    mostrarErroDialogo(dlgEditar, "A data de alojamento não pode ser futura.");
    return;
  }

  // só envia o que mudou
  const mudancas = {};
  if (descricao !== (d.descricao || "")) mudancas.descricao = descricao || null;
  if (ambiente !== d.ambiente) mudancas.ambiente = ambiente;
  if (ativo !== d.ativo) mudancas.ativo = ativo;
  if (data !== d.data_alojamento) mudancas.data_alojamento = data;
  const faixaId = faixa === "" ? null : Number(faixa);
  if (faixaId !== d.faixa_manual_id) mudancas.faixa_manual_id = faixaId;

  if (Object.keys(mudancas).length === 0) {
    fecharDialogo(dlgEditar);
    return;
  }
  if (mudancas.ativo === false) {
    const confirmou = await pedirConfirmacao(
      dlgEditar,
      "As mensagens deste ESP passarão a ser rejeitadas em até 5 minutos (é o tempo do cache do ingestor) e ele sairá da visão geral e do histórico.",
    );
    if (!confirmou) return;
  }
  try {
    await api("PATCH", `/dispositivos/${encodeURIComponent(d.id)}`, mudancas);
    fecharDialogo(dlgEditar);
    mostrarAviso("Dispositivo atualizado.");
    carregar();
  } catch (e) {
    erroNoDialogo(dlgEditar, e);
  }
});

carregar();
