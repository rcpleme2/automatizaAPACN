"""
notaparana_bot.py
-----------------
Automação Playwright para login e doação manual no portal Nota Paraná.

Todas as credenciais são recebidas como parâmetros em tempo de execução.
Nenhum dado sensível é lido de arquivo neste módulo.
"""

import json
import logging
import re
from typing import Callable, Optional
from urllib.parse import urlparse, parse_qs, unquote

from playwright.sync_api import (
    sync_playwright,
    Browser,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeout,
)

# ---------------------------------------------------------------------------
# Logging (destino configurado pelo chamador; ver painel.configurar_log)
# ---------------------------------------------------------------------------
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
URL_LOGIN_DIRETO = "https://notaparana.pr.gov.br/"
URL_SAIR         = "https://notaparana.pr.gov.br/nfprweb/publico/sair"
URL_FORM_DOACAO  = "https://notaparana.pr.gov.br/nfprweb/DoacaoDocumentoFiscalCadastrar"
TIMEOUT_PADRAO      = 30_000   # ms
TIMEOUT_CURTO       =  5_000   # ms
TIMEOUT_COOKIE      =    500   # ms – falha rápida na checagem de popup de cookies
TIMEOUT_LOGIN_ERRO  =  1_500   # ms – tempo máximo para mensagens de erro após o login
TIMEOUT_NAVEGACAO   = 20_000   # ms – aguarda redirecionamento após clicar em DOAR

# Número máximo de erros 400 consecutivos antes de pausar e perguntar ao operador
LIMITE_ERROS_CHAVE = 5

# Rejeições ligadas ao próprio documento (ex.: nota fora do prazo de doação).
# São resultados normais: não contam para LIMITE_ERROS_CHAVE e não são relançadas.
_PADROES_ERRO_DOCUMENTO = (
    re.compile(r"prazo para doar esta nota expirou", re.IGNORECASE),
)


# ---------------------------------------------------------------------------
# Exceções públicas
# ---------------------------------------------------------------------------

class CNPJInvalidoError(Exception):
    """CNPJ da entidade inválido — portal retornou HTTP 400."""
    pass


class CredenciaisInvalidasError(Exception):
    """Usuário ou senha rejeitados pelo portal."""
    pass


# ---------------------------------------------------------------------------
# Seletores do formulário (reutilizados em múltiplos pontos)
# ---------------------------------------------------------------------------
_SEL_CNPJ  = "input[placeholder*='CNPJ'], input[id*='cnpj'], input[name*='cnpj']"
_SEL_CHAVE = (
    "input[placeholder*='Chave'], input[placeholder*='chave'], "
    "input[id*='chave'], input[name*='chave'], input[maxlength='44']"
)


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

def so_digitos(texto: str) -> str:
    return re.sub(r'\D', '', texto)


def _is_cnpj_check(response) -> bool:
    """Identifica a requisição de verificação de CNPJ da entidade."""
    return (
        response.request.resource_type in ("xhr", "fetch")
        and "entidadePorCnpj" in response.url
    )


def _is_doacao_post(response) -> bool:
    """Identifica a requisição POST de doação de documento fiscal."""
    return (
        response.request.resource_type in ("xhr", "fetch")
        and "documentoFiscalDoadoWeb" in response.url
    )


def _is_erro_documento(msg_erro: str) -> bool:
    """True se a rejeição se refere ao documento em si (ex.: prazo expirado)."""
    return any(p.search(msg_erro) for p in _PADROES_ERRO_DOCUMENTO)


def _extrair_params_url(url: str) -> dict:
    """Retorna os parâmetros de query string de uma URL como dict simples."""
    params = parse_qs(urlparse(url).query)
    return {k: unquote(v[0]) for k, v in params.items()}


def _msg_erro_400(response) -> str:
    """Tenta ler a mensagem de erro de uma resposta HTTP 400 em JSON."""
    try:
        body = response.json()
        if isinstance(body, dict):
            return "; ".join(f"{k}: {v}" for k, v in body.items())
        return str(body)
    except Exception:
        return "Erro 400 (corpo não legível)"


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

    log.info("Submetendo login...")
    btn = page.get_by_role("button", name=re.compile(r"acessar", re.IGNORECASE))
    btn.wait_for(state="visible", timeout=TIMEOUT_PADRAO)
    btn.click()

    page.wait_for_load_state("domcontentloaded")


def _fazer_login(page: Page, usuario: str, senha: str) -> None:
    """Login com tratamento de credenciais inválidas e sessão duplicada.

    Raises:
        CredenciaisInvalidasError: se usuário ou senha estiverem incorretos.
    """
    _tentar_login(page, usuario, senha)

    # Verifica credenciais inválidas
    try:
        page.locator("text=Usuário/Senha inválido.").first.wait_for(
            state="visible", timeout=TIMEOUT_LOGIN_ERRO
        )
        raise CredenciaisInvalidasError(
            "Usuário ou senha incorretos. Verifique e tente novamente."
        )
    except PlaywrightTimeout:
        pass

    # Verifica sessão duplicada
    try:
        page.locator(
            "text=Ops! O usuário autenticado possui mais de uma sessão ativa."
        ).first.wait_for(state="visible", timeout=TIMEOUT_LOGIN_ERRO)

        log.warning("Sessão duplicada detectada. Encerrando sessão anterior...")
        page.goto(URL_SAIR, wait_until="domcontentloaded")
        log.info("Sessão encerrada. Realizando novo login...")

        _tentar_login(page, usuario, senha)

        try:
            page.locator("text=Usuário/Senha inválido.").first.wait_for(
                state="visible", timeout=TIMEOUT_LOGIN_ERRO
            )
            raise CredenciaisInvalidasError(
                "Usuário ou senha incorretos após relogin."
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

    page.locator(_SEL_CNPJ).first.wait_for(state="visible", timeout=TIMEOUT_PADRAO)


def _sessao_expirada(page: Page) -> bool:
    """True se a página atual é a tela de login (sessão encerrada pelo portal)."""
    try:
        return page.locator("#attribute").first.is_visible()
    except Exception:
        return False


def _formulario_visivel(page: Page) -> bool:
    try:
        return page.locator(_SEL_CNPJ).first.is_visible()
    except Exception:
        return False


def _restaurar_formulario(page: Page, relogin: Callable[[], None]) -> bool:
    """Volta ao formulário de doação, refazendo o login se a sessão caiu.

    Retorna True se o formulário ficou disponível (o CNPJ precisa ser
    preenchido novamente, pois a página foi recarregada).
    """
    log.warning("  Formulário de doação indisponível. Verificando a sessão...")
    try:
        page.goto(URL_FORM_DOACAO, wait_until="domcontentloaded")
        if _esta_no_formulario_doacao(page):
            return True
        if _sessao_expirada(page):
            log.warning("  Sessão expirada. Refazendo login...")
            relogin()
        else:
            try:
                _navegar_para_doacoes(page)
                return True
            except PlaywrightTimeout:
                log.warning("  Menu de doações indisponível. Refazendo login...")
                relogin()
        _navegar_para_doacoes(page)
        log.info("  Sessão restaurada.")
        return True
    except Exception as exc:
        log.error(f"  Não foi possível restaurar a sessão: {exc}")
        return False


def _doar_chave(page: Page, cnpj_entidade: str, chave: str,
                numero: int, total: int,
                verificar_cnpj: bool = True) -> tuple[bool, str]:
    """Preenche e submete o formulário de doação para uma única chave.

    verificar_cnpj=True  → preenche o CNPJ, aciona a verificação automática do
                           portal (blur/change) e confere a resposta HTTP.
    verificar_cnpj=False → o CNPJ já está preenchido e verificado; pula o passo 1.

    Após clicar em DOAR, captura especificamente o POST para documentoFiscalDoadoWeb
    (usando _is_doacao_post) para detectar erros 500 imediatamente, e aguarda a
    navegação automática do portal para a URL de resultado ('_mensagem' ou '_erro')
    para determinar sucesso/falha — sem dependência de XHR genérico.

    Raises:
        CNPJInvalidoError: se a verificação do CNPJ retornar HTTP 400.
    """
    # nNF (posições 26–34) é o número impresso no cupom; os 10 primeiros
    # dígitos se repetem entre notas da mesma loja e não ajudam a identificar.
    log.info(f"Doando chave {numero}/{total}: nota nº {chave[25:34].lstrip('0')} (…{chave[-8:]})")

    try:
        # ── 1. Preenche o CNPJ e aguarda a verificação automática ─────────
        if verificar_cnpj:
            campo_cnpj = page.locator(_SEL_CNPJ).first
            campo_cnpj.wait_for(state="visible", timeout=TIMEOUT_PADRAO)
            campo_cnpj.fill("")
            try:
                with page.expect_response(_is_cnpj_check, timeout=TIMEOUT_PADRAO) as resp_info:
                    campo_cnpj.fill(cnpj_entidade)
                    campo_cnpj.press("Tab")
                cnpj_resp = resp_info.value
                if cnpj_resp.status == 400:
                    msg = _msg_erro_400(cnpj_resp)
                    raise CNPJInvalidoError(
                        f"CNPJ {cnpj_entidade} rejeitado pelo portal (HTTP 400) – {msg}"
                    )
                log.info(f"  CNPJ verificado (HTTP {cnpj_resp.status}).")
            except PlaywrightTimeout:
                log.warning("  Verificação de CNPJ não interceptada (timeout). Prosseguindo.")

        # ── 2. Preenche a chave de acesso ──────────────────────────────────
        # O Tab dispara os eventos blur/change que o JS do portal usa para
        # capturar o valor do campo antes de montar o payload do POST.
        # O wait_for_timeout garante que o JS processe o evento antes do clique.
        campo_chave = page.locator(_SEL_CHAVE).first
        campo_chave.wait_for(state="visible", timeout=TIMEOUT_PADRAO)
        campo_chave.fill("")
        campo_chave.fill(chave)
        campo_chave.press("Tab")          # dispara blur/change
        page.wait_for_timeout(1_000)      # aguarda JS capturar o valor

        # ── 3. Clica em "DOAR DOCUMENTOS" e captura resposta + navegação ──
        # Intercepta especificamente o POST de doação para detectar HTTP 500
        # rapidamente, sem esperar o timeout de navegação inteiro.
        # Para 200 e 400 o portal sempre redireciona para a URL de resultado.
        status_post = None
        try:
            with page.expect_response(_is_doacao_post, timeout=TIMEOUT_NAVEGACAO) as resp_info:
                page.locator("#btnDoarDocumento").click()
            doacao_resp = resp_info.value
            status_post = doacao_resp.status
            log.debug(f"  POST documentoFiscalDoadoWeb retornou HTTP {status_post}.")
        except PlaywrightTimeout:
            log.warning("  Resposta do POST de doação não interceptada. Prosseguindo com verificação por URL.")

        if status_post == 500:
            try:
                corpo = doacao_resp.text()[:300]
            except Exception:
                corpo = "(sem corpo)"
            msg_500 = f"HTTP 500 – {corpo}"
            log.error(f"  ✗ Servidor retornou {msg_500}")
            return False, msg_500

        # Aguarda o redirecionamento do portal para a URL de resultado.
        # (Após 200 e 400 o JS sempre navega; para outros status pode não navegar.)
        try:
            page.wait_for_url(
                lambda url: "_mensagem" in url or "_erro" in url,
                timeout=TIMEOUT_NAVEGACAO,
            )
        except PlaywrightTimeout:
            log.warning("  Redirecionamento pós-doação não detectado. Verificando página atual.")

        # ── 4. Interpreta resultado via URL ────────────────────────────────
        url_atual = page.url
        params = _extrair_params_url(url_atual)

        if "_mensagem" in params:
            mensagem = params["_mensagem"]
            log.info(f"  ✓ Chave {numero}/{total} doada – {mensagem}")
            page.locator(_SEL_CNPJ).first.wait_for(state="visible", timeout=TIMEOUT_PADRAO)
            return True, ""

        if "_erro" in params:
            erro_raw = params["_erro"]
            try:
                erro_obj = json.loads(erro_raw)
                msg_erro = "; ".join(f"{k}: {v}" for k, v in erro_obj.items())
            except Exception:
                msg_erro = erro_raw or "Erro desconhecido"
            log.error(f"  ✗ Doação rejeitada (HTTP 400) – {msg_erro}")
            page.locator(_SEL_CNPJ).first.wait_for(state="visible", timeout=TIMEOUT_PADRAO)
            return False, msg_erro

        msg_indet = f"Resultado indeterminado (URL: {url_atual})"
        log.error(f"  ✗ {msg_indet}")
        return False, msg_indet

    except CNPJInvalidoError:
        raise
    except PlaywrightTimeout as exc:
        msg = f"Timeout: {exc}"
        log.error(f"  ✗ {msg} (chave {numero}/{total})")
        return False, msg
    except Exception as exc:
        msg = f"Erro inesperado: {exc}"
        log.error(f"  ✗ {msg} (chave {numero}/{total})")
        return False, msg


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def abrir_navegador(headless: bool = False) -> tuple[Playwright, Browser, Page]:
    """Abre o navegador e retorna (pw, browser, page) sem fazer login."""
    pw      = sync_playwright().start()
    browser = pw.chromium.launch(headless=headless)
    page    = browser.new_context().new_page()
    page.set_default_timeout(TIMEOUT_PADRAO)
    return pw, browser, page


def fazer_login_portal(page: Page, usuario: str, senha: str) -> None:
    """Realiza login no portal Nota Paraná em uma página já aberta.

    Raises:
        CredenciaisInvalidasError: se usuário ou senha estiverem incorretos.
    """
    _fazer_login(page, so_digitos(usuario), senha)
    _fechar_modal_contato(page)


def doar_lote(page: Page, cnpj_entidade: str, chaves: list[str],
              verificar_cnpj: bool = True,
              relogin: Optional[Callable[[], None]] = None,
              ao_progresso: Optional[Callable[[str, str, str], None]] = None) -> dict:
    """
    Processa um lote de chaves de acesso.

    Para após LIMITE_ERROS_CHAVE erros consecutivos de HTTP 400, definindo
    'parou_por_limite_erros': True no resultado para que o chamador decida
    se continua ou encerra. Rejeições do próprio documento (ex.: prazo de
    doação expirado) não contam para esse limite e não entram em
    'chaves_com_erro' (lista usada para relançamento).

    relogin       → chamado se a sessão expirar no meio do lote; a chave que
                    falhou é tentada mais uma vez após o novo login.
    ao_progresso  → chamado com (chave, status, mensagem) ao iniciar cada nota
                    ("enviando") e ao obter o resultado ("doada",
                    "fora_do_prazo" ou "erro").

    Returns:
        {
            "sucesso":                int,
            "erro":                   int,
            "chaves_com_erro":        list[str],   # falhas + não processadas
            "erros_com_mensagem":     list[tuple[str, str]],  # (chave, msg_erro)
            "chaves_expiradas":       list[str],
            "nao_processadas":        int,
            "cnpj_invalido":          bool,
            "parou_por_limite_erros": bool,
        }
    """
    resultado = {
        "sucesso": 0,
        "erro": 0,
        "chaves_com_erro": [],
        "erros_com_mensagem": [],
        "chaves_expiradas": [],
        "nao_processadas": 0,
        "cnpj_invalido": False,
        "parou_por_limite_erros": False,
    }

    if not chaves:
        return resultado

    if _esta_no_formulario_doacao(page):
        log.info("Formulário de doação já está aberto. Pulando navegação.")
    else:
        _navegar_para_doacoes(page)

    erros_consecutivos = 0
    preencher_cnpj = verificar_cnpj
    avisar = ao_progresso or (lambda *_: None)

    for idx, chave in enumerate(chaves, start=1):
        avisar(chave, "enviando", "")
        try:
            sucesso, msg_erro = _doar_chave(page, cnpj_entidade, chave, idx, len(chaves),
                                            verificar_cnpj=preencher_cnpj)
            preencher_cnpj = False

            # Sessão caiu no meio do lote → novo login e uma nova tentativa
            if (not sucesso and not _is_erro_documento(msg_erro)
                    and relogin is not None and not _formulario_visivel(page)
                    and _restaurar_formulario(page, relogin)):
                sucesso, msg_erro = _doar_chave(page, cnpj_entidade, chave, idx, len(chaves),
                                                verificar_cnpj=True)
        except CNPJInvalidoError as exc:
            log.error(str(exc))
            resultado["cnpj_invalido"] = True
            msg_cnpj = str(exc)
            for c in chaves[idx - 1:]:
                resultado["chaves_com_erro"].append(c)
                resultado["erros_com_mensagem"].append((c, msg_cnpj))
            resultado["erro"] += len(chaves) - idx + 1
            break

        if sucesso:
            resultado["sucesso"] += 1
            erros_consecutivos = 0
            avisar(chave, "doada", "")
        elif _is_erro_documento(msg_erro):
            # Problema da nota, não da execução: registra e segue sem relançar.
            resultado["erro"] += 1
            resultado["chaves_expiradas"].append(chave)
            resultado["erros_com_mensagem"].append((chave, msg_erro))
            avisar(chave, "fora_do_prazo", msg_erro)
        else:
            resultado["erro"] += 1
            resultado["chaves_com_erro"].append(chave)
            resultado["erros_com_mensagem"].append((chave, msg_erro))
            avisar(chave, "erro", msg_erro)
            erros_consecutivos += 1

            if erros_consecutivos >= LIMITE_ERROS_CHAVE:
                log.warning(
                    f"  {LIMITE_ERROS_CHAVE} erros consecutivos. "
                    "Interrompendo lote para verificação do operador."
                )
                resultado["parou_por_limite_erros"] = True
                msg_nao_proc = "Não processada (lote interrompido por erros consecutivos)"
                for c in chaves[idx:]:
                    resultado["chaves_com_erro"].append(c)
                    resultado["erros_com_mensagem"].append((c, msg_nao_proc))
                resultado["nao_processadas"] = len(chaves) - idx
                resultado["erro"] += len(chaves) - idx
                break

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
