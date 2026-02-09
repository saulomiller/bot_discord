from fastapi import APIRouter, Request, HTTPException, Body
from pydantic import BaseModel
import logging
import asyncio
import os
import json
from config import DATA_DIR, TOKEN_FILE, PLAYLIST_DIR, save_token_to_json, load_token_from_json

router = APIRouter()

# --- Modelos Pydantic ---
class MusicRequest(BaseModel):
    search: str

class PlaylistRequest(BaseModel):
    filename: str

class VolumeRequest(BaseModel):
    level: float

class RadioRequest(BaseModel):
    name: str
    url: str
    location: str = "Desconhecido"
    description: str = "Rádio personalizada"

class RadioRemoveRequest(BaseModel):
    radio_id: str

class RadioPlayRequest(BaseModel):
    radio_id: str

class SoundboardPlayRequest(BaseModel):
    guild_id: int
    sfx_id: str

class SoundboardFavoriteRequest(BaseModel):
    sfx_id: str
    favorite: bool

class SoundboardVolumeRequest(BaseModel):
    sfx_id: str
    volume: float

# --- Rotas ---

@router.get("/api/status")
async def get_status(request: Request):
    """Retorna o status atual do bot."""
    bot = request.app.state.bot
    
    # Tentar obter o player ativo
    player = None
    if bot.voice_clients:
        vc = bot.voice_clients[0]
        if vc.guild.id in bot.players:
            player = bot.players[vc.guild.id]
    
    # Valores padrão
    stat_current_song = None
    stat_queue = []
    stat_volume = 0.5
    stat_paused = False
    stat_loop = False
    stat_shuffle = False
    
    # Se houver player ativo, usar seus dados
    if player:
        stat_current_song = player.current_song
        stat_queue = player.queue
        stat_volume = player.volume
        stat_paused = player.is_paused
        stat_loop = player.is_looping
        stat_shuffle = player.is_shuffling

    # Processar current_song
    current_song_info = None
    if stat_current_song:
        try:
            if isinstance(stat_current_song, dict):
                current_song_info = {
                    "title": stat_current_song.get('title', 'Desconhecido'),
                    "thumbnail": stat_current_song.get('thumbnail', ''),
                    "user": str(stat_current_song.get('user', 'Desconhecido')),
                    "duration": stat_current_song.get('duration', 'Desconhecida'),
                    "channel": stat_current_song.get('channel', 'Desconhecido')
                }
                u = stat_current_song.get('user')
                if hasattr(u, 'display_name'):
                    current_song_info['user'] = u.display_name
        except Exception as e:
            logging.error(f"Erro ao processar current_song: {e}")
            current_song_info = {"title": "Erro ao ler música"}

    # Processar fila
    queue_info = []
    display_queue = list(stat_queue)[:10]
    
    for song in display_queue:
        try:
            if isinstance(song, dict):
                u = song.get('user')
                user_name = u.display_name if hasattr(u, 'display_name') else str(u)
                queue_info.append({
                    "title": song.get('title', 'Desconhecido'),
                    "user": user_name,
                    "duration": song.get('duration', '?')
                })
        except Exception:
            queue_info.append({"title": "Erro na fila"})

    return {
        "bot_user": str(bot.user),
        "is_ready": bot.is_ready(),
        "guilds": len(bot.guilds),
        "guild_id": bot.voice_clients[0].guild.id if bot.voice_clients else None,
        "current_song": current_song_info,
        "queue": queue_info,
        "volume": stat_volume,
        "is_looping": stat_loop,
        "is_shuffling": stat_shuffle,
        "is_paused": stat_paused,
        "voice_connections": len(bot.voice_clients),
        "progress": player.get_progress() if player else {"current": 0, "duration": 0, "percent": 0}
    }

@router.get("/queue")
async def get_queue(request: Request):
    """Retorna a fila de músicas atual."""
    bot = request.app.state.bot
    if bot.voice_clients:
        vc = bot.voice_clients[0]
        if vc.guild.id in bot.players:
            player = bot.players[vc.guild.id]
            return {"queue": list(player.queue)}
    return {"queue": []}

@router.post("/api/play")
async def api_play(request: Request, body: MusicRequest):
    """Adiciona uma música à fila e inicia a reprodução."""
    bot = request.app.state.bot
    logging.info(f"🔥 [API/PLAY] ENDPOINT CHAMADO! Request: {body.search}")
    
    if not bot.voice_clients:
        raise HTTPException(status_code=400, detail="Bot não está em um canal de voz.")
    
    vc = bot.voice_clients[0]
    
    # Importar MusicPlayer localmente ou garantir que music cog carregou
    if vc.guild.id not in bot.players:
         # Precisamos garantir que o player existe.
         # Como o bot.players é populado pelos Cogs, e aqui estamos na API...
         # Se o Cog de música não criou, criamos aqui?
         # Melhor acessar o Cog se possível.
         music_cog = bot.get_cog('MusicCog')
         if music_cog:
             player = music_cog.get_player(vc.guild.id)
         else:
             raise HTTPException(status_code=500, detail="MusicCog não carregado.")
    else:
        player = bot.players[vc.guild.id]

    try:
        api_user = bot.user 
        search = body.search
        is_playlist = False
        
        if search.startswith(('http://', 'https://')):
            playlist_indicators = ['/playlist', '/sets/', 'list=', '/album/']
            for indicator in playlist_indicators:
                if indicator in search:
                    is_playlist = True
                    break
        
        if is_playlist:
            logging.info(f"🎵 PLAYLIST DETECTADA! Usando processamento assíncrono: {search}")
            song = await player.add_playlist_async(search, api_user)
            return {
                "status": "success", 
                "message": f"Playlist adicionada! Tocando: '{song['title']}'. Processando resto em segundo plano...",
                "is_playlist": True
            }
        else:
            logging.info(f"Processando como música única: {search}")
            song = await player.add_to_queue(search, api_user)
            
            if not vc.is_playing() and not player.is_paused:
                await player.play_next()
            
            return {
                "status": "success", 
                "message": f"'{song['title']}' adicionado à fila.",
                "is_playlist": False
            }
            
    except Exception as e:
        logging.error(f"API /play error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/skip")
async def api_skip(request: Request):
    """Pula a música atual."""
    bot = request.app.state.bot
    if not bot.voice_clients:
        raise HTTPException(status_code=400, detail="Bot não está em um canal de voz.")
    
    vc = bot.voice_clients[0]
    if vc.guild.id in bot.players:
        player = bot.players[vc.guild.id]
        player.skip()
    return {"status": "success", "message": "Música pulada."}

@router.post("/api/pause")
async def api_pause(request: Request):
    """Pausa a música atual."""
    bot = request.app.state.bot
    if not bot.voice_clients:
        raise HTTPException(status_code=400, detail="Bot não está em um canal de voz.")
    
    vc = bot.voice_clients[0]
    if vc.guild.id in bot.players:
        player = bot.players[vc.guild.id]
        player.pause()
    return {"status": "success", "message": "Música pausada."}

@router.post("/api/resume")
async def api_resume(request: Request):
    """Retoma a música pausada."""
    bot = request.app.state.bot
    if not bot.voice_clients:
        raise HTTPException(status_code=400, detail="Bot não está em um canal de voz.")
    
    vc = bot.voice_clients[0]
    if vc.guild.id in bot.players:
        player = bot.players[vc.guild.id]
        player.resume()
    return {"status": "success", "message": "Música retomada."}

@router.post("/api/volume")
async def api_volume(request: Request, body: VolumeRequest):
    """Ajusta o volume do bot."""
    bot = request.app.state.bot
    if body.level < 0 or body.level > 1:
        raise HTTPException(status_code=400, detail="O volume deve estar entre 0.0 e 1.0")
        
    count = 0
    for vc in bot.voice_clients:
        if vc.guild.id in bot.players:
            player = bot.players[vc.guild.id]
            player.set_volume(body.level)
            count += 1
        
    return {"status": "success", "message": f"Volume ajustado para {int(body.level*100)}%"}

@router.post("/api/set_token")
async def set_token(request: Request, body: dict = Body(...)):
    """Define o token do Discord (USO RESTRITO E INSEGURO)."""
    bot = request.app.state.bot
    token = body.get("token")
    if not token or len(token) < 50:
        raise HTTPException(status_code=400, detail="Token não fornecido.")
    
    try:
        save_token_to_json(token)
        os.environ['DISCORD_TOKEN'] = token
        logging.info("Token do Discord foi salvo/atualizado via API.")

        if bot.is_ready():
            logging.info("Bot já está online. Tentando reiniciar com o novo token...")
            await bot.close()
            await asyncio.sleep(1)
            
        # Nota: Reiniciar o bot completamente a partir daqui é complexo
        # pois o loop principal está em bot.py.
        # Mas podemos fechar o bot atual e torcer pra que o script superior reinicie,
        # ou tentar reinicializar o bot aqui se tivermos acesso à função main/setup.
        # Por enquanto vamos apenas salvar e fechar.
        
        return {"status": "success", "message": "Token atualizado. Reinicie o bot manualmente se ele não voltar."}

    except Exception as e:
        logging.error(f"Erro ao salvar token via API: {e}")
        raise HTTPException(status_code=500, detail="Falha ao salvar o token.")

@router.post("/api/restart")
async def restart_bot(request: Request):
    """Reinicia o bot."""
    bot = request.app.state.bot
    try:
        logging.info("Reiniciando bot via API...")
        if bot.is_ready() or not bot.is_closed():
            await bot.close()
        return {"status": "success", "message": "Bot reiniciando..."}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Falha ao reiniciar o bot.")

@router.post("/api/shutdown")
async def shutdown_bot(request: Request):
    """Desliga o bot."""
    bot = request.app.state.bot
    try:
        logging.info("Desligando bot via API...")
        await bot.close()
        return {"status": "success", "message": "Bot desligado."}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Falha ao desligar o bot.")

@router.post("/api/upload_playlist")
async def upload_playlist(file: bytes = Body(...), filename: str = Body(...)):
    """Faz upload de um arquivo de playlist .txt"""
    try:
        if not filename.endswith('.txt'):
            raise HTTPException(status_code=400, detail="Apenas arquivos .txt são permitidos.")
        
        if not os.path.exists(PLAYLIST_DIR):
            os.makedirs(PLAYLIST_DIR)
        
        file_path = os.path.join(PLAYLIST_DIR, filename)
        content = file.decode('utf-8')
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logging.info(f"Playlist '{filename}' salva com sucesso via API")
        return {"status": "success", "message": f"Playlist '{filename}' salva com sucesso."}
    except Exception as e:
        logging.error(f"Erro no upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))
