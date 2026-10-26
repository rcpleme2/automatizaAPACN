# automatizaAPACN

Sistema de coleta de notas fiscais do Paraná via leitor de QR code/código de barras e envio automático para doação no portal **Nota Paraná**.

Inicializar sempre pelo arquivo inicia.bat. Ao abrir, o próprio programa verifica se há versão nova no GitHub e se atualiza com um único **S**.


## Visão geral do fluxo

```
[ Atualização ] ──▶ [ Menu ] ──▶ [ Credenciais ] ──▶ [ Leitor QR/Barcode ] ──▶ [ Confirmação ] ──▶ [ Playwright → Nota Paraná ] ──▶ [ Histórico ]
                       └──▶ [ Relatório do histórico (HTML / PDF) ]
```

0. **Menu** – `1` lança notas, `2` gera o relatório do histórico, `0` sai.
1. **Credenciais** – No primeiro lançamento o programa solicita CPF, CNPJ da entidade e senha. CPF e CNPJ são salvos localmente para a próxima execução; a senha nunca é salva.
2. **Coleta** – O operador passa o leitor USB nos QR codes/códigos de barras das notas. Cada chave é validada em tempo real, e notas que já constam no histórico deste computador são recusadas na leitura.
3. **Confirmação** – O operador revisa a lista antes de prosseguir.
4. **Doação automática** – O script abre o navegador, faz login no portal e processa cada nota:
   - **1ª doação:** preenche o CNPJ da entidade, aguarda a verificação automática do portal (HTTP 200 = ok, HTTP 400 = CNPJ inválido) e, se válido, lança a nota.
   - **Demais doações:** o CNPJ já está preenchido; o script vai direto ao preenchimento da chave e ao clique no botão de doação.
   - Cada doação aguarda a confirmação do portal (`_mensagem: "Documento fiscal doado com sucesso!"`) antes de avançar para a próxima.
   - Se a sessão do portal expirar no meio do lote, o login é refeito automaticamente e a nota é tentada de novo.
5. **Resultado** – Aviso visual informa quantas notas foram doadas com sucesso e quais tiveram erro. Cada nota doada (ou recusada por prazo) é gravada no histórico local na hora.
6. **Volta ao menu** – O operador pode lançar novos lotes sem precisar refazer o login. Ao sair, as notas com erro são relançadas automaticamente uma vez.

---

## Instalação e uso (Windows)

### Pré-requisitos

**1. Instalar o Python**
Baixe em **https://www.python.org/downloads/** e execute o instalador.
> Durante a instalação, marque obrigatoriamente a opção **"Add Python to PATH"**.

**2. Baixar o projeto**
Baixe o ZIP do repositório e extraia em uma pasta de sua preferência.

**3. Instalar as dependências**
Abra o terminal na pasta do projeto e execute:

```bash
pip install -r requirements.txt
playwright install chromium
```

**4. Executar**

Dê dois cliques em `inicia.bat` (recomendado) ou, no terminal:

```bash
python main.py
```

Para rodar sem janela do navegador (modo oculto):

```bash
python main.py --headless
```

---

## Como usar o programa

1. Execute `inicia.bat`. Se houver versão nova, confirme com **S** (ou ENTER); o programa se atualiza e reinicia sozinho.
2. No menu, escolha **1 – Lançar notas**.
3. Informe o **CPF**, o **CNPJ da entidade** e a **senha** do portal Nota Paraná.
   - CPF e CNPJ são pré-preenchidos com os valores da última execução — pressione ENTER para manter.
   - A senha **aparece na tela** durante a digitação (para evitar erros de digitação), mas **nunca é salva**.
4. Aponte o leitor USB para o QR code ou código de barras de cada nota — ele lê e registra automaticamente.
5. Para **encerrar a coleta**: leia um código com o texto `FIM`, ou pressione **ENTER** com o campo vazio.
6. Revise a lista exibida e confirme digitando **S** + ENTER.
7. Aguarde o envio automático. A tela de envio mostra barra de progresso, contadores (doadas, fora do prazo, com erro), tempo restante e as últimas notas. Ao final, o resumo separa as notas fora do prazo (normal) das notas com erro (verificar).
8. Pressione ENTER para voltar ao menu: **1** lança mais notas (sem refazer login), **0** encerra.

---

## Histórico e relatório

Toda nota **doada** ou **recusada por prazo expirado** é gravada em `historico_doacoes.csv`
(pode ser aberto no Excel) no momento em que o portal confirma o resultado.

No menu, a opção **2 – Relatório do histórico** pede o período (data inicial e final) e gera
um HTML em `relatorios/`, que abre automaticamente no navegador. O botão
**Imprimir / Salvar em PDF** exporta o documento.

> O relatório deixa claro que se refere **apenas às notas processadas naquele computador**
> no período informado. Doações feitas em outro computador ou direto no portal não aparecem.

---

## Atualização automática

Ao iniciar, o `main.py` chama o `atualizador.py` (não depende do `inicia.bat`):

1. Baixa a versão do branch `main` do GitHub e compara com os arquivos locais.
2. Havendo diferença, mostra a última alteração e os arquivos afetados e pergunta **Atualizar agora? [S/n]**.
3. Atualiza os arquivos do programa; se o `requirements.txt` mudou, reinstala as dependências. Em seguida o programa reinicia já na versão nova.
4. `config.json`, `historico_doacoes.csv`, `relatorios/`, `logs/` e `venv/` **nunca são alterados**.
5. O `inicia.bat` não é atualizado automaticamente (o Windows lê o `.bat` enquanto ele roda; trocá-lo no meio causaria erros). Ele é só o lançador e raramente muda.

Para pular a verificação: `python main.py --sem-atualizar`.

---

## Log técnico

Durante o envio a tela mostra apenas o painel de progresso. O registro técnico completo
de cada execução fica em `logs/AAAA-MM-DD.log`, útil para suporte.

Sem internet, a verificação é ignorada e o programa segue normalmente.

---

## Verificação de CNPJ da entidade

Na **primeira doação de cada sessão** o script:

1. Preenche o campo de CNPJ no formulário.
2. Aciona a verificação automática do portal (evento blur/change).
3. Aguarda a resposta HTTP:
   - **200** → CNPJ válido, prossegue para a doação.
   - **400** → CNPJ inválido; exibe tela de erro e solicita o CNPJ correto. O novo CNPJ é salvo para as próximas execuções.

A partir da segunda doação o campo permanece preenchido, portanto a verificação é ignorada.

---

## Verificação de sucesso da doação

Após clicar no botão **DOAR DOCUMENTOS** (`#btnDoarDocumento`), o script intercepta a resposta HTTP:

- **HTTP 200** + `_mensagem: "Documento fiscal doado com sucesso!"` → nota contabilizada como doada.
- Qualquer outra resposta → nota registrada como erro e incluída na lista de chaves com falha.
- **Nota fora do prazo** (`O prazo para doar esta nota expirou`) → aparece no resultado, mas não conta para o limite de 5 erros consecutivos e não é relançada.

---

## Validação das chaves de acesso

Cada código escaneado passa pelas seguintes verificações antes de ser aceito:

- Possui exatamente **44 dígitos numéricos**
- `cUF = 41` (estado do **Paraná**)
- Modelo `55` (NF-e) ou `65` (NFC-e)
- Dígito verificador correto (Módulo 11, conforme manual SEFAZ)

Leituras duplicadas ou inválidas são descartadas com aviso imediato na tela.
A chave pode ser fornecida com espaços ou hífens entre grupos — o sistema normaliza automaticamente.

**Digitação manual:** digite os 44 números da chave (eles aparecem na tela) e tecle **ENTER**. Com o leitor USB não é preciso ENTER: a leitura termina sozinha.

---

## Estrutura dos arquivos

```
automatizaAPACN/
├── inicia.bat           # Inicializador (ambiente virtual + programa)
├── atualizador.py       # Verifica e aplica versão nova do GitHub
├── painel.py            # Painel de envio e configuração do log
├── main.py              # Ponto de entrada – menu e fluxo completo
├── qr_collector.py      # Coleta via leitor HID + validação de chaves
├── notaparana_bot.py    # Automação Playwright do portal Nota Paraná
├── historico.py         # Histórico local e relatório HTML
├── requirements.txt     # Dependências Python
├── config.json          # CPF e CNPJ salvos entre execuções (gerado automaticamente)
├── historico_doacoes.csv  # Histórico das notas processadas neste computador (gerado)
├── relatorios/          # Relatórios HTML gerados
├── logs/                # Log técnico por dia
├── .gitignore
└── README.md
```

> `config.json`, `historico_doacoes.csv`, `relatorios/` e `logs/` são gerados automaticamente e estão no `.gitignore`.

---

## Segurança

- **Senha nunca é salva** — solicitada a cada execução (fica visível durante a digitação).
- CPF e CNPJ da entidade são salvos em `config.json` apenas para conveniência do operador.
- O `config.json` está no `.gitignore` e não deve ser versionado.
- O script não grava credenciais em logs ou arquivos de saída.
