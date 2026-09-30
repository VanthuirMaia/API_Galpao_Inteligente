// Administração de usuários: lista, novo, editar, redefinir senha.
// O perfil no front só esconde menu; as regras de verdade (último admin, permissões) são da API.
import { api } from "./api.js";
import {
  abrirDialogo, configurarDialogo, copiar, erroNoDialogo, fecharDialogo, linhaInfo, mostrarAviso,
  mostrarErroDialogo, mostrarErroPagina, pedirConfirmacao, semPermissao, textoDoErro,
} from "./admin.js";
import { dataHora, el } from "./formato.js";
import { montarLayout } from "./layout.js";
import { exigirAdmin, lerSessao, limparSessao, salvarSessao } from "./sessao.js";

exigirAdmin();
montarLayout();

const SENHA_MIN = 10;
const SENHA_TAMANHO = 14;
// sem caracteres ambíguos: 0/O, 1/l/I
const ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789";
const REGRA_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const principal = document.getElementById("principal");
const lista = document.getElementById("lista");
const carregando = document.getElementById("carregando");
const dlgNovo = document.getElementById("dlg-novo");
const dlgEditar = document.getElementById("dlg-editar");
const dlgSenha = document.getElementById("dlg-senha");
[dlgNovo, dlgEditar].forEach(configurarDialogo);

let usuarios = [];
let meuId = null; // id do admin logado (vem de /auth/me)
let editando = null;
let sairAoFecharSenha = false; // redefiniu a própria senha: o token dele foi invalidado pela API

// ---------- senha gerada ----------

/** Senha aleatória de 14 caracteres com crypto.getRandomValues (sem viés de módulo). */
export function gerarSenha() {
  const n = ALFABETO.length;
  const limite = Math.floor(0x100000000 / n) * n; // descarta valores que causariam viés
  const saida = [];
  const buffer = new Uint32Array(1);
  while (saida.length < SENHA_TAMANHO) {
    crypto.getRandomValues(buffer);
    if (buffer[0] < limite) saida.push(ALFABETO[buffer[0] % n]);
  }
  return saida.join("");
}

/** Mostra a senha uma única vez. Ao fechar, o texto é apagado da tela. */
function mostrarSenhaUmaVez(usuario, senha, eraEuMesmo = false) {
  document.getElementById("senha-usuario").textContent = `${usuario.nome} (${usuario.email})`;
  document.getElementById("senha-gerada").textContent = senha;
  document.getElementById("senha-aviso-sessao").hidden = !eraEuMesmo;
  sairAoFecharSenha = eraEuMesmo;
  abrirDialogo(dlgSenha);
}

function fecharSenha() {
  document.getElementById("senha-gerada").textContent = ""; // não deixa a senha no DOM
  fecharDialogo(dlgSenha);
  if (sairAoFecharSenha) {
    // a API invalidou o token ao trocar a senha: volta ao login com a mensagem
    limparSessao();
    location.replace("login.html?msg=senha-alterada");
  }
}

document.getElementById("fechar-senha").addEventListener("click", fecharSenha);
dlgSenha.addEventListener("cancel", (evento) => {
  evento.preventDefault(); // Esc passa pelo mesmo caminho do botão Fechar
  fecharSenha();
});
document.getElementById("copiar-senha").addEventListener("click", (evento) => {
  copiar(document.getElementById("senha-gerada").textContent, evento.currentTarget);
});

// ---------- lista ----------

function cartao(u) {
  const card = el("article", u.ativo ? "card" : "card inativo");
  card.dataset.id = String(u.id);
  card.dataset.email = u.email;

  const titulo = el("div");
  titulo.append(el("h3", null, u.id === meuId ? `${u.nome} (você)` : u.nome), el("p", "sub", u.email));
  const selos = el("div");
  selos.append(el("span", `chip ${u.perfil === "admin" ? "alerta" : "sem_faixa"}`, u.perfil === "admin" ? "Administrador" : "Leitor"));
  if (!u.ativo) selos.append(" ", el("span", "chip inativo", "Inativo"));
  const topo = el("div", "card-topo");
  topo.append(titulo, selos);
  card.append(topo, linhaInfo("Último login", u.ultimo_login ? dataHora(u.ultimo_login) : "nunca"));

  const editar = el("button", "botao-simples claro pequeno", "Editar");
  editar.type = "button";
  editar.dataset.acao = "editar";
  editar.addEventListener("click", () => abrirEdicao(u));
  const acoes = el("div", "acoes-card");
  acoes.append(editar);
  card.append(acoes);
  return card;
}

async function carregar() {
  try {
    if (meuId === null) meuId = (await api("GET", "/auth/me")).id;
    usuarios = await api("GET", "/usuarios");
    lista.replaceChildren(...usuarios.map(cartao));
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

// ---------- novo usuário ----------

document.getElementById("btn-novo").addEventListener("click", () => {
  document.getElementById("form-novo").reset();
  abrirDialogo(dlgNovo);
  document.getElementById("n-nome").focus();
});

document.getElementById("gerar-senha").addEventListener("click", () => {
  document.getElementById("n-senha").value = gerarSenha();
});

document.getElementById("form-novo").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const nome = document.getElementById("n-nome").value.trim();
  const email = document.getElementById("n-email").value.trim().toLowerCase();
  const perfil = document.getElementById("n-perfil").value;
  const senha = document.getElementById("n-senha").value;

  if (!nome) return mostrarErroDialogo(dlgNovo, "Informe o nome.");
  if (!REGRA_EMAIL.test(email)) return mostrarErroDialogo(dlgNovo, "Informe um e-mail válido.");
  if (senha.length < SENHA_MIN) return mostrarErroDialogo(dlgNovo, `A senha precisa ter pelo menos ${SENHA_MIN} caracteres (use "Gerar senha").`);

  try {
    const criado = await api("POST", "/usuarios", { nome, email, perfil, senha });
    fecharDialogo(dlgNovo);
    document.getElementById("form-novo").reset(); // a senha não fica no formulário
    mostrarSenhaUmaVez(criado, senha);
    carregar();
  } catch (e) {
    erroNoDialogo(dlgNovo, e); // 409 (e-mail já cadastrado) e 422 aparecem no formulário
  }
});

// ---------- editar ----------

function abrirEdicao(u) {
  editando = u;
  document.getElementById("ed-email").textContent = u.email;
  document.getElementById("ed-nome").value = u.nome;
  document.getElementById("ed-perfil").value = u.perfil;
  document.getElementById("ed-ativo").checked = u.ativo;
  abrirDialogo(dlgEditar);
}

/** O admin se rebaixou: atualiza a sessão com o /auth/me e sai das telas de admin. */
async function aposMudarAPropriaConta() {
  try {
    const eu = await api("GET", "/auth/me");
    const sessao = lerSessao();
    salvarSessao({ ...sessao, nome: eu.nome, perfil: eu.perfil });
    location.replace("index.html");
  } catch {
    // se falhar (ex.: 401 por desativação), o api() já levou ao login
  }
}

document.getElementById("form-editar").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const u = editando;
  const souEu = u.id === meuId;
  const nome = document.getElementById("ed-nome").value.trim();
  const perfil = document.getElementById("ed-perfil").value;
  const ativo = document.getElementById("ed-ativo").checked;
  if (!nome) return mostrarErroDialogo(dlgEditar, "Informe o nome.");

  const mudancas = {};
  if (nome !== u.nome) mudancas.nome = nome;
  if (perfil !== u.perfil) mudancas.perfil = perfil;
  if (ativo !== u.ativo) mudancas.ativo = ativo;
  if (Object.keys(mudancas).length === 0) {
    fecharDialogo(dlgEditar);
    return;
  }

  // confirmações que explicam a consequência
  if (mudancas.ativo === false) {
    const texto = souEu
      ? "Você está desativando a SUA conta: será desconectado na hora e não conseguirá entrar de novo."
      : "O usuário será desconectado na hora e não conseguirá entrar até ser reativado.";
    if (!(await pedirConfirmacao(dlgEditar, texto))) return;
  } else if (souEu && mudancas.perfil === "leitor") {
    const texto = "Você está deixando de ser administrador: perderá o acesso a estas telas assim que salvar.";
    if (!(await pedirConfirmacao(dlgEditar, texto))) return;
  }

  try {
    await api("PATCH", `/usuarios/${u.id}`, mudancas);
    fecharDialogo(dlgEditar);
    if (souEu && mudancas.ativo === false) {
      limparSessao();
      location.replace("login.html");
      return;
    }
    if (souEu && mudancas.perfil === "leitor") {
      await aposMudarAPropriaConta();
      return;
    }
    if (souEu && mudancas.nome) salvarSessao({ ...lerSessao(), nome });
    mostrarAviso("Usuário atualizado.");
    carregar();
  } catch (e) {
    erroNoDialogo(dlgEditar, e); // 409 do último admin: mensagem da API no formulário
  }
});

document.getElementById("redefinir").addEventListener("click", async () => {
  const u = editando;
  const souEu = u.id === meuId;
  const texto = souEu
    ? "Será gerada uma nova senha para a SUA conta. Depois disso você será desconectado e precisará entrar com a nova senha."
    : "Será gerada uma nova senha. A senha atual deixa de funcionar e o usuário será desconectado.";
  if (!(await pedirConfirmacao(dlgEditar, texto))) return;

  const senha = gerarSenha();
  try {
    await api("POST", `/usuarios/${u.id}/senha`, { senha });
    fecharDialogo(dlgEditar);
    mostrarSenhaUmaVez(u, senha, souEu);
    if (!souEu) carregar();
  } catch (e) {
    erroNoDialogo(dlgEditar, e);
  }
});

carregar();
