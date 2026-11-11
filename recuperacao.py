"""
recuperacao.py
--------------
Guarda em disco as notas lidas que ainda não tiveram resultado definitivo.

Cada chave é gravada assim que é lida. Se o programa fechar, o computador
desligar ou o lançamento der erro, as notas continuam em notas_pendentes.json
e o programa oferece retomá-las na próxima vez. Notas que já constam no
histórico (doadas ou fora do prazo) saem da lista sozinhas.
"""

import json
import os
import re
from pathlib import Path
from typing import Iterable

CAMINHO = Path(__file__).parent / "notas_pendentes.json"


def _ler() -> list[str]:
    try:
        dados = json.loads(CAMINHO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(dados, list):
        return []
    return [c for c in dados if isinstance(c, str) and re.fullmatch(r"\d{44}", c)]


def _gravar(chaves: list[str]) -> None:
    """Grava por arquivo temporário, para nunca deixar o arquivo pela metade."""
    try:
        if not chaves:
            CAMINHO.unlink(missing_ok=True)
            return
        tmp = CAMINHO.with_suffix(".tmp")
        tmp.write_text(json.dumps(chaves), encoding="utf-8")
        os.replace(tmp, CAMINHO)
    except OSError:
        pass   # falha ao guardar não pode interromper a leitura das notas


def carregar(resolvidas: Iterable[str] = ()) -> list[str]:
    """Notas guardadas ainda sem resultado; limpa do arquivo as já resolvidas."""
    resolvidas = set(resolvidas)
    guardadas = list(dict.fromkeys(_ler()))
    pendentes = [c for c in guardadas if c not in resolvidas]
    if pendentes != _ler():
        _gravar(pendentes)
    return pendentes


def adicionar(chave: str) -> None:
    guardadas = _ler()
    if chave not in guardadas:
        _gravar(guardadas + [chave])


def remover(chaves: Iterable[str]) -> None:
    retirar = set(chaves)
    _gravar([c for c in _ler() if c not in retirar])
