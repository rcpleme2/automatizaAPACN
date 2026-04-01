# automatizaAPACN

Sistema de coleta de QR codes de notas fiscais do Paraná e envio automático para doação no portal **Nota Paraná**.

## Visão geral do fluxo

```
[ Câmera ] ──QR codes──▶ [ Validação ] ──chaves──▶ [ Confirmação ] ──▶ [ Playwright → Nota Paraná ]
```

1. **Coleta** – A câmera lê os QR codes das notas; cada chave de acesso (44 dígitos) é validada em tempo real.
2. **Confirmação** – O operador revisa as chaves antes de prosseguir.
3. **Doação automática** – O script faz login no portal e preenche o formulário de doação manual para cada chave.

---

## Pré-requisitos

| Dependência | Instalação |
|---|---|
| Python 3.11+ | `python3 --version` |
| libzbar (pyzbar) | `sudo apt-get install libzbar0` (Linux) |
| Playwright Chromium | `playwright install chromium` |

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
python main.py [--headless] [--camera INDICE]

  --headless        Executa o navegador sem janela gráfica
  --camera INDICE   Índice da câmera (padrão: 0)
```

### Somente coleta de QR codes (teste)

```bash
python qr_collector.py
```

#### Controles durante a coleta

| Tecla | Ação |
|---|---|
| `Q` | Finaliza a coleta e avança para a doação |
| `R` | Remove a última chave adicionada (desfaz leitura) |

---

## Validação das chaves de acesso

Cada QR code passa pelas seguintes verificações antes de ser aceito:

- Possui exatamente **44 dígitos numéricos**
- `cUF = 41` (estado do **Paraná**)
- Modelo `55` (NF-e) ou `65` (NFC-e)
- Dígito verificador correto (Módulo 11, conforme manual SEFAZ)

Chaves duplicadas ou inválidas são descartadas com aviso no console.

---

## Estrutura dos arquivos

```
automatizaAPACN/
├── main.py              # Ponto de entrada – orquestra o fluxo completo
├── qr_collector.py      # Leitura de QR codes via câmera + validação
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
