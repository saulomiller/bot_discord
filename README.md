# 🎵 bot_discord
Bot de músicas para Discord com soundboard e interface web de gerenciamento,
rodando em homelab pessoal via Docker. Desenvolvido para fins de estudo e aprendizado.

> Documentação em andamento...
> ## 🚧 Status do projeto & Problemas conhecidos

O projeto está em desenvolvimento ativo. Algumas funcionalidades podem apresentar
instabilidades ou estar incompletas.

**Problemas conhecidos:**
- Controle do soundboard pela GUI ainda não implementado

**Em desenvolvimento:**
- melhora do soundboard
- gerenciamento muti-chat
- Mensagens automáticas
- opção em ingles
- melhoria na seguranca do token .env
- possibilidade de desativar funções 
## 🖥️ Interface Web

<img width="2940" height="1912" alt="image" src="https://github.com/user-attachments/assets/609bf028-6e9c-4921-82d7-18bcecb99adc" />


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

Os áudios do soundboard podem ser adicionados e gerenciados pela interface web (GUI).

> ⚠️ O controle do soundboard pela GUI ainda está em desenvolvimento. Por enquanto, o gerenciamento de sfx via chat do Discord funciona normalmente.

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

**Opção A — Via CLI:** edite o arquivo `token.json` na raiz do projeto:
```json
{
  "token": "SEU_TOKEN_AQUI"
}
```

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
