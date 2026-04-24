# bot_discord

Bot de musicas para Discord com soundboard, radios online, playlists e painel web
de gerenciamento. O projeto foi pensado para rodar em homelab via Docker, mas
tambem pode ser executado localmente para desenvolvimento.

> Projeto em desenvolvimento ativo. Algumas telas e fluxos ainda podem receber
> ajustes de layout, seguranca e experiencia de instalacao.

## Interface Web

O painel web permite controlar o bot pelo navegador, configurar o token do
Discord, escolher o servidor ativo, gerenciar fila, radios, playlists e
soundboard.

<<<<<<< Updated upstream
<img width="2560" height="1333" alt="image" src="https://github.com/user-attachments/assets/51780682-bd9c-4969-9b36-143e1f64be34" />

<img width="2560" height="1325" alt="{3D7AAACA-BF3D-45FD-9C73-02878186FFA3}" src="https://github.com/user-attachments/assets/7305b4e0-834e-4d7c-9877-8a48673700f7" />

=======
<img width="2940" height="1912" alt="Interface web do bot" src="https://github.com/user-attachments/assets/609bf028-6e9c-4921-82d7-18bcecb99adc" />
>>>>>>> Stashed changes

## Principais recursos

- Reproducao de musicas via YouTube, SoundCloud e buscas por nome.
- Suporte a radios online.
- Soundboard com upload, favoritos, volume por efeito e reproducao via painel.
- Interface web protegida por senha admin.
- Setup inicial pelo navegador para adicionar o token do Discord.
- Player web compacto em formato de barra fixa.
- Fila de musicas com skip, pausa, resume, volume e remocao de playlists.
- Upload de playlists `.txt` pela interface web.
- Suporte multi-servidor no painel.
- API FastAPI para controle do bot.
- Execucao em Docker com volume persistente em `data/`.

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

## Estrutura

```text
bot_discord/
|-- api/                  # Rotas FastAPI usadas pelo painel web
|-- cogs/                 # Comandos e cogs do Discord
|-- data/                 # Dados persistentes locais, ignorados pelo Git
|-- playlist/             # Utilitarios de playlist
|-- services/             # Servicos de playback e regras auxiliares
|-- static/               # Interface web
|-- utils/                # Helpers, embeds, i18n e player modules
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
- Em Docker, configure pelo menos `WEB_ADMIN_PASSWORD`.
- `DISCORD_TOKEN` pode ser definido no `.env`, pelo terminal interativo ou pela tela `/setup`.
- Quando o token e salvo pela interface web, ele fica em `data/token.json`.
- `data/` e persistente e ignorado pelo Git, pois pode conter token, senha hash, API key, playlists e soundboard.

## Primeiro acesso

Ao abrir `http://localhost:8000` ou `http://IP_DO_SERVIDOR:8000`, o backend segue este fluxo:

1. Se o usuario nao estiver autenticado, redireciona para `/login`.
2. Depois do login, se ainda nao existir token valido, redireciona para `/setup`.
3. Na tela `/setup`, informe o token do Discord.
4. O token e validado, salvo em `data/token.json` e o bot tenta iniciar.
5. Com senha e token configurados, `/` abre o dashboard principal.

## Opcoes de terminal

O projeto mantem prompts de terminal apenas para execucao local interativa. No
Docker/headless, esses prompts sao pulados automaticamente porque o container nao
recebe stdin.

### Senha admin do painel

Se nao existir `WEB_ADMIN_PASSWORD` no `.env` e nao existir `data/auth.json`, o
`bot.py` so pergunta a senha quando o processo estiver em um terminal interativo:

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
`DISCORD_TOKEN`, o terminal interativo mostra apenas:

```text
Inserir token agora? (s/N):
```

- Respondendo `s`, o token e solicitado e salvo em `data/token.json`.
- Respondendo `N` ou deixando vazio, a API sobe e voce configura pela interface web.
- Em Docker/headless, essa pergunta nao aparece; use `DISCORD_TOKEN` no `.env` ou a tela `/setup`.

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

No Docker, mantenha pelo menos:

```env
WEB_ADMIN_PASSWORD=sua-senha-forte
```

Se quiser configurar o token depois pela interface web, deixe:

```env
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

Nesse modo, se o terminal for interativo, o `bot.py` pode perguntar a senha admin
e o token conforme descrito acima.

## Resetar para uma instalacao nova

Use com cuidado: isso remove configuracoes locais persistidas.

```bash
docker compose down
rm -rf data
mkdir -p data
docker compose up -d --build
```

Isso apaga token salvo, API key local, senha hash do painel, playlists,
soundboard e metadados locais. Se voce usa `.env`, ele continua existindo e sera
reutilizado no proximo start.

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
- Nao exponha a porta `8000` diretamente na internet sem proxy, HTTPS e controles adicionais.

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
