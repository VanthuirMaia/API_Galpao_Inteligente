// Menu lateral, usuário e rodapé compartilhados pelas páginas internas (o mesmo menu da página principal).
import { el } from "./formato.js";
import { lerSessao, sair } from "./sessao.js";

const PROJETO = "Projeto Galpão Inteligente";
const EQUIPE = "Equipe de desenvolvimento: alunos e professores do Espaço CRIA, ETEGEC.";
const APOIO_TEXTO = "Desenvolvido no Espaço CRIA da ETEGEC com apoio da FACEPE, processo ARC-0572-1.03/26.";
// Marcas parceiras servidas localmente (img/parceiros): a CSP do painel só aceita imagens do próprio site.
const APOIADORES = [
  { arq: "see.png", classe: "see", alt: "Secretaria de Educação de Pernambuco (SEE-PE)" },
  { arq: "secti.png", classe: "secti", alt: "Secretaria de Ciência, Tecnologia e Inovação de Pernambuco (SECTI-PE)" },
  { arq: "ete.svg", classe: "ete", alt: "ETE — Escola Técnica Estadual Governador Eduardo Campos" },
  { arq: "facepe.png", classe: "facepe", alt: "Fundação de Amparo à Ciência e Tecnologia de Pernambuco (FACEPE)" },
  { arq: "agil.png", classe: "agil", alt: "Agil Pernambuco" },
];

// Ícones: constantes do código (nunca dado da API), mesmos traços da página principal.
const ICONES = {
  inicio: '<path d="m3 11 9-8 9 8v10h-6v-6H9v6H3z" stroke-linejoin="round"/>',
  galpao: '<path d="M3 10 12 3l9 7M5 9v12h14V9M9 21v-7h6v7" stroke-linejoin="round"/>',
  grafico: '<path d="M3 3v18h18M6 15l5-5 4 3 6-7M17 6h4v4" stroke-linecap="round" stroke-linejoin="round"/>',
  sino: '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15L6 16Z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  engrenagem: '<circle cx="12" cy="12" r="3"/><path d="m19.4 15 .1.1 1.2 1-1.6 2.8-1.5-.5a8 8 0 0 1-1.6.9l-.3 1.6h-3.2l-.3-1.6a8 8 0 0 1-1.6-.9l-1.5.5-1.6-2.8 1.2-1a8 8 0 0 1 0-1.9l-1.2-1 1.6-2.8 1.5.5a8 8 0 0 1 1.6-.9l.3-1.6h3.2l.3 1.6a8 8 0 0 1 1.6.9l1.5-.5 1.6 2.8-1.2 1a8 8 0 0 1 0 1.9Z" transform="translate(-1 -1) scale(1.08)"/>',
  pulso: '<path d="M3 12h4l3-8 4 16 3-8h4" stroke-linecap="round" stroke-linejoin="round"/>',
  usuario: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7" stroke-linecap="round"/>',
  dispositivo: '<rect x="4" y="5" width="16" height="11" rx="2"/><path d="M9 20h6M12 16v4" stroke-linecap="round"/>',
  sair: '<path d="M9 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h4"/><path d="M16 8l4 4-4 4M20 12H9" stroke-linecap="round" stroke-linejoin="round"/>',
  faixas: '<path d="M4 7h16M4 12h16M4 17h16" stroke-linecap="round"/>',
  usuarios: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6M17 11a3 3 0 1 0 0-6" stroke-linecap="round"/>',
};

const PRINCIPAL = [
  { href: "index.html#home", rotulo: "Início", icone: "inicio" },
  { href: "index.html#barn", rotulo: "Ver galpão", icone: "galpao" },
  { href: "index.html#history", rotulo: "Histórico", icone: "grafico" },
  { href: "index.html#alerts", rotulo: "Alertas", icone: "sino" },
  { href: "index.html#settings", rotulo: "Configurações", icone: "engrenagem" },
];
const MAIS = [
  { href: "historico.html", rotulo: "Histórico detalhado", icone: "grafico" },
  { href: "diagnostico.html", rotulo: "Diagnóstico", icone: "pulso" },
  { href: "conta.html", rotulo: "Minha conta", icone: "usuario" },
];
const MAIS_ADMIN = [
  { href: "dispositivos.html", rotulo: "Dispositivos", icone: "dispositivo" },
  { href: "faixas.html", rotulo: "Faixas de ITGU", icone: "faixas" },
  { href: "usuarios.html", rotulo: "Usuários", icone: "usuarios" },
];

/** Rodapé fixo: nome do projeto, créditos e logos dos apoiadores. Usado em todas as páginas. */
export function montarRodape() {
  const rodape = document.getElementById("rodape");
  if (!rodape) return;
  rodape.className = "rodape";
  rodape.setAttribute("aria-label", "Créditos e apoiadores");

  const info = el("div", "rodape-info");
  info.append(
    el("p", "rodape-titulo", `© ${new Date().getFullYear()} ${PROJETO} · Nexar`),
    el("p", "rodape-texto", APOIO_TEXTO),
    el("p", "rodape-texto", EQUIPE),
  );
  const logos = el("ul", "rodape-logos");
  logos.setAttribute("aria-label", "Apoiadores");
  for (const l of APOIADORES) {
    const item = el("li", `brand-logo ${l.classe}`);
    const img = el("img");
    img.src = `img/parceiros/${l.arq}`;
    img.alt = l.alt;
    img.decoding = "async";
    item.append(img);
    logos.append(item);
  }
  rodape.replaceChildren(info, logos);
  document.body.classList.add("tem-rodape");
}

/** Nome do arquivo da página atual ("/" vale index.html). */
function paginaAtual() {
  const arquivo = location.pathname.split("/").pop();
  return arquivo || "index.html";
}

function icone(nome) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">${ICONES[nome]}</svg>`;
}

function itemMenu(item) {
  const a = el("a", "nav-button");
  a.href = item.href;
  a.innerHTML = icone(item.icone);
  a.append(el("span", null, item.rotulo));
  if (item.href === paginaAtual()) a.setAttribute("aria-current", "page");
  return a;
}

function escuroAtivo() {
  return document.documentElement.classList.contains("dark");
}

/** Troca o tema e guarda a escolha. Páginas com gráficos ouvem "nexar-tema" para se redesenhar. */
function alternarTema(botao) {
  const escuro = !escuroAtivo();
  document.documentElement.classList.toggle("dark", escuro);
  try {
    localStorage.setItem("nexar_tema", escuro ? "escuro" : "claro");
  } catch {
    // armazenamento bloqueado: vale só até recarregar
  }
  botao.textContent = escuro ? "Tema claro" : "Tema escuro";
  window.dispatchEvent(new Event("nexar-tema"));
}

/** Monta o menu lateral (marca, páginas, usuário, tema e Sair) e o rodapé. */
export function montarLayout() {
  montarRodape();
  const cabecalho = document.getElementById("cabecalho");
  const sessao = lerSessao();
  if (!cabecalho || !sessao) return;

  const marca = el("a", "brand");
  marca.href = "index.html";
  const logo = el("img", "brand-mark");
  logo.src = "img/nexar-icone.png";
  logo.alt = "";
  logo.width = 52;
  logo.height = 52;
  const texto = el("div", "brand-texto");
  texto.append(el("div", "brand-name", "Nexar"));
  marca.append(logo, texto);

  const principal = el("nav", "nav nav-principal");
  principal.setAttribute("aria-label", "Páginas");
  principal.append(...PRINCIPAL.map(itemMenu));

  const mais = el("nav", "nav nav-mais");
  mais.id = "menu";
  mais.setAttribute("aria-label", "Outras páginas");
  const extras = sessao.perfil === "admin" ? [...MAIS, ...MAIS_ADMIN] : MAIS;
  mais.append(el("p", "nav-titulo", "Mais"), ...extras.map(itemMenu));
  // no celular o bloco do usuário some: o Sair vira um atalho na fila
  const sairAtalho = el("button", "nav-button nav-sair");
  sairAtalho.type = "button";
  sairAtalho.innerHTML = icone("sair");
  sairAtalho.append(el("span", null, "Sair"));
  sairAtalho.addEventListener("click", sair);
  mais.append(sairAtalho);

  const tema = el("button", "small-button", escuroAtivo() ? "Tema claro" : "Tema escuro");
  tema.type = "button";
  tema.addEventListener("click", () => alternarTema(tema));
  const sairBtn = el("button", "small-button", "Sair");
  sairBtn.type = "button";
  sairBtn.id = "btn-sair";
  sairBtn.addEventListener("click", sair);
  const usuario = el("div", "side-usuario");
  usuario.append(el("span", "side-nome", sessao.nome), el("span", "side-perfil", sessao.perfil));
  const lateral = el("div", "side-bottom side-conta");
  const botoes = el("div", "side-botoes");
  botoes.append(tema, sairBtn);
  lateral.append(usuario, botoes);

  document.body.classList.add("com-menu", "legado");
  cabecalho.className = "sidebar";
  cabecalho.replaceChildren(marca, principal, mais, lateral);
}
