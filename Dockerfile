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
        npm && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip3 install --upgrade pip

# instala dependências do projeto
RUN pip3 install --no-cache-dir -r requirements.txt

# 🔥 GARANTE yt-dlp sempre atualizado (evita 403 do YouTube)
RUN pip3 install --no-cache-dir -U yt-dlp

# usuário não-root
ARG UID=1000
ARG GID=1000

RUN groupadd -g ${GID} -o appgroup
RUN useradd -m -r -d /app -u ${UID} -g appgroup -o -s /bin/bash appuser

RUN mkdir -p /app/playlist

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

COPY . .

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["python3", "bot.py"]
