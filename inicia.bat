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

echo [OK] Iniciando script principal...
echo.

:: Executa o main.py. Use "python main.py --headless" se quiser ocultar o navegador.
python main.py

echo.
echo ======================================================
echo    Execucao finalizada. Pressione qualquer tecla.
echo ======================================================
pause