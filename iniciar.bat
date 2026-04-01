@echo off
chcp 65001 >nul
title Nota Paraná – Doação Automática

:: ─────────────────────────────────────────────
:: Verifica se Python está instalado
:: ─────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERRO: Python nao encontrado.
    echo  Baixe e instale em: https://www.python.org/downloads/
    echo  Marque a opcao "Add Python to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

:: ─────────────────────────────────────────────
:: Cria ambiente virtual na primeira execução
:: ─────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo.
    echo  Primeira execucao: configurando o ambiente...
    echo  Isso pode levar alguns minutos. Aguarde.
    echo.
    python -m venv venv
    if errorlevel 1 (
        echo  ERRO ao criar ambiente virtual.
        pause
        exit /b 1
    )
)

:: ─────────────────────────────────────────────
:: Ativa o ambiente virtual
:: ─────────────────────────────────────────────
call venv\Scripts\activate.bat

:: ─────────────────────────────────────────────
:: Instala / atualiza dependências se necessário
:: ─────────────────────────────────────────────
if not exist "venv\.instalado" (
    echo  Instalando dependencias Python...
    pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo  ERRO ao instalar dependencias.
        pause
        exit /b 1
    )

    echo  Instalando navegador Chromium ^(Playwright^)...
    playwright install chromium
    if errorlevel 1 (
        echo  ERRO ao instalar Chromium.
        pause
        exit /b 1
    )

    echo instalado > venv\.instalado
    echo  Configuracao concluida!
    echo.
)

:: ─────────────────────────────────────────────
:: Verifica se o arquivo .env existe
:: ─────────────────────────────────────────────
if not exist ".env" (
    echo.
    echo  ATENCAO: Arquivo de configuracao ".env" nao encontrado.
    echo  Copie o arquivo ".env.example" para ".env" e preencha:
    echo    - NOTAPARANA_USER      = seu CPF ou CNPJ
    echo    - NOTAPARANA_PASSWORD  = sua senha
    echo    - NOTAPARANA_CNPJ_ENTIDADE = CNPJ da entidade
    echo.
    pause
    exit /b 1
)

:: ─────────────────────────────────────────────
:: Executa o sistema
:: ─────────────────────────────────────────────
echo.
python main.py
echo.
pause
