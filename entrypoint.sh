#!/bin/bash

# Garante que os diretorios base existam.
# Os subdiretorios e arquivos JSON sao criados pela aplicacao quando necessario.
mkdir -p /app/data /app/.cache

echo "Corrigindo permissoes dos arquivos..."
# Ajusta o dono dos arquivos para o usuario appuser.
chown -R appuser:appgroup /app/data /app/.cache

# Verifica se o arquivo do bot existe para facilitar debug de imagem quebrada.
if [ ! -f /app/bot.py ]; then
    echo "ERRO: O arquivo bot.py nao foi encontrado em /app/"
    ls -la /app/
    exit 1
fi

echo "Iniciando aplicacao..."
exec gosu appuser "$@"
