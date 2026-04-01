"""
main.py
-------
Ponto de entrada da automação de doação no Nota Paraná.

Fluxo:
  1. Coleta de códigos via leitor de QR/barcode USB (entrada de teclado HID).
  2. Confirmação visual das chaves coletadas pelo operador.
  3. Login e doação automática no portal Nota Paraná via Playwright.
  4. Exibição de aviso visual com o resultado final.

Uso:
    python main.py [--headless]

    --headless   Executa o navegador sem janela gráfica.
"""

import argparse
import os
import sys

from qr_collector import coletar_qr_codes, _fmt as fmt_chave, _cor, \
    _VERDE, _VERMELHO, _AMARELO, _AZUL, _NEGRITO, _RESET, _limpar_tela
from notaparana_bot import executar_doacoes


# ---------------------------------------------------------------------------
# Telas de apoio ao usuário leigo
# ---------------------------------------------------------------------------

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


def _tela_resultado(total: int, sucesso: int, erros: int,
                    chaves_erro: list[str]) -> None:
    """Exibe o aviso visual final de resultado – adequado para leigo."""
    _limpar_tela()

    if erros == 0:
        # ─── Tudo certo ─────────────────────────────────────────────────
        borda = _cor("=" * 62, _VERDE)
        titulo = _cor("   ✔  DOAÇÃO CONCLUÍDA COM SUCESSO!", _VERDE + _NEGRITO)
        print(borda)
        print(titulo)
        print(borda)
        print()
        print(f"   {_cor(str(sucesso), _VERDE + _NEGRITO)} nota(s) doadas com sucesso.")
        print()
        print(borda)

    elif sucesso == 0:
        # ─── Tudo falhou ────────────────────────────────────────────────
        borda = _cor("=" * 62, _VERMELHO)
        titulo = _cor("   ✘  NENHUMA DOAÇÃO FOI REALIZADA", _VERMELHO + _NEGRITO)
        print(borda)
        print(titulo)
        print(borda)
        print()
        print("   Verifique sua conexão com a internet e as credenciais")
        print("   do arquivo .env, depois tente novamente.")
        print()
        print(borda)

    else:
        # ─── Resultado parcial ───────────────────────────────────────────
        borda = _cor("=" * 62, _AMARELO)
        titulo = _cor("   ⚠  DOAÇÃO PARCIALMENTE CONCLUÍDA", _AMARELO + _NEGRITO)
        print(borda)
        print(titulo)
        print(borda)
        print()
        print(f"   {_cor(str(sucesso), _VERDE + _NEGRITO)} nota(s) doadas com sucesso.")
        print(f"   {_cor(str(erros),   _VERMELHO + _NEGRITO)} nota(s) com erro:")
        print()
        for c in chaves_erro:
            print(f"      •  {fmt_chave(c)}")
        print()
        print("   As notas com erro podem ser tentadas manualmente no site.")
        print()
        print(borda)

    print()
    input("   Pressione ENTER para fechar...")


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

    # ── ETAPA 1: Coleta ──────────────────────────────────────────────────
    chaves = coletar_qr_codes()

    if not chaves:
        _limpar_tela()
        print(_cor("=" * 62, _AMARELO))
        print(_cor("   Nenhuma nota registrada. Encerrando.", _AMARELO))
        print(_cor("=" * 62, _AMARELO))
        print()
        input("   Pressione ENTER para fechar...")
        sys.exit(0)

    # ── ETAPA 2: Confirmação ──────────────────────────────────────────────
    if not _tela_confirmacao(chaves):
        _limpar_tela()
        print(_cor("   Doação cancelada pelo operador.", _AMARELO))
        print()
        input("   Pressione ENTER para fechar...")
        sys.exit(0)

    # ── ETAPA 3: Doação automática ────────────────────────────────────────
    _tela_processando(len(chaves))
    resultado = executar_doacoes(chaves, headless=args.headless)

    # ── ETAPA 4: Resultado visual ─────────────────────────────────────────
    _tela_resultado(
        total=len(chaves),
        sucesso=resultado["sucesso"],
        erros=resultado["erro"],
        chaves_erro=resultado["chaves_com_erro"],
    )

    sys.exit(1 if resultado["erro"] > 0 else 0)


if __name__ == "__main__":
    main()
