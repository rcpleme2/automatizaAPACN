"""
atualizador.py
--------------
Verifica se há versão nova do programa no branch main do GitHub e, havendo,
atualiza os arquivos com um único "S" do operador.

Chamado pelo inicia.bat antes do programa principal. Usa apenas a biblioteca
padrão do Python (funciona mesmo antes de o ambiente virtual existir).

- Compara os arquivos do ZIP do main com os locais (ignorando CRLF/LF).
- Só sobrescreve arquivos que fazem parte do repositório: config.json,
  historico_doacoes.csv, relatorios/ e venv/ nunca são tocados.
- O próprio inicia.bat não é sobrescrito enquanto roda: é salvo como
  inicia.bat.novo e trocado pelo inicia.bat após esta etapa.
- Sem internet ou com qualquer falha, segue com a versão atual.

Códigos de saída (lidos pelo inicia.bat):
    0 = nada a fazer      2 = atualizado, reinstalar dependências
    1 = atualizado        (falhas também saem com 0)
"""

import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = "rcpleme2/automatizaAPACN"
BRANCH = "main"
URL_ZIP = f"https://codeload.github.com/{REPO}/zip/refs/heads/{BRANCH}"
URL_COMMIT = f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"
TIMEOUT = 8  # segundos

_PASTA = Path(__file__).parent
# Arquivos do repositório que não fazem sentido no computador do operador
_IGNORAR = {".gitignore"}


def _baixar(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "automatizaAPACN-atualizador"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def _normalizar(dados: bytes) -> bytes:
    return dados.replace(b"\r\n", b"\n")


def _arquivos_remotos(conteudo_zip: bytes) -> dict[str, bytes]:
    """Retorna {caminho relativo: conteúdo} dos arquivos do ZIP do GitHub."""
    arquivos = {}
    with zipfile.ZipFile(io.BytesIO(conteudo_zip)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            # O GitHub coloca tudo dentro de "<repo>-<branch>/"
            partes = info.filename.split("/", 1)
            if len(partes) < 2 or not partes[1]:
                continue
            relativo = partes[1]
            if relativo in _IGNORAR or ".." in Path(relativo).parts:
                continue
            arquivos[relativo] = zf.read(info)
    return arquivos


def _alterados(remotos: dict[str, bytes]) -> list[str]:
    alterados = []
    for relativo, dados in remotos.items():
        local = _PASTA / relativo
        if not local.exists() or _normalizar(local.read_bytes()) != _normalizar(dados):
            alterados.append(relativo)
    return sorted(alterados)


def _descricao_ultima_versao() -> str:
    """Data e mensagem do último commit (opcional; falha silenciosamente)."""
    try:
        commit = json.loads(_baixar(URL_COMMIT))["commit"]
        data = commit["committer"]["date"][:10]
        titulo = commit["message"].splitlines()[0]
        return f"{data[8:10]}/{data[5:7]}/{data[:4]} – {titulo}"
    except Exception:
        return ""


def main() -> int:
    print("   Verificando atualizações...")
    try:
        remotos = _arquivos_remotos(_baixar(URL_ZIP))
    except Exception as exc:
        print(f"   Não foi possível verificar atualizações ({exc.__class__.__name__}). "
              "Seguindo com a versão atual.")
        return 0

    alterados = _alterados(remotos)
    if not alterados:
        print("   Programa já está na versão mais recente.")
        return 0

    print()
    print("   ==================================================")
    print("   NOVA VERSÃO DISPONÍVEL")
    print("   ==================================================")
    descricao = _descricao_ultima_versao()
    if descricao:
        print(f"   Última alteração: {descricao}")
    print("   Arquivos que serão atualizados:")
    for nome in alterados:
        print(f"     • {nome}")
    print()
    print("   Seus dados (config, histórico e relatórios) são preservados.")
    try:
        resp = input("   Atualizar agora? [S/n]: ").strip().upper()
    except EOFError:
        resp = "N"
    if resp not in ("", "S", "SIM"):
        print("   Atualização adiada.")
        return 0

    try:
        for relativo in alterados:
            destino = _PASTA / relativo
            if relativo == "inicia.bat":
                destino = _PASTA / "inicia.bat.novo"
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(remotos[relativo])
    except Exception as exc:
        print(f"   Falha ao gravar arquivos ({exc}). Seguindo com a versão atual.")
        return 0

    print("   Atualização concluída.")
    return 2 if "requirements.txt" in alterados else 1


if __name__ == "__main__":
    sys.exit(main())
