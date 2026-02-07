# Script para iniciar o bot com a opção 2 (interface web)
cd $PSScriptRoot
Write-Host "Iniciando Discord Music Bot com interface web..."
Write-Host ""

# Pipar a opção 2 para escolher interface web
echo "2" | & .\.venv\Scripts\python.exe bot.py
