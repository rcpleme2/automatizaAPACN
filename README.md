# automatizaAPACN

Sistema de coleta de notas fiscais do Paraná via leitor de QR code/código de barras e envio automático para doação no portal **Nota Paraná**.

## Visão geral do fluxo

```
[ Credenciais ] ──▶ [ Leitor QR/Barcode ] ──▶ [ Confirmação ] ──▶ [ Playwright → Nota Paraná ]
```

1. **Credenciais** – O programa solicita CPF, CNPJ da entidade e senha. CPF e CNPJ são salvos localmente para a próxima execução; a senha nunca é salva.
2. **Coleta** – O operador passa o leitor USB nos QR codes/códigos de barras das notas. Cada chave é validada em tempo real.
3. **Confirmação** – O operador revisa a lista antes de prosseguir.
4. **Doação automática** – O script abre o navegador, faz login no portal e processa cada nota:
   - **1ª doação:** preenche o CNPJ da entidade, aguarda a verificação automática do portal (HTTP 200 = ok, HTTP 400 = CNPJ inválido) e, se válido, lança a nota.
   - **Demais doações:** o CNPJ já está preenchido; o script vai direto ao preenchimento da chave e ao clique no botão de doação.
   - Cada doação aguarda a confirmação do portal (`_mensagem: "Documento fiscal doado com sucesso!"`) antes de avançar para a próxima.
5. **Resultado** – Aviso visual informa quantas notas foram doadas com sucesso e quais tiveram erro.
6. **Mais notas?** – O operador pode lançar novos lotes sem precisar refazer o login.

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

```bash
python main.py
```

Para rodar sem janela do navegador (modo oculto):

```bash
python main.py --headless
```

---

## Como usar o programa

1. Execute `python main.py`.
2. Informe o **CPF**, o **CNPJ da entidade** e a **senha** do portal Nota Paraná.
   - CPF e CNPJ são pré-preenchidos com os valores da última execução — pressione ENTER para manter.
   - A senha não é exibida durante a digitação e **nunca é salva**.
3. Aponte o leitor USB para o QR code ou código de barras de cada nota — ele lê e registra automaticamente.
4. Para **encerrar a coleta**: leia um código com o texto `FIM`, ou pressione **ENTER** com o campo vazio.
5. Revise a lista exibida e confirme digitando **S** + ENTER.
6. Aguarde o envio automático. Ao final, um aviso mostra quantas notas foram doadas.
7. Escolha **S** para lançar mais notas (sem refazer login) ou **N** para encerrar.

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

---

## Validação das chaves de acesso

Cada código escaneado passa pelas seguintes verificações antes de ser aceito:

- Possui exatamente **44 dígitos numéricos**
- `cUF = 41` (estado do **Paraná**)
- Modelo `55` (NF-e) ou `65` (NFC-e)
- Dígito verificador correto (Módulo 11, conforme manual SEFAZ)

Leituras duplicadas ou inválidas são descartadas com aviso imediato na tela.
A chave pode ser fornecida com espaços ou hífens entre grupos — o sistema normaliza automaticamente.

---

## Estrutura dos arquivos

```
automatizaAPACN/
├── main.py              # Ponto de entrada – orquestra o fluxo completo
├── qr_collector.py      # Coleta via leitor HID + validação de chaves
├── notaparana_bot.py    # Automação Playwright do portal Nota Paraná
├── requirements.txt     # Dependências Python
├── config.json          # CPF e CNPJ salvos entre execuções (gerado automaticamente)
├── .gitignore
└── README.md
```

> `config.json` é gerado automaticamente na primeira execução e está no `.gitignore`.

---

## Segurança

- **Senha nunca é salva** — solicitada a cada execução via `getpass` (entrada oculta).
- CPF e CNPJ da entidade são salvos em `config.json` apenas para conveniência do operador.
- O `config.json` está no `.gitignore` e não deve ser versionado.
- O script não grava credenciais em logs ou arquivos de saída.
