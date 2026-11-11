"""
mensagens.py
------------
Traduz mensagens técnicas do portal e do log para frases simples, com a
orientação do que fazer. O texto técnico original continua no log
(logs/AAAA-MM-DD.log) e no histórico, para o suporte.
"""

import re

_ERROS = (
    (r"prazo para doar esta nota expirou",
     "O prazo para doar esta nota já passou."),
    (r"CNPJ .*rejeitado pelo portal",
     "O portal não aceitou o CNPJ da entidade. Confira os números."),
    (r"^HTTP 5\d\d",
     "O portal está com problemas no momento. Tente de novo mais tarde."),
    (r"^Timeout",
     "O portal demorou demais para responder."),
    (r"Resultado indeterminado",
     "Não deu para confirmar se a nota foi doada. Confira no site do Nota Paraná."),
    (r"^Não processada",
     "Esta nota ainda não foi enviada, pois o envio foi interrompido."),
    (r"^Erro inesperado",
     "Aconteceu um problema inesperado ao enviar esta nota."),
)

_AVISOS = (
    (r"Formulário de doação indisponível|Sessão expirada|Menu de doações indisponível"
     r"|Sessão restaurada|Sessão duplicada",
     "A conexão com o portal caiu. Entrando de novo, aguarde..."),
    (r"não interceptada|não detectado|interceptad",
     ""),   # detalhe técnico sem relevância para o operador
)


def traduzir_erro(msg: str) -> str:
    """Frase simples para o motivo pelo qual uma nota não foi doada."""
    msg = (msg or "").strip()
    for padrao, frase in _ERROS:
        if re.search(padrao, msg, re.IGNORECASE):
            return frase
    if not msg or msg.startswith("Erro 400"):
        return "O portal não aceitou esta nota."
    return f"O portal não aceitou esta nota. Motivo informado: {msg}"


def traduzir_aviso(msg: str) -> str:
    """Frase simples para um aviso do log; vazio = não mostrar nada."""
    for padrao, frase in _AVISOS:
        if re.search(padrao, msg, re.IGNORECASE):
            return frase
    return "O portal está lento. Aguarde, o programa continua tentando..."
