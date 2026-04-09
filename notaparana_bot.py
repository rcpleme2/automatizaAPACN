"""
notaparana_bot.py
-----------------
Automação Playwright para login e doação manual no portal Nota Paraná.

Todas as credenciais são recebidas como parâmetros em tempo de execução.
Nenhum dado sensível é lido de arquivo neste módulo.
"""

import sys
import logging
import re

from playwright.sync_api import (
    sync_playwright,
    Browser,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeout,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
URL_LOGIN_DIRETO = "https://notaparana.pr.gov.br/"
URL_SAIR         = "https://notaparana.pr.gov.br/nfprweb/publico/sair"
TIMEOUT_PADRAO   = 30_000   # ms
TIMEOUT_CURTO    =  5_000   # ms
TIMEOUT_COOKIE   =    500   # ms – falha rápida na checagem de popup de cookies


# ---------------------------------------------------------------------------
# Seletor do campo CNPJ (reutilizado em múltiplos pontos)
# ---------------------------------------------------------------------------
_SEL_CNPJ  = "input[placeholder*='CNPJ'], input[id*='cnpj'], input[name*='cnpj']"
_SEL_CHAVE = (
    "input[placeholder*='Chave'], input[placeholder*='chave'], "
    "input[id*='chave'], input[name*='chave'], input[maxlength='44']"
)


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

def _so_digitos(texto: str) -> str:
    return re.sub(r'\D', '', texto)


# ---------------------------------------------------------------------------
# Etapas internas da automação
# ---------------------------------------------------------------------------

def _fechar_popup_cookies(page: Page) -> None:
    """
    Tenta fechar banner de cookies em até ~1 s no total.
    Combina todos os seletores em uma única consulta para falhar rápido.
    """
    textos_botao = re.compile(
        r"^(aceitar( todos)?|concordo|ok|entendi|permitir( todos)?)$",
        re.IGNORECASE,
    )

    # Tentativa 1: seletores CSS conhecidos combinados em um único locator
    try:
        btn = page.locator(
            "#acceptCookies, #accept-cookies, #btnAceitarCookies, "
            ".cookie-accept, .btn-cookie-accept"
        ).first
        btn.wait_for(state="visible", timeout=TIMEOUT_COOKIE)
        btn.click()
        log.info("Popup de cookies fechado (seletor CSS).")
        page.wait_for_load_state("domcontentloaded")
        return
    except PlaywrightTimeout:
        pass

    # Tentativa 2: botão por texto dentro de containers LGPD/cookie
    try:
        btn = page.locator(
            "div[class*='cookie'] button, div[id*='cookie'] button, "
            "#cookieBar button, .lgpd button, [class*='lgpd'] button, "
            "[class*='consent'] button"
        ).filter(has_text=textos_botao).first
        btn.wait_for(state="visible", timeout=TIMEOUT_COOKIE)
        btn.click()
        log.info("Popup de cookies fechado (texto do botão).")
        page.wait_for_load_state("domcontentloaded")
        return
    except PlaywrightTimeout:
        pass

    log.debug("Nenhum popup de cookies detectado.")


def _tentar_login(page: Page, usuario: str, senha: str) -> None:
    """Preenche e submete o formulário de login uma única vez."""
    log.info(f"Acessando página de autenticação: {URL_LOGIN_DIRETO}")
    # domcontentloaded é suficiente para o formulário aparecer e é mais rápido que "load"
    page.goto(URL_LOGIN_DIRETO, wait_until="domcontentloaded")
    _fechar_popup_cookies(page)

    log.info("Preenchendo credenciais...")
    campo_usuario = page.locator("#attribute")
    campo_usuario.wait_for(state="visible", timeout=TIMEOUT_PADRAO)
    page.evaluate("document.querySelector('#attribute').value = ''")
    campo_usuario.fill(usuario)

    campo_senha = page.locator("#password")
    page.evaluate("document.querySelector('#password').value = ''")
    campo_senha.fill(senha)

    # Aguarda o botão ficar visível e clica — sem espera fixa
    log.info("Submetendo login...")
    btn = page.get_by_role("button", name=re.compile(r"acessar", re.IGNORECASE))
    btn.wait_for(state="visible", timeout=TIMEOUT_PADRAO)
    btn.click()

    # Aguarda navegação pós-login usando elemento que indica página logada
    page.wait_for_load_state("domcontentloaded")


def _fazer_login(page: Page, usuario: str, senha: str) -> None:
    """Login com tratamento de credenciais inválidas e sessão duplicada."""
    _tentar_login(page, usuario, senha)

    # Verifica credenciais inválidas
    try:
        page.locator("text=Usuário/Senha inválido.").first.wait_for(
            state="visible", timeout=TIMEOUT_CURTO
        )
        sys.exit(
            "[ERRO] Login falhou: usuário ou senha incorretos.\n"
            "       Verifique o usuário digitado e tente novamente."
        )
    except PlaywrightTimeout:
        pass

    # Verifica sessão duplicada
    try:
        page.locator(
            "text=Ops! O usuário autenticado possui mais de uma sessão ativa."
        ).first.wait_for(state="visible", timeout=TIMEOUT_CURTO)

        log.warning("Sessão duplicada detectada. Encerrando sessão anterior...")
        page.goto(URL_SAIR, wait_until="domcontentloaded")
        log.info("Sessão encerrada. Realizando novo login...")

        _tentar_login(page, usuario, senha)

        try:
            page.locator("text=Usuário/Senha inválido.").first.wait_for(
                state="visible", timeout=TIMEOUT_CURTO
            )
            sys.exit("[ERRO] Login falhou após relogin: usuário ou senha incorretos.")
        except PlaywrightTimeout:
            pass

    except PlaywrightTimeout:
        pass

    log.info("Login realizado com sucesso.")


def _fechar_modal_contato(page: Page) -> None:
    """Fecha o modal 'Informações de contato', se aparecer."""
    try:
        btn_fechar = page.locator("#btnFecharModalContato")
        btn_fechar.wait_for(state="visible", timeout=TIMEOUT_CURTO)
        btn_fechar.click()
        log.info("Modal 'Informações de contato' fechado.")
    except PlaywrightTimeout:
        log.debug("Modal de contato não apareceu.")


def _esta_no_formulario_doacao(page: Page) -> bool:
    """Retorna True se o formulário de doação manual já está visível na página."""
    try:
        page.locator(_SEL_CNPJ).first.wait_for(state="visible", timeout=2_000)
        return True
    except PlaywrightTimeout:
        return False


def _navegar_para_doacoes(page: Page) -> None:
    """Clica em 'MINHAS DOAÇÕES' → 'Doação manual' e aguarda o formulário."""
    log.info("Navegando para MINHAS DOAÇÕES...")
    link_doacoes = page.get_by_role(
        "link", name=re.compile(r"minhas doa", re.IGNORECASE)
    )
    link_doacoes.wait_for(state="visible", timeout=TIMEOUT_PADRAO)
    link_doacoes.click()

    log.info("Selecionando Doação manual...")
    link_manual = page.get_by_role(
        "link", name=re.compile(r"doa.{0,5}o manual", re.IGNORECASE)
    )
    link_manual.wait_for(state="visible", timeout=TIMEOUT_PADRAO)
    link_manual.click()

    # Confirma que o formulário carregou
    page.locator(_SEL_CNPJ).first.wait_for(state="visible", timeout=TIMEOUT_PADRAO)


def _doar_chave(page: Page, cnpj_entidade: str, chave: str, numero: int, total: int) -> bool:
    """Preenche e submete o formulário de doação para uma única chave."""
    log.info(f"Doando chave {numero}/{total}: {chave[:10]}...")

    try:
        campo_cnpj = page.locator(_SEL_CNPJ).first
        campo_cnpj.wait_for(state="visible", timeout=TIMEOUT_PADRAO)
        campo_cnpj.fill("")
        campo_cnpj.fill(cnpj_entidade)

        campo_chave = page.locator(_SEL_CHAVE).first
        campo_chave.wait_for(state="visible", timeout=TIMEOUT_PADRAO)
        campo_chave.fill("")
        campo_chave.fill(chave)

        page.get_by_role(
            "button", name=re.compile(r"doar documento", re.IGNORECASE)
        ).click()

        # Aguarda a página processar e o formulário estar pronto para a próxima nota
        page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT_PADRAO)
        try:
            page.wait_for_load_state("networkidle", timeout=TIMEOUT_CURTO)
        except PlaywrightTimeout:
            pass
        page.locator(_SEL_CNPJ).first.wait_for(state="visible", timeout=TIMEOUT_PADRAO)

        log.info(f"  ✓ Chave {numero}/{total} doada.")
        return True

    except PlaywrightTimeout as exc:
        log.error(f"  ✗ Timeout ao processar chave {numero}/{total}: {exc}")
        return False
    except Exception as exc:
        log.error(f"  ✗ Erro inesperado na chave {numero}/{total}: {exc}")
        return False


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def iniciar_sessao(usuario: str, senha: str, headless: bool = False) -> tuple[Playwright, Browser, Page]:
    """Abre o navegador, faz login e retorna (pw, browser, page)."""
    pw      = sync_playwright().start()
    browser = pw.chromium.launch(headless=headless)
    page    = browser.new_context().new_page()
    page.set_default_timeout(TIMEOUT_PADRAO)

    _fazer_login(page, _so_digitos(usuario), senha)
    _fechar_modal_contato(page)

    return pw, browser, page


def doar_lote(page: Page, cnpj_entidade: str, chaves: list[str]) -> dict:
    """
    Processa um lote de chaves de acesso.
    Navega para o formulário apenas se ainda não estiver nele.

    Returns:
        {"sucesso": int, "erro": int, "chaves_com_erro": list}
    """
    resultado = {"sucesso": 0, "erro": 0, "chaves_com_erro": []}

    if not chaves:
        return resultado

    if _esta_no_formulario_doacao(page):
        log.info("Formulário de doação já está aberto. Pulando navegação.")
    else:
        _navegar_para_doacoes(page)

    for idx, chave in enumerate(chaves, start=1):
        if _doar_chave(page, cnpj_entidade, chave, idx, len(chaves)):
            resultado["sucesso"] += 1
        else:
            resultado["erro"] += 1
            resultado["chaves_com_erro"].append(chave)

    return resultado


def encerrar_sessao(pw: Playwright, browser: Browser, page: Page) -> None:
    """Faz logout no site e encerra o navegador."""
    log.info("Encerrando sessão no Nota Paraná...")
    try:
        page.goto(URL_SAIR, wait_until="domcontentloaded")
        log.info("Logout realizado.")
    except Exception as exc:
        log.warning(f"Não foi possível acessar a URL de saída: {exc}")
    finally:
        browser.close()
        pw.stop()
