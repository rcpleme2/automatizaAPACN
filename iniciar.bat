@echo off
chcp 65001 >nul
title Nota Paraná – Verificando atualizações...

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
:: Atualiza o aplicativo via Git (se disponível)
:: ─────────────────────────────────────────────
git --version >nul 2>&1
if errorlevel 1 (
    echo  AVISO: Git nao encontrado. Pulando verificacao de atualizacoes.
    echo  Para habilitar atualizacoes automaticas, instale o Git em: https://git-scm.com
    echo.
    goto :configurar
)

echo  Verificando atualizacoes no GitHub...
git fetch origin main >nul 2>&1
if errorlevel 1 (
    echo  AVISO: Nao foi possivel conectar ao GitHub. Continuando com a versao local.
    echo.
    goto :configurar
)

:: Compara commit local com remoto
for /f %%i in ('git rev-parse HEAD') do set LOCAL=%%i
for /f %%i in ('git rev-parse origin/main') do set REMOTO=%%i

if "%LOCAL%"=="%REMOTO%" (
    echo  Aplicativo ja esta na versao mais recente.
    echo.
    goto :configurar
)

echo  Nova versao disponivel. Atualizando...
git pull origin main
if errorlevel 1 (
    echo  AVISO: Falha ao atualizar. Continuando com a versao local.
) else (
    echo  Atualizado com sucesso!
    :: Força reinstalação de dependências após atualização
    if exist "venv\.instalado" del "venv\.instalado"
)
echo.

:: ─────────────────────────────────────────────
:configurar
:: Cria ambiente virtual se necessário
:: ─────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo  Configurando ambiente pela primeira vez. Aguarde...
    python -m venv venv
    if errorlevel 1 (
        echo  ERRO ao criar ambiente virtual.
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat

:: ─────────────────────────────────────────────
:: Instala / atualiza dependências se necessário
:: ─────────────────────────────────────────────
if not exist "venv\.instalado" (
    echo  Instalando dependencias...
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
:: Inicia o aplicativo
:: ─────────────────────────────────────────────
title Nota Paraná – Doação Automática
python main.py
echo.
pause
