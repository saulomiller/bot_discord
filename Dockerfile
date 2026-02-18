FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# dependências do sistema
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    ffmpeg \
    gosu \
    curl \
    nodejs \
    npm \
    libopus0 \
    unzip && \
    rm -rf /var/lib/apt/lists/*

# Instala deno para extração do YouTube (resolve WARNING do yt-dlp)
RUN curl -fsSL https://deno.land/install.sh | sh && \
    mv /root/.deno/bin/deno /usr/local/bin/deno && \
    chmod +x /usr/local/bin/deno && \
    echo 'export PATH="/usr/local/bin:$PATH"' >> /etc/environment

COPY requirements.txt .

RUN pip3 install --upgrade pip

# instala dependências do projeto
RUN pip3 install --no-cache-dir -r requirements.txt

# 🔥 GARANTE yt-dlp sempre atualizado + yt-dlp-ejs (JS challenge solver)
RUN pip3 install --no-cache-dir -U "yt-dlp[default]"

# Pré-baixa os scripts EJS para resolver desafios JS do YouTube (no cache da app)
RUN yt-dlp --cache-dir /app/.cache --remote-components ejs:github -o /dev/null --no-download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" 2>/dev/null || true

# usuário não-root
ARG UID=1000
ARG GID=1000

RUN groupadd -g ${GID} -o appgroup
RUN useradd -m -r -d /app -u ${UID} -g appgroup -o -s /bin/bash appuser

# Cria diretórios necessários com permissões corretas
RUN mkdir -p /app/playlist /app/.cache && \
    chown -R appuser:appgroup /app/playlist /app/.cache

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

COPY . .

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["python3", "bot.py"]
