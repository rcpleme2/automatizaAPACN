"""
qr_collector.py
---------------
Coleta de chaves de acesso NF-e/NFC-e a partir de um leitor de código
de barras / QR code USB (modo HID – emula teclado).

O leitor não precisa estar configurado para enviar ENTER: o script lê
caractere a caractere e encerra a leitura automaticamente após um breve
período de inatividade (padrão: 150 ms sem novo caractere).

Para encerrar a coleta: pressione ENTER com o campo vazio, ou
                        leia um QR/código com o texto "FIM".
"""

import re
import os
import sys
import time
from datetime import datetime
from typing import Callable, Optional

import som

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

    # Chave digitada ou emitida com espaços/hífens entre grupos (ex: "4126 0313 ...")
    apenas_digitos = re.sub(r'[\s\-]', '', dado)
    if re.match(r'^\d{44}$', apenas_digitos):
        return apenas_digitos

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
        return False, "o código está incompleto ou tem números a mais"

    if chave[:2] not in _CUFS_VALIDOS:
        return False, "esta nota não é do Paraná"

    if chave[20:22] not in ("55", "65"):
        return False, "este código não é de uma nota fiscal"

    if _calcular_dv(chave[:43]) != int(chave[43]):
        return False, "o código foi lido com defeito; passe o leitor de novo"

    return True, ""


# ---------------------------------------------------------------------------
# Leitura de input sem depender de ENTER do leitor
# ---------------------------------------------------------------------------
# O leitor "digita" a leitura inteira em poucos milissegundos, então uma pausa
# curta (timeout) marca o fim da leitura. Uma pessoa digitando faz pausas bem
# maiores; por isso, enquanto o campo tiver só dígitos e menos de 44, a leitura
# só termina com ENTER (ou ao completar os 44 dígitos e pausar).

_BACKSPACE = ("\x08", "\x7f")


def _leitura_completa(buffer: list[str]) -> bool:
    """True se o conteúdo já pode ser uma leitura do leitor (fim por pausa)."""
    texto = "".join(buffer)
    if re.search(r"[^\d\s\-]", texto):   # URL de QR code ou texto ("FIM")
        return True
    return len(re.sub(r"\D", "", texto)) >= 44


def _tratar_tecla(ch: str, buffer: list[str]) -> bool:
    """Atualiza o buffer com a tecla e ecoa na tela. Retorna True no ENTER."""
    if ch in ("\r", "\n"):
        return True
    if ch == "\x03":                       # Ctrl+C no modo caractere a caractere
        raise KeyboardInterrupt
    if ch in _BACKSPACE:
        if buffer:
            buffer.pop()
            sys.stdout.write("\b \b")
    elif ch.isprintable():
        buffer.append(ch)
        sys.stdout.write(ch)
    sys.stdout.flush()
    return False


if os.name == "nt":
    import msvcrt

    def _ler_scan(prompt: str = "   > ", timeout: float = 0.15) -> str:
        """
        Lê caracteres um a um (Windows/msvcrt), mostrando o que é digitado.
        Encerra com CR/LF ou, se a leitura parecer completa, após `timeout`
        segundos sem novo caractere. Não exige que o leitor envie ENTER.
        """
        sys.stdout.write(prompt)
        sys.stdout.flush()
        buffer: list[str] = []
        ultimo: float | None = None

        while True:
            if msvcrt.kbhit():
                if _tratar_tecla(msvcrt.getwch(), buffer):
                    break
                ultimo = time.time()
            else:
                if (buffer and ultimo is not None
                        and time.time() - ultimo >= timeout
                        and _leitura_completa(buffer)):
                    break
                time.sleep(0.005)

        print()
        return "".join(buffer)

else:
    # Linux / macOS: usa termios para leitura raw caractere a caractere
    import tty
    import termios
    import select

    def _ler_scan(prompt: str = "   > ", timeout: float = 0.15) -> str:
        """
        Lê caracteres um a um (Linux/macOS via termios), mostrando o que é
        digitado. Encerra com CR/LF ou, se a leitura parecer completa, após
        `timeout` segundos sem novo caractere.
        """
        sys.stdout.write(prompt)
        sys.stdout.flush()
        buffer: list[str] = []
        fd = sys.stdin.fileno()
        config_orig = termios.tcgetattr(fd)

        try:
            tty.setraw(fd)
            while True:
                pronto, _, _ = select.select([sys.stdin], [], [], timeout)
                if pronto:
                    if _tratar_tecla(sys.stdin.read(1), buffer):
                        break
                elif buffer and _leitura_completa(buffer):
                    break   # pausa após leitura completa → fim da leitura
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, config_orig)

        print()
        return "".join(buffer)


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
    print("   Quando terminar: aperte ENTER sem digitar nada (ou leia um código 'FIM').")
    print("   Sem o leitor: digite os 44 números da nota e aperte ENTER.")
    print("   Um bip agudo = nota aceita.  Dois bips graves = nota recusada.")
    print(_cor("=" * 62, _AZUL))
    print()


# ---------------------------------------------------------------------------
# Loop principal de coleta
# ---------------------------------------------------------------------------

def coletar_qr_codes(
    ja_processadas: Optional[dict[str, tuple[str, datetime]]] = None,
    iniciais: Optional[list[str]] = None,
    ao_registrar: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """
    Aguarda leituras do leitor de código de barras/QR (entrada via teclado HID).

    ja_processadas → mapa chave → (status, data) do histórico local; essas
                     notas são recusadas na leitura (já doadas ou fora do prazo).
    iniciais       → chaves recuperadas de uma leitura anterior; já entram na lista.
    ao_registrar   → chamada com cada chave nova aceita (usada para guardá-la
                     em disco na hora, caso o programa feche).

    Retorna lista de chaves de acesso válidas e únicas.
    """
    ja_processadas = ja_processadas or {}
    chaves: list[str] = list(dict.fromkeys(iniciais or []))
    invalidas: int = 0
    mensagens: list[str] = []   # feedback mostrado abaixo do cabeçalho

    if chaves:
        mensagens.append(_cor(
            f"  ↺  {len(chaves)} nota(s) recuperada(s) da leitura anterior.", _AZUL))

    def mostrar(msg: str, cor: str, aceita: bool) -> None:
        mensagens.append(_cor(msg, cor))
        _cabecalho(len(chaves), invalidas)
        for linha in mensagens[-15:]:   # mostra as últimas 15 mensagens
            print(linha)
        if aceita:
            som.sucesso()
        else:
            som.falha()

    _cabecalho(len(chaves), 0)
    for linha in mensagens:
        print(linha)

    while True:
        try:
            entrada = _ler_scan().strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        # Sinaliza fim da coleta
        if entrada == "" or entrada.upper() == "FIM":
            break

        chave = _extrair_chave(entrada)

        if chave is None:
            invalidas += 1
            mostrar("  ✗  Não consegui ler este código. Passe o leitor de novo.",
                    _VERMELHO, False)
            continue

        if chave in chaves:
            mostrar(f"  ⚠  Esta nota já foi lida (não conta duas vezes): {_fmt(chave)}",
                    _AMARELO, False)
            continue

        if chave in ja_processadas:
            status, quando = ja_processadas[chave]
            situacao = ("já foi doada" if status == "doada"
                        else "já foi enviada, mas estava fora do prazo")
            mostrar(f"  ⚠  Esta nota {situacao} em {quando:%d/%m/%Y} "
                    f"(não será enviada de novo): {_fmt(chave)}", _AMARELO, False)
            continue

        valida, motivo = validar_chave(chave)
        if not valida:
            invalidas += 1
            mostrar(f"  ✗  Nota recusada, {motivo}: {_fmt(chave)}", _VERMELHO, False)
            continue

        chaves.append(chave)
        if ao_registrar:
            ao_registrar(chave)
        mostrar(f"  ✓  #{len(chaves):>3}  {_fmt(chave)}", _VERDE, True)

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
