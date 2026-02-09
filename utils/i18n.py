import json
import os
import logging
from config import DATA_DIR

I18N_FILE = os.path.join(DATA_DIR, 'i18n.json')

class I18n:
    _instance = None
    _language = 'pt' # Padrão
    _translations = {
        'pt': {
            # --- Embeds ---
            'unknown': 'Desconhecido',
            'in_queue': 'na fila',
            'queue': 'Fila',
            'songs': 'músicas',
            'minutes_abbr': 'min',
            'playing_now': 'Tocando:',
            'and_more_songs': '... e mais {count} música(s)',
            'live': 'ao vivo',
            'connected': 'Conectado',
            'disconnected': 'Desconectado',
            'error': 'Erro',
            'info': 'Informação',
            'success': 'Sucesso',
            'suggestion': 'Sugestão',
            
            # --- Messages ---
            'joined_channel': 'Juntei-me ao canal **{channel}**.',
            'left_channel': 'Saí do canal de voz.',
            'not_in_voice': 'Não estou em um canal de voz.',
            'left_all_channels': 'Saí de {count} canais de voz em todos os servidores.',
            'adding_songs': 'Adicionando {count} músicas...',
            'added_songs_queue': 'Adicionadas {count} músicas à fila.',
            'processing_playlist': '⏳ Processando Playlist',
            'extracting_playlist': 'Extraindo músicas da playlist...',
            'playlist_added': 'Playlist Adicionada',
            'processing_background': '**{title}** está sendo processada em segundo plano!',
            'added_to_queue': 'Adicionada à fila',
            'position_in_queue': 'Posição #{position}',
            'user_must_be_in_voice': 'Você precisa estar em um canal de voz!',
            'song_skipped': 'Música pulada.',
            'music_stopped_queue_cleared': 'Música parada e fila limpa.',
            'volume_adjusted': 'Volume ajustado',
            'volume_set_to': 'Volume definido para {volume}%',
            'playback': 'Reprodução',
            'not_playing': 'Não estou tocando nada no momento.',
            'now_playing': '🎵 Tocando Agora',
            'channel': 'Canal',
            'duration': 'Duração',
            'added_by': 'Adicionado por',
            'next_songs_in_queue': 'Próximas: {count} música(s) na fila',
            'queue_empty': 'Fila vazia',
            'queue_no_songs': 'Não há músicas na fila no momento.',
            'no_radios_found': 'Nenhuma rádio encontrada.',
            'radios_available': '📻 Rádios Disponíveis',
            'use_radio_command': 'Use /radio [nome] para tocar uma rádio',
            'radio_not_found': 'Rádio não encontrada. Use /radios para ver a lista de rádios disponíveis.',
            'radio_added': 'Rádio Adicionada',
            'radio_added_success': "Rádio '{name}' adicionada com sucesso!\nUse `/radio {id}` para tocar.",
            'radio_removed': 'Rádio Removida',
            'radio_removed_success': "Rádio '{name}' removida com sucesso!",
            'syncing': 'Sincronizando...',
            'synced_commands': '{count} comandos sincronizados.',
            'need_admin': 'Precisa de admin.',
            'invalid_url': 'URL inválida.',
            'radio_exists': "Uma rádio com o nome '{name}' já existe.",
            'error_saving_radio': 'Ocorreu um erro ao salvar a rádio.',
            'error_removing_radio': 'Erro ao remover rádio.',
        },
        'en': {
            # --- Embeds ---
            'unknown': 'Unknown',
            'in_queue': 'in queue',
            'queue': 'Queue',
            'songs': 'songs',
            'minutes_abbr': 'min',
            'playing_now': 'Playing:',
            'and_more_songs': '... and {count} more song(s)',
            'live': 'live',
            'connected': 'Connected',
            'disconnected': 'Disconnected',
            'error': 'Error',
            'info': 'Information',
            'success': 'Success',
            'suggestion': 'Suggestion',

            # --- Messages ---
            'joined_channel': 'Joined **{channel}**.',
            'left_channel': 'Left the voice channel.',
            'not_in_voice': 'I am not in a voice channel.',
            'left_all_channels': 'Left {count} voice channels across all servers.',
            'adding_songs': 'Adding {count} songs...',
            'added_songs_queue': 'Added {count} songs to queue.',
            'processing_playlist': '⏳ Processing Playlist',
            'extracting_playlist': 'Extracting songs from playlist...',
            'playlist_added': 'Playlist Added',
            'processing_background': '**{title}** is being processed in background!',
            'added_to_queue': 'Added to queue',
            'position_in_queue': 'Position #{position}',
            'user_must_be_in_voice': 'You must be in a voice channel!',
            'song_skipped': 'Song skipped.',
            'music_stopped_queue_cleared': 'Music stopped and queue cleared.',
            'volume_adjusted': 'Volume adjusted',
            'volume_set_to': 'Volume set to {volume}%',
            'playback': 'Playback',
            'not_playing': 'I am not playing anything right now.',
            'now_playing': '🎵 Now Playing',
            'channel': 'Channel',
            'duration': 'Duration',
            'added_by': 'Added by',
            'next_songs_in_queue': 'Next: {count} song(s) in queue',
            'queue_empty': 'Queue empty',
            'queue_no_songs': 'No songs in queue at the moment.',
            'no_radios_found': 'No radios found.',
            'radios_available': '📻 Available Radios',
            'use_radio_command': 'Use /radio [name] to play a radio',
            'radio_not_found': 'Radio not found. Use /radios to see the list.',
            'radio_added': 'Radio Added',
            'radio_added_success': "Radio '{name}' added successfully!\nUse `/radio {id}` to play.",
            'radio_removed': 'Radio Removed',
            'radio_removed_success': "Radio '{name}' removed successfully!",
            'syncing': 'Syncing...',
            'synced_commands': '{count} commands synced.',
            'need_admin': 'Admin required.',
            'invalid_url': 'Invalid URL.',
            'radio_exists': "A radio with the name '{name}' already exists.",
            'error_saving_radio': 'Error saving radio.',
            'error_removing_radio': 'Error removing radio.',
        }
    }

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = I18n()
        return cls._instance

    def __init__(self):
        self.load_language()

    def load_language(self):
        """Carrega a preferência de idioma do arquivo."""
        try:
            if os.path.exists(I18N_FILE):
                with open(I18N_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._language = data.get('language', 'pt')
            else:
                self.save_language('pt')
        except Exception as e:
            logging.error(f"Erro ao carregar idioma: {e}")
            self._language = 'pt'

    def save_language(self, lang):
        """Salva a preferência de idioma."""
        if lang not in self._translations:
            return False
            
        try:
            self._language = lang
            with open(I18N_FILE, 'w', encoding='utf-8') as f:
                json.dump({'language': lang}, f)
            return True
        except Exception as e:
            logging.error(f"Erro ao salvar idioma: {e}")
            return False

    @property
    def language(self):
        return self._language

    def get(self, key, **kwargs):
        """Retorna o texto traduzido para a chave especificada."""
        lang_dict = self._translations.get(self._language, self._translations['pt'])
        text = lang_dict.get(key, key)
        
        try:
            return text.format(**kwargs)
        except Exception as e:
            logging.error(f"Erro ao formatar string '{key}': {e}")
            return text

# Helper function global
def t(key, **kwargs):
    return I18n.get_instance().get(key, **kwargs)
