FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
# Define o diretório de trabalho no início
WORKDIR /app

# Instalar dependências do sistema: Python, pip, FFmpeg e Node.js (para o yt-dlp)
# Adicionar --no-install-recommends para reduzir o tamanho e limpar o cache do apt
RUN apt-get update && \ 
    apt-get install -y --no-install-recommends python3 python3-pip ffmpeg nodejs gosu && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

COPY requirements.txt .
RUN pip3 install --upgrade pip
# Usar --no-cache-dir para reduzir o tamanho da imagem
RUN pip3 install --no-cache-dir -r requirements.txt

# Adicionar argumentos para UID e GID do usuário do host
ARG UID=1000
ARG GID=1000

# Criar um usuário não-root para executar a aplicação por segurança
# Criar o grupo primeiro, depois o usuário com o UID/GID especificados
RUN groupadd -g ${GID} -o appgroup
RUN useradd -m -r -d /app -u ${UID} -g appgroup -o -s /bin/bash appuser

RUN mkdir -p /app/playlist

# --- MUDANÇAS AQUI ---

# 1. Copia o script de entrypoint e dá permissão de execução
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# 2. Copia o resto dos arquivos
COPY . .

# 4. Define o script como ponto de entrada
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
# 5. O comando padrão do bot
CMD ["python3", "bot.py"]
