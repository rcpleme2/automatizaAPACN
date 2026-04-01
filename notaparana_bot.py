"""
notaparana_bot.py
-----------------
Automação Playwright para login e doação manual no portal Nota Paraná.

Lê credenciais e CNPJ da entidade exclusivamente do arquivo .env:
    NOTAPARANA_USER          – CPF ou CNPJ do titular (somente números)
    NOTAPARANA_PASSWORD      – Senha
    NOTAPARANA_CNPJ_ENTIDADE – CNPJ da entidade a receber as doações
"""

import os
import sys
import logging
import re
from typing import Optional

from dotenv import load_dotenv
from playwright.sync_api import (
    sync_playwright,
    Page,
    TimeoutError as PlaywrightTimeout,
)

load_dotenv()

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
URL_NOTA_PARANA = "https://www.notaparana.pr.gov.br/"
TIMEOUT_PADRAO  = 30_000   # ms
TIMEOUT_CURTO   = 5_000    # ms – para checagem opcional de modais


# ---------------------------------------------------------------------------
# Funções auxiliares de ambiente
# ---------------------------------------------------------------------------

def _obter_env(nome: str) -> str:
    valor = os.getenv(nome, "").strip()
    if not valor:
        sys.exit(
            f"[ERRO] Variável de ambiente '{nome}' não encontrada ou vazia.\n"
            "       Configure o arquivo .env a partir do modelo .env.example."
        )
    return valor


def _so_digitos(texto: str) -> str:
    return re.sub(r'\D', '', texto)


# ---------------------------------------------------------------------------
# Etapas da automação
# ---------------------------------------------------------------------------

def _fazer_login(page: Page, usuario: str, senha: str) -> None:
    """Navega até o login e autentica o usuário."""
    log.info("Acessando portal Nota Paraná...")
    page.goto(URL_NOTA_PARANA, wait_until="domcontentloaded")

    # Tenta clicar no botão "Acessar" da home (redireciona para Identidade SEFA)
    try:
        page.get_by_role("link", name=re.compile(r"acessar", re.IGNORECASE)).first.click()
        page.wait_for_load_state("domcontentloaded")
    except PlaywrightTimeout:
        log.warning("Botão 'Acessar' não encontrado na home; tentando URL de login direta.")

    log.info("Preenchendo credenciais...")
    # Campo usuário (CPF/CNPJ) – atributo id="attribute" conforme PRD
    campo_usuario = page.locator("#attribute")
    campo_usuario.wait_for(state="visible", timeout=TIMEOUT_PADRAO)
    campo_usuario.fill("")          # limpa explicitamente
    campo_usuario.fill(usuario)

    campo_senha = page.locator("#password")
    campo_senha.fill("")
    campo_senha.fill(senha)

    page.get_by_role("button", name=re.compile(r"acessar", re.IGNORECASE)).click()
    page.wait_for_load_state("domcontentloaded")

    # Verifica mensagem de erro de login
    try:
        erro = page.locator("text=Usuário/Senha inválido.").first
        erro.wait_for(state="visible", timeout=TIMEOUT_CURTO)
        sys.exit(
            "[ERRO] Login falhou: credenciais inválidas (Usuário/Senha inválido.).\n"
            "       Corrija NOTAPARANA_USER e NOTAPARANA_PASSWORD no arquivo .env."
        )
    except PlaywrightTimeout:
        pass  # mensagem de erro não apareceu – login provavelmente ok

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
    page.get_by_role(
        "link", name=re.compile(r"minhas doa", re.IGNORECASE)
    ).click()
    page.wait_for_load_state("domcontentloaded")

    log.info("Selecionando Doação manual...")
    page.get_by_role(
        "link", name=re.compile(r"doa.{0,5}o manual", re.IGNORECASE)
    ).click()
    page.wait_for_load_state("domcontentloaded")


def _doar_chave(page: Page, cnpj_entidade: str, chave: str, numero: int, total: int) -> bool:
    """
    Preenche e submete o formulário de doação manual para uma única chave.

    Retorna True se bem-sucedido, False se houver erro não-fatal.
    """
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

        # Aguarda algum feedback (modal de sucesso ou redirecionamento)
        page.wait_for_load_state("networkidle", timeout=TIMEOUT_PADRAO)

        log.info(f"  ✓ Chave {numero}/{total} doada.")
        return True

    except PlaywrightTimeout as exc:
        log.error(f"  ✗ Timeout ao processar chave {numero}/{total}: {exc}")
        return False
    except Exception as exc:
        log.error(f"  ✗ Erro inesperado na chave {numero}/{total}: {exc}")
        return False


# ---------------------------------------------------------------------------
# Função pública principal
# ---------------------------------------------------------------------------

def executar_doacoes(chaves: list[str], headless: bool = False) -> dict:
    """
    Realiza o login no Nota Paraná e doa todas as chaves da lista.

    Args:
        chaves:   Lista de chaves de acesso de 44 dígitos.
        headless: Se True, executa o navegador sem interface gráfica.

    Returns:
        Dicionário com totais: {"sucesso": int, "erro": int, "chaves_com_erro": list}
    """
    if not chaves:
        log.warning("Nenhuma chave para doar.")
        return {"sucesso": 0, "erro": 0, "chaves_com_erro": []}

    usuario          = _so_digitos(_obter_env("NOTAPARANA_USER"))
    senha            = _obter_env("NOTAPARANA_PASSWORD")
    cnpj_entidade    = _so_digitos(_obter_env("NOTAPARANA_CNPJ_ENTIDADE"))

    if len(cnpj_entidade) != 14:
        sys.exit(
            f"[ERRO] NOTAPARANA_CNPJ_ENTIDADE deve ter 14 dígitos; "
            f"encontrado: {len(cnpj_entidade)} dígito(s)."
        )

    resultado = {"sucesso": 0, "erro": 0, "chaves_com_erro": []}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context()
        page    = context.new_page()

        page.set_default_timeout(TIMEOUT_PADRAO)

        _fazer_login(page, usuario, senha)
        _fechar_modal_contato(page)
        _navegar_para_doacoes(page)

        total = len(chaves)
        for idx, chave in enumerate(chaves, start=1):
            sucesso = _doar_chave(page, cnpj_entidade, chave, idx, total)
            if sucesso:
                resultado["sucesso"] += 1
            else:
                resultado["erro"] += 1
                resultado["chaves_com_erro"].append(chave)

        browser.close()

    return resultado
