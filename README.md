# bot_discord

Bot de musica para Discord com painel web, player compacto, radios online,
playlists e soundboard. O projeto foi pensado para homelab com Docker, mas
tambem pode rodar localmente para desenvolvimento.

> Projeto em desenvolvimento ativo. Fluxos de instalacao, seguranca e interface
> web ainda podem receber ajustes.

## Interface web

O painel web permite controlar o bot pelo navegador:

- escolher o servidor ativo;
- adicionar musicas por nome ou link;
- controlar fila, volume, pausa, resume e skip;
- gerenciar radios customizadas;
- enviar playlists `.txt`;
- enviar e tocar efeitos de soundboard;
- configurar o token do Discord pela tela de setup;
- usar um player compacto em barra fixa, independente do scroll da pagina.

<img width="2940" height="1912" alt="Interface web do bot" src="https://github.com/user-attachments/assets/609bf028-6e9c-4921-82d7-18bcecb99adc" />

## Principais recursos

- Reproducao de musicas via YouTube, SoundCloud e busca por nome.
- Suporte a playlists e URLs de playlist.
- Radios online com cadastro pela interface web.
- Soundboard com upload, favoritos, volume por efeito e pre-escuta no navegador.
- Painel web protegido por senha admin.
- Setup inicial pelo navegador para salvar o token do Discord.
- API FastAPI usada pelo painel.
- Suporte multi-servidor no painel.
- Docker com volume persistente em `data/`.

## Tecnologias

- Python 3
- discord.py
- FastAPI
- Uvicorn
- yt-dlp
- FFmpeg
- Deno
- Pillow
- Docker e Docker Compose

## Estrutura do projeto

```text
bot_discord/
|-- api/                  # Rotas FastAPI usadas pelo painel web
|-- cogs/                 # Comandos e cogs do Discord
|-- data/                 # Dados persistentes locais, ignorados pelo Git
|-- playlist/             # Utilitarios de playlist
|-- services/             # Regras de playback e dominio
|-- static/               # Interface web
|-- utils/                # Helpers, i18n, imagens e player modules
|-- bot.py                # Entrada principal: bot Discord + API web
|-- config.py             # Configuracoes, paths, token, auth e API key
|-- docker-compose.yml
|-- Dockerfile
`-- .env.example
```

## Configuracao por `.env`

Copie o exemplo e ajuste localmente:

```bash
cp .env.example .env
```

Exemplo recomendado para Docker:

```env
# Obrigatorio em Docker/headless para conseguir fazer login no painel.
WEB_ADMIN_PASSWORD=troque-por-uma-senha-forte

# Opcional. Pode ficar vazio se voce quiser configurar pela interface web.
DISCORD_TOKEN=

# Opcional. Usado no build para alinhar usuario/grupo do container.
UID=1000
GID=1000
```

Recomendacoes:

- Nunca comite `.env`.
- Em Docker/headless, configure `WEB_ADMIN_PASSWORD`.
- `DISCORD_TOKEN` pode ficar vazio para ser configurado pela tela `/setup`.
- Quando o token e salvo pela interface web, ele fica em `data/token.json`.
- `data/` e persistente e ignorado pelo Git, pois pode conter token, hash de
  senha, API key, playlists, radios e soundboard.

### Posso rodar sem token no `.env`?

Sim. Esse e o fluxo recomendado quando voce quer configurar tudo pela interface:

1. Defina apenas `WEB_ADMIN_PASSWORD` no `.env`.
2. Suba o container.
3. Acesse `http://IP_DO_SERVIDOR:8000`.
4. Faca login com a senha do painel.
5. Informe o token do Discord na tela `/setup`.

O bot inicia a API mesmo sem token. Nesse estado, o painel abre o setup e o bot
fica offline ate receber um token valido.

## Primeiro acesso

Ao abrir `http://localhost:8000` ou `http://IP_DO_SERVIDOR:8000`, o backend
segue este fluxo:

1. Se o usuario nao estiver autenticado, redireciona para `/login`.
2. Depois do login, se ainda nao existir token valido, redireciona para `/setup`.
3. Na tela `/setup`, informe o token do Discord.
4. O token e salvo em `data/token.json` e o bot tenta iniciar.
5. Com senha e token configurados, `/` abre o dashboard principal.

## Opcoes de terminal

O projeto mantem prompts de terminal apenas para execucao local interativa. No
Docker/headless, os prompts sao pulados automaticamente porque o container nao
tem stdin interativo.

### Senha admin do painel

Se nao existir `WEB_ADMIN_PASSWORD` no `.env` e nao existir `data/auth.json`, o
`bot.py` so pergunta a senha quando o processo estiver em um terminal
interativo:

```text
Definir senha agora? (s/N):
Senha do painel (min. 8 caracteres):
Confirme a senha:
```

Se voce responder `s`, a senha e salva como hash em `data/auth.json`.

Em Docker, use o `.env`:

```env
WEB_ADMIN_PASSWORD=sua-senha-forte
```

### Token do Discord

Se nao existir token em `data/token.json`, `token.json` legado ou
`DISCORD_TOKEN`, o terminal interativo mostra:

```text
Inserir token agora? (s/N):
Cole o token do Discord:
```

- Respondendo `s`, o token e solicitado sem eco no terminal e salvo em
  `data/token.json`.
- Respondendo `N` ou deixando vazio, a API sobe e voce configura pela interface
  web.
- Em Docker/headless, essa pergunta nao aparece; use `DISCORD_TOKEN` no `.env`
  ou a tela `/setup`.

## Instalacao com Docker

### 1. Clonar o repositorio

```bash
git clone https://github.com/saulomiller/bot_discord.git
cd bot_discord
```

### 2. Criar o `.env`

```bash
cp .env.example .env
nano .env
```

Para configurar o token pela interface web, deixe:

```env
WEB_ADMIN_PASSWORD=sua-senha-forte
DISCORD_TOKEN=
```

### 3. Subir o bot

```bash
docker compose up -d --build
```

### 4. Acompanhar logs

```bash
docker compose logs -f bot
```

### 5. Abrir a interface web

Local:

```text
http://localhost:8000
```

Homelab/rede local:

```text
http://IP_DO_SERVIDOR:8000
```

Exemplo:

```text
http://192.168.15.7:8000
```

## Instalacao local/interativa

Para desenvolvimento fora do Docker, crie um ambiente Python e instale as
dependencias:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

Nesse modo, se o terminal for interativo, o `bot.py` pode perguntar a senha
admin e o token.

## Resetar para uma instalacao nova

Use com cuidado: isso remove configuracoes locais persistidas.

```bash
docker compose down
rm -rf data
mkdir -p data
docker compose up -d --build
```

Isso apaga token salvo, API key local, senha hash do painel, playlists,
soundboard, radios customizadas e metadados locais. Se voce usa `.env`, ele
continua existindo e sera reutilizado no proximo start.

Para remover tambem a imagem local criada pelo projeto:

```bash
docker compose down --rmi local --remove-orphans
```

## Comandos do Discord

### Slash commands

| Comando | Descricao |
| --- | --- |
| `/play <link ou nome>` | Adiciona musica ou playlist a fila |
| `/skip` | Pula para a proxima musica |
| `/stop` | Para a reproducao e limpa a fila |
| `/pause` | Pausa a reproducao |
| `/resume` | Retoma a reproducao |
| `/agora` | Mostra a musica atual |
| `/nowplaying` | Mostra a musica atual com progresso |
| `/fila` | Mostra a fila |
| `/volume <valor>` | Ajusta o volume |
| `/join` | Entra no canal de voz |
| `/leave` | Sai do canal de voz |
| `/removeplaylist` | Remove musicas de playlist da fila |
| `/radios` | Lista radios disponiveis |
| `/radio <id>` | Toca uma radio |
| `/addradio` | Adiciona radio customizada, exige admin |
| `/removeradio` | Remove radio customizada, exige admin |
| `/sfx <nome>` | Toca um efeito do soundboard |

### Prefix commands

O bot tambem mantem comandos por prefixo `!` para compatibilidade:

```text
!play
!skip
!stop
!pause
!resume
!agora
!fila
!volume
!join
!leave
!removeplaylist
!radios
!radio
!clear
!clearforce
!sair_todos
```

## Soundboard

O bot precisa estar conectado a um canal de voz. Ao tocar um efeito com
`/sfx <nome>`, ele pausa a musica atual, reproduz o efeito e retoma a musica em
seguida.

Os arquivos aceitos ficam em `data/soundboard/` e podem ser enviados pela
interface web. Extensoes aceitas:

```text
.mp3, .wav, .ogg, .m4a, .webm
```

## Seguranca

- O painel exige senha admin.
- A senha pode vir de `WEB_ADMIN_PASSWORD` ou de `data/auth.json`.
- A sessao admin usa cookie HTTP-only.
- A API usa API key interna gerada em `data/api_key.json`.
- Rotas sensiveis exigem sessao admin e API key.
- Arquivos de upload passam por validacao de nome, extensao e tamanho.
- O token digitado no terminal interativo nao e ecoado na tela.
- Nao exponha a porta `8000` diretamente na internet sem proxy, HTTPS e
  controles adicionais.

### Radios customizadas e URLs externas

Radios customizadas aceitam URLs `http` e `https`. Como essas URLs podem ser
resolvidas e acessadas pelo backend na hora de tocar, cadastre apenas fontes
confiaveis.

Para homelab fechado, login + API key ja reduzem bastante o risco. Se o painel
for exposto fora da rede confiavel, a recomendacao e adicionar hardening extra:

- bloquear `localhost`, IPs privados e IPs link-local por padrao;
- resolver DNS antes de salvar/tocar a radio;
- permitir excecoes explicitas por allowlist no `.env`.

## Arquivos persistentes importantes

| Caminho | Funcao |
| --- | --- |
| `.env` | Senha admin e variaveis locais, nao versionar |
| `data/token.json` | Token do Discord salvo pela web ou terminal |
| `data/auth.json` | Hash da senha admin quando criada pelo terminal |
| `data/api_key.json` | API key local gerada automaticamente |
| `data/soundboard/` | Efeitos enviados pelo painel |
| `data/playlist/` | Playlists e dados locais |
| `data/radios.json` | Radios customizadas |
| `token.json` | Caminho legado ainda lido para compatibilidade |

## Qualidade de codigo

- O codigo Python deve seguir PEP 8.
- Docstrings seguem a intencao da PEP 257.
- Antes de preparar merge, rode verificacoes de sintaxe/lint quando possivel.

Exemplos:

```bash
python -m py_compile bot.py config.py utils/helpers.py
python -m ruff check .
python -m ruff format --check .
```

## Licenca

MIT
