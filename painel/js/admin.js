// Utilitários das telas de administração: diálogos, confirmação, avisos, erros e copiar.
// Lembrete: o perfil no front só esconde menu; quem garante a permissão é a API (403).
import { el } from "./formato.js";

let temporizadorAviso = null;

/** Aviso de sucesso que some sozinho. Precisa existir <p id="aviso-ok">. */
export function mostrarAviso(texto) {
  const caixa = document.getElementById("aviso-ok");
  caixa.textContent = texto;
  caixa.hidden = false;
  clearTimeout(temporizadorAviso);
  temporizadorAviso = setTimeout(() => (caixa.hidden = true), 5000);
}

/** Erro no nível da página (carga da lista). Precisa existir <p id="erro-pagina">. */
export function mostrarErroPagina(texto) {
  const caixa = document.getElementById("erro-pagina");
  caixa.textContent = texto;
  caixa.hidden = !texto;
}

/** 403: o perfil mudou com a página aberta. Avisa e volta para a visão geral. */
export function semPermissao() {
  mostrarErroPagina("Sem permissão para esta ação");
  setTimeout(() => location.replace("index.html"), 1500);
}

/** Mensagem de um erro de rede ou da API. */
export function textoDoErro(e) {
  return e instanceof TypeError ? "Sem conexão com o servidor." : e.message;
}

/** Erro de uma ação dentro de um diálogo: 403 sai da tela; o resto aparece no formulário. */
export function erroNoDialogo(dlg, e) {
  if (e.status === 403) {
    fecharDialogo(dlg);
    semPermissao();
    return;
  }
  mostrarErroDialogo(dlg, textoDoErro(e));
}

export function mostrarErroDialogo(dlg, texto) {
  const caixa = dlg.querySelector(".erro-dialogo");
  if (!caixa) return; // alguns diálogos (resultado, senha) não têm área de erro
  caixa.textContent = texto;
  caixa.hidden = !texto;
}

export function abrirDialogo(dlg) {
  mostrarErroDialogo(dlg, "");
  esconderConfirmacao(dlg);
  if (!dlg.open) dlg.showModal();
}

export function fecharDialogo(dlg) {
  if (dlg.open) dlg.close();
}

/** Liga os botões [data-fechar] e o clique fora da caixa. Chamar uma vez por diálogo. */
export function configurarDialogo(dlg) {
  dlg.querySelectorAll("[data-fechar]").forEach((b) => b.addEventListener("click", () => fecharDialogo(dlg)));
  dlg.addEventListener("click", (evento) => {
    if (evento.target === dlg) fecharDialogo(dlg); // clique no fundo escurecido
  });
}

function esconderConfirmacao(dlg) {
  const area = dlg.querySelector(".confirmacao");
  if (area) area.hidden = true;
  const acoes = dlg.querySelector(".acoes-form");
  if (acoes) acoes.hidden = false;
}

/**
 * Confirmação dentro do próprio diálogo: mostra o texto e os botões Voltar/Confirmar
 * no lugar dos botões do formulário. Resolve true (confirmou) ou false (voltou).
 */
export function pedirConfirmacao(dlg, texto) {
  const area = dlg.querySelector(".confirmacao");
  const acoes = dlg.querySelector(".acoes-form");
  area.querySelector(".confirmacao-texto").textContent = texto;
  area.hidden = false;
  if (acoes) acoes.hidden = true;
  return new Promise((resolve) => {
    const voltar = area.querySelector("[data-voltar]");
    const confirmar = area.querySelector("[data-confirmar]");
    const terminar = (resposta) => {
      voltar.removeEventListener("click", aoVoltar);
      confirmar.removeEventListener("click", aoConfirmar);
      esconderConfirmacao(dlg);
      resolve(resposta);
    };
    const aoVoltar = () => terminar(false);
    const aoConfirmar = () => terminar(true);
    voltar.addEventListener("click", aoVoltar);
    confirmar.addEventListener("click", aoConfirmar);
  });
}

/** Copia para a área de transferência; se o navegador não permitir, seleciona o texto do elemento. */
export async function copiar(texto, botao) {
  const original = botao.textContent;
  try {
    await navigator.clipboard.writeText(texto);
    botao.textContent = "Copiado!";
  } catch {
    botao.textContent = "Selecione e copie";
  }
  setTimeout(() => (botao.textContent = original), 2000);
}

/** Ajuda a montar linhas "rótulo: valor" nos cards. */
export function linhaInfo(rotulo, valor) {
  const p = el("p", "linha-info");
  p.append(el("span", "rot", `${rotulo}: `), el("span", null, valor));
  return p;
}
