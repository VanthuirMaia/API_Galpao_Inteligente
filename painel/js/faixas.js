// Administração das faixas de ITGU por idade.
import { api } from "./api.js";
import {
  abrirDialogo, configurarDialogo, erroNoDialogo, fecharDialogo, linhaInfo, mostrarAviso,
  mostrarErroDialogo, mostrarErroPagina, semPermissao, textoDoErro,
} from "./admin.js";
import { el, numero } from "./formato.js";
import { montarLayout } from "./layout.js";
import { exigirAdmin } from "./sessao.js";

exigirAdmin();
montarLayout();

const principal = document.getElementById("principal");
const lista = document.getElementById("lista");
const carregando = document.getElementById("carregando");
const semFaixas = document.getElementById("sem-faixas");
const coberturaEl = document.getElementById("cobertura");
const dlgFaixa = document.getElementById("dlg-faixa");
const dlgConfirma = document.getElementById("dlg-confirma");
[dlgFaixa, dlgConfirma].forEach(configurarDialogo);

const CAMPOS = {
  nome: "f-nome", idade_inicio_dias: "f-ini", idade_fim_dias: "f-fim",
  critico_min: "f-cmin", conforto_min: "f-mmin", conforto_max: "f-mmax", critico_max: "f-cmax",
};

let faixas = [];
let editandoId = null; // null = nova faixa
let acaoConfirmada = null; // função chamada pelo botão Confirmar do diálogo de confirmação

// ---------- régua e cobertura ----------

/** Barra com as 5 zonas (crítico, alerta, conforto, alerta, crítico). O tamanho vem de --peso (CSSOM). */
function regua(f) {
  const margem = (f.critico_max - f.critico_min) * 0.2;
  const pesos = [
    ["critico", margem],
    ["alerta", f.conforto_min - f.critico_min],
    ["conforto", f.conforto_max - f.conforto_min],
    ["alerta", f.critico_max - f.conforto_max],
    ["critico", margem],
  ];
  const barra = el("div", "regua");
  barra.setAttribute("aria-hidden", "true");
  for (const [classe, peso] of pesos) {
    const zona = el("span", `zona ${classe}`);
    zona.style.setProperty("--peso", String(peso));
    barra.append(zona);
  }
  return barra;
}

/** Faixas de idade sem faixa ativa entre 0 e a maior idade cadastrada. */
function lacunasDeIdade(ativas) {
  const ordenadas = [...ativas].sort((a, b) => a.idade_inicio_dias - b.idade_inicio_dias);
  const lacunas = [];
  let proxima = 0; // primeira idade ainda não coberta
  for (const f of ordenadas) {
    if (f.idade_inicio_dias > proxima) lacunas.push([proxima, f.idade_inicio_dias - 1]);
    proxima = Math.max(proxima, f.idade_fim_dias + 1);
  }
  return lacunas;
}

function textoCobertura(ativas) {
  const lacunas = lacunasDeIdade(ativas);
  const maior = Math.max(...ativas.map((f) => f.idade_fim_dias));
  if (lacunas.length === 0) return `Todas as idades de 0 a ${maior} dias têm faixa. Idades acima de ${maior} dias ficam sem faixa.`;
  const partes = lacunas.map(([a, b]) => (a === b ? `idade ${a}` : `idades ${a} a ${b}`));
  return `Sem faixa ativa: ${partes.join("; ")}.`;
}

// ---------- lista ----------

function cartao(f) {
  const card = el("article", f.ativo ? "card" : "card inativo");
  card.dataset.id = String(f.id);

  const titulo = el("div");
  titulo.append(el("h3", null, f.nome), el("p", "sub", `idades ${f.idade_inicio_dias} a ${f.idade_fim_dias} dias`));
  const topo = el("div", "card-topo");
  topo.append(titulo, el("span", f.ativo ? "selo online" : "selo offline", f.ativo ? "Ativa" : "Inativa"));
  card.append(topo, regua(f));
  card.append(
    el("p", "sub", `Crítico abaixo de ${numero(f.critico_min, 1)} · Conforto de ${numero(f.conforto_min, 1)} a ${numero(f.conforto_max, 1)} · Crítico acima de ${numero(f.critico_max, 1)}`),
    linhaInfo("Alerta", `de ${numero(f.critico_min, 1)} a ${numero(f.conforto_min, 1)} e de ${numero(f.conforto_max, 1)} a ${numero(f.critico_max, 1)}`),
  );

  const editar = el("button", "botao-simples claro pequeno", "Editar");
  editar.type = "button";
  editar.dataset.acao = "editar";
  editar.addEventListener("click", () => abrirFormulario(f));
  const alternar = el("button", `botao-simples pequeno ${f.ativo ? "perigo" : ""}`.trim(), f.ativo ? "Desativar" : "Reativar");
  alternar.type = "button";
  alternar.dataset.acao = "alternar";
  alternar.addEventListener("click", () => pedirAlternar(f));
  const acoes = el("div", "acoes-card");
  acoes.append(editar, alternar);
  card.append(acoes);
  return card;
}

async function carregar() {
  try {
    faixas = await api("GET", "/faixas");
    lista.replaceChildren(...faixas.map(cartao));
    const ativas = faixas.filter((f) => f.ativo);
    semFaixas.hidden = ativas.length > 0;
    coberturaEl.hidden = ativas.length === 0;
    if (ativas.length > 0) {
      coberturaEl.textContent = textoCobertura(ativas);
      coberturaEl.className = `msg ${lacunasDeIdade(ativas).length > 0 ? "aviso" : "ok"}`;
    }
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

// ---------- nova / editar ----------

function abrirFormulario(faixa) {
  editandoId = faixa ? faixa.id : null;
  document.getElementById("t-faixa").textContent = faixa ? "Editar faixa" : "Nova faixa";
  for (const [campo, id] of Object.entries(CAMPOS)) {
    document.getElementById(id).value = faixa ? String(faixa[campo]) : "";
  }
  abrirDialogo(dlgFaixa);
  document.getElementById("f-nome").focus();
}

/** Lê e valida o formulário (mesmas regras da API). Devolve {dados} ou {erro}. */
function lerFormulario() {
  const nome = document.getElementById(CAMPOS.nome).value.trim();
  const numeros = {};
  for (const campo of Object.keys(CAMPOS).filter((c) => c !== "nome")) {
    const texto = document.getElementById(CAMPOS[campo]).value.trim();
    numeros[campo] = texto === "" ? NaN : Number(texto);
  }
  if (!nome) return { erro: "Informe o nome da faixa." };
  if (Object.values(numeros).some((v) => Number.isNaN(v))) return { erro: "Preencha todos os números." };
  const { idade_inicio_dias: ini, idade_fim_dias: fim, critico_min: cmin, conforto_min: mmin, conforto_max: mmax, critico_max: cmax } = numeros;
  if (!Number.isInteger(ini) || !Number.isInteger(fim) || ini < 0) return { erro: "As idades devem ser números inteiros, a partir de 0." };
  if (fim < ini) return { erro: "A idade fim deve ser maior ou igual à idade início." };
  if (!(cmin < mmin && mmin < mmax && mmax < cmax)) {
    return { erro: "Os limites devem obedecer: crítico mínimo < conforto mínimo < conforto máximo < crítico máximo." };
  }
  return { dados: { nome, ...numeros } };
}

document.getElementById("btn-nova").addEventListener("click", () => abrirFormulario(null));

document.getElementById("form-faixa").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const { dados, erro } = lerFormulario();
  if (erro) {
    mostrarErroDialogo(dlgFaixa, erro);
    return;
  }
  try {
    if (editandoId === null) await api("POST", "/faixas", dados);
    else await api("PATCH", `/faixas/${editandoId}`, dados);
    fecharDialogo(dlgFaixa);
    mostrarAviso(editandoId === null ? "Faixa criada." : "Faixa atualizada.");
    carregar();
  } catch (e) {
    erroNoDialogo(dlgFaixa, e); // 409 (sobreposição) e 422 aparecem no formulário
  }
});

// ---------- desativar / reativar ----------

function pedirAlternar(f) {
  const desativar = f.ativo;
  document.getElementById("t-confirma").textContent = desativar ? `Desativar "${f.nome}"?` : `Reativar "${f.nome}"?`;
  document.getElementById("confirma-texto").textContent = desativar
    ? "Dispositivos que usam esta faixa pela idade do lote passarão a aparecer como 'sem faixa definida'. O histórico continua, mas a classificação deixa de existir para essas idades."
    : "A faixa volta a valer para as idades dela. Se outra faixa ativa cobrir as mesmas idades, a API vai recusar.";
  acaoConfirmada = async () => {
    await api("PATCH", `/faixas/${f.id}`, { ativo: !f.ativo });
    mostrarAviso(desativar ? "Faixa desativada." : "Faixa reativada.");
  };
  abrirDialogo(dlgConfirma);
}

document.getElementById("confirma-ok").addEventListener("click", async () => {
  try {
    await acaoConfirmada();
    fecharDialogo(dlgConfirma);
    carregar();
  } catch (e) {
    erroNoDialogo(dlgConfirma, e); // 409: faixa em uso manual, com o id do dispositivo
  }
});

carregar();
