# automatizaAPACN

Sistema de coleta de notas fiscais do Paraná via leitor de QR code/código de barras e envio automático para doação no portal **Nota Paraná**.

## Visão geral do fluxo

```
[ Leitor QR/Barcode ] ──leitura──▶ [ Validação ] ──chaves──▶ [ Confirmação ] ──▶ [ Playwright → Nota Paraná ]
```

1. **Coleta** – O operador passa o leitor USB nos QR codes/códigos de barras das notas. Cada chave é validada na hora.
2. **Confirmação** – O operador revisa a lista antes de prosseguir.
3. **Doação automática** – O script faz login no portal e preenche o formulário de doação manual para cada chave.
4. **Resultado** – Aviso visual na tela informa quantas notas foram doadas com sucesso.

---

## Pré-requisitos

| Dependência | Instalação |
|---|---|
| Python 3.11+ | `python3 --version` |
| Playwright Chromium | `playwright install chromium` |
| Leitor de QR/barcode USB | Qualquer modelo que emule teclado (HID) |

> **Não é necessária webcam.** O leitor USB funciona como teclado: ao escanear, ele digita o código e tecla ENTER automaticamente.

---

## Instalação

```bash
# 1. Clone o repositório
git clone <url-do-repo>
cd automatizaAPACN

# 2. Crie e ative um ambiente virtual (recomendado)
python3 -m venv venv
source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate    # Windows

# 3. Instale as dependências Python
pip install -r requirements.txt

# 4. Instale o navegador Chromium para o Playwright
playwright install chromium

# 5. Configure o arquivo .env
cp .env.example .env
# Edite .env com seu CPF/CNPJ, senha e CNPJ da entidade
```

### Conteúdo do `.env`

```env
NOTAPARANA_USER=00000000000          # CPF ou CNPJ (somente números)
NOTAPARANA_PASSWORD=suasenha
NOTAPARANA_CNPJ_ENTIDADE=00000000000000   # CNPJ da entidade (14 dígitos)
```

> **O arquivo `.env` nunca deve ser versionado.** Ele já está no `.gitignore`.

---

## Uso

### Execução completa (recomendado)

```bash
python main.py
```

### Opções disponíveis

```
python main.py [--headless]

  --headless   Executa o navegador sem janela gráfica
```

### Como usar durante a coleta

1. Execute `python main.py` no terminal.
2. Aponte o leitor para o QR code ou código de barras de cada nota.
3. O leitor lê e envia automaticamente — a nota aparece listada na tela.
4. Para **encerrar**: leia um QR com o texto `FIM`, ou pressione **ENTER** com o campo vazio.
5. Confirme a lista exibida digitando **S** + ENTER.
6. Aguarde o envio automático. Ao final, um aviso mostra quantas notas foram doadas.

### Somente coleta (teste sem doação)

```bash
python qr_collector.py
```

---

## Validação das chaves de acesso

Cada código escaneado passa pelas seguintes verificações antes de ser aceito:

- Possui exatamente **44 dígitos numéricos**
- `cUF = 41` (estado do **Paraná**)
- Modelo `55` (NF-e) ou `65` (NFC-e)
- Dígito verificador correto (Módulo 11, conforme manual SEFAZ)

Leituras duplicadas ou inválidas são descartadas com aviso imediato na tela.

---

## Estrutura dos arquivos

```
automatizaAPACN/
├── main.py              # Ponto de entrada – orquestra o fluxo completo
├── qr_collector.py      # Coleta via leitor HID + validação de chaves
├── notaparana_bot.py    # Automação Playwright do portal Nota Paraná
├── requirements.txt     # Dependências Python
├── .env.example         # Modelo do arquivo de configuração
├── .gitignore
└── README.md
```

---

## Segurança

- Credenciais e CNPJ da entidade são lidos **exclusivamente** do arquivo `.env`.
- O `.env` está no `.gitignore` e **nunca** deve ser commitado.
- O script não armazena senhas em logs ou arquivos de saída.
