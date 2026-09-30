// Sessão do usuário no navegador (token, nome e perfil no localStorage).
// O perfil aqui serve só para esconder menu: quem garante a permissão é a API (403).

const CHAVE = "galpao_sessao";

/** Devolve {token, nome, perfil} ou null. */
export function lerSessao() {
  try {
    const bruto = localStorage.getItem(CHAVE);
    const dados = bruto ? JSON.parse(bruto) : null;
    return dados && dados.token ? dados : null;
  } catch {
    return null;
  }
}

export function salvarSessao(dados) {
  try {
    localStorage.setItem(CHAVE, JSON.stringify(dados));
  } catch {
    // armazenamento bloqueado: a sessão vale só até recarregar a página
  }
}

/** Troca só o token (ex.: depois de trocar a senha), mantendo nome e perfil. */
export function salvarToken(token) {
  const atual = lerSessao();
  if (atual) salvarSessao({ ...atual, token });
}

export function limparSessao() {
  try {
    localStorage.removeItem(CHAVE);
  } catch {
    // ignora
  }
}

export function token() {
  const s = lerSessao();
  return s ? s.token : null;
}

/** Só aceita caminhos internos ("/x"), nunca "//host" nem "/\host" (redirecionamento aberto). */
export function caminhoInternoSeguro(caminho) {
  return typeof caminho === "string" && caminho.startsWith("/") && !caminho.startsWith("//") && !caminho.startsWith("/\\");
}

export function irParaLogin() {
  if (location.pathname.endsWith("/login.html")) return; // já está no login: evita laço
  const volta = encodeURIComponent(location.pathname + location.search);
  location.replace("login.html?volta=" + volta);
}

/** Chamar no topo de toda página protegida. Devolve a sessão, ou redireciona. */
export function exigirLogin() {
  const s = lerSessao();
  if (!s) irParaLogin();
  return s;
}

/** Páginas de admin: quem não é admin volta para a visão geral. */
export function exigirAdmin() {
  const s = exigirLogin();
  if (s && s.perfil !== "admin") location.replace("index.html");
  return s;
}

export function sair() {
  limparSessao();
  location.replace("login.html");
}
