// Minha conta: dados do usuário e troca de senha.
import { api } from "./api.js";
import { montarLayout } from "./layout.js";
import { exigirLogin, salvarToken } from "./sessao.js";

exigirLogin();
montarLayout();

const SENHA_MIN = 10;

const form = document.getElementById("form-senha");
const campoAtual = document.getElementById("senha-atual");
const campoNova = document.getElementById("senha-nova");
const campoConfirma = document.getElementById("senha-confirma");
const botao = document.getElementById("trocar");
const mensagem = document.getElementById("msg-senha");

function mostrarMensagem(texto, tipo) {
  mensagem.textContent = texto;
  mensagem.className = `msg ${tipo}`;
  mensagem.hidden = !texto;
}

async function carregarDados() {
  try {
    const eu = await api("GET", "/auth/me");
    document.getElementById("d-nome").textContent = eu.nome;
    document.getElementById("d-email").textContent = eu.email;
    document.getElementById("d-perfil").textContent = eu.perfil === "admin" ? "Administrador" : "Leitor";
  } catch (e) {
    const caixa = document.getElementById("erro-dados");
    caixa.textContent = e.message;
    caixa.hidden = false;
  }
}

form.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  mostrarMensagem("", "");
  const atual = campoAtual.value;
  const nova = campoNova.value;

  if (!atual) return mostrarMensagem("Informe a senha atual.", "erro");
  if (nova.length < SENHA_MIN) return mostrarMensagem(`A nova senha precisa ter pelo menos ${SENHA_MIN} caracteres.`, "erro");
  if (nova !== campoConfirma.value) return mostrarMensagem("A confirmação não confere com a nova senha.", "erro");
  if (nova === atual) return mostrarMensagem("A nova senha deve ser diferente da atual.", "erro");

  botao.disabled = true;
  try {
    const r = await api("POST", "/auth/senha", { senha_atual: atual, senha_nova: nova });
    salvarToken(r.access_token); // a API invalida os tokens antigos: guarda o novo para não deslogar
    form.reset();
    mostrarMensagem("Senha alterada com sucesso.", "ok");
  } catch (e) {
    mostrarMensagem(e instanceof TypeError ? "Sem conexão com o servidor." : e.message, "erro");
  } finally {
    botao.disabled = false;
  }
});

carregarDados();
