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
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

BASE = os.environ.get("PAINEL_URL", "http://localhost:8080")
ADMIN = (os.environ.get("ADMIN_EMAIL", "admin@galpao.com"), os.environ.get("ADMIN_SENHA", "senha-forte-12345"))
LEITOR = (os.environ.get("LEITOR_EMAIL", "leitor@galpao.dev"), os.environ.get("LEITOR_SENHA", "leitor-dev-12345"))
NOVA_SENHA = "nova-senha-dev-67890"
CAPTURAS = Path(__file__).resolve().parent.parent / "capturas"
RODAPE = "Projeto desenvolvido no Espaço CRIA da ETEGEC com apoio da FACEPE, processo ARC-0572-1.03/26."
ITENS_ADMIN = {"Dispositivos", "Faixas de ITGU", "Usuários"}
CLASSES = ("Conforto", "Alerta", "Crítico", "Sem faixa definida")
RECIFE = ZoneInfo("America/Recife")

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


def esperar_estado(page, estado: str = "ok") -> None:
    page.wait_for_selector(f"#principal[data-estado='{estado}']", timeout=20000)


def grafico_existe(page, canvas_id: str) -> bool:
    return page.evaluate(f"Chart.getChart('{canvas_id}') !== undefined")


def rotulos_grafico(page, canvas_id: str) -> list[str]:
    return page.evaluate(f"Chart.getChart('{canvas_id}').data.datasets.map(d => d.label)")


def baixar(page, seletor: str):
    """Clica no botão e devolve (nome sugerido, conteúdo) do download."""
    with page.expect_download() as info:
        page.click(seletor)
    download = info.value
    caminho = download.path()
    return download.suggested_filename, Path(caminho).read_text(encoding="utf-8")


def testar_historico(page) -> None:
    print("--- histórico")
    page.goto(f"{BASE}/historico.html")
    page.wait_for_function("() => document.getElementById('dispositivo').options.length >= 2")
    esperar_estado(page)
    item("histórico: 24 h desenha os 3 gráficos", all(grafico_existe(page, g) for g in ("grafico-itgu", "grafico-temp", "grafico-ur")))
    item("histórico: 24 h usa dados brutos", "dados brutos" in page.inner_text("#agregacao"), page.inner_text("#agregacao"))
    page.screenshot(path=str(CAPTURAS / "historico_1280.png"), full_page=True)

    # esp01: sem faixa
    page.select_option("#dispositivo", "esp01")
    esperar_estado(page)
    item("esp01: aviso 'sem faixa definida'", page.locator("#aviso-faixa").is_visible() and "Sem faixa definida" in page.inner_text("#aviso-faixa"))
    item("esp01: sem percentuais de conforto", "% do tempo em conforto" not in page.inner_text("#resumo"))

    # esp02: faixa, 7 dias e lacuna de 2 h
    page.select_option("#dispositivo", "esp02")
    page.click("[data-periodo='7d']")
    esperar_estado(page)
    item("7 dias mostra 'médias de 15 min'", "médias de 15 min" in page.inner_text("#agregacao"), page.inner_text("#agregacao"))
    resumo = page.inner_text("#resumo")
    item("esp02: resumo com maior lacuna de ~120 min", "120 min" in resumo.replace("\n", " "), re.sub(r"\s+", " ", resumo)[:160])
    item("esp02: % de conforto/alerta/crítico no resumo", all(t in resumo for t in ("% do tempo em conforto", "% do tempo em alerta", "% do tempo em crítico")))
    item("esp02: nota explica o cálculo com a faixa vigente hoje", "faixa vigente hoje (EXEMPLO - Semana 3)" in page.inner_text("#nota-resumo"))
    rotulos = rotulos_grafico(page, "grafico-itgu")
    item("esp02: área de conforto e limites críticos no gráfico", any("faixa vigente hoje (EXEMPLO - Semana 3)" in r for r in rotulos) and any("Limites críticos" in r for r in rotulos), "; ".join(rotulos))
    item("esp02: sem aviso de faixa", not page.locator("#aviso-faixa").is_visible())
    tem_quebra = page.evaluate("Chart.getChart('grafico-itgu').data.datasets[0].data.some(p => p.y === null)")
    item("lacuna vira ponto nulo (a linha quebra)", tem_quebra)
    page.screenshot(path=str(CAPTURAS / "historico_1280_7d.png"), full_page=True)

    # trocar dispositivo e período várias vezes, sem erro e sem vazar gráficos
    erros_antes = len([1 for t, _ in console if t in ("error", "pageerror")])
    for dispositivo in ("esp01", "esp02", "esp01"):
        page.select_option("#dispositivo", dispositivo)
        for periodo in ("6h", "24h", "30d", "7d"):
            page.click(f"[data-periodo='{periodo}']")
            esperar_estado(page)
    instancias = page.evaluate("Object.keys(Chart.instances).length")
    item("trocar filtros várias vezes não vaza gráficos", instancias == 3, f"{instancias} instâncias")
    item("trocar filtros várias vezes sem erro no console", len([1 for t, _ in console if t in ("error", "pageerror")]) == erros_antes)
    item("último dispositivo lembrado no localStorage", page.evaluate("localStorage.getItem('galpao_ultimo_dispositivo')") == "esp01")

    # CSV
    page.select_option("#dispositivo", "esp01")
    page.click("[data-periodo='24h']")
    esperar_estado(page)
    nome, conteudo = baixar(page, "#csv-bruto")
    linhas = conteudo.strip().splitlines()
    item("CSV bruto: nome vem do servidor", re.fullmatch(r"galpao_esp01_\d{8}_\d{8}\.csv", nome) is not None, nome)
    item("CSV bruto: cabeçalho e linhas", linhas[0].startswith("ts,ts_origem,recebido_em,t_int") and len(linhas) > 1000, f"{len(linhas) - 1} linhas")
    nome, conteudo = baixar(page, "#csv-agregado")
    linhas = conteudo.strip().splitlines()
    item("CSV agregado: cabeçalho de janelas", linhas[0].startswith("janela,n,t_int") and len(linhas) > 100, f"{len(linhas) - 1} linhas")

    # período personalizado, em horário de Recife: ontem 10:00 a 10:30 (= 13:00Z a 13:30Z)
    ontem = (datetime.now(RECIFE) - timedelta(days=1)).date()
    page.click("[data-periodo='custom']")
    page.fill("#inicio", f"{ontem}T10:00")
    page.fill("#fim", f"{ontem}T10:30")
    page.click("#aplicar")
    esperar_estado(page)
    item("personalizado: 31 leituras no intervalo (extremos inclusos)", "31" in page.inner_text("#resumo").split("Leituras")[1][:10], page.inner_text("#agregacao"))
    _, conteudo = baixar(page, "#csv-bruto")
    linhas = conteudo.strip().splitlines()
    primeiro_ts = linhas[1].split(",")[0]
    esperado = f"{ontem}T13:00:00+00:00"
    item("personalizado: primeiro ts do CSV em UTC confere com 10:00 de Recife", primeiro_ts == esperado, f"{primeiro_ts} (esperado {esperado})")
    page.fill("#fim", f"{ontem}T09:00")
    page.click("#aplicar")
    page.wait_for_selector("#principal[data-estado='erro']")
    item("personalizado: fim antes do início mostra erro", "depois do início" in page.inner_text("#erro"))
    page.click("[data-periodo='24h']")
    esperar_estado(page)

    # celular
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(300)
    item("histórico 390 px: sem rolagem horizontal", sem_rolagem_horizontal(page))
    page.screenshot(path=str(CAPTURAS / "historico_390.png"), full_page=True)
    page.set_viewport_size({"width": 360, "height": 740})
    page.wait_for_timeout(400)  # o Chart.js redimensiona o canvas depois do resize
    item("histórico 360 px: sem rolagem horizontal", sem_rolagem_horizontal(page))
    page.set_viewport_size({"width": 1280, "height": 900})


def testar_diagnostico(page) -> None:
    print("--- diagnóstico")
    page.goto(f"{BASE}/diagnostico.html")
    esperar_estado(page)
    page.wait_for_selector("#corpo-erros tr")
    texto = page.inner_text("#tabela-erros")
    item("diagnóstico: motivo traduzido (json_invalido)", "O texto enviado não é um JSON válido" in texto)
    item("diagnóstico: motivo com campo (campo_ausente:globo.t)", "Faltou o campo globo.t" in texto)
    item("diagnóstico: fora_da_faixa e device_desconhecido", "O campo interno.ur está fora da faixa aceita" in texto and "Dispositivo não cadastrado ou desativado" in texto)
    item("diagnóstico: código original continua visível", "json_invalido" in texto)
    item("diagnóstico: payload dentro de <details>", page.locator("#corpo-erros details").count() >= 4)
    cartoes = page.inner_text("#lista-situacao")
    item("diagnóstico: sinal Wi-Fi com texto", len(re.findall(r"\b(bom|regular|fraco|não informado)\b", cartoes)) >= 2, re.sub(r"\s+", " ", cartoes)[:140])
    item("diagnóstico: online/offline e última leitura", "Última leitura" in cartoes and re.search(r"\b(Online|Offline)\b", cartoes) is not None)
    page.screenshot(path=str(CAPTURAS / "diagnostico_1280.png"), full_page=True)

    page.select_option("#filtro-dispositivo", "esp01")
    page.wait_for_function("() => !document.getElementById('tabela-erros').innerText.includes('esp99')")
    linhas = page.locator("#corpo-erros tr")
    disp = set(page.locator("#corpo-erros td[data-rotulo='Dispositivo']").all_inner_texts())
    item("filtro por dispositivo mostra só o esp01", linhas.count() == 2 and disp == {"esp01"}, f"{linhas.count()} linhas, {disp}")
    page.select_option("#filtro-dispositivo", "")
    page.wait_for_function("() => document.querySelectorAll('#corpo-erros tr').length >= 4")
    item("filtro 'Todos' volta a mostrar tudo", True)

    page.uncheck("#auto")
    item("checkbox de atualização automática pode ser pausado", not page.is_checked("#auto"))
    page.check("#auto")

    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(300)
    item("diagnóstico 390 px: sem rolagem horizontal", sem_rolagem_horizontal(page))
    item("diagnóstico 390 px: tabela vira cartões (sem cabeçalho)", not page.locator("#tabela-erros thead").is_visible())
    page.screenshot(path=str(CAPTURAS / "diagnostico_390.png"), full_page=True)
    page.set_viewport_size({"width": 1280, "height": 900})


# ---------------------------------------------------------------------------
# Administração (etapa 14). Usa sufixos únicos por execução e desativa o que cria,
# porque a API não apaga (desativa-se). Premissa: o admin principal é o único admin ativo.
# ---------------------------------------------------------------------------

def observar(pg) -> None:
    pg.on("console", lambda m: console.append((m.type, m.text)))
    pg.on("pageerror", lambda e: console.append(("pageerror", str(e))))


def novo_contexto(navegador, largura: int = 1280):
    contexto = navegador.new_context(viewport={"width": largura, "height": 900}, locale="pt-BR", timezone_id="America/Recife")
    pg = contexto.new_page()
    observar(pg)
    return contexto, pg


def esperar_dialogo_fechado(page, seletor: str) -> None:
    page.locator(seletor).wait_for(state="hidden")


def card_por_texto(page, texto: str):
    return page.locator("article.card", has_text=texto)


def testar_acesso_de_leitor(navegador) -> None:
    print("--- admin: leitor bloqueado")
    ctx, pg = novo_contexto(navegador)
    entrar(pg, *LEITOR)
    pg.wait_for_url(re.compile(r"/index\.html$"))
    for pagina in ("dispositivos", "faixas", "usuarios"):
        pg.goto(f"{BASE}/{pagina}.html")
        pg.wait_for_url(re.compile(r"/index\.html$"))
        item(f"leitor em {pagina}.html é levado para index.html", True)
    ctx.close()


def testar_dispositivos(page, sufixo: str) -> str:
    print("--- admin: dispositivos")
    device = f"tst{sufixo}"
    page.goto(f"{BASE}/dispositivos.html")
    page.wait_for_selector("article.card[data-id='esp01']")

    page.click("#btn-novo")
    page.fill("#novo-id", "ESP/1")
    page.click("#form-novo button[type=submit]")
    item("id inválido é barrado no front", "Id inválido" in page.inner_text("#dlg-novo .erro-dialogo"))
    item("id inválido não cria cartão", page.locator("article.card[data-id='ESP/1']").count() == 0)

    page.fill("#novo-id", device)
    page.select_option("#novo-ambiente", "modelo")
    page.fill("#novo-descricao", "Teste do painel")
    page.click("#form-novo button[type=submit]")
    page.wait_for_selector("#dlg-criado[open]")
    item("criação mostra o aviso da API", "cadastre o usuário MQTT" in page.inner_text("#criado-aviso"))
    item("criação mostra o comando pronto", page.inner_text("#criado-comando") == f"sh scripts/criar_usuario_mqtt.sh {device} <senha>")
    page.click("#copiar-comando")
    page.wait_for_function("() => ['Copiado!', 'Selecione e copie'].includes(document.getElementById('copiar-comando').textContent)")
    item("botão Copiar responde", True)
    page.click("#dlg-criado [data-fechar]")
    page.wait_for_selector(f"article.card[data-id='{device}']")
    item("dispositivo novo aparece na lista", "Teste do painel" in card_por_texto(page, device).inner_text())

    def editar():
        page.click(f"article.card[data-id='{device}'] [data-acao='editar']")
        page.wait_for_selector("#dlg-editar[open]")

    # data de alojamento 10 dias atrás: idade, faixa pela idade e prévia
    data = (datetime.now(RECIFE) - timedelta(days=10)).date().isoformat()
    editar()
    page.fill("#ed-data", data)
    item("prévia mostra a idade do lote", "10 dias" in page.inner_text("#ed-previa"), page.inner_text("#ed-previa"))
    page.click("#form-editar button[type=submit]")
    esperar_dialogo_fechado(page, "#dlg-editar")
    page.wait_for_selector("#aviso-ok:not([hidden])")
    texto = card_por_texto(page, device).inner_text()
    item("lista mostra idade e faixa pela idade", "10 dias" in texto and "EXEMPLO - Semana 2" in texto and "pela idade" in texto, re.sub(r"\s+", " ", texto)[:150])

    # faixa manual
    editar()
    page.select_option("#ed-faixa", label="EXEMPLO - Semana 1 (0 a 7 dias)")
    page.click("#form-editar button[type=submit]")
    esperar_dialogo_fechado(page, "#dlg-editar")
    page.wait_for_function(f"() => document.querySelector(\"article.card[data-id='{device}']\").innerText.includes('escolhida à mão')")
    item("faixa manual vale acima da idade", "EXEMPLO - Semana 1" in card_por_texto(page, device).inner_text())

    # data futura é barrada no front
    editar()
    amanha = (datetime.now(RECIFE) + timedelta(days=1)).date().isoformat()
    page.fill("#ed-data", amanha)
    page.click("#form-editar button[type=submit]")
    item("data de alojamento futura é barrada", "futura" in page.inner_text("#dlg-editar .erro-dialogo"))
    page.click("#dlg-editar .acoes-form [data-fechar]")

    # encerrar lote, com confirmação
    editar()
    page.click("#encerrar-lote")
    page.wait_for_selector("#dlg-editar .confirmacao:not([hidden])")
    item("encerrar lote pede confirmação", "Encerrar o lote" in page.inner_text("#dlg-editar .confirmacao-texto"))
    page.click("#dlg-editar [data-confirmar]")
    esperar_dialogo_fechado(page, "#dlg-editar")
    page.wait_for_function(f"() => document.querySelector(\"article.card[data-id='{device}']\").innerText.includes('lote não informado')")
    item("lote encerrado volta a 'lote não informado'", True)

    # desativar com confirmação
    editar()
    page.uncheck("#ed-ativo")
    page.click("#form-editar button[type=submit]")
    page.wait_for_selector("#dlg-editar .confirmacao:not([hidden])")
    item("desativar explica o prazo de 5 minutos", "5 minutos" in page.inner_text("#dlg-editar .confirmacao-texto"))
    page.click("#dlg-editar [data-confirmar]")
    esperar_dialogo_fechado(page, "#dlg-editar")
    page.wait_for_function(f"() => document.querySelector(\"article.card[data-id='{device}']\").innerText.includes('Inativo')")
    item("dispositivo desativado aparece como Inativo", True)
    page.screenshot(path=str(CAPTURAS / "dispositivos_1280.png"), full_page=True)
    return device


def testar_faixas(page, sufixo: str, device: str) -> None:
    print("--- admin: faixas")
    nome = f"Teste {sufixo}"
    page.goto(f"{BASE}/faixas.html")
    page.wait_for_selector("article.card")
    item("faixas: cobertura completa das faixas de exemplo", "Todas as idades de 0 a 21" in page.inner_text("#cobertura"), page.inner_text("#cobertura"))
    zonas = page.locator("article.card .regua .zona")
    item("faixas: régua com 5 zonas por faixa", zonas.count() >= 15, f"{zonas.count()} zonas")
    peso = page.evaluate("getComputedStyle(document.querySelector('article.card .regua .zona:nth-child(2)')).flexGrow")
    item("faixas: tamanho da zona vem de --peso (CSSOM)", float(peso) > 0 and float(peso) != 1.0, f"flex-grow={peso}")

    def preencher(nome_, ini, fim, cmin, mmin, mmax, cmax):
        page.fill("#f-nome", nome_)
        for campo, valor in (("ini", ini), ("fim", fim), ("cmin", cmin), ("mmin", mmin), ("mmax", mmax), ("cmax", cmax)):
            page.fill(f"#f-{campo}", str(valor))

    # limites fora de ordem barrados no front
    page.click("#btn-nova")
    preencher(nome, 25, 30, 70, 65, 75, 80)
    page.click("#form-faixa button[type=submit]")
    item("limites fora de ordem são barrados no front", "crítico mínimo < conforto mínimo" in page.inner_text("#dlg-faixa .erro-dialogo"))
    preencher(nome, 30, 25, 60, 65, 75, 80)
    page.click("#form-faixa button[type=submit]")
    item("idade fim < início é barrada no front", "idade fim" in page.inner_text("#dlg-faixa .erro-dialogo"))

    # criar com lacuna (25 a 30; as idades 22 a 24 ficam sem faixa)
    preencher(nome, 25, 30, 60, 65, 75, 80)
    page.click("#form-faixa button[type=submit]")
    esperar_dialogo_fechado(page, "#dlg-faixa")
    page.wait_for_selector(f"article.card:has-text('{nome}')")
    item("faixa criada aparece na lista", True)
    item("cobertura mostra a lacuna 22 a 24", "idades 22 a 24" in page.inner_text("#cobertura"), page.inner_text("#cobertura"))

    # sobreposição: 409 da API no formulário
    page.click("#btn-nova")
    preencher(f"{nome} B", 28, 32, 60, 65, 75, 80)
    page.click("#form-faixa button[type=submit]")
    page.wait_for_function("() => !document.querySelector('#dlg-faixa .erro-dialogo').hidden")
    item("sobreposição mostra o 409 no formulário", "sobrepõe" in page.inner_text("#dlg-faixa .erro-dialogo"), page.inner_text("#dlg-faixa .erro-dialogo"))
    page.click("#dlg-faixa .acoes-form [data-fechar]")

    # desativar faixa em uso manual: 409 com o id do dispositivo
    card_por_texto(page, "EXEMPLO - Semana 1").locator("[data-acao='alternar']").click()
    page.wait_for_selector("#dlg-confirma[open]")
    page.click("#confirma-ok")
    page.wait_for_function("() => !document.querySelector('#dlg-confirma .erro-dialogo').hidden")
    msg = page.inner_text("#dlg-confirma .erro-dialogo")
    item("desativar faixa em uso manual mostra 409 com o id do dispositivo", device in msg, msg[:140])
    page.click("#dlg-confirma .acoes-form [data-fechar]")

    # limpeza: desativa a faixa de teste
    card_por_texto(page, nome).locator("[data-acao='alternar']").click()
    page.wait_for_selector("#dlg-confirma[open]")
    page.click("#confirma-ok")
    esperar_dialogo_fechado(page, "#dlg-confirma")
    page.wait_for_function(f"() => [...document.querySelectorAll('article.card')].some(c => c.innerText.includes('{nome}') && c.innerText.includes('Inativa'))")
    item("faixa de teste desativada (limpeza)", True)
    page.screenshot(path=str(CAPTURAS / "faixas_1280.png"), full_page=True)


SENHA_GERADA = r"[A-HJ-NP-Za-km-z2-9]{14}"


def criar_usuario(page, nome: str, email: str, perfil: str) -> str:
    """Cria pelo painel com senha gerada e devolve a senha (mostrada uma única vez)."""
    page.click("#btn-novo")
    page.fill("#n-nome", nome)
    page.fill("#n-email", email)
    page.select_option("#n-perfil", perfil)
    page.click("#form-novo button[type=submit]")
    item("usuário: senha curta ou vazia é barrada no front", "pelo menos 10" in page.inner_text("#dlg-novo .erro-dialogo"))
    page.click("#gerar-senha")
    senha = page.input_value("#n-senha")
    item("senha gerada: 14 caracteres sem ambíguos", re.fullmatch(SENHA_GERADA, senha) is not None, senha)
    page.click("#form-novo button[type=submit]")
    page.wait_for_selector("#dlg-senha[open]")
    item("senha aparece uma vez para copiar", page.inner_text("#senha-gerada") == senha and "não será exibida de novo" in page.inner_text("#dlg-senha"))
    page.click("#copiar-senha")
    page.wait_for_function("() => ['Copiado!', 'Selecione e copie'].includes(document.getElementById('copiar-senha').textContent)")
    page.click("#fechar-senha")
    item("ao fechar, a senha some da tela", page.inner_text("#senha-gerada") == "")
    page.wait_for_selector(f"article.card[data-email='{email}']")
    return senha


def cartao_usuario(page, email: str):
    return page.locator(f"article.card[data-email='{email}']")


def testar_usuarios(navegador, page, sufixo: str) -> None:
    print("--- admin: usuários")
    page.goto(f"{BASE}/usuarios.html")
    page.wait_for_selector("article.card")
    item("lista marca a própria conta com '(você)'", "(você)" in cartao_usuario(page, ADMIN[0]).inner_text())

    # leitor criado com senha gerada, que consegue logar
    email_leitor = f"leitor.{sufixo}@teste.com"
    senha_leitor = criar_usuario(page, f"Leitor Teste {sufixo}", email_leitor, "leitor")
    ctx_l, pg_l = novo_contexto(navegador)
    entrar(pg_l, email_leitor, senha_leitor)
    pg_l.wait_for_url(re.compile(r"/index\.html$"))
    item("o novo leitor consegue logar com a senha gerada", True)

    # desativar o leitor derruba a sessão dele
    cartao_usuario(page, email_leitor).locator("[data-acao='editar']").click()
    page.wait_for_selector("#dlg-editar[open]")
    page.uncheck("#ed-ativo")
    page.click("#form-editar button[type=submit]")
    page.wait_for_selector("#dlg-editar .confirmacao:not([hidden])")
    item("desativar usuário explica a consequência", "desconectado" in page.inner_text("#dlg-editar .confirmacao-texto"))
    page.click("#dlg-editar [data-confirmar]")
    esperar_dialogo_fechado(page, "#dlg-editar")
    page.wait_for_function(f"() => document.querySelector(\"article.card[data-email='{email_leitor}']\").innerText.includes('Inativo')")
    pg_l.reload()
    pg_l.wait_for_url(re.compile(r"/login\.html"))
    item("a sessão do leitor desativado cai (401 leva ao login)", True)
    ctx_l.close()

    # único admin: rebaixar a si mesmo dá 409 com a mensagem da API
    cartao_usuario(page, ADMIN[0]).locator("[data-acao='editar']").click()
    page.wait_for_selector("#dlg-editar[open]")
    page.select_option("#ed-perfil", "leitor")
    page.click("#form-editar button[type=submit]")
    page.wait_for_selector("#dlg-editar .confirmacao:not([hidden])")
    page.click("#dlg-editar [data-confirmar]")
    page.wait_for_function("() => !document.querySelector('#dlg-editar .erro-dialogo').hidden")
    msg = page.inner_text("#dlg-editar .erro-dialogo")
    item("rebaixar o único admin mostra o 409 da API", "pelo menos um admin ativo" in msg, msg)
    item("continua admin depois do 409", "Usuários" in itens_menu(page))
    page.click("#dlg-editar .acoes-form [data-fechar]")
    page.screenshot(path=str(CAPTURAS / "usuarios_1280.png"), full_page=True)

    # segundo admin: redefinir a própria senha e depois rebaixar a si mesmo
    email_admin = f"admin.{sufixo}@teste.com"
    senha_admin = criar_usuario(page, f"Admin Teste {sufixo}", email_admin, "admin")
    ctx_a, pg_a = novo_contexto(navegador)
    entrar(pg_a, email_admin, senha_admin)
    pg_a.wait_for_url(re.compile(r"/index\.html$"))
    pg_a.goto(f"{BASE}/usuarios.html")
    pg_a.wait_for_selector("article.card")
    item("o segundo admin vê as telas de administração", "Usuários" in itens_menu(pg_a))

    cartao_usuario(pg_a, email_admin).locator("[data-acao='editar']").click()
    pg_a.wait_for_selector("#dlg-editar[open]")
    pg_a.click("#redefinir")
    pg_a.wait_for_selector("#dlg-editar .confirmacao:not([hidden])")
    pg_a.click("#dlg-editar [data-confirmar]")
    pg_a.wait_for_selector("#dlg-senha[open]")
    nova_senha = pg_a.inner_text("#senha-gerada")
    item("redefinir a própria senha mostra a nova senha e avisa da saída", re.fullmatch(SENHA_GERADA, nova_senha) is not None and pg_a.locator("#senha-aviso-sessao").is_visible())
    pg_a.click("#fechar-senha")
    pg_a.wait_for_url(re.compile(r"/login\.html\?msg=senha-alterada"))
    item("depois de redefinir a própria senha vai ao login com a mensagem", "Senha alterada. Entre novamente." in pg_a.inner_text("#info"))
    entrar(pg_a, email_admin, senha_admin)
    pg_a.wait_for_selector("#erro:not([hidden])")
    item("a senha antiga deixou de funcionar", "credenciais" in pg_a.inner_text("#erro").lower())
    pg_a.fill("#senha", nova_senha)
    pg_a.click("#entrar")
    pg_a.wait_for_url(re.compile(r"/index\.html$"))

    pg_a.goto(f"{BASE}/usuarios.html")
    pg_a.wait_for_selector("article.card")
    cartao_usuario(pg_a, email_admin).locator("[data-acao='editar']").click()
    pg_a.wait_for_selector("#dlg-editar[open]")
    pg_a.select_option("#ed-perfil", "leitor")
    pg_a.click("#form-editar button[type=submit]")
    pg_a.wait_for_selector("#dlg-editar .confirmacao:not([hidden])")
    pg_a.click("#dlg-editar [data-confirmar]")
    pg_a.wait_for_url(re.compile(r"/index\.html$"))
    pg_a.wait_for_selector("#menu a", state="attached")
    menu = itens_menu(pg_a)
    item("com dois admins, rebaixar a si mesmo vai para index e some o menu admin", not (ITENS_ADMIN & menu), ", ".join(sorted(menu)))
    ctx_a.close()

    # limpeza: desativa o segundo admin (agora leitor)
    page.reload()
    page.wait_for_selector(f"article.card[data-email='{email_admin}']")
    cartao_usuario(page, email_admin).locator("[data-acao='editar']").click()
    page.wait_for_selector("#dlg-editar[open]")
    page.uncheck("#ed-ativo")
    page.click("#form-editar button[type=submit]")
    page.wait_for_selector("#dlg-editar .confirmacao:not([hidden])")
    page.click("#dlg-editar [data-confirmar]")
    esperar_dialogo_fechado(page, "#dlg-editar")
    item("usuários de teste desativados (limpeza)", True)


def testar_celular_admin(page) -> None:
    print("--- admin: celular")
    page.set_viewport_size({"width": 390, "height": 844})
    for nome in ("dispositivos", "faixas", "usuarios"):
        page.goto(f"{BASE}/{nome}.html")
        page.wait_for_selector("article.card")
        page.wait_for_timeout(300)
        item(f"{nome} 390 px: sem rolagem horizontal", sem_rolagem_horizontal(page))
        page.screenshot(path=str(CAPTURAS / f"{nome}_390.png"), full_page=True)
    # diálogo aberto no celular (editar dispositivo)
    page.goto(f"{BASE}/dispositivos.html")
    page.wait_for_selector("article.card[data-id='esp01']")
    page.click("article.card[data-id='esp01'] [data-acao='editar']")
    page.wait_for_selector("#dlg-editar[open]")
    page.wait_for_timeout(300)
    item("dialog aberto em 390 px: sem rolagem horizontal da página", sem_rolagem_horizontal(page))
    page.screenshot(path=str(CAPTURAS / "dispositivos_390_dialog.png"))
    page.click("#dlg-editar .acoes-form [data-fechar]")
    page.set_viewport_size({"width": 1280, "height": 900})


def testar_admin(navegador, page) -> None:
    sufixo = datetime.now().strftime("%H%M%S")
    testar_acesso_de_leitor(navegador)
    device = testar_dispositivos(page, sufixo)
    testar_faixas(page, sufixo, device)
    testar_usuarios(navegador, page, sufixo)
    testar_celular_admin(page)


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
        cards = page.locator("#lista-ativos article.card")
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

        testar_admin(navegador, page)
        page.goto(f"{BASE}/index.html")
        page.wait_for_selector("#btn-sair")

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

        # ---------- histórico e diagnóstico (o leitor também acessa) ----------
        testar_historico(page)
        testar_diagnostico(page)

        # ---------- minha conta ----------
        page.goto(f"{BASE}/conta.html")
        page.wait_for_function("() => document.getElementById('d-email').textContent.includes('@')")
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
        page.wait_for_function("() => document.getElementById('d-email').textContent.includes('@')")
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
