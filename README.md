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

## Instalação e uso (Windows)

### Pré-requisitos

**1. Instalar o Python**
Baixe em **https://www.python.org/downloads/** e execute o instalador.
> Durante a instalação, marque obrigatoriamente a opção **"Add Python to PATH"**.

**2. Baixar o projeto**
Baixe o ZIP do repositório e extraia em uma pasta de sua preferência.

**3. Configurar o arquivo `.env`**
Dentro da pasta extraída, copie o arquivo `.env.example`, renomeie a cópia para `.env` e preencha os dados:

```env
NOTAPARANA_USER=00000000000          # seu CPF ou CNPJ (somente números)
NOTAPARANA_PASSWORD=suasenha
NOTAPARANA_CNPJ_ENTIDADE=00000000000000   # CNPJ da entidade (14 dígitos)
```

> **O arquivo `.env` nunca deve ser versionado.** Ele já está no `.gitignore`.

**4. Executar**
Dê dois cliques no arquivo **`iniciar.bat`**.

- **Primeira execução:** o sistema instala automaticamente todas as dependências (pode levar alguns minutos). Aguarde a conclusão.
- **Execuções seguintes:** abre o programa diretamente.

---

## Como usar o programa

1. Execute `iniciar.bat`.
2. Aponte o leitor USB para o QR code ou código de barras de cada nota — ele lê e registra automaticamente.
3. Para **encerrar a coleta**: leia um código com o texto `FIM`, ou pressione **ENTER** com o campo vazio.
4. Revise a lista exibida e confirme digitando **S** + ENTER.
5. Aguarde o envio automático. Ao final, um aviso mostra quantas notas foram doadas.

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
├── iniciar.bat          # Clique duplo para instalar e executar (Windows)
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
