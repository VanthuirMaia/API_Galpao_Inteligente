// Cliente da API. Tudo que fala com o servidor passa por aqui.
import { irParaLogin, limparSessao, token } from "./sessao.js";

export const BASE = "/api";

/** Extrai a mensagem do corpo de erro da API ("detail" texto ou lista de erros de validação). */
async function mensagemDeErro(resposta) {
  try {
    const corpo = await resposta.json();
    const detalhe = corpo.detail;
    if (typeof detalhe === "string") return detalhe;
    if (Array.isArray(detalhe)) return detalhe.map((d) => d.msg || String(d)).join("; ");
  } catch {
    // corpo vazio ou não JSON
  }
  return `Erro ${resposta.status}`;
}

/**
 * Chama a API com o token da sessão. Corpo e resposta em JSON.
 * 401: limpa a sessão e vai para o login. Outros erros: lança Error com a mensagem da API.
 */
export async function api(metodo, caminho, corpo) {
  const cabecalhos = {};
  const tk = token();
  if (tk) cabecalhos.Authorization = `Bearer ${tk}`;
  const opcoes = { method: metodo, headers: cabecalhos };
  if (corpo !== undefined) {
    cabecalhos["Content-Type"] = "application/json";
    opcoes.body = JSON.stringify(corpo);
  }

  const resposta = await fetch(BASE + caminho, opcoes); // falha de rede lança TypeError
  if (resposta.status === 401) {
    limparSessao();
    irParaLogin();
    throw new Error("Sessão expirada. Entre novamente.");
  }
  if (!resposta.ok) throw new Error(await mensagemDeErro(resposta));
  if (resposta.status === 204) return null;
  return resposta.json();
}

/** Login OAuth2: formulário urlencoded com username (e-mail) e password. */
export async function login(email, senha) {
  const corpo = new URLSearchParams({ username: email, password: senha });
  const resposta = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: corpo,
  });
  if (resposta.status === 429) throw new Error("Muitas tentativas. Aguarde um minuto.");
  if (!resposta.ok) throw new Error(await mensagemDeErro(resposta));
  return resposta.json(); // {access_token, token_type, perfil, nome}
}
