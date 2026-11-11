"""
rede.py
-------
Verificação rápida da conexão antes de abrir o navegador.

Distingue "sem internet" de "internet funcionando, mas o site do Nota Paraná
não responde", para que a mensagem ao operador diga o que fazer. Usa urllib
(respeita o proxy do Windows, como o atualizador) e considera "conectado"
qualquer resposta do servidor, mesmo erro HTTP: o que importa é chegar nele.
"""

import ssl
import urllib.error
import urllib.request

URL_PORTAL = "https://notaparana.pr.gov.br/"
URL_INTERNET = "https://www.google.com/"
TIMEOUT = 6  # segundos

SEM_INTERNET = "sem_internet"
PORTAL_FORA = "portal_fora"
OK = "ok"


def _responde(url: str) -> bool:
    req = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": "automatizaAPACN-rede"}
    )
    try:
        urllib.request.urlopen(req, timeout=TIMEOUT).close()
        return True
    except urllib.error.HTTPError:
        return True                              # o servidor respondeu
    except urllib.error.URLError as exc:
        # Erro de certificado também prova que há rede (ex.: antivírus que
        # inspeciona HTTPS); não deve travar o operador.
        return isinstance(exc.reason, ssl.SSLError)
    except Exception:
        return False


def diagnosticar() -> str:
    """Retorna OK, PORTAL_FORA ou SEM_INTERNET."""
    if _responde(URL_PORTAL):
        return OK
    return PORTAL_FORA if _responde(URL_INTERNET) else SEM_INTERNET
