// Cabeçalho, menu e rodapé compartilhados.
import { el } from "./formato.js";
import { lerSessao, sair } from "./sessao.js";

const RODAPE = "Projeto desenvolvido no Espaço CRIA da ETEGEC com apoio da FACEPE, processo ARC-0572-1.03/26.";

const MENU = [
  { href: "index.html", rotulo: "Visão geral" },
  { href: "historico.html", rotulo: "Histórico" },
  { href: "diagnostico.html", rotulo: "Diagnóstico" },
  { href: "conta.html", rotulo: "Minha conta" },
];
const MENU_ADMIN = [
  { href: "dispositivos.html", rotulo: "Dispositivos" },
  { href: "faixas.html", rotulo: "Faixas de ITGU" },
  { href: "usuarios.html", rotulo: "Usuários" },
];

export function montarRodape() {
  const rodape = document.getElementById("rodape");
  if (rodape) rodape.textContent = RODAPE;
}

/** Nome do arquivo da página atual ("/" vale index.html). */
function paginaAtual() {
  const arquivo = location.pathname.split("/").pop();
  return arquivo || "index.html";
}

function itemMenu(item) {
  const a = el("a", null, item.rotulo);
  a.href = item.href;
  if (item.href === paginaAtual()) a.setAttribute("aria-current", "page");
  return a;
}

/** Monta o cabeçalho (marca, usuário, Sair, menu recolhível) e o rodapé. */
export function montarLayout() {
  montarRodape();
  const cabecalho = document.getElementById("cabecalho");
  const sessao = lerSessao();
  if (!cabecalho || !sessao) return;

  const marca = el("a", "marca", "Galpão Inteligente");
  marca.href = "index.html";
  const usuario = el("span", "usuario", `${sessao.nome} (${sessao.perfil})`);
  const sairBtn = el("button", "botao-sair", "Sair");
  sairBtn.type = "button";
  sairBtn.id = "btn-sair";
  sairBtn.addEventListener("click", sair);

  const menuBtn = el("button", "botao-menu", "Menu");
  menuBtn.type = "button";
  menuBtn.setAttribute("aria-expanded", "false");
  menuBtn.setAttribute("aria-controls", "menu");

  const topo = el("div", "cabecalho-topo");
  topo.append(marca, usuario, sairBtn, menuBtn);

  const itens = sessao.perfil === "admin" ? [...MENU, ...MENU_ADMIN] : MENU;
  const menu = el("nav", "menu");
  menu.id = "menu";
  menu.setAttribute("aria-label", "Principal");
  menu.append(...itens.map(itemMenu));

  menuBtn.addEventListener("click", () => {
    const aberto = menu.classList.toggle("aberto");
    menuBtn.setAttribute("aria-expanded", String(aberto));
  });

  cabecalho.replaceChildren(topo, menu);
}
