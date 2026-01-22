#!/bin/bash

# Garante que os arquivos json existam
if [ ! -f /app/token.json ]; then
    echo "{}" > /app/token.json
fi

if [ ! -f /app/radios.json ]; then
    echo "{}" > /app/radios.json
fi

echo "Corrigindo permissões dos arquivos..."
# Ajusta o dono dos arquivos para o usuário appuser
chown -R appuser:appgroup /app/token.json
chown -R appuser:appgroup /app/radios.json
chown -R appuser:appgroup /app/playlist

# Verifica se o arquivo do bot existe (para debug)
if [ ! -f /app/bot.py ]; then
    echo "ERRO: O arquivo bot.py não foi encontrado em /app/"
    ls -la /app/
    exit 1
fi

echo "Iniciando aplicação..."
# Executa o comando original (python3 bot.py) como o usuário appuser usando gosu
exec gosu appuser "$@"