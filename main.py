"""
main.py
-------
Ponto de entrada da automação de doação no Nota Paraná.

Fluxo:
  1. Solicita usuário, CNPJ da entidade e senha (esta última não é salva).
     Usuário e CNPJ são pré-preenchidos com os valores da última execução.
  2. Abre o navegador e faz login no portal.
     Se as credenciais estiverem erradas, pede novamente SEM fechar o navegador.
  3. Loop:
       a. Coleta QR codes via leitor USB.
       b. Confirmação do operador.
       c. Doação automática no portal (mesmo navegador).
       d. Exibe resultado visual.
       e. Se houver ≥ LIMITE_ERROS_CHAVE erros consecutivos, pergunta se continua.
       f. Pergunta se deseja lançar mais notas.
  4. Ao encerrar, tenta automaticamente relançar todas as notas com erro.
  5. Faz logout no site e encerra o navegador.

Uso:
    python main.py [--headless]
"""

import argparse
import getpass
import json
import re
import sys
from pathlib import Path

from qr_collector import coletar_qr_codes, _fmt as fmt_chave, _cor, \
    _VERDE, _VERMELHO, _AMARELO, _AZUL, _NEGRITO, _RESET, _limpar_tela
from notaparana_bot import (
    abrir_navegador,
    fazer_login_portal,
    iniciar_sessao,
    doar_lote,
    encerrar_sessao,
    CredenciaisInvalidasError,
    LIMITE_ERROS_CHAVE,
)

# Arquivo de configuração local (não versionado)
_CONFIG_PATH = Path(__file__).parent / "config.json"


# ---------------------------------------------------------------------------
# Persistência de configuração
# ---------------------------------------------------------------------------

def _carregar_config() -> dict:
    """Lê config.json; retorna dict vazio se não existir."""
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _salvar_config(config: dict) -> None:
    """Grava config.json com os dados não-sensíveis."""
    _CONFIG_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Prompts de entrada
# ---------------------------------------------------------------------------

def _input_com_padrao(label: str, padrao: str = "") -> str:
    """Exibe prompt com valor padrão pré-preenchido. ENTER mantém o padrão."""
    if padrao:
        valor = input(f"   {label} [{padrao}]: ").strip()
        return valor if valor else padrao
    return input(f"   {label}: ").strip()


def _so_digitos(texto: str) -> str:
    return re.sub(r'\D', '', texto)


def _tela_credenciais(config: dict) -> tuple[str, str, str]:
    """
    Solicita usuário, CNPJ da entidade e senha.
    Retorna (usuario, cnpj_entidade, senha).
    Usuário e CNPJ são pré-preenchidos com valores salvos (editáveis).
    Senha nunca é pré-preenchida nem salva.
    """
    _limpar_tela()
    print(_cor("=" * 62, _AZUL))
    print(_cor("   NOTA PARANÁ – DOAÇÃO AUTOMÁTICA", _NEGRITO))
    print(_cor("=" * 62, _AZUL))
    print()
    print("   Preencha os dados abaixo.")
    print("   Campos com [ ] já possuem valor salvo — pressione ENTER para manter.")
    print()

    # Usuário
    usuario = ""
    while not usuario:
        usuario = _so_digitos(
            _input_com_padrao("Usuário (CPF)", config.get("usuario", ""))
        )
        if not usuario:
            print("   Campo obrigatório.\n")

    # CNPJ da entidade
    cnpj_entidade = ""
    while len(cnpj_entidade) != 14:
        raw = _input_com_padrao(
            "CNPJ da entidade (14 dígitos)", config.get("cnpj_entidade", "")
        )
        cnpj_entidade = _so_digitos(raw)
        if len(cnpj_entidade) != 14:
            print(f"   CNPJ deve ter 14 dígitos (informado: {len(cnpj_entidade)}).\n")

    # Senha (oculta, nunca salva)
    print()
    print("   A senha não será exibida durante a digitação.")
    senha = ""
    while not senha:
        senha = getpass.getpass("   Senha: ")
        if not senha:
            print("   Campo obrigatório.\n")

    return usuario, cnpj_entidade, senha


def _tela_login_invalido(usuario: str) -> tuple[str, str]:
    """
    Exibe mensagem de credenciais inválidas e pede novo usuário/senha.
    O navegador permanece aberto. Retorna (usuario, senha).
    """
    _limpar_tela()
    print(_cor("=" * 62, _VERMELHO))
    print(_cor("   LOGIN FALHOU – CREDENCIAIS INVÁLIDAS", _VERMELHO + _NEGRITO))
    print(_cor("=" * 62, _VERMELHO))
    print()
    print("   Usuário ou senha incorretos.")
    print("   Informe as credenciais corretas abaixo.")
    print("   O navegador permanece aberto.")
    print()

    novo_usuario_raw = _input_com_padrao("Usuário (CPF)", usuario).strip()
    novo_usuario = _so_digitos(novo_usuario_raw) if novo_usuario_raw else usuario

    print()
    print("   A senha não será exibida durante a digitação.")
    nova_senha = ""
    while not nova_senha:
        nova_senha = getpass.getpass("   Senha: ")
        if not nova_senha:
            print("   Campo obrigatório.\n")

    return novo_usuario, nova_senha


# ---------------------------------------------------------------------------
# Telas de navegação
# ---------------------------------------------------------------------------

def _tela_confirmacao(chaves: list[str]) -> bool:
    _limpar_tela()
    print(_cor("=" * 62, _AZUL))
    print(_cor("   CONFIRMAÇÃO – NOTAS PARA DOAÇÃO", _NEGRITO))
    print(_cor("=" * 62, _AZUL))
    print(f"\n   {_cor(str(len(chaves)), _NEGRITO)} nota(s) serão doadas:\n")
    for i, c in enumerate(chaves, 1):
        print(f"   {i:>3}.  {fmt_chave(c)}")
    print()
    print(_cor("-" * 62, _AZUL))
    print("   S = confirmar  |  N = cancelar")
    print(_cor("=" * 62, _AZUL))
    while True:
        resp = input("\n   Sua escolha [S/N]: ").strip().upper()
        if resp in ("S", "SIM"):
            return True
        if resp in ("N", "NAO", "NÃO", ""):
            return False
        print("   Por favor, digite S ou N.")


def _tela_processando(total: int) -> None:
    _limpar_tela()
    print(_cor("=" * 62, _AZUL))
    print(_cor("   ENVIANDO DOAÇÕES...", _NEGRITO))
    print(_cor("=" * 62, _AZUL))
    print(f"\n   Aguarde. Processando {total} nota(s)...")
    print("   Não feche esta janela.\n")


def _tela_resultado(sucesso: int, erros: int,
                    erros_com_mensagem: list[tuple[str, str]]) -> None:
    _limpar_tela()

    if erros == 0:
        borda  = _cor("=" * 62, _VERDE)
        titulo = _cor("   ✔  DOAÇÃO CONCLUÍDA COM SUCESSO!", _VERDE + _NEGRITO)
        print(borda)
        print(titulo)
        print(borda)
        print(f"\n   {_cor(str(sucesso), _VERDE + _NEGRITO)} nota(s) doadas com sucesso.\n")
        print(borda)

    elif sucesso == 0:
        borda  = _cor("=" * 62, _VERMELHO)
        titulo = _cor("   ✘  NENHUMA DOAÇÃO FOI REALIZADA", _VERMELHO + _NEGRITO)
        print(borda)
        print(titulo)
        print(borda)
        print(f"\n   {_cor(str(erros), _VERMELHO + _NEGRITO)} nota(s) com erro:\n")
        for chave, msg in erros_com_mensagem:
            print(f"      •  {fmt_chave(chave)}")
            print(f"         {_cor(msg, _VERMELHO)}")
        print()
        print(borda)

    else:
        borda  = _cor("=" * 62, _AMARELO)
        titulo = _cor("   ⚠  DOAÇÃO PARCIALMENTE CONCLUÍDA", _AMARELO + _NEGRITO)
        print(borda)
        print(titulo)
        print(borda)
        print(f"\n   {_cor(str(sucesso), _VERDE + _NEGRITO)} nota(s) doadas com sucesso.")
        print(f"   {_cor(str(erros),    _VERMELHO + _NEGRITO)} nota(s) com erro:\n")
        for chave, msg in erros_com_mensagem:
            print(f"      •  {fmt_chave(chave)}")
            print(f"         {_cor(msg, _VERMELHO)}")
        print()
        print(borda)


def _pedir_cnpj_valido(cnpj_invalido: str) -> str:
    """Informa ao operador que o CNPJ foi rejeitado e solicita o CNPJ correto."""
    _limpar_tela()
    print(_cor("=" * 62, _VERMELHO))
    print(_cor("   CNPJ INVÁLIDO", _VERMELHO + _NEGRITO))
    print(_cor("=" * 62, _VERMELHO))
    print(f"\n   O CNPJ informado foi rejeitado pelo portal (HTTP 400).")
    print(f"   CNPJ recusado: {cnpj_invalido}")
    print("   Informe o CNPJ correto para prosseguir com as doações.\n")
    print(_cor("-" * 62, _VERMELHO))

    novo = ""
    while len(novo) != 14:
        raw = _input_com_padrao("CNPJ correto da entidade (14 dígitos)", "")
        novo = _so_digitos(raw)
        if len(novo) != 14:
            print(f"   CNPJ deve ter 14 dígitos (informado: {len(novo)}).\n")
    return novo


def _tela_limite_erros(n_erros: int, n_restantes: int) -> bool:
    """
    Exibe aviso de muitos erros consecutivos e pergunta se deve continuar.
    Retorna True se o operador quiser continuar, False para encerrar.
    """
    _limpar_tela()
    print(_cor("=" * 62, _AMARELO))
    print(_cor(f"   {LIMITE_ERROS_CHAVE} ERROS CONSECUTIVOS – LOTE INTERROMPIDO",
               _AMARELO + _NEGRITO))
    print(_cor("=" * 62, _AMARELO))
    print(f"\n   {n_erros} nota(s) com erro HTTP 400 seguidas.")
    print(f"   {n_restantes} nota(s) restante(s) ainda não processada(s).")
    print()
    print("   Possíveis causas:")
    print("   • Chaves de acesso inválidas ou já doadas anteriormente")
    print("   • Problema temporário no portal")
    print()
    print(_cor("-" * 62, _AMARELO))
    print("   S = tentar as notas restantes  |  N = encerrar lançamento")
    print(_cor("=" * 62, _AMARELO))
    while True:
        resp = input("\n   Sua escolha [S/N]: ").strip().upper()
        if resp in ("S", "SIM"):
            return True
        if resp in ("N", "NAO", "NÃO", ""):
            return False
        print("   Por favor, digite S ou N.")


def _perguntar_mais_notas() -> bool:
    print()
    print(_cor("-" * 62, _AZUL))
    print("   Deseja lançar mais notas?")
    print("   S = sim, continuar  |  N = não, encerrar")
    print(_cor("-" * 62, _AZUL))
    while True:
        resp = input("\n   Sua escolha [S/N]: ").strip().upper()
        if resp in ("S", "SIM"):
            return True
        if resp in ("N", "NAO", "NÃO", ""):
            return False
        print("   Por favor, digite S ou N.")


# ---------------------------------------------------------------------------
# Fluxo principal
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automação de doação de notas fiscais no Nota Paraná"
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Executa o navegador sem janela gráfica",
    )
    args = parser.parse_args()

    # ── Lê configuração salva e solicita credenciais ─────────────────────────
    config = _carregar_config()
    usuario, cnpj_entidade, senha = _tela_credenciais(config)

    # Salva usuário e CNPJ (nunca a senha)
    config["usuario"]       = usuario
    config["cnpj_entidade"] = cnpj_entidade
    _salvar_config(config)

    pw = browser = page = None
    houve_erro_geral = False
    cnpj_verificado  = False
    todas_chaves_erro: list[str] = []   # acumula erros de todos os lotes

    try:
        while True:
            # ── Coleta ────────────────────────────────────────────────────
            chaves = coletar_qr_codes()

            if not chaves:
                _limpar_tela()
                print(_cor("   Nenhuma nota registrada.", _AMARELO))
                if pw is None or not _perguntar_mais_notas():
                    break
                continue

            # ── Confirmação ───────────────────────────────────────────────
            if not _tela_confirmacao(chaves):
                print("\n   Lote cancelado pelo operador.")
                if pw is None or not _perguntar_mais_notas():
                    break
                continue

            # ── Abre navegador (apenas no primeiro lançamento) ────────────
            if pw is None:
                print("\n   Iniciando sessão no Nota Paraná...")
                pw, browser, page = abrir_navegador(headless=args.headless)

                # Login com retry – navegador permanece aberto em caso de erro
                while True:
                    try:
                        fazer_login_portal(page, usuario, senha)
                        break
                    except CredenciaisInvalidasError:
                        usuario, senha = _tela_login_invalido(usuario)
                        config["usuario"] = usuario
                        _salvar_config(config)

            # ── Doação (com retry em caso de CNPJ inválido ou limite de erros) ─
            _tela_processando(len(chaves))
            chaves_lote = list(chaves)

            while True:
                resultado = doar_lote(
                    page, cnpj_entidade, chaves_lote,
                    verificar_cnpj=not cnpj_verificado,
                )

                # CNPJ rejeitado → pede novo CNPJ e reprocessa as mesmas chaves
                if resultado.get("cnpj_invalido"):
                    cnpj_entidade = _pedir_cnpj_valido(cnpj_entidade)
                    config["cnpj_entidade"] = cnpj_entidade
                    _salvar_config(config)
                    chaves_lote = resultado["chaves_com_erro"]
                    _tela_processando(len(chaves_lote))
                    continue

                # Muitos erros seguidos → pergunta ao operador se continua
                if resultado.get("parou_por_limite_erros"):
                    n_restantes = len(resultado["chaves_com_erro"])
                    continuar = _tela_limite_erros(resultado["erro"], n_restantes)
                    if continuar:
                        chaves_lote = resultado["chaves_com_erro"]
                        cnpj_verificado = True
                        _tela_processando(len(chaves_lote))
                        continue
                    else:
                        # Operador optou por não continuar
                        break

                cnpj_verificado = True
                break

            # ── Resultado ────────────────────────────────────────────────
            _tela_resultado(
                resultado["sucesso"],
                resultado["erro"],
                resultado["erros_com_mensagem"],
            )

            if resultado["erro"] > 0:
                houve_erro_geral = True
                todas_chaves_erro.extend(resultado["chaves_com_erro"])

            if not _perguntar_mais_notas():
                break

        # ── Retry automático das notas com erro ──────────────────────────────
        # Remove duplicatas preservando a ordem
        chaves_retry = list(dict.fromkeys(todas_chaves_erro))
        if chaves_retry and pw is not None:
            _limpar_tela()
            print(_cor("=" * 62, _AZUL))
            print(_cor("   RELANÇANDO NOTAS COM ERRO", _NEGRITO))
            print(_cor("=" * 62, _AZUL))
            print(f"\n   Tentando novamente {len(chaves_retry)} nota(s) que deram erro...\n")

            _tela_processando(len(chaves_retry))
            resultado_retry = doar_lote(
                page, cnpj_entidade, chaves_retry, verificar_cnpj=False
            )
            _tela_resultado(
                resultado_retry["sucesso"],
                resultado_retry["erro"],
                resultado_retry["erros_com_mensagem"],
            )
            if resultado_retry["erro"] == 0:
                houve_erro_geral = False   # todos os erros foram recuperados

    finally:
        # ── Logout e encerramento (só se o navegador foi aberto) ─────────
        if pw is not None:
            encerrar_sessao(pw, browser, page)
            print("\n   Sessão encerrada. Até logo!")
        else:
            print("\n   Nenhuma sessão iniciada. Até logo!")

    sys.exit(1 if houve_erro_geral else 0)


if __name__ == "__main__":
    main()
