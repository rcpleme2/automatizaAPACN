"""
historico.py
------------
Histórico local das notas processadas neste computador e geração do
relatório em HTML (pronto para imprimir / salvar em PDF pelo navegador).

O histórico é gravado em historico_doacoes.csv (uma linha por nota, gravada
assim que o portal confirma o resultado). Apenas resultados definitivos são
registrados: nota doada ou nota recusada por prazo expirado.
"""

import csv
import html
import platform
import webbrowser
from datetime import date, datetime
from pathlib import Path

_PASTA = Path(__file__).parent
HISTORICO_PATH = _PASTA / "historico_doacoes.csv"
PASTA_RELATORIOS = _PASTA / "relatorios"

STATUS_DOADA = "doada"
STATUS_FORA_PRAZO = "fora_do_prazo"

_CAMPOS = ["data_hora", "chave", "numero_nota", "cnpj_emitente",
           "status", "cnpj_entidade", "mensagem"]


# ---------------------------------------------------------------------------
# Helpers de formatação
# ---------------------------------------------------------------------------

def numero_nota(chave: str) -> str:
    """Número da nota (nNF, posições 26–34 da chave) sem zeros à esquerda."""
    return chave[25:34].lstrip("0") or "0"


def _fmt_cnpj(cnpj: str) -> str:
    if len(cnpj) != 14:
        return cnpj
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def _fmt_chave(chave: str) -> str:
    return " ".join(chave[i:i+4] for i in range(0, 44, 4))


# ---------------------------------------------------------------------------
# Gravação e leitura
# ---------------------------------------------------------------------------

def registrar(chave: str, status: str, cnpj_entidade: str, mensagem: str = "") -> None:
    """Acrescenta uma nota ao histórico (cria o arquivo se não existir)."""
    novo = not HISTORICO_PATH.exists()
    # utf-8-sig: o Excel reconhece os acentos ao abrir o CSV
    with HISTORICO_PATH.open("a", newline="", encoding="utf-8-sig" if novo else "utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_CAMPOS, delimiter=";")
        if novo:
            w.writeheader()
        w.writerow({
            "data_hora": datetime.now().isoformat(timespec="seconds"),
            "chave": chave,
            "numero_nota": numero_nota(chave),
            "cnpj_emitente": chave[6:20],
            "status": status,
            "cnpj_entidade": cnpj_entidade,
            "mensagem": mensagem,
        })


def carregar() -> list[dict]:
    """Lê todo o histórico; linhas corrompidas são ignoradas."""
    if not HISTORICO_PATH.exists():
        return []
    registros = []
    with HISTORICO_PATH.open(newline="", encoding="utf-8-sig") as f:
        for linha in csv.DictReader(f, delimiter=";"):
            try:
                linha["_dt"] = datetime.fromisoformat(linha["data_hora"])
            except (KeyError, TypeError, ValueError):
                continue
            registros.append(linha)
    return registros


def chaves_ja_processadas() -> dict[str, tuple[str, datetime]]:
    """Mapa chave → (status, data) das notas com resultado definitivo."""
    return {r["chave"]: (r["status"], r["_dt"]) for r in carregar()}


# ---------------------------------------------------------------------------
# Relatório HTML
# ---------------------------------------------------------------------------

_CSS = """
:root { --tinta:#1f2933; --suave:#52606d; --linha:#d9e2ec; --fundo:#f5f7fa;
        --verde:#1b7f4b; --ambar:#a15c00; --azul:#1d4f91; }
* { box-sizing:border-box; }
body { margin:0; background:var(--fundo); color:var(--tinta);
       font:14px/1.45 "Segoe UI", Roboto, Arial, sans-serif; }
main { max-width:960px; margin:24px auto; background:#fff; padding:32px 36px;
       border:1px solid var(--linha); border-radius:8px; }
h1 { margin:0 0 4px; font-size:22px; color:var(--azul); }
h2 { font-size:16px; margin:28px 0 8px; }
.sub { color:var(--suave); margin:0; }
.aviso { margin:20px 0; padding:12px 16px; border-left:4px solid var(--azul);
         background:#eef4fb; }
.cards { display:flex; gap:12px; flex-wrap:wrap; margin:16px 0; }
.card { flex:1 1 160px; border:1px solid var(--linha); border-radius:6px; padding:10px 14px; }
.card b { display:block; font-size:24px; }
.card.ok b { color:var(--verde); } .card.prazo b { color:var(--ambar); }
table { width:100%; border-collapse:collapse; font-size:13px; }
th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--linha); }
th { background:var(--fundo); font-weight:600; }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
td.chave { font-family:Consolas, monospace; font-size:12px; white-space:nowrap; }
.vazio { color:var(--suave); font-style:italic; }
.acoes { text-align:right; margin-bottom:8px; }
button { font:inherit; padding:8px 16px; border:0; border-radius:4px;
         background:var(--azul); color:#fff; cursor:pointer; }
footer { margin-top:28px; color:var(--suave); font-size:12px; }
@media print {
  body { background:#fff; } main { margin:0; border:0; padding:0; max-width:none; }
  .acoes { display:none; } tr { page-break-inside:avoid; }
}
"""


def _tabela(registros: list[dict]) -> str:
    if not registros:
        return '<p class="vazio">Nenhuma nota neste período.</p>'
    linhas = []
    for i, r in enumerate(registros, 1):
        linhas.append(
            "<tr>"
            f'<td class="num">{i}</td>'
            f'<td>{r["_dt"]:%d/%m/%Y %H:%M}</td>'
            f'<td class="num">{html.escape(r.get("numero_nota", ""))}</td>'
            f'<td>{_fmt_cnpj(r.get("cnpj_emitente", ""))}</td>'
            f'<td class="chave">{_fmt_chave(r["chave"])}</td>'
            "</tr>"
        )
    return (
        "<table><thead><tr><th>#</th><th>Data/hora</th><th>Nº nota</th>"
        "<th>CNPJ emitente</th><th>Chave de acesso</th></tr></thead>"
        f"<tbody>{''.join(linhas)}</tbody></table>"
    )


def gerar_relatorio(inicio: date, fim: date, abrir: bool = True) -> Path:
    """Gera o relatório HTML do período [inicio, fim] e abre no navegador."""
    registros = [r for r in carregar() if inicio <= r["_dt"].date() <= fim]
    doadas = [r for r in registros if r["status"] == STATUS_DOADA]
    fora_prazo = [r for r in registros if r["status"] == STATUS_FORA_PRAZO]
    entidades = sorted({r.get("cnpj_entidade", "") for r in doadas} - {""})

    computador = html.escape(platform.node() or "este computador")
    periodo = f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"
    agora = datetime.now()
    txt_entidades = ", ".join(_fmt_cnpj(c) for c in entidades) or "—"

    pagina = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Histórico de doações – {periodo}</title>
<style>{_CSS}</style></head>
<body><main>
<div class="acoes"><button onclick="window.print()">Imprimir / Salvar em PDF</button></div>
<h1>Histórico de doações – Nota Paraná</h1>
<p class="sub">Período: <b>{periodo}</b> · Computador: <b>{computador}</b></p>

<div class="aviso">
  Este histórico diz respeito <b>apenas às notas processadas neste computador
  ({computador})</b> pelo programa de doação automática, no período de
  <b>{periodo}</b>. Doações feitas em outros computadores ou diretamente no
  portal Nota Paraná não constam deste relatório.
</div>

<div class="cards">
  <div class="card ok"><b>{len(doadas)}</b>nota(s) doada(s)</div>
  <div class="card prazo"><b>{len(fora_prazo)}</b>recusada(s) por prazo expirado</div>
</div>
<p class="sub">Entidade(s) beneficiada(s): {txt_entidades}</p>

<h2>Notas doadas</h2>
{_tabela(doadas)}

<h2>Notas recusadas por prazo expirado</h2>
{_tabela(fora_prazo)}

<footer>Gerado em {agora:%d/%m/%Y às %H:%M}. Fonte: {HISTORICO_PATH.name}.</footer>
</main></body></html>
"""

    PASTA_RELATORIOS.mkdir(exist_ok=True)
    destino = PASTA_RELATORIOS / f"historico_{inicio:%Y%m%d}_{fim:%Y%m%d}_{agora:%H%M%S}.html"
    destino.write_text(pagina, encoding="utf-8")
    if abrir:
        webbrowser.open(destino.resolve().as_uri())
    return destino
