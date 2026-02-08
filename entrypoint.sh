#!/bin/bash

# Garante que o diretório de dados exista
mkdir -p /app/data/playlist

# Garante que os arquivos json existam
if [ ! -f /app/data/token.json ]; then
    echo "{}" > /app/data/token.json
fi

if [ ! -f /app/data/radios.json ]; then
    echo "{}" > /app/data/radios.json
fi

echo "Corrigindo permissões dos arquivos..."
# Ajusta o dono dos arquivos para o usuário appuser
chown -R appuser:appgroup /app/data /app/.cache

# Verifica se o arquivo do bot existe (para debug)
if [ ! -f /app/bot.py ]; then
    echo "ERRO: O arquivo bot.py não foi encontrado em /app/"
    ls -la /app/
    exit 1
fi

echo "Iniciando aplicação..."
# Executa o comando original (python3 bot.py) como o usuário appuser usando gosu
exec gosu appuser "$@"