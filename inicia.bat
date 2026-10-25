@echo off
title Automatiza APACN - Inicializador
cls

echo ======================================================
echo          INICIALIZANDO AUTOMATIZA APACN
echo ======================================================

:: Verifica se a pasta do ambiente virtual existe (ajuste 'venv' se o seu tiver outro nome)
if not exist venv (
    echo [!] Ambiente virtual nao encontrado. Criando...
    python -m venv venv
    call venv\Scripts\activate
    echo [!] Instalando dependencias...
    pip install -r requirements.txt
    playwright install chromium
) else (
    echo [OK] Ambiente virtual detectado.
    call venv\Scripts\activate
)

:: Verifica se ha versao nova no GitHub (sai com 2 quando requirements.txt mudou)
python atualizador.py
if errorlevel 2 (
    echo [!] Atualizando dependencias...
    pip install -r requirements.txt
    playwright install chromium
)

:: O proprio inicializador e baixado como inicia.bat.novo; troca e reinicia.
:: O bloco entre parenteses e lido inteiro antes de executar, por isso a troca
:: do arquivo em uso e segura aqui.
if exist inicia.bat.novo (
    move /y inicia.bat.novo inicia.bat >nul
    echo [OK] Inicializador atualizado. Reiniciando...
    start "" "%~f0"
    exit
)

echo [OK] Iniciando script principal...
echo.

:: Executa o main.py. Use "python main.py --headless" se quiser ocultar o navegador.
python main.py

echo.
echo ======================================================
echo    Execucao finalizada. Pressione qualquer tecla.
echo ======================================================
pause
