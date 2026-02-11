from fastapi import APIRouter, Request, HTTPException, Body
from pydantic import BaseModel
import logging
import asyncio
import os
import json
from config import DATA_DIR, TOKEN_FILE, PLAYLIST_DIR, SOUNDBOARD_DIR, SOUNDBOARD_METADATA_FILE, save_token_to_json, load_token_from_json
from utils.helpers import load_soundboard_metadata, save_soundboard_metadata, get_sfx_metadata, update_sfx_metadata
from utils.i18n import I18n, t


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

class LanguageRequest(BaseModel):
    language: str

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
        "progress": player.get_progress() if player else {"current": 0, "duration": 0, "percent": 0},
        "language": I18n.get_instance().language
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


@router.post("/api/removeplaylist")
async def api_remove_playlist(request: Request):
    """Remove da fila todas as músicas que foram adicionadas via playlist (channel == 'Playlist').
    
    Também pula a música ATUAL se ela fizer parte de uma playlist.
    """
    bot = request.app.state.bot

    # Se não houver players carregados, nada a fazer
    if not getattr(bot, 'players', None):
        return {"status": "success", "message": "Nenhum player encontrado."}

    total_removed = 0
    any_player = False
    skipped_current = False

    # Iterar por todos os players conhecidos e remover itens marcados como 'Playlist'
    for gid, player in list(bot.players.items()):
        any_player = True
        retained = []
        removed = 0
        
        # 1. Verificar música ATUAL
        if player.current_song and player.current_song.get('channel') == 'Playlist':
            logging.info(f"Skipping current song from playlist: {player.current_song.get('title')}")
            player.skip()
            skipped_current = True

        # 2. Filtrar a FILA
        for song in list(player.queue):
            try:
                # Verificar channel ou flag is_lazy (que geralmente indica playlist grande)
                if (isinstance(song, dict) and 
                   (song.get('channel') == 'Playlist' or song.get('is_lazy', False))):
                    removed += 1
                else:
                    retained.append(song)
            except Exception:
                retained.append(song)

        if removed > 0:
            total_removed += removed
            player.queue.clear()
            for s in retained:
                player.queue.append(s)
            logging.info(f"Removed {removed} songs from queue (Playlist cleanup)")

    if not any_player:
        return {"status": "success", "message": "Nenhum player encontrado."}
    
    msg = []
    if skipped_current:
        msg.append("Pulei a música atual (Era playlist).")
    if total_removed > 0:
        msg.append(f"Removidas {total_removed} músicas da fila.")
    
    if not msg:
        return {"status": "success", "message": "Nenhuma música de playlist encontrada para remover."}

    return {"status": "success", "message": " ".join(msg)}

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

@router.get("/api/settings/language")
async def get_language():
    """Retorna o idioma atual do bot."""
    return {"language": I18n.get_instance().language}

@router.post("/api/settings/language")
async def set_language(request: LanguageRequest):
    """Define o idioma do bot."""
    if request.language not in ['pt', 'en']:
        raise HTTPException(status_code=400, detail="Idioma não suportado.")
    
    success = I18n.get_instance().save_language(request.language)
    if success:
        return {"status": "success", "message": f"Idioma alterado para {request.language}"}
    else:
        raise HTTPException(status_code=500, detail="Erro ao salvar idioma.")

@router.post("/api/shutdown")
async def shutdown(request: Request):
    """Desliga o bot."""
    bot = request.app.state.bot
    asyncio.create_task(bot.close())
    return {"status": "success", "message": "Bot desligando..."}

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

# --- Rotas de Soundboard ---

@router.get("/api/soundboard")
async def get_soundboard():
    """Retorna a lista de efeitos sonoros disponíveis."""
    try:
        if not os.path.exists(SOUNDBOARD_DIR):
            os.makedirs(SOUNDBOARD_DIR)
            
        files = [f for f in os.listdir(SOUNDBOARD_DIR) if f.endswith(('.mp3', '.wav', '.ogg', '.m4a'))]
        metadata = load_soundboard_metadata()
        soundboard_list = []
        
        for filename in files:
            sfx_id = os.path.splitext(filename)[0]
            meta = get_sfx_metadata(sfx_id) # Usa helper que já busca no metadata carregado
            
            soundboard_list.append({
                "id": sfx_id,
                "name": sfx_id.replace("_", " ").title(),
                "filename": filename,
                "favorite": meta.get("favorite", False),
                "volume": meta.get("volume", 1.0)
            })
            
        # Ordenar: Favoritos primeiro, depois alfabético
        soundboard_list.sort(key=lambda x: (not x['favorite'], x['name']))
        
        return {"soundboard": soundboard_list}
    except Exception as e:
        logging.error(f"Erro ao listar soundboard: {e}")
        raise HTTPException(status_code=500, detail="Erro ao listar soundboard.")

@router.post("/api/soundboard/play")
async def play_soundboard(request: Request, body: SoundboardPlayRequest):
    """Toca um efeito sonoro no servidor especificado."""
    bot = request.app.state.bot
    
    # Encontrar o cliente de voz correto
    voice_client = None
    for vc in bot.voice_clients:
        if vc.guild.id == body.guild_id:
            voice_client = vc
            break
            
    if not voice_client:
        raise HTTPException(status_code=400, detail="Bot não está conectado ao canal de voz neste servidor.")

    # Obter MusicPlayer
    music_cog = bot.get_cog('MusicCog')
    if not music_cog:
        raise HTTPException(status_code=500, detail="Erro interno: MusicCog não encontrado.")
        
    player = music_cog.get_player(body.guild_id)
    if not player:
        raise HTTPException(status_code=500, detail="Erro interno: Player não inicializado.")

    # Verificar arquivo
    sfx_path = None
    for ext in ['.mp3', '.wav', '.ogg', '.m4a']:
        path = os.path.join(SOUNDBOARD_DIR, f"{body.sfx_id}{ext}")
        if os.path.exists(path):
            sfx_path = path
            break
            
    if not sfx_path:
        raise HTTPException(status_code=404, detail="Efeito sonoro não encontrado.")

    # Tocar
    try:
        meta = get_sfx_metadata(body.sfx_id)
        volume = meta.get("volume", 1.0)
        
        # Usar o método play_soundboard do player (que já tem a lógica de pause/resume)
        await player.play_soundboard(sfx_path, volume)
        
        return {"status": "success", "message": f"Tocando {body.sfx_id}"}
    except Exception as e:
        logging.error(f"Erro ao tocar SFX: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao tocar efeito: {str(e)}")



# Redefinindo rota de upload corretamente para usar UploadFile
from fastapi import UploadFile, File

@router.post("/api/soundboard/upload")
async def upload_soundboard_file(file: UploadFile = File(...)):
    """Upload de arquivo para o soundboard."""
    try:
        if not os.path.exists(SOUNDBOARD_DIR):
            os.makedirs(SOUNDBOARD_DIR)
            
        if not file.filename.endswith(('.mp3', '.wav', '.ogg', '.m4a')):
             raise HTTPException(status_code=400, detail="Formato não suportado.")
             
        file_path = os.path.join(SOUNDBOARD_DIR, file.filename)
        
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
            
        # Adicionar metadata inicial
        sfx_id = os.path.splitext(file.filename)[0]
        update_sfx_metadata(sfx_id, {"favorite": False, "volume": 1.0})
        
        return {"status": "success", "message": "Upload concluído."}
    except Exception as e:
        logging.error(f"Erro no upload SFX: {e}")
        raise HTTPException(status_code=500, detail=f"Erro no upload: {str(e)}")

@router.delete("/api/soundboard/{sfx_id}")
async def delete_soundboard(sfx_id: str):
    """Deleta um efeito sonoro."""
    try:
        deleted = False
        for ext in ['.mp3', '.wav', '.ogg', '.m4a']:
            path = os.path.join(SOUNDBOARD_DIR, f"{sfx_id}{ext}")
            if os.path.exists(path):
                os.remove(path)
                deleted = True
                break
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
            
        # Remover metadata (opcional, pode manter ou limpar)
        # O helper update_sfx_metadata cria se não existe, mas não temos remove.
        # Vamos carregar e salvar manualmente para remover
        metadata = load_soundboard_metadata()
        metadata['soundboard'] = [s for s in metadata.get('soundboard', []) if s.get('id') != sfx_id]
        save_soundboard_metadata(metadata)
        
        return {"status": "success", "message": "Efeito deletado."}
    except Exception as e:
        logging.error(f"Erro ao deletar SFX: {e}")
        raise HTTPException(status_code=500, detail="Erro ao deletar arquivo.")

@router.post("/api/soundboard/favorite")
async def toggle_favorite_soundboard(body: SoundboardFavoriteRequest):
    """Alterna o status de favorito de um efeito."""
    try:
        update_sfx_metadata(body.sfx_id, {"favorite": body.favorite})
        return {"status": "success", "message": "Favorito atualizado."}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Erro ao atualizar favorito.")

@router.post("/api/soundboard/volume")
async def volume_soundboard(body: SoundboardVolumeRequest):
    """Define o volume padrão de um efeito."""
    try:
        update_sfx_metadata(body.sfx_id, {"volume": body.volume})
        return {"status": "success", "message": "Volume atualizado."}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Erro ao atualizar volume.")
