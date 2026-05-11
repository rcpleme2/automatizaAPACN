Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "         INICIALIZANDO AUTOMATIZA APACN" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

# Verifica se a pasta do ambiente virtual existe
if (-not (Test-Path "venv")) {
    Write-Host "[!] Ambiente virtual nao encontrado. Criando..." -ForegroundColor Yellow
    python -m venv venv
    ./venv/Scripts/Activate.ps1
    Write-Host "[!] Instalando dependencias..." -ForegroundColor Yellow
    pip install -r requirements.txt
    playwright install chromium
} else {
    Write-Host "[OK] Ambiente virtual detectado." -ForegroundColor Green
    ./venv/Scripts/Activate.ps1
}

Write-Host "[OK] Iniciando script principal..." -ForegroundColor Green
Write-Host ""

# Executa o main.py
python main.py

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "    Execucao finalizada. Pressione ENTER para sair." -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Pause