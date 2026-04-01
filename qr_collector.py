"""
qr_collector.py
---------------
Coleta de chaves de acesso NF-e/NFC-e a partir de um leitor de código
de barras / QR code USB (modo HID – emula teclado).

O leitor envia o conteúdo escaneado seguido de ENTER automaticamente.
Basta apontar para os códigos; nenhuma interação adicional é necessária.

Para encerrar a coleta: pressione ENTER com o campo vazio, ou
                        leia um QR/código com o texto "FIM".
"""

import re
import os
import sys
from typing import Optional

# ---------------------------------------------------------------------------
# Cores ANSI (funcionam em Linux/macOS; no Windows requer terminal moderno)
# ---------------------------------------------------------------------------
_VERDE   = "\033[92m"
_VERMELHO = "\033[91m"
_AMARELO = "\033[93m"
_AZUL    = "\033[94m"
_NEGRITO = "\033[1m"
_RESET   = "\033[0m"


def _cor(texto: str, cor: str) -> str:
    return f"{cor}{texto}{_RESET}"


# ---------------------------------------------------------------------------
# Funções de extração e validação
# ---------------------------------------------------------------------------

_CUFS_VALIDOS = {"41"}   # cUF do Paraná


def _extrair_chave(dado: str) -> Optional[str]:
    """Extrai a chave de acesso de 44 dígitos de qualquer formato de QR/barcode."""
    # NFC-e Paraná: URL com ?p=CHAVE44|...
    m = re.search(r'[?&]p=(\d{44})', dado)
    if m:
        return m.group(1)

    # Parâmetro chNFe= em URL
    m = re.search(r'chNFe=(\d{44})', dado, re.IGNORECASE)
    if m:
        return m.group(1)

    # Sequência pura de 44 dígitos (código de barras linear ou QR simples)
    m = re.search(r'(?<!\d)(\d{44})(?!\d)', dado)
    if m:
        return m.group(1)

    return None


def _calcular_dv(chave43: str) -> int:
    """Dígito verificador Módulo 11 conforme manual SEFAZ."""
    pesos = list(range(2, 10)) * 6
    soma = sum(int(d) * p for d, p in zip(reversed(chave43), pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def validar_chave(chave: str) -> tuple[bool, str]:
    """Retorna (True, '') se válida, ou (False, motivo) se inválida."""
    if not re.match(r'^\d{44}$', chave):
        return False, "precisa ter exatamente 44 dígitos numéricos"

    if chave[:2] not in _CUFS_VALIDOS:
        return False, f"código de estado '{chave[:2]}' não é o Paraná (esperado 41)"

    if chave[20:22] not in ("55", "65"):
        return False, f"modelo '{chave[20:22]}' desconhecido (esperado 55=NF-e, 65=NFC-e)"

    if _calcular_dv(chave[:43]) != int(chave[43]):
        return False, "dígito verificador inválido (código corrompido?)"

    return True, ""


# ---------------------------------------------------------------------------
# Helpers de exibição
# ---------------------------------------------------------------------------

def _fmt(chave: str) -> str:
    """Formata a chave em grupos de 4 dígitos para facilitar leitura."""
    return " ".join(chave[i:i+4] for i in range(0, 44, 4))


def _limpar_tela() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _cabecalho(total: int, invalidas: int) -> None:
    _limpar_tela()
    print(_cor("=" * 62, _AZUL))
    print(_cor("   LEITOR DE NOTAS FISCAIS – NOTA PARANÁ", _NEGRITO))
    print(_cor("=" * 62, _AZUL))
    print(f"   Notas registradas : {_cor(str(total), _VERDE)}")
    if invalidas:
        print(f"   Leituras inválidas: {_cor(str(invalidas), _VERMELHO)}")
    print(_cor("-" * 62, _AZUL))
    print("   Aponte o leitor para o QR code ou código de barras da nota.")
    print("   Para FINALIZAR: leia um código 'FIM' ou tecle ENTER vazio.")
    print(_cor("=" * 62, _AZUL))
    print()


# ---------------------------------------------------------------------------
# Loop principal de coleta
# ---------------------------------------------------------------------------

def coletar_qr_codes() -> list[str]:
    """
    Aguarda leituras do leitor de código de barras/QR (entrada via teclado HID).

    Retorna lista de chaves de acesso válidas e únicas.
    """
    chaves: list[str] = []
    invalidas: int = 0
    historico: list[str] = []   # log de mensagens de feedback

    _cabecalho(0, 0)

    while True:
        try:
            entrada = input("   > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        # Sinaliza fim da coleta
        if entrada == "" or entrada.upper() == "FIM":
            break

        chave = _extrair_chave(entrada)

        if chave is None:
            invalidas += 1
            msg = _cor(f"  ✗  Código não reconhecido: {entrada[:60]}", _VERMELHO)
            historico.append(msg)
            _cabecalho(len(chaves), invalidas)
            for linha in historico[-15:]:   # mostra as últimas 15 mensagens
                print(linha)
            continue

        if chave in chaves:
            msg = _cor(
                f"  ⚠  Nota já registrada (ignorada): {_fmt(chave)}",
                _AMARELO
            )
            historico.append(msg)
            _cabecalho(len(chaves), invalidas)
            for linha in historico[-15:]:
                print(linha)
            continue

        valida, motivo = validar_chave(chave)
        if not valida:
            invalidas += 1
            msg = _cor(f"  ✗  Chave inválida ({motivo}): {_fmt(chave)}", _VERMELHO)
            historico.append(msg)
            _cabecalho(len(chaves), invalidas)
            for linha in historico[-15:]:
                print(linha)
            continue

        chaves.append(chave)
        msg = _cor(
            f"  ✓  #{len(chaves):>3}  {_fmt(chave)}",
            _VERDE
        )
        historico.append(msg)
        _cabecalho(len(chaves), invalidas)
        for linha in historico[-15:]:
            print(linha)

    return chaves


# ---------------------------------------------------------------------------
# Execução direta (teste isolado)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    chaves = coletar_qr_codes()
    print()
    if chaves:
        print(_cor(f"  {len(chaves)} chave(s) coletada(s) com sucesso.", _VERDE))
    else:
        print("  Nenhuma chave coletada.")
