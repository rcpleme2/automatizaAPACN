"""
main.py
-------
Ponto de entrada da automação de doação no Nota Paraná.

Fluxo:
  1. Menu principal:
       1 = Lançar notas   2 = Relatório do histórico   0 = Sair
  2. Lançar notas:
       0. Se sobraram notas lidas de uma vez anterior (programa fechado ou erro
          no lançamento), oferece continuar com elas (recuperacao.py).
       a. Na primeira vez, solicita usuário, CNPJ da entidade e senha
          (esta última não é salva). Usuário e CNPJ vêm pré-preenchidos.
       b. Coleta QR codes via leitor USB (notas já doadas neste computador
          são recusadas na leitura).
       c. Confirmação do operador.
       d. Confere a internet (rede.py), abre o navegador e faz login (apenas
          no primeiro lote).
          Se as credenciais estiverem erradas, pede novamente SEM fechar o navegador.
       e. Doação automática; cada resultado definitivo vai para o histórico.
          Se a sessão expirar, o login é refeito automaticamente.
       f. Se houver LIMITE_ERROS_CHAVE erros consecutivos, pergunta se continua.
       g. Exibe o resultado e volta ao menu.
  3. Relatório: gera um HTML com as notas doadas no período informado.
  4. Ao sair, tenta automaticamente relançar todas as notas com erro,
     faz logout no site e encerra o navegador.

Ao iniciar, verifica se há versão nova no GitHub (atualizador.py) e, se o
operador aceitar, atualiza os arquivos e reinicia sozinho.

Uso:
    python main.py [--headless] [--sem-atualizar]
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import historico
import rede
import recuperacao
import som
from atualizador import verificar_e_atualizar
from mensagens import traduzir_erro
from painel import PASTA_LOGS, PainelEnvio, configurar_log, preparar_console
from qr_collector import coletar_qr_codes, _fmt as fmt_chave, _cor, \
    _VERDE, _VERMELHO, _AMARELO, _AZUL, _NEGRITO, _limpar_tela
from notaparana_bot import (
    abrir_navegador,
    fazer_login_portal,
    doar_lote,
    encerrar_sessao,
    so_digitos,
    CredenciaisInvalidasError,
    LIMITE_ERROS_CHAVE,
)

# Arquivo de configuração local (não versionado)
_CONFIG_PATH = Path(__file__).parent / "config.json"

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Persistência de configuração
# ---------------------------------------------------------------------------

def _carregar_config() -> dict:
    """Lê config.json; retorna dict vazio se não existir."""
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _salvar_config(config: dict) -> None:
    """Grava config.json com os dados não-sensíveis."""
    _CONFIG_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Prompts de entrada
# ---------------------------------------------------------------------------

def _input_com_padrao(label: str, padrao: str = "") -> str:
    """Exibe prompt com valor padrão pré-preenchido. ENTER mantém o padrão."""
    if padrao:
        valor = input(f"   {label} [{padrao}]: ").strip()
        return valor if valor else padrao
    return input(f"   {label}: ").strip()


def _pausar(msg: str = "Pressione ENTER para voltar ao menu...") -> None:
    try:
        input(f"\n   {msg}")
    except EOFError:
        pass


def _tela_credenciais(config: dict) -> tuple[str, str, str]:
    """
    Solicita usuário, CNPJ da entidade e senha.
    Retorna (usuario, cnpj_entidade, senha).
    Usuário e CNPJ são pré-preenchidos com valores salvos (editáveis).
    Senha nunca é pré-preenchida nem salva.
    """
    _limpar_tela()
    print(_cor("=" * 62, _AZUL))
    print(_cor("   NOTA PARANÁ – DOAÇÃO AUTOMÁTICA", _NEGRITO))
    print(_cor("=" * 62, _AZUL))
    print()
    print("   Preencha os dados abaixo.")
    print("   O que aparece entre [ ] já está salvo. Se estiver certo, só aperte ENTER.")
    print()

    # Usuário
    usuario = ""
    while not usuario:
        usuario = so_digitos(
            _input_com_padrao("Usuário do portal (seu CPF)", config.get("usuario", ""))
        )
        if not usuario:
            print("   Este campo precisa ser preenchido.\n")

    # CNPJ da entidade
    cnpj_entidade = ""
    while len(cnpj_entidade) != 14:
        raw = _input_com_padrao(
            "CNPJ da entidade (14 dígitos)", config.get("cnpj_entidade", "")
        )
        cnpj_entidade = so_digitos(raw)
        if len(cnpj_entidade) != 14:
            print(f"   O CNPJ precisa ter 14 números e você digitou {len(cnpj_entidade)}. "
                  "Confira e digite de novo.\n")

    # Senha (nunca salva)
    print()
    senha = ""
    while not senha:
        senha = input("   Senha do portal: ")
        if not senha:
            print("   Este campo precisa ser preenchido.\n")

    return usuario, cnpj_entidade, senha


def _tela_login_invalido(usuario: str) -> tuple[str, str]:
    """
    Exibe mensagem de credenciais inválidas e pede novo usuário/senha.
    O navegador permanece aberto. Retorna (usuario, senha).
    """
    _limpar_tela()
    print(_cor("=" * 62, _VERMELHO))
    print(_cor("   NÃO FOI POSSÍVEL ENTRAR NO PORTAL", _VERMELHO + _NEGRITO))
    print(_cor("=" * 62, _VERMELHO))
    print()
    print("   O portal não aceitou o usuário (CPF) ou a senha.")
    print("   Ele não informa qual dos dois está errado, então confira os dois:")
    print("     • o CPF: o que aparece entre [ ] é o último que foi usado;")
    print("     • a senha: veja se as letras maiúsculas e minúsculas estão certas.")
    print()
    print("   Digite novamente abaixo. Não feche a janela do navegador.")
    print()

    novo_usuario_raw = _input_com_padrao("Usuário do portal (seu CPF)", usuario).strip()
    novo_usuario = so_digitos(novo_usuario_raw) if novo_usuario_raw else usuario

    print()
    nova_senha = ""
    while not nova_senha:
        nova_senha = input("   Senha do portal: ")
        if not nova_senha:
            print("   Este campo precisa ser preenchido.\n")

    return novo_usuario, nova_senha


# ---------------------------------------------------------------------------
# Telas de navegação
# ---------------------------------------------------------------------------

def _tela_menu(sessao_ativa: bool, pendentes: int) -> str:
    """Menu principal. Retorna '1', '2' ou '0'."""
    _limpar_tela()
    print(_cor("=" * 62, _AZUL))
    print(_cor("   NOTA PARANÁ – DOAÇÃO AUTOMÁTICA", _NEGRITO))
    print(_cor("=" * 62, _AZUL))
    status = _cor("conectado", _VERDE) if sessao_ativa else "ainda não conectado"
    print(f"   Portal Nota Paraná : {status}")
    if pendentes:
        print(f"   Notas não doadas   : {_cor(str(pendentes), _AMARELO)}"
              " (o programa tenta de novo ao sair)")
    print(_cor("-" * 62, _AZUL))
    print(f"   {_cor('1', _NEGRITO)}  Lançar notas")
    print(f"   {_cor('2', _NEGRITO)}  Relatório do histórico de doações")
    print(f"   {_cor('0', _NEGRITO)}  Sair")
    print(_cor("=" * 62, _AZUL))
    while True:
        resp = input("\n   Sua escolha: ").strip()
        if resp in ("1", "2", "0"):
            return resp
        print("   Digite apenas 1, 2 ou 0 e aperte ENTER.")


def _ler_data(label: str, padrao: date) -> date:
    while True:
        raw = _input_com_padrao(f"{label} (dd/mm/aaaa)", f"{padrao:%d/%m/%Y}")
        try:
            return datetime.strptime(raw, "%d/%m/%Y").date()
        except ValueError:
            print("   Data inválida. Digite assim: dia/mês/ano, por exemplo 31/12/2025.\n")


def _tela_relatorio() -> None:
    _limpar_tela()
    print(_cor("=" * 62, _AZUL))
    print(_cor("   RELATÓRIO DO HISTÓRICO DE DOAÇÕES", _NEGRITO))
    print(_cor("=" * 62, _AZUL))
    print()

    registros = historico.carregar()
    if not registros:
        print(_cor("   Nenhuma nota registrada neste computador até o momento.", _AMARELO))
        _pausar()
        return

    primeira = min(r["_dt"] for r in registros).date()
    print(f"   Histórico disponível desde {primeira:%d/%m/%Y}.")
    print("   Informe o período (ENTER mantém o valor sugerido).\n")
    inicio = _ler_data("Data inicial", primeira)
    fim = _ler_data("Data final  ", date.today())
    if fim < inicio:
        inicio, fim = fim, inicio

    destino = historico.gerar_relatorio(inicio, fim)
    print()
    print(_cor("   Relatório gerado e aberto no navegador.", _VERDE))
    print(f"   Arquivo: {destino}")
    print("   Para PDF: botão 'Imprimir / Salvar em PDF' no topo da página.")
    _pausar()


def _tela_confirmacao(chaves: list[str]) -> bool:
    _limpar_tela()
    print(_cor("=" * 62, _AZUL))
    print(_cor("   CONFIRMAÇÃO – NOTAS PARA DOAÇÃO", _NEGRITO))
    print(_cor("=" * 62, _AZUL))
    print(f"\n   {_cor(str(len(chaves)), _NEGRITO)} nota(s) serão doadas. "
          "Confira a lista:\n")
    for i, c in enumerate(chaves, 1):
        print(f"   {i:>3}.  {fmt_chave(c)}")
    print()
    print(_cor("-" * 62, _AZUL))
    print("   S = sim, doar essas notas  |  N = não, voltar sem doar")
    print(_cor("=" * 62, _AZUL))
    while True:
        resp = input("\n   Sua escolha [S/N]: ").strip().upper()
        if resp in ("S", "SIM"):
            return True
        if resp in ("N", "NAO", "NÃO", ""):
            return False
        print("   Digite S para sim ou N para não.")


def _tela_resultado(resultado: dict) -> None:
    """Resumo do lote: notas fora do prazo (informativo) separadas dos erros."""
    _limpar_tela()
    doadas = resultado["sucesso"]
    expiradas = resultado["chaves_expiradas"]
    set_expiradas = set(expiradas)
    erros = [(c, m) for c, m in resultado["erros_com_mensagem"] if c not in set_expiradas]

    if erros and doadas:
        cor, titulo = _AMARELO, "⚠  ALGUMAS NOTAS NÃO FORAM DOADAS"
    elif erros:
        cor, titulo = _VERMELHO, "✘  NENHUMA NOTA FOI DOADA"
    elif doadas:
        cor, titulo = _VERDE, "✔  TUDO CERTO! AS NOTAS FORAM DOADAS"
    else:
        cor, titulo = _AMARELO, "⏱  AS NOTAS ESTAVAM FORA DO PRAZO"

    borda = _cor("=" * 62, cor)
    print(borda)
    print(_cor(f"   {titulo}", cor + _NEGRITO))
    print(borda)
    print()
    print(f"   {_cor(f'✔ {doadas:>4}', _VERDE + _NEGRITO)}  nota(s) doada(s)")
    print(f"   {_cor(f'⏱ {len(expiradas):>4}', _AMARELO + _NEGRITO)}  fora do prazo"
          " (o prazo já passou, não dá mais para doar)")
    print(f"   {_cor(f'✘ {len(erros):>4}', _VERMELHO + _NEGRITO)}  não doada(s)"
          + (" (o programa tenta de novo ao sair)" if erros else ""))

    if expiradas:
        print(_cor("\n   Fora do prazo:", _AMARELO))
        for chave in expiradas:
            print(f"      ⏱  nota nº {historico.numero_nota(chave):<9} {fmt_chave(chave)}")

    if erros:
        print(_cor("\n   Notas que não foram doadas:", _VERMELHO))
        for chave, msg in erros:
            print(f"      ✘  nota nº {historico.numero_nota(chave):<9} {fmt_chave(chave)}")
            print(f"         {_cor(traduzir_erro(msg), _VERMELHO)}")
            log.info("Detalhe técnico da nota %s: %s", historico.numero_nota(chave), msg)
    print()
    print(borda)
    if erros or not doadas:
        som.falha()
    else:
        som.sucesso()


def _pedir_cnpj_valido(cnpj_invalido: str) -> str:
    """Informa ao operador que o CNPJ foi rejeitado e solicita o CNPJ correto."""
    _limpar_tela()
    print(_cor("=" * 62, _VERMELHO))
    print(_cor("   O PORTAL NÃO ACEITOU O CNPJ DA ENTIDADE", _VERMELHO + _NEGRITO))
    print(_cor("=" * 62, _VERMELHO))
    print(f"\n   CNPJ digitado: {cnpj_invalido}")
    print("   Confira os 14 números e digite o CNPJ certo da entidade.")
    print("   Depois disso, as notas serão enviadas de novo.\n")
    print(_cor("-" * 62, _VERMELHO))

    novo = ""
    while len(novo) != 14:
        raw = _input_com_padrao("CNPJ correto da entidade (14 dígitos)", "")
        novo = so_digitos(raw)
        if len(novo) != 14:
            print(f"   O CNPJ precisa ter 14 números e você digitou {len(novo)}. "
                  "Confira e digite de novo.\n")
    return novo


def _tela_limite_erros(n_com_erro: int, n_restantes: int) -> bool:
    """
    Exibe aviso de muitos erros consecutivos e pergunta se deve continuar.
    Retorna True se o operador quiser continuar, False para encerrar.
    """
    _limpar_tela()
    print(_cor("=" * 62, _AMARELO))
    print(_cor(f"   O ENVIO PAROU: {LIMITE_ERROS_CHAVE} NOTAS SEGUIDAS NÃO FORAM DOADAS",
               _AMARELO + _NEGRITO))
    print(_cor("=" * 62, _AMARELO))
    print(f"\n   {n_com_erro} nota(s) não foram doadas e {n_restantes} ainda não foram enviadas.")
    print()
    print("   O que pode ter acontecido:")
    print("   • o site do Nota Paraná está lento ou com problemas;")
    print("   • a internet está instável;")
    print("   • as notas já tinham sido doadas antes.")
    print()
    print("   Nenhuma nota foi perdida: elas continuam guardadas.")
    print()
    print(_cor("-" * 62, _AMARELO))
    print(f"   S = sim, tentar de novo essas {n_com_erro + n_restantes} nota(s)"
          "  |  N = parar por agora")
    print(_cor("=" * 62, _AMARELO))
    while True:
        resp = input("\n   Sua escolha [S/N]: ").strip().upper()
        if resp in ("S", "SIM"):
            return True
        if resp in ("N", "NAO", "NÃO", ""):
            return False
        print("   Digite S para sim ou N para não.")


def _tela_recuperacao(qtd: int) -> bool:
    """Oferece continuar com notas lidas antes e que ainda não foram doadas."""
    _limpar_tela()
    print(_cor("=" * 62, _AMARELO))
    print(_cor("   HÁ NOTAS GUARDADAS DA ÚLTIMA VEZ", _AMARELO + _NEGRITO))
    print(_cor("=" * 62, _AMARELO))
    print(f"\n   {_cor(str(qtd), _NEGRITO)} nota(s) foram lidas antes e ainda não foram doadas.")
    print("   Isso acontece quando o programa é fechado ou dá algum problema")
    print("   antes de terminar o envio.")
    print()
    print(_cor("-" * 62, _AMARELO))
    print("   S = sim, continuar com essas notas  |  N = não, descartá-las")
    print(_cor("=" * 62, _AMARELO))
    while True:
        resp = input("\n   Sua escolha [S/N]: ").strip().upper()
        if resp in ("S", "SIM", ""):
            return True
        if resp in ("N", "NAO", "NÃO"):
            return False
        print("   Digite S para sim ou N para não.")


def _garantir_internet() -> bool:
    """Confere a conexão antes de abrir o navegador. False = voltar ao menu."""
    while True:
        print("\n   Verificando a conexão com a internet...")
        situacao = rede.diagnosticar()
        if situacao == rede.OK:
            return True

        som.falha()
        _limpar_tela()
        print(_cor("=" * 62, _VERMELHO))
        if situacao == rede.SEM_INTERNET:
            print(_cor("   SEM INTERNET", _VERMELHO + _NEGRITO))
            print(_cor("=" * 62, _VERMELHO))
            print("\n   O computador não está conectado à internet.")
            print("   Confira o cabo de rede ou o Wi-Fi.")
        else:
            print(_cor("   SITE DO NOTA PARANÁ NÃO RESPONDE", _VERMELHO + _NEGRITO))
            print(_cor("=" * 62, _VERMELHO))
            print("\n   A internet está funcionando, mas o site do Nota Paraná")
            print("   não respondeu. Ele pode estar fora do ar ou muito lento.")
            print("   Aguarde alguns minutos.")
        print("\n   Suas notas lidas continuam guardadas.")
        print()
        print(_cor("-" * 62, _VERMELHO))
        print("   ENTER = tentar de novo  |  N = voltar ao menu")
        print(_cor("=" * 62, _VERMELHO))
        resp = input("\n   Sua escolha: ").strip().upper()
        if resp in ("N", "NAO", "NÃO"):
            return False


# ---------------------------------------------------------------------------
# Processamento de lote
# ---------------------------------------------------------------------------

def _acumular(anterior: dict | None, novo: dict) -> dict:
    """Soma uma nova rodada ao resultado das anteriores do mesmo lote.

    As chaves com erro da rodada anterior foram reenviadas na nova, então
    para elas vale apenas o novo resultado; doadas e expiradas se somam.
    """
    if anterior is None:
        return novo
    expiradas = anterior["chaves_expiradas"] + novo["chaves_expiradas"]
    ja_expiradas = set(anterior["chaves_expiradas"])
    mensagens = [m for m in anterior["erros_com_mensagem"] if m[0] in ja_expiradas]
    return {
        **novo,
        "sucesso": anterior["sucesso"] + novo["sucesso"],
        "chaves_expiradas": expiradas,
        "erros_com_mensagem": mensagens + novo["erros_com_mensagem"],
        "erro": len(expiradas) + len(novo["chaves_com_erro"]),
    }


# ---------------------------------------------------------------------------
# Fluxo principal
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automação de doação de notas fiscais no Nota Paraná"
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Executa o navegador sem janela gráfica",
    )
    parser.add_argument(
        "--sem-atualizar", action="store_true",
        help="Não verifica se há versão nova no GitHub",
    )
    args = parser.parse_args()

    preparar_console()
    configurar_log()

    # ── Atualização: aplica a versão nova e reinicia com o código novo ───────
    # APACN_REINICIADO evita checar de novo logo após reiniciar.
    if not args.sem_atualizar and not os.environ.get("APACN_REINICIADO"):
        if verificar_e_atualizar():
            env = {**os.environ, "APACN_REINICIADO": "1"}
            comando = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]
            sys.exit(subprocess.call(comando, env=env))

    config = _carregar_config()
    usuario = cnpj_entidade = senha = None

    pw = browser = page = None
    houve_erro_geral = False
    cnpj_verificado  = False
    todas_chaves_erro: list[str] = []   # acumula erros de todos os lotes

    def relogin() -> None:
        fazer_login_portal(page, usuario, senha)

    def enviar(chaves_envio: list[str], verificar: bool,
               titulo: str = "ENVIANDO DOAÇÕES") -> dict:
        """Envia um lote mostrando o painel e gravando o histórico nota a nota."""
        with PainelEnvio(len(chaves_envio), titulo) as painel:
            def progresso(chave: str, status: str, msg: str) -> None:
                if status in (historico.STATUS_DOADA, historico.STATUS_FORA_PRAZO):
                    historico.registrar(chave, status, cnpj_entidade, msg)
                painel.atualizar(chave, status, msg)

            return doar_lote(page, cnpj_entidade, chaves_envio,
                             verificar_cnpj=verificar, relogin=relogin,
                             ao_progresso=progresso)

    try:
        while True:
            opcao = _tela_menu(pw is not None, len(set(todas_chaves_erro)))
            if opcao == "0":
                break
            if opcao == "2":
                _tela_relatorio()
                continue

            # ── Notas guardadas de uma leitura anterior ───────────────────
            pendentes = recuperacao.carregar(historico.chaves_ja_processadas())
            recuperadas: list[str] = []
            if pendentes:
                if _tela_recuperacao(len(pendentes)):
                    recuperadas = pendentes
                else:
                    recuperacao.remover(pendentes)

            # ── Credenciais (apenas no primeiro lançamento) ───────────────
            if senha is None:
                usuario, cnpj_entidade, senha = _tela_credenciais(config)
                # Salva usuário e CNPJ (nunca a senha)
                config["usuario"]       = usuario
                config["cnpj_entidade"] = cnpj_entidade
                _salvar_config(config)

            # ── Coleta ────────────────────────────────────────────────────
            # Cada nota lida é guardada em disco na hora (ver recuperacao.py)
            chaves = coletar_qr_codes(historico.chaves_ja_processadas(),
                                      iniciais=recuperadas,
                                      ao_registrar=recuperacao.adicionar)

            if not chaves:
                _limpar_tela()
                print(_cor("   Nenhuma nota foi lida. Voltando ao menu.", _AMARELO))
                _pausar()
                continue

            # ── Confirmação ───────────────────────────────────────────────
            if not _tela_confirmacao(chaves):
                print("\n   Tudo bem, nada foi doado.")
                print("   As notas lidas continuam guardadas: na próxima vez o programa")
                print("   pergunta se você quer continuar com elas.")
                _pausar()
                continue

            # ── Abre navegador (apenas no primeiro lançamento) ────────────
            if pw is None:
                if not _garantir_internet():
                    print("\n   As notas lidas continuam guardadas.")
                    _pausar()
                    continue
                print("\n   Entrando no portal Nota Paraná. Aguarde...")
                pw, browser, page = abrir_navegador(headless=args.headless)

                # Login com retry – navegador permanece aberto em caso de erro
                while True:
                    try:
                        fazer_login_portal(page, usuario, senha)
                        break
                    except CredenciaisInvalidasError:
                        usuario, senha = _tela_login_invalido(usuario)
                        config["usuario"] = usuario
                        _salvar_config(config)

            # ── Doação (com retry em caso de CNPJ inválido ou limite de erros) ─
            chaves_lote = list(chaves)
            resultado = None

            while True:
                rodada = enviar(chaves_lote, verificar=not cnpj_verificado)
                resultado = _acumular(resultado, rodada)

                # CNPJ rejeitado → pede novo CNPJ e reprocessa as mesmas chaves
                if rodada.get("cnpj_invalido"):
                    cnpj_entidade = _pedir_cnpj_valido(cnpj_entidade)
                    config["cnpj_entidade"] = cnpj_entidade
                    _salvar_config(config)
                    chaves_lote = rodada["chaves_com_erro"]
                    continue

                # Muitos erros seguidos → pergunta ao operador se continua
                if rodada.get("parou_por_limite_erros"):
                    n_restantes = rodada["nao_processadas"]
                    n_com_erro  = len(rodada["chaves_com_erro"]) - n_restantes
                    if _tela_limite_erros(n_com_erro, n_restantes):
                        chaves_lote = rodada["chaves_com_erro"]
                        cnpj_verificado = True
                        continue
                    break   # operador optou por não continuar

                cnpj_verificado = True
                break

            # ── Resultado ────────────────────────────────────────────────
            recuperacao.carregar(historico.chaves_ja_processadas())   # tira as já doadas
            _tela_resultado(resultado)

            # Notas fora do prazo não entram aqui: não há o que relançar.
            if resultado["chaves_com_erro"]:
                houve_erro_geral = True
                todas_chaves_erro.extend(resultado["chaves_com_erro"])

            _pausar()

        # ── Retry automático das notas com erro ──────────────────────────────
        # Remove duplicatas preservando a ordem e ignora as que já foram
        # resolvidas em um lote posterior (constam no histórico).
        resolvidas = historico.chaves_ja_processadas()
        chaves_retry = [c for c in dict.fromkeys(todas_chaves_erro) if c not in resolvidas]
        if not chaves_retry:
            houve_erro_geral = False
        elif pw is not None:
            resultado_retry = enviar(chaves_retry, verificar=not cnpj_verificado,
                                     titulo="TENTANDO DE NOVO AS NOTAS NÃO DOADAS")
            recuperacao.carregar(historico.chaves_ja_processadas())
            _tela_resultado(resultado_retry)
            if not resultado_retry["chaves_com_erro"]:
                houve_erro_geral = False   # todos os erros foram recuperados

    except KeyboardInterrupt:
        houve_erro_geral = True
        print("\n\n   O programa foi interrompido.")
        print("   As notas lidas e ainda não doadas ficam guardadas.")
        print("   Ao abrir de novo, o programa oferece continuar de onde parou.")
    except Exception:
        # Problema inesperado: explica sem mostrar o erro técnico (que vai ao log)
        houve_erro_geral = True
        log.exception("Erro inesperado no lançamento", extra={"so_arquivo": True})
        som.falha()
        print()
        print(_cor("=" * 62, _VERMELHO))
        print(_cor("   ACONTECEU UM PROBLEMA INESPERADO", _VERMELHO + _NEGRITO))
        print(_cor("=" * 62, _VERMELHO))
        print("\n   Não se preocupe: nenhuma nota foi perdida.")
        print("   As notas lidas e ainda não doadas ficaram guardadas.")
        print("   Feche esta janela, abra o programa de novo e escolha")
        print("   continuar com as notas guardadas.")
        print("\n   Se o problema se repetir, avise o suporte e informe que")
        print(f"   o registro está em: {PASTA_LOGS}")
    finally:
        # ── Logout e encerramento (só se o navegador foi aberto) ─────────
        if pw is not None:
            try:
                encerrar_sessao(pw, browser, page)
            except Exception:
                log.exception("Falha ao encerrar a sessão", extra={"so_arquivo": True})
            print("\n   Sessão encerrada. Até logo!")
        else:
            print("\n   Até logo!")

    sys.exit(1 if houve_erro_geral else 0)


if __name__ == "__main__":
    main()
