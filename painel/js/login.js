// Tela de login.
import { api, login } from "./api.js";
import { montarRodape } from "./layout.js";
import { caminhoInternoSeguro, lerSessao, salvarSessao } from "./sessao.js";

montarRodape();

const form = document.getElementById("form-login");
const campoEmail = document.getElementById("email");
const campoSenha = document.getElementById("senha");
const botao = document.getElementById("entrar");
const erro = document.getElementById("erro");

/** Destino depois do login: ?volta= só se for caminho interno; senão a visão geral. */
function destino() {
  const volta = new URLSearchParams(location.search).get("volta");
  return caminhoInternoSeguro(volta) ? volta : "index.html";
}

function mostrarErro(texto) {
  erro.textContent = texto;
  erro.hidden = !texto;
}

// já tem sessão válida? vai direto (o /auth/me confirma que o token ainda vale)
if (lerSessao()) {
  api("GET", "/auth/me").then(() => location.replace(destino())).catch(() => {});
}

form.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  mostrarErro("");
  const email = campoEmail.value.trim();
  const senha = campoSenha.value;
  if (!email || !senha) {
    mostrarErro("Informe e-mail e senha.");
    return;
  }

  botao.disabled = true;
  botao.textContent = "Entrando…";
  try {
    const r = await login(email, senha);
    salvarSessao({ token: r.access_token, nome: r.nome, perfil: r.perfil });
    location.replace(destino());
  } catch (e) {
    mostrarErro(e instanceof TypeError ? "Sem conexão com o servidor." : e.message);
    botao.disabled = false;
    botao.textContent = "Entrar";
  }
});
