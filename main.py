"""
main.py
-------
Ponto de entrada da automação de doação no Nota Paraná.

Fluxo:
  1. Coleta de QR codes via câmera (com validação em tempo real).
  2. Confirmação das chaves coletadas pelo operador.
  3. Login e doação automática no portal Nota Paraná via Playwright.

Uso:
    python main.py [--headless] [--camera INDICE]

    --headless         Executa o navegador sem janela gráfica (modo CI).
    --camera INDICE    Índice da câmera (padrão: 0).
"""

import argparse
import json
import sys
from pathlib import Path

from qr_collector import coletar_qr_codes, _fmt as fmt_chave
from notaparana_bot import executar_doacoes


def _confirmar(chaves: list[str]) -> bool:
    """Exibe as chaves coletadas e pede confirmação antes de prosseguir."""
    print("\n" + "=" * 60)
    print(f"  {len(chaves)} chave(s) prontas para doação:")
    print("=" * 60)
    for i, c in enumerate(chaves, 1):
        print(f"  {i:>3}. {fmt_chave(c)}")
    print("=" * 60)
    resp = input("\nConfirmar doação de todas as chaves acima? [s/N] ").strip().lower()
    return resp in ("s", "sim", "y", "yes")


def _salvar_log(chaves: list[str], resultado: dict) -> None:
    """Grava um JSON com o resumo da execução."""
    log_path = Path("resultado_doacao.json")
    dados = {
        "total_chaves": len(chaves),
        "sucesso": resultado["sucesso"],
        "erro": resultado["erro"],
        "chaves_com_erro": resultado["chaves_com_erro"],
    }
    log_path.write_text(json.dumps(dados, indent=2, ensure_ascii=False))
    print(f"\n[LOG] Resumo salvo em: {log_path.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automação de doação de notas fiscais no Nota Paraná"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Executa o navegador sem interface gráfica",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        metavar="INDICE",
        help="Índice da câmera a usar (padrão: 0)",
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # ETAPA 1 – Coleta de QR codes
    # ------------------------------------------------------------------
    print("\n>>> ETAPA 1: Coleta de QR Codes\n")
    chaves = coletar_qr_codes(indice_camera=args.camera)

    if not chaves:
        print("\nNenhuma chave válida coletada. Encerrando.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # ETAPA 2 – Confirmação do operador
    # ------------------------------------------------------------------
    print("\n>>> ETAPA 2: Confirmação\n")
    if not _confirmar(chaves):
        print("Doação cancelada pelo operador.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # ETAPA 3 – Login e doação automática
    # ------------------------------------------------------------------
    print("\n>>> ETAPA 3: Doação automática no Nota Paraná\n")
    resultado = executar_doacoes(chaves, headless=args.headless)

    # ------------------------------------------------------------------
    # Resumo final
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("  RESUMO FINAL")
    print("=" * 60)
    print(f"  Total de chaves   : {len(chaves)}")
    print(f"  Doadas com sucesso: {resultado['sucesso']}")
    print(f"  Com erro          : {resultado['erro']}")
    if resultado["chaves_com_erro"]:
        print("\n  Chaves que falharam:")
        for c in resultado["chaves_com_erro"]:
            print(f"    • {fmt_chave(c)}")
    print("=" * 60)

    _salvar_log(chaves, resultado)

    sys.exit(1 if resultado["erro"] > 0 else 0)


if __name__ == "__main__":
    main()
