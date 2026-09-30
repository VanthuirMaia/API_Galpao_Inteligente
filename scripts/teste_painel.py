"""Teste de navegador do painel (Playwright). Roda contra o stack de dev.

Pré-requisitos: stack de dev no ar (painel em :8080), scripts/gerar_dados_dev.py já executado e um admin
criado (scripts/criar_admin.py). Instalação: pip install playwright && python -m playwright install chromium

Uso: python scripts/teste_painel.py
Variáveis opcionais: PAINEL_URL, ADMIN_EMAIL, ADMIN_SENHA, LEITOR_EMAIL, LEITOR_SENHA.
Screenshots em capturas/ (ignorada pelo git). Sai com código != 0 se algum item falhar.
"""
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("PAINEL_URL", "http://localhost:8080")
ADMIN = (os.environ.get("ADMIN_EMAIL", "admin@galpao.com"), os.environ.get("ADMIN_SENHA", "senha-forte-12345"))
LEITOR = (os.environ.get("LEITOR_EMAIL", "leitor@galpao.dev"), os.environ.get("LEITOR_SENHA", "leitor-dev-12345"))
NOVA_SENHA = "nova-senha-dev-67890"
CAPTURAS = Path(__file__).resolve().parent.parent / "capturas"
RODAPE = "Projeto desenvolvido no Espaço CRIA da ETEGEC com apoio da FACEPE, processo ARC-0572-1.03/26."
ITENS_ADMIN = {"Dispositivos", "Faixas de ITGU", "Usuários"}
CLASSES = ("Conforto", "Alerta", "Crítico", "Sem faixa definida")

falhas = 0
console = []  # mensagens do console do navegador


def item(nome: str, ok: bool, detalhe: str = "") -> None:
    global falhas
    falhas += 0 if ok else 1
    print(f"{'OK   ' if ok else 'FALHA'} {nome}" + (f" ({detalhe})" if detalhe else ""))


def entrar(page, email: str, senha: str) -> None:
    page.goto(f"{BASE}/login.html")
    page.fill("#email", email)
    page.fill("#senha", senha)
    page.click("#entrar")


def itens_menu(page) -> set[str]:
    page.wait_for_selector("#menu a", state="attached")
    return set(page.locator("#menu a").evaluate_all("els => els.map(e => e.textContent.trim())"))


def sem_rolagem_horizontal(page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def main() -> None:
    CAPTURAS.mkdir(exist_ok=True)
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        contexto = navegador.new_context(viewport={"width": 1280, "height": 900}, locale="pt-BR", timezone_id="America/Recife")
        page = contexto.new_page()
        page.on("console", lambda m: console.append((m.type, m.text)))
        page.on("pageerror", lambda e: console.append(("pageerror", str(e))))

        # ---------- guarda de página e login com erro ----------
        page.goto(f"{BASE}/conta.html")
        page.wait_for_url(re.compile(r"login\.html\?volta="))
        item("página protegida sem sessão redireciona para o login com ?volta=", "volta=%2Fconta.html" in page.url, page.url)

        page.fill("#email", ADMIN[0])
        page.fill("#senha", "senha-errada-123")
        page.click("#entrar")
        page.wait_for_selector("#erro:not([hidden])")
        item("senha errada mostra mensagem de erro", "credenciais" in page.inner_text("#erro").lower(), page.inner_text("#erro"))

        # ---------- admin ----------
        page.fill("#senha", ADMIN[1])
        page.click("#entrar")
        page.wait_for_url(re.compile(r"/conta\.html$"))
        item("login do admin volta para a página pedida (?volta=/conta.html)", True)

        page.goto(f"{BASE}/index.html")
        page.wait_for_selector("article.card[data-id='esp01'] .itgu-valor")
        page.wait_for_selector("article.card[data-id='esp02'] .itgu-valor")
        cards = page.locator("article.card")
        item("visão geral mostra um card por dispositivo ativo", cards.count() == 2, f"{cards.count()} cards")

        for device in ("esp01", "esp02"):
            texto = page.inner_text(f"article.card[data-id='{device}']")
            item(f"{device}: selo Online/Offline", bool(re.search(r"\b(Online|Offline)\b", texto)))
            item(f"{device}: classificação com texto", any(c in texto for c in CLASSES), next((c for c in CLASSES if c in texto), ""))
            item(f"{device}: números com vírgula decimal (pt-BR)", bool(re.search(r"\d,\d", texto)))
            item(f"{device}: 'Última leitura há ...'", "Última leitura há" in texto)
        texto02 = page.inner_text("article.card[data-id='esp02']")
        item("esp02: idade do lote e nome da faixa", "Lote com 20 dias" in texto02 and "EXEMPLO - Semana 3" in texto02)
        item("esp01: sem faixa definida", "sem faixa definida" in page.inner_text("article.card[data-id='esp01']").lower())
        item("indicador 'atualizado às'", bool(re.search(r"atualizado às \d\d:\d\d", page.inner_text("#atualizado"))))
        item("rodapé obrigatório", page.inner_text("#rodape").strip() == RODAPE)
        itens = itens_menu(page)
        item("admin vê os itens de admin no menu", ITENS_ADMIN <= itens, ", ".join(sorted(itens)))
        item("item da página atual marcado", page.locator("#menu a[aria-current='page']").inner_text().strip() == "Visão geral")
        page.screenshot(path=str(CAPTURAS / "visao_geral_1280.png"), full_page=True)

        # celular
        page.set_viewport_size({"width": 390, "height": 844})
        item("390 px: sem rolagem horizontal", sem_rolagem_horizontal(page))
        item("390 px: menu começa recolhido", not page.locator("#menu").is_visible())
        page.screenshot(path=str(CAPTURAS / "visao_geral_390.png"), full_page=True)
        page.click(".botao-menu")
        item("390 px: botão abre o menu", page.locator("#menu").is_visible())
        page.screenshot(path=str(CAPTURAS / "visao_geral_390_menu.png"))
        page.set_viewport_size({"width": 360, "height": 740})
        item("360 px: sem rolagem horizontal", sem_rolagem_horizontal(page))
        page.set_viewport_size({"width": 1280, "height": 900})

        # logout
        page.click("#btn-sair")
        page.wait_for_url(re.compile(r"/login\.html$"))
        item("sair volta ao login e limpa a sessão", page.evaluate("localStorage.getItem('galpao_sessao')") is None)
        page.screenshot(path=str(CAPTURAS / "login_1280.png"))

        # ---------- redirecionamento aberto ----------
        page.goto(f"{BASE}/login.html?volta=%2F%2Fevil.example.com")
        page.fill("#email", LEITOR[0])
        page.fill("#senha", LEITOR[1])
        page.click("#entrar")
        page.wait_for_url(re.compile(r"/index\.html$"))
        item("?volta= externo (//host) é ignorado", "evil.example.com" not in page.url, page.url)

        # ---------- leitor ----------
        page.wait_for_selector("article.card")
        itens = itens_menu(page)
        item("leitor não vê itens de admin", not (ITENS_ADMIN & itens), ", ".join(sorted(itens)))
        item("leitor vê o menu básico", {"Visão geral", "Minha conta"} <= itens)

        # ---------- minha conta ----------
        page.goto(f"{BASE}/conta.html")
        page.wait_for_function("document.getElementById('d-email').textContent.includes('@')")
        item("minha conta mostra e-mail e perfil", page.inner_text("#d-email") == LEITOR[0] and page.inner_text("#d-perfil") == "Leitor")

        page.fill("#senha-atual", LEITOR[1])
        page.fill("#senha-nova", "curta")
        page.fill("#senha-confirma", "curta")
        page.click("#trocar")
        item("senha curta é recusada no formulário", "pelo menos 10" in page.inner_text("#msg-senha"))

        page.fill("#senha-nova", NOVA_SENHA)
        page.fill("#senha-confirma", NOVA_SENHA)
        page.click("#trocar")
        page.wait_for_selector("#msg-senha.ok")
        item("troca de senha com sucesso", "sucesso" in page.inner_text("#msg-senha"))
        page.screenshot(path=str(CAPTURAS / "conta_1280.png"), full_page=True)

        page.reload()
        page.wait_for_function("document.getElementById('d-email').textContent.includes('@')")
        item("continua logado depois de trocar a senha (token novo salvo)", page.url.endswith("/conta.html"))
        page.goto(f"{BASE}/index.html")
        page.wait_for_selector("article.card")
        item("e navega normalmente na visão geral", page.url.endswith("/index.html"))

        # desfaz a troca, para o teste poder rodar de novo
        page.goto(f"{BASE}/conta.html")
        page.fill("#senha-atual", NOVA_SENHA)
        page.fill("#senha-nova", LEITOR[1])
        page.fill("#senha-confirma", LEITOR[1])
        page.click("#trocar")
        page.wait_for_selector("#msg-senha.ok")
        item("senha restaurada ao valor original", True)

        page.click("#btn-sair")
        page.wait_for_url(re.compile(r"/login\.html$"))
        item("logout do leitor", True)

        # ---------- console ----------
        erros = [(t, m) for t, m in console if t in ("error", "pageerror")]
        csp = [m for t, m in console if "content security policy" in m.lower() or "refused to" in m.lower()]
        item("console sem violações de CSP", not csp, "; ".join(csp)[:200])
        # 401 do login com senha errada aparece como "Failed to load resource" (esperado): ignora
        outros = [m for t, m in erros if "401" not in m and "Failed to load resource" not in m]
        item("console sem outros erros", not outros, "; ".join(outros)[:200])

        navegador.close()

    print(f"\ncapturas em: {CAPTURAS}")
    print("RESULTADO:", "tudo OK" if not falhas else f"{falhas} FALHA(S)")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
