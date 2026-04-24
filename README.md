# 🎵 bot_discord
Bot de músicas para Discord com soundboard e interface web de gerenciamento,
rodando em homelab pessoal via Docker. Desenvolvido para fins de estudo e aprendizado.

> Documentação em andamento...
> ## 🚧 Status do projeto & Problemas conhecidos

O projeto está em desenvolvimento ativo. Algumas funcionalidades podem apresentar
instabilidades ou estar incompletas.

**Problemas conhecidos:**
- Projeto em evolucao; a interface web ainda recebe melhorias de layout e estados offline.

**Em desenvolvimento:**
- melhora do soundboard
- gerenciamento muti-chat
- Mensagens automáticas
- opção em ingles
- melhoria na seguranca do token .env
- possibilidade de desativar funções 
## 🖥️ Interface Web

<img width="2560" height="1333" alt="image" src="https://github.com/user-attachments/assets/51780682-bd9c-4969-9b36-143e1f64be34" />

<img width="2560" height="1325" alt="{3D7AAACA-BF3D-45FD-9C73-02878186FFA3}" src="https://github.com/user-attachments/assets/7305b4e0-834e-4d7c-9877-8a48673700f7" />



## 🛠️ Tecnologias utilizadas

- **Python 3** — linguagem principal
- **discord.py** — comandos assíncronos (async/await)
- **FastAPI** — API e interface web de gerenciamento
- **Uvicorn** — servidor ASGI
- **yt-dlp** — extração e reprodução de áudio (YouTube, SoundCloud e rádios online)
- **FFmpeg** — processamento de áudio
- **Pillow (PIL)** — geração dinâmica de embeds com capa do álbum e barra de progresso
- **Deno** — resolução de desafios JS do YouTube
- **Docker / Docker Compose** — containerização e deploy

## 📁 Estrutura do projeto
```
bot_discord/
├── api/          # Rotas e endpoints da interface web (FastAPI)
├── cogs/         # Módulos de comandos do bot (discord.py)
├── playlist/     # Gerenciamento de playlists
├── services/     # Serviços auxiliares
├── static/       # Arquivos estáticos da interface web
├── utils/        # Utilitários gerais
├── bot.py        # Ponto de entrada do bot
├── config.py     # Configurações gerais
├── Dockerfile
└── docker-compose.yml
```

## 📌 Funcionalidades

- Reprodução de músicas via YouTube e SoundCloud no Discord
- Suporte a rádios online
- Soundboard integrado via comandos no Discord
- Interface web (GUI) para controle e gerenciamento do bot em tempo real
- Fila de músicas com controle de skip e navegação
- Gerenciamento de playlists via GUI — upload de arquivos `.txt` com lista de músicas
- Embed dinâmico com capa do álbum e barra de progresso em tempo real (gerado com Pillow)
- Cache de imagens para evitar reprocessamento desnecessário
- Limpeza automática do chat ao término da música
- Execução em container Docker com usuário não-root (segurança)
- Deploy contínuo em homelab pessoal

## 💬 Experiência no chat

- **Mensagens efêmeras** — ao adicionar uma música, apenas o usuário que solicitou recebe a confirmação, mantendo o chat limpo
- **Limpeza automática** — ao término da música, o bot remove as mensagens relacionadas do canal automaticamente

## 🎵 Como funciona o Soundboard

O bot precisa estar em um canal de voz. Ao usar o comando `/sfx <nome>`, o bot:

1. Pausa a música que estiver tocando (se houver)
2. Reproduz o efeito de áudio solicitado
3. Retoma a música automaticamente em seguida

Os áudios do soundboard podem ser adicionados, testados, favoritados,
removidos e tocados no Discord pela interface web (GUI).

## 🤖 Comandos disponíveis

### Comandos de usuário (/)

| Comando | Descrição |
|---|---|
| `/play <link ou nome>` | Toca uma música do YouTube ou SoundCloud |
| `/radio <nome>` | Toca uma rádio específica |
| `/radios` | Lista as rádios disponíveis |
| `/skip` | Pula para a próxima música |
| `/sfx <nome>` | Toca um efeito sonoro do soundboard |
| `/leave` | Faz o bot sair do canal de voz |

### Comandos administrativos (!)

> Exclusivos para administradores do servidor.

## ✅ Qualidade de código

- **PEP 8** — estilo e formatação do código Python
- **PEP 257** — padronização de docstrings
- **Pytest** — testes de complexidade e comportamento
- **W3C Validator** — validação de semântica HTML na interface web

## 🤖 Desenvolvimento assistido por IA

Este projeto contou com o auxílio de ferramentas de IA (Claude e ChatGPT)
para resolução de problemas, revisão de código e aceleração do aprendizado.

## 🚀 Como executar

### 1. Clone o repositório
```bash
git clone https://github.com/saulomiller/bot_discord.git
cd bot_discord
```

### 2. Configure o token do Discord

**Opção A — Via CLI:** edite o arquivo `data/token.json`:
```json
{
  "DISCORD_TOKEN": "SEU_TOKEN_AQUI"
}
```

O bot ainda aceita o `token.json` antigo na raiz do projeto como fallback,
mas o caminho recomendado e persistido pela interface web é `data/token.json`.

**Opção B — Via interface web:** após subir o container, acesse a GUI pelo navegador e adicione o token diretamente pelo painel de configurações.

### 3. Build e execução
```bash
docker compose up -d --build
```

### 4. Verificar logs
```bash
# Logs em tempo real
docker compose logs -f

# Logs apenas do bot
docker compose logs -f bot
```

### 5. Parar o bot
```bash
docker compose down
```

## 📄 Licença

MIT
