"""
qr_collector.py
---------------
Módulo de coleta e validação de chaves de acesso NF-e/NFC-e a partir
de QR codes lidos pela câmera.

Uso:
    python qr_collector.py

Controles durante a coleta:
    Q  – Finaliza a coleta e retorna as chaves válidas coletadas.
    R  – Remove a última chave adicionada (desfaz última leitura).
"""

import re
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
from pyzbar import pyzbar


# ---------------------------------------------------------------------------
# Estrutura de estado da coleta
# ---------------------------------------------------------------------------

@dataclass
class Coleta:
    chaves: list[str] = field(default_factory=list)
    invalidas: list[str] = field(default_factory=list)
    ultima_leitura: float = 0.0          # timestamp do último QR lido
    debounce_seg: float = 2.0            # evita duplicar leitura imediata


# ---------------------------------------------------------------------------
# Funções de extração e validação
# ---------------------------------------------------------------------------

# Dígitos de cUF do Paraná = 41
_CUFS_VALIDOS = {"41"}

def _extrair_chave(dado_qr: str) -> Optional[str]:
    """Tenta extrair uma chave de acesso de 44 dígitos do conteúdo do QR."""
    # QR de NFC-e Paraná: URL com parâmetro ?p=CHAVE44DIGITOS|...
    m = re.search(r'[?&]p=(\d{44})', dado_qr)
    if m:
        return m.group(1)

    # Alternativa: parâmetro chNFe=
    m = re.search(r'chNFe=(\d{44})', dado_qr, re.IGNORECASE)
    if m:
        return m.group(1)

    # Chave solta no QR (44 dígitos isolados)
    m = re.search(r'(?<!\d)(\d{44})(?!\d)', dado_qr)
    if m:
        return m.group(1)

    return None


def _calcular_digito_verificador(chave43: str) -> int:
    """Módulo 11 conforme manual do SEFAZ para chave de acesso NF-e."""
    pesos = list(range(2, 10)) * 6          # [2,3,...,9, 2,3,...,9, ...]
    soma = sum(int(d) * p for d, p in zip(reversed(chave43), pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def validar_chave(chave: str) -> tuple[bool, str]:
    """
    Valida uma chave de acesso NF-e.

    Retorna (True, "") se válida, ou (False, motivo) se inválida.
    """
    if not re.match(r'^\d{44}$', chave):
        return False, "Não possui exatamente 44 dígitos numéricos"

    cuf = chave[:2]
    if cuf not in _CUFS_VALIDOS:
        return False, f"cUF '{cuf}' não corresponde ao Paraná (esperado '41')"

    mod = chave[20:22]
    if mod not in ("55", "65"):
        return False, f"Modelo '{mod}' desconhecido (esperado 55=NF-e ou 65=NFC-e)"

    dv_calculado = _calcular_digito_verificador(chave[:43])
    dv_nota = int(chave[43])
    if dv_calculado != dv_nota:
        return False, (
            f"Dígito verificador incorreto "
            f"(calculado={dv_calculado}, nota={dv_nota})"
        )

    return True, ""


# ---------------------------------------------------------------------------
# Loop de coleta via câmera
# ---------------------------------------------------------------------------

def coletar_qr_codes(indice_camera: int = 0) -> list[str]:
    """
    Abre a câmera e aguarda o operador escanear QR codes de notas fiscais.

    Retorna lista com as chaves de acesso válidas e únicas coletadas.
    """
    cap = cv2.VideoCapture(indice_camera)
    if not cap.isOpened():
        sys.exit(
            f"[ERRO] Não foi possível abrir a câmera de índice {indice_camera}. "
            "Verifique se há uma webcam conectada."
        )

    estado = Coleta()
    print("\n" + "=" * 60)
    print("  COLETOR DE QR CODES – NOTA FISCAL PARANÁ")
    print("=" * 60)
    print("  Q  → Finalizar coleta")
    print("  R  → Remover última chave adicionada")
    print("=" * 60 + "\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[AVISO] Falha ao capturar frame da câmera.")
            continue

        qr_codes = pyzbar.decode(frame)
        agora = time.time()

        for qr in qr_codes:
            dado = qr.data.decode("utf-8", errors="replace").strip()

            # debounce: ignora releituras muito rápidas
            if agora - estado.ultima_leitura < estado.debounce_seg:
                continue

            chave = _extrair_chave(dado)
            if chave is None:
                print(f"[IGNORADO] QR sem chave de acesso detectável: {dado[:80]}")
                estado.ultima_leitura = agora
                continue

            if chave in estado.chaves:
                print(f"[DUPLICADO] Chave já registrada: {_fmt(chave)}")
                estado.ultima_leitura = agora
                continue

            valida, motivo = validar_chave(chave)
            if not valida:
                print(f"[INVÁLIDA]  {_fmt(chave)}  ← {motivo}")
                if chave not in estado.invalidas:
                    estado.invalidas.append(chave)
                estado.ultima_leitura = agora
                continue

            estado.chaves.append(chave)
            estado.ultima_leitura = agora
            print(
                f"[OK #{len(estado.chaves):>3}]  {_fmt(chave)}"
            )

            # Desenha contorno verde no QR detectado
            pts = qr.polygon
            if len(pts) == 4:
                for i in range(4):
                    cv2.line(frame, pts[i], pts[(i + 1) % 4], (0, 255, 0), 3)

        # Overlay de status no frame
        _draw_status(frame, estado)
        cv2.imshow("Coletor QR – Nota Paraná  (Q=finalizar | R=desfazer)", frame)

        tecla = cv2.waitKey(1) & 0xFF
        if tecla == ord('q') or tecla == ord('Q'):
            break
        elif tecla == ord('r') or tecla == ord('R'):
            if estado.chaves:
                removida = estado.chaves.pop()
                print(f"[REMOVIDA]  {_fmt(removida)}")
            else:
                print("[INFO] Nenhuma chave para remover.")

    cap.release()
    cv2.destroyAllWindows()

    print("\n" + "=" * 60)
    print(f"  Coleta encerrada.")
    print(f"  Chaves válidas  : {len(estado.chaves)}")
    print(f"  Chaves inválidas: {len(estado.invalidas)}")
    print("=" * 60 + "\n")

    return estado.chaves


# ---------------------------------------------------------------------------
# Helpers de exibição
# ---------------------------------------------------------------------------

def _fmt(chave: str) -> str:
    """Formata a chave em grupos legíveis: 4444 4444 4444 ..."""
    return " ".join(chave[i:i+4] for i in range(0, 44, 4))


def _draw_status(frame, estado: Coleta) -> None:
    """Escreve o contador de chaves no canto superior esquerdo do frame."""
    texto = f"Coletadas: {len(estado.chaves)}  |  Q=Finalizar  R=Desfazer"
    cv2.putText(
        frame, texto, (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 0), 2, cv2.LINE_AA
    )


# ---------------------------------------------------------------------------
# Execução direta (teste isolado)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    chaves = coletar_qr_codes()
    if chaves:
        print("Chaves coletadas:")
        for i, c in enumerate(chaves, 1):
            print(f"  {i:>3}. {_fmt(c)}")
    else:
        print("Nenhuma chave coletada.")
