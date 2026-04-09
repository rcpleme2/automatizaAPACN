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


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

def _so_digitos(texto: str) -> str:
    return re.sub(r'\D', '', texto)


# ---------------------------------------------------------------------------
# Etapas internas da automação
# ---------------------------------------------------------------------------

def _fechar_popup_cookies(page: Page) -> None:
    """Tenta fechar banners de consentimento de cookies. Silencioso."""
    seletores_botao = [
        "#acceptCookies", "#accept-cookies", "#btnAceitarCookies",
        ".cookie-accept", ".btn-cookie-accept",
    ]
    textos_botao = re.compile(
        r"^(aceitar( todos)?|concordo|ok|entendi|permitir( todos)?)$",
        re.IGNORECASE,
    )

    for seletor in seletores_botao:
        try:
            btn = page.locator(seletor).first
            btn.wait_for(state="visible", timeout=1_500)
            btn.click()
            log.info(f"Popup de cookies fechado via seletor: {seletor}")
            page.wait_for_load_state("domcontentloaded")
            return
        except PlaywrightTimeout:
            continue

    try:
        btn = page.locator(
            "div[class*='cookie'] button, div[id*='cookie'] button, "
            "#cookieBar button, .lgpd button, [class*='lgpd'] button, "
            "[class*='consent'] button"
        ).filter(has_text=textos_botao).first
        btn.wait_for(state="visible", timeout=1_500)
        btn.click()
        log.info("Popup de cookies fechado via texto do botão.")
        page.wait_for_load_state("domcontentloaded")
        return
    except PlaywrightTimeout:
        pass

    log.debug("Nenhum popup de cookies detectado.")


def _tentar_login(page: Page, usuario: str, senha: str) -> None:
    """Preenche e submete o formulário de login uma única vez."""
    log.info(f"Acessando página de autenticação: {URL_LOGIN_DIRETO}")
    page.goto(URL_LOGIN_DIRETO, wait_until="load")
    _fechar_popup_cookies(page)

    log.info("Preenchendo credenciais...")
    campo_usuario = page.locator("#attribute")
    campo_usuario.wait_for(state="visible", timeout=TIMEOUT_PADRAO)
    page.evaluate("document.querySelector('#attribute').value = ''")
    campo_usuario.fill(usuario)

    campo_senha = page.locator("#password")
    page.evaluate("document.querySelector('#password').value = ''")
    campo_senha.fill(senha)

    # Aguarda o botão ficar ativo e a página estabilizar antes de submeter
    btn = page.get_by_role("button", name=re.compile(r"acessar", re.IGNORECASE))
    btn.wait_for(state="visible", timeout=TIMEOUT_PADRAO)
    try:
        page.wait_for_load_state("networkidle", timeout=TIMEOUT_CURTO)
    except PlaywrightTimeout:
        pass  # prossegue mesmo se a página não estabilizar completamente

    log.info("Submetendo login...")
    btn.click()
    page.wait_for_load_state("load")


def _fazer_login(page: Page, usuario: str, senha: str) -> None:
    """Login com tratamento de sessão duplicada."""
    _tentar_login(page, usuario, senha)

    # Verifica credenciais inválidas
    try:
        page.locator("text=Usuário/Senha inválido.").first.wait_for(
            state="visible", timeout=TIMEOUT_CURTO
        )
        sys.exit(
            "[ERRO] Login falhou: usuário ou senha incorretos.\n"
            "       Verifique NOTAPARANA_USER no .env e a senha digitada."
        )
    except PlaywrightTimeout:
        pass

    # Verifica sessão duplicada
    try:
        page.locator(
            "text=Ops! O usuário autenticado possui mais de uma sessão ativa."
        ).first.wait_for(state="visible", timeout=TIMEOUT_CURTO)

        log.warning("Sessão duplicada detectada. Encerrando sessão anterior...")
        page.goto(URL_SAIR, wait_until="load")
        log.info("Sessão encerrada. Realizando novo login...")

        _tentar_login(page, usuario, senha)

        try:
            page.locator("text=Usuário/Senha inválido.").first.wait_for(
                state="visible", timeout=TIMEOUT_CURTO
            )
            sys.exit(
                "[ERRO] Login falhou após relogin: usuário ou senha incorretos."
            )
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


def _navegar_para_doacoes(page: Page) -> None:
    """Clica em 'MINHAS DOAÇÕES' e depois em 'Doação manual'."""
    log.info("Navegando para MINHAS DOAÇÕES...")
    link_doacoes = page.get_by_role(
        "link", name=re.compile(r"minhas doa", re.IGNORECASE)
    )
    link_doacoes.wait_for(state="visible", timeout=TIMEOUT_PADRAO)
    link_doacoes.click()

    # Aguarda o link de Doação manual aparecer (indica que a aba carregou)
    log.info("Selecionando Doação manual...")
    link_manual = page.get_by_role(
        "link", name=re.compile(r"doa.{0,5}o manual", re.IGNORECASE)
    )
    link_manual.wait_for(state="visible", timeout=TIMEOUT_PADRAO)
    link_manual.click()

    # Aguarda o campo CNPJ aparecer (indica que o formulário está pronto)
    page.locator(
        "input[placeholder*='CNPJ'], input[id*='cnpj'], input[name*='cnpj']"
    ).first.wait_for(state="visible", timeout=TIMEOUT_PADRAO)


def _doar_chave(page: Page, cnpj_entidade: str, chave: str, numero: int, total: int) -> bool:
    """Preenche e submete o formulário de doação para uma única chave."""
    log.info(f"Doando chave {numero}/{total}: {chave[:10]}...")

    try:
        campo_cnpj = page.locator(
            "input[placeholder*='CNPJ'], input[id*='cnpj'], input[name*='cnpj']"
        ).first
        campo_cnpj.wait_for(state="visible", timeout=TIMEOUT_PADRAO)
        campo_cnpj.fill("")
        campo_cnpj.fill(cnpj_entidade)

        campo_chave = page.locator(
            "input[placeholder*='Chave'], input[placeholder*='chave'], "
            "input[id*='chave'], input[name*='chave'], "
            "input[maxlength='44']"
        ).first
        campo_chave.wait_for(state="visible", timeout=TIMEOUT_PADRAO)
        campo_chave.fill("")
        campo_chave.fill(chave)

        page.get_by_role(
            "button", name=re.compile(r"doar documento", re.IGNORECASE)
        ).click()

        # Verificação em duas etapas: aguarda estabilização da página,
        # depois confirma que o formulário está pronto para a próxima nota
        page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT_PADRAO)
        try:
            page.wait_for_load_state("networkidle", timeout=TIMEOUT_CURTO)
        except PlaywrightTimeout:
            pass  # prossegue mesmo se houver requisições residuais
        campo_cnpj_prox = page.locator(
            "input[placeholder*='CNPJ'], input[id*='cnpj'], input[name*='cnpj']"
        ).first
        campo_cnpj_prox.wait_for(state="visible", timeout=TIMEOUT_PADRAO)

        log.info(f"  ✓ Chave {numero}/{total} doada.")
        return True

    except PlaywrightTimeout as exc:
        log.error(f"  ✗ Timeout ao processar chave {numero}/{total}: {exc}")
        return False
    except Exception as exc:
        log.error(f"  ✗ Erro inesperado na chave {numero}/{total}: {exc}")
        return False


# ---------------------------------------------------------------------------
# API pública – três funções para controle externo do ciclo de vida
# ---------------------------------------------------------------------------

def iniciar_sessao(usuario: str, senha: str, headless: bool = False) -> tuple[Playwright, Browser, Page]:
    """
    Abre o navegador, faz login e retorna os objetos de sessão.

    Args:
        usuario:  CPF ou CNPJ do titular (somente dígitos).
        senha:    Senha de acesso.
        headless: Se True, executa sem janela gráfica.

    Returns:
        (pw, browser, page)
    """
    pw      = sync_playwright().start()
    browser = pw.chromium.launch(headless=headless)
    page    = browser.new_context().new_page()
    page.set_default_timeout(TIMEOUT_PADRAO)

    _fazer_login(page, _so_digitos(usuario), senha)
    _fechar_modal_contato(page)

    return pw, browser, page


def doar_lote(page: Page, cnpj_entidade: str, chaves: list[str]) -> dict:
    """
    Navega para a doação manual e processa todas as chaves do lote.

    Returns:
        {"sucesso": int, "erro": int, "chaves_com_erro": list}
    """
    resultado = {"sucesso": 0, "erro": 0, "chaves_com_erro": []}

    if not chaves:
        return resultado

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
        page.goto(URL_SAIR, wait_until="load")
        log.info("Logout realizado.")
    except Exception as exc:
        log.warning(f"Não foi possível acessar a URL de saída: {exc}")
    finally:
        browser.close()
        pw.stop()
