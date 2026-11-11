"""
som.py
------
Sons curtos de sucesso e de falha.

Quem passa o leitor nas notas olha para a nota, não para a tela: o som avisa
na hora se a leitura foi aceita (um "bip" agudo e curto) ou recusada (um "bip"
grave e mais longo). No Windows usa winsound; nos demais sistemas, o sinal
sonoro do terminal. Qualquer falha ao tocar é ignorada (o som é só um aviso).
"""

import sys

try:
    import winsound
except ImportError:     # Linux / macOS
    winsound = None


def _tocar(notas: list[tuple[int, int]]) -> None:
    """Toca uma sequência de (frequência em Hz, duração em ms)."""
    try:
        if winsound is not None:
            for freq, ms in notas:
                winsound.Beep(freq, ms)
        else:
            sys.stdout.write("\a" * len(notas))
            sys.stdout.flush()
    except Exception:
        pass


def sucesso() -> None:
    """Um bip agudo e curto."""
    _tocar([(1200, 110)])


def falha() -> None:
    """Dois bips graves, mais longos – inconfundível com o de sucesso."""
    _tocar([(400, 150), (300, 200)])
