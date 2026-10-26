"""
painel.py
---------
Tela fixa de envio das doações e configuração do log.

Durante o envio, em vez de um log rolando, o console mostra um painel
redesenhado a cada nota: barra de progresso, contadores, previsão de término
e as últimas notas. O log técnico completo vai para logs/AAAA-MM-DD.log.
"""

import logging
import os
import shutil
import sys
import time
from collections import deque
from datetime import date
from pathlib import Path

from qr_collector import _cor, _VERDE, _VERMELHO, _AMARELO, _AZUL, _NEGRITO

PASTA_LOGS = Path(__file__).parent / "logs"
LARGURA_CONSOLE = 100
_ULTIMAS = 8
_LARGURA_BARRA = 40
_CINZA = "\033[90m"

# Painel em exibição (None fora do envio); avisos do log são desviados para ele
_painel_ativo: "PainelEnvio | None" = None


# ---------------------------------------------------------------------------
# Console e log
# ---------------------------------------------------------------------------

def preparar_console() -> None:
    """Ativa cores ANSI no Windows e alarga a janela para evitar quebras de linha."""
    if os.name != "nt":
        return
    os.system("")   # habilita sequências ANSI no console do Windows 10+
    if shutil.get_terminal_size().columns < LARGURA_CONSOLE:
        os.system(f"mode con cols={LARGURA_CONSOLE} >nul 2>&1")


class _ParaPainel(logging.Handler):
    """Mostra avisos e erros no painel em vez de imprimi-los por cima dele."""

    def emit(self, record: logging.LogRecord) -> None:
        if _painel_ativo is not None:
            _painel_ativo.aviso(record.getMessage().strip())


def configurar_log() -> Path:
    """Log completo em arquivo; no console, só avisos e fora do painel de envio."""
    PASTA_LOGS.mkdir(exist_ok=True)
    arquivo = PASTA_LOGS / f"{date.today():%Y-%m-%d}.log"

    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    for h in list(raiz.handlers):
        raiz.removeHandler(h)

    em_arquivo = logging.FileHandler(arquivo, encoding="utf-8")
    em_arquivo.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S"))
    raiz.addHandler(em_arquivo)

    no_console = logging.StreamHandler(sys.stdout)
    no_console.setLevel(logging.WARNING)
    no_console.setFormatter(logging.Formatter("   %(message)s"))
    no_console.addFilter(lambda _: _painel_ativo is None)
    raiz.addHandler(no_console)

    # Só WARNING: os erros de cada nota (ERROR) já aparecem na lista do painel
    no_painel = _ParaPainel()
    no_painel.addFilter(lambda r: r.levelno == logging.WARNING)
    raiz.addHandler(no_painel)
    return arquivo


# ---------------------------------------------------------------------------
# Painel
# ---------------------------------------------------------------------------

def _numero_nota(chave: str) -> str:
    return chave[25:34].lstrip("0") or "0"


def _fmt_tempo(segundos: float) -> str:
    segundos = int(round(segundos))
    if segundos < 60:
        return f"{segundos} s"
    return f"{segundos // 60} min {segundos % 60:02d} s"


class PainelEnvio:
    """Painel de progresso de um lote. Use como gerenciador de contexto."""

    def __init__(self, total: int, titulo: str = "ENVIANDO DOAÇÕES"):
        self.total = total
        self.titulo = titulo
        self.doadas = self.fora_prazo = self.erros = 0
        self.atual: str | None = None
        self.ultimas: deque[str] = deque(maxlen=_ULTIMAS)
        self.ultimo_aviso = ""
        self._inicio = time.monotonic()

    def __enter__(self) -> "PainelEnvio":
        global _painel_ativo
        _painel_ativo = self
        self._desenhar()
        return self

    def __exit__(self, *_exc) -> None:
        global _painel_ativo
        _painel_ativo = None

    @property
    def processadas(self) -> int:
        return self.doadas + self.fora_prazo + self.erros

    # ── Eventos ──────────────────────────────────────────────────────────

    def atualizar(self, chave: str, status: str, msg: str = "") -> None:
        """status: 'enviando', 'doada', 'fora_do_prazo' ou 'erro'."""
        if status == "enviando":
            self.atual = chave
            self._desenhar()
            return

        n = self.processadas + 1
        nota = f"nota nº {_numero_nota(chave):<9}"
        if status == "doada":
            self.doadas += 1
            self.ultimo_aviso = ""   # voltou a doar: o aviso anterior foi superado
            linha = _cor(f"✔  {n:>3}  {nota}", _VERDE) + _cor(f"  …{chave[-8:]}", _CINZA)
        elif status == "fora_do_prazo":
            self.fora_prazo += 1
            linha = _cor(f"⏱  {n:>3}  {nota}", _AMARELO) + _cor("  prazo expirado", _CINZA)
        else:
            self.erros += 1
            linha = _cor(f"✘  {n:>3}  {nota}", _VERMELHO) + _cor(f"  {msg[:45]}", _CINZA)
        self.ultimas.appendleft(linha)
        self.atual = None
        self._desenhar()

    def aviso(self, msg: str) -> None:
        self.ultimo_aviso = msg
        self._desenhar()

    # ── Desenho ──────────────────────────────────────────────────────────

    def _desenhar(self) -> None:
        feitas = self.processadas
        cheio = int(_LARGURA_BARRA * feitas / self.total) if self.total else _LARGURA_BARRA
        barra = _cor("█" * cheio, _VERDE) + _cor("░" * (_LARGURA_BARRA - cheio), _CINZA)

        if feitas:
            por_nota = (time.monotonic() - self._inicio) / feitas
            restante = f"tempo restante ≈ {_fmt_tempo(por_nota * (self.total - feitas))}"
        else:
            restante = "calculando tempo restante..."

        linhas = [
            _cor("=" * 62, _AZUL),
            _cor(f"   {self.titulo}", _NEGRITO) + _cor("   (não feche esta janela)", _CINZA),
            _cor("=" * 62, _AZUL),
            "",
            f"   {barra}  {_cor(f'{feitas}/{self.total}', _NEGRITO)}",
            _cor(f"   {restante}", _CINZA),
            "",
            _cor(f"   ✔ Doadas         {self.doadas:>4}", _VERDE),
            _cor(f"   ⏱ Fora do prazo  {self.fora_prazo:>4}", _AMARELO)
            + _cor("   normal, não são relançadas", _CINZA),
            _cor(f"   ✘ Com erro       {self.erros:>4}", _VERMELHO)
            + _cor("   relançadas ao sair do programa", _CINZA),
            "",
            _cor("-" * 62, _AZUL),
        ]
        if self.atual:
            linhas.append(f"   Enviando nota nº {_numero_nota(self.atual)}...")
        else:
            linhas.append("")
        if self.ultimo_aviso:
            linhas.append(_cor(f"   ⚠ {self.ultimo_aviso[:90]}", _AMARELO))
        linhas.append(_cor("   Últimas notas", _CINZA))
        linhas += [f"   {l}" for l in self.ultimas]

        # Cursor para o topo + limpa a tela: redesenha sem piscar como o "cls"
        sys.stdout.write("\033[H\033[J" + "\n".join(linhas) + "\n")
        sys.stdout.flush()
