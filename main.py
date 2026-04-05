"""
main.py
-------
Ponto de entrada da automação de doação no Nota Paraná.

Fluxo:
  1. Solicita a senha ao usuário (oculta na digitação).
  2. Abre o navegador e faz login no portal.
  3. Loop:
       a. Coleta QR codes via leitor USB.
       b. Confirmação do operador.
       c. Doação automática no portal (mesmo navegador).
       d. Exibe resultado visual.
       e. Pergunta se deseja lançar mais notas.
  4. Faz logout no site e encerra o navegador.

Uso:
    python main.py [--headless]
"""

import argparse
import getpass
import sys

from qr_collector import coletar_qr_codes, _fmt as fmt_chave, _cor, \
    _VERDE, _VERMELHO, _AMARELO, _AZUL, _NEGRITO, _RESET, _limpar_tela
from notaparana_bot import iniciar_sessao, doar_lote, encerrar_sessao


# ---------------------------------------------------------------------------
# Telas de apoio ao usuário
# ---------------------------------------------------------------------------

def _tela_senha() -> str:
    """Solicita a senha de forma segura (caracteres ocultos)."""
    _limpar_tela()
    print(_cor("=" * 62, _AZUL))
    print(_cor("   NOTA PARANÁ – DOAÇÃO AUTOMÁTICA", _NEGRITO))
    print(_cor("=" * 62, _AZUL))
    print()
    print("   Digite sua senha de acesso ao Nota Paraná.")
    print("   (Os caracteres não serão exibidos durante a digitação.)")
    print()
    return getpass.getpass("   Senha: ")


def _tela_confirmacao(chaves: list[str]) -> bool:
    """Exibe a lista de chaves coletadas e pede confirmação simples."""
    _limpar_tela()
    print(_cor("=" * 62, _AZUL))
    print(_cor("   CONFIRMAÇÃO – NOTAS PARA DOAÇÃO", _NEGRITO))
    print(_cor("=" * 62, _AZUL))
    print(f"\n   {_cor(str(len(chaves)), _NEGRITO)} nota(s) serão doadas:\n")
    for i, c in enumerate(chaves, 1):
        print(f"   {i:>3}.  {fmt_chave(c)}")
    print()
    print(_cor("-" * 62, _AZUL))
    print("   Digite  S  e pressione ENTER para confirmar.")
    print("   Digite  N  e pressione ENTER para cancelar.")
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


def _tela_resultado(sucesso: int, erros: int, chaves_erro: list[str]) -> None:
    """Exibe o aviso visual de resultado do lote."""
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
        print("\n   Verifique sua conexão e tente novamente.\n")
        print(borda)

    else:
        borda  = _cor("=" * 62, _AMARELO)
        titulo = _cor("   ⚠  DOAÇÃO PARCIALMENTE CONCLUÍDA", _AMARELO + _NEGRITO)
        print(borda)
        print(titulo)
        print(borda)
        print(f"\n   {_cor(str(sucesso), _VERDE + _NEGRITO)} nota(s) doadas com sucesso.")
        print(f"   {_cor(str(erros),    _VERMELHO + _NEGRITO)} nota(s) com erro:\n")
        for c in chaves_erro:
            print(f"      •  {fmt_chave(c)}")
        print("\n   As notas com erro podem ser tentadas manualmente no site.")
        print()
        print(borda)


def _perguntar_mais_notas() -> bool:
    """Pergunta se o operador deseja lançar mais um lote de notas."""
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
        "--headless",
        action="store_true",
        help="Executa o navegador sem janela gráfica",
    )
    args = parser.parse_args()

    # ── Solicita senha (oculta) ──────────────────────────────────────────────
    senha = _tela_senha()
    if not senha:
        print("\n   Senha não informada. Encerrando.")
        sys.exit(0)

    # ── Abre navegador e faz login ────────────────────────────────────────────
    print("\n   Iniciando sessão no Nota Paraná...")
    pw, browser, page, cnpj_entidade = iniciar_sessao(senha, headless=args.headless)

    houve_erro_geral = False

    try:
        while True:
            # ── Coleta de QR codes ─────────────────────────────────────────
            chaves = coletar_qr_codes()

            if not chaves:
                _limpar_tela()
                print(_cor("   Nenhuma nota registrada.", _AMARELO))
                if not _perguntar_mais_notas():
                    break
                continue

            # ── Confirmação ────────────────────────────────────────────────
            if not _tela_confirmacao(chaves):
                print("\n   Lote cancelado pelo operador.")
                if not _perguntar_mais_notas():
                    break
                continue

            # ── Doação ────────────────────────────────────────────────────
            _tela_processando(len(chaves))
            resultado = doar_lote(page, cnpj_entidade, chaves)

            # ── Resultado ─────────────────────────────────────────────────
            _tela_resultado(resultado["sucesso"], resultado["erro"],
                            resultado["chaves_com_erro"])

            if resultado["erro"] > 0:
                houve_erro_geral = True

            if not _perguntar_mais_notas():
                break

    finally:
        # ── Logout e encerramento ──────────────────────────────────────────
        encerrar_sessao(pw, browser, page)
        print("\n   Sessão encerrada. Até logo!")

    sys.exit(1 if houve_erro_geral else 0)


if __name__ == "__main__":
    main()
