// Modulo: define os dicionarios de traducao usados na interface web.

/**
 * Dicionario de traducoes disponiveis na interface web.
 */
export const translations = {
    "pt": {
        "app_title": "Controlador de Bot de Música",
        "header_title": "🎵 Painel de Controle",
        "status_disconnected": "Desconectado",
        "settings_title": "Ajustes",
        "discord_token": "Token Discord",
        "token_placeholder": "Cole o token...",
        "save_token": "Salvar Token",
        "bot_control": "Controle do Bot",
        "server_label": "Servidor",
        "server_none": "Sem servidor",
        "server_connected_tag": "conectado",
        "server_idle_tag": "offline",
        "btn_start": "Iniciar",
        "btn_restart": "Reiniciar",
        "btn_shutdown": "Desligar",
        "no_song": "Nenhuma música",
        "waiting": "Aguardando comando...",
        "add_to_queue": "Adicionar à Fila",
        "input_placeholder": "Cole o link ou nome...",
        "queue_title": "Fila",
        "queue_next": "Próximas",
        "queue_empty": "A fila está vazia.",
        "playlists_title": "Playlists Salvas",
        "upload_playlist": "Upload Nova Playlist (.txt)",
        "drag_drop": "Arraste arquivo .txt",
        "my_playlists": "Minhas Playlists",
        "radios_title": "Rádios",
        "btn_add": "Adicionar",
        "soundboard_title": "Soundboard",
        "btn_upload": "Upload",
        "modal_radio_title": "Adicionar Nova Rádio",
        "label_radio_name": "Nome da Rádio *",
        "label_radio_url": "URL do Stream *",
        "label_radio_location": "Localização",
        "label_radio_desc": "Descrição",
        "btn_save": "Salvar",
        "modal_sfx_title": "Enviar Efeito Sonoro",
        "label_sfx_file": "Arquivo de Áudio (MP3, WAV, OGG, M4A)",
        "label_preview": "Prévia",
        "btn_send": "Enviar",
        "language_label": "Idioma / Language",
        "status_connected": "Conectado",
        "status_disconnected": "Desconectado",
        "playing": "Tocando",
        "paused": "Pausado",
        "resume": "Retomar",
        "skip": "Pular",
        "empty_playlists": "Nenhuma playlist salva.",
        "error_search": "Por favor, insira um token.",
        "added_to_queue_toast": "Adicionado à fila!",
        "success_update": "Atualizado!",
        "error_update": "Erro ao atualizar",
        "no_radios": "Nenhuma rádio disponível",
        "radio_added_toast": "Rádio adicionada!",
        "radio_playing_toast": "Tocando rádio...",
        "radio_removed_toast": "Rádio removida",
        "radio_delete_confirm": "Deletar esta rádio?",
        "no_sfx": "Nenhum efeito sonoro. Faça upload!",
        "sfx_select_file_toast": "Selecione um arquivo",
        "sfx_upload_success_toast": "Upload concluído!",
        "sfx_playing_discord_toast": "Tocando no Discord: {name}",
        "sfx_deleted_toast": "Efeito deletado",
        "sfx_delete_confirm": "Deletar \"{name}\"?",
        "sfx_test_error_toast": "Erro ao reproduzir áudio locally",
        "sfx_favorite_remove": "Remover dos favoritos",
        "sfx_favorite_add": "Adicionar aos favoritos",
        "sfx_test_title": "Testar (ouvir no navegador)",
        "sfx_play_discord_title": "Tocar no Discord",
        "sfx_delete_title": "Deletar",
        "confirm_shutdown": "Deseja desligar o bot? A música irá parar.",
        "skip_toast": "Música pulada",
        "txt_only_error": "Apenas arquivos .txt são permitidos!",
        "guild_id_error": "Guild ID não configurado",
        "sfx_test_error": "Erro ao testar áudio",
        "radio_delete_error": "Erro ao deletar rádio"
    },
    "en": {
        "app_title": "Music Bot Controller",
        "header_title": "🎵 Control Panel",
        "status_disconnected": "Disconnected",
        "settings_title": "Settings",
        "discord_token": "Discord Token",
        "token_placeholder": "Paste token...",
        "save_token": "Save Token",
        "bot_control": "Bot Control",
        "server_label": "Server",
        "server_none": "No server",
        "server_connected_tag": "connected",
        "server_idle_tag": "offline",
        "btn_start": "Start",
        "btn_restart": "Restart",
        "btn_shutdown": "Shutdown",
        "no_song": "No song playing",
        "waiting": "Waiting for command...",
        "add_to_queue": "Add to Queue",
        "input_placeholder": "Paste link or name...",
        "queue_title": "Queue",
        "queue_next": "Next",
        "queue_empty": "The queue is empty.",
        "playlists_title": "Saved Playlists",
        "upload_playlist": "Upload New Playlist (.txt)",
        "drag_drop": "Drag .txt file here",
        "my_playlists": "My Playlists",
        "radios_title": "Radios",
        "btn_add": "Add",
        "soundboard_title": "Soundboard",
        "btn_upload": "Upload",
        "modal_radio_title": "Add New Radio",
        "label_radio_name": "Radio Name *",
        "label_radio_url": "Stream URL *",
        "label_radio_location": "Location",
        "label_radio_desc": "Description",
        "btn_save": "Save",
        "modal_sfx_title": "Upload Sound Effect",
        "label_sfx_file": "Audio File (MP3, WAV, OGG, M4A)",
        "label_preview": "Preview",
        "btn_send": "Upload",
        "language_label": "Idioma / Language",
        "status_connected": "Connected",
        "status_disconnected": "Disconnected",
        "playing": "Playing",
        "paused": "Paused",
        "resume": "Resume",
        "skip": "Skip",
        "empty_playlists": "No playlists saved.",
        "error_search": "Please enter a token.",
        "added_to_queue_toast": "Added to queue!",
        "success_update": "Updated!",
        "error_update": "Error updating",
        "no_radios": "No radios available",
        "radio_added_toast": "Radio added!",
        "radio_playing_toast": "Playing radio...",
        "radio_removed_toast": "Radio removed",
        "radio_delete_confirm": "Delete this radio?",
        "no_sfx": "No sound effects. Upload one!",
        "sfx_select_file_toast": "Select a file",
        "sfx_upload_success_toast": "Upload complete!",
        "sfx_playing_discord_toast": "Playing on Discord: {name}",
        "sfx_deleted_toast": "Effect deleted",
        "sfx_delete_confirm": "Delete \"{name}\"?",
        "sfx_test_error_toast": "Error playing audio locally",
        "sfx_favorite_remove": "Remove from favorites",
        "sfx_favorite_add": "Add to favorites",
        "sfx_test_title": "Test (hear in browser)",
        "sfx_play_discord_title": "Play on Discord",
        "sfx_delete_title": "Delete",
        "confirm_shutdown": "Do you want to shutdown the bot? Music will stop.",
        "skip_toast": "Song skipped",
        "txt_only_error": "Only .txt files are allowed!",
        "guild_id_error": "Guild ID not configured",
        "sfx_test_error": "Error testing audio",
        "radio_delete_error": "Error deleting radio"
    }
};

/**
 * Gerencia idioma atual e aplicacao de traducoes na interface.
 */
export class TranslationManager {
    constructor() {
        this.currentLang = localStorage.getItem('app_language') || 'pt'; // Default to PT
        this.applyTranslations(this.currentLang);
    }

    /**
     * Define o idioma ativo e sincroniza mudanca com o backend.
     * @param {'pt'|'en'} lang
     */
    setLanguage(lang) {
        if (translations[lang]) {
            this.currentLang = lang;
            localStorage.setItem('app_language', lang);
            this.applyTranslations(lang);

            // Disparar evento para outras partes da UI saberem
            document.dispatchEvent(new CustomEvent('languageChanged', { detail: { lang } }));

            // Aqui vamos chamar a API depois para persistir no backend
            this.syncWithBackend(lang);
        }
    }

    /**
     * Aplica os textos traduzidos em elementos com atributos data-i18n.
     * @param {'pt'|'en'} lang
     */
    applyTranslations(lang) {
        const t = translations[lang];
        document.querySelectorAll('[data-i18n]').forEach(element => {
            const key = element.getAttribute('data-i18n');
            if (t[key]) {
                if (element.tagName === 'INPUT' && element.getAttribute('placeholder')) {
                    element.placeholder = t[key];
                } else if (element.tagName === 'INPUT' && element.type === 'button') {
                    element.value = t[key];
                } else {
                    // Se o elemento tem filhos (ícones), tentamos preservar
                    const icon = element.querySelector('i, svg');
                    if (icon) {
                        // Preserva o ícone e atualiza apenas o texto
                        // Vamos assumir que o texto vem depois do ícone (padrão do app)

                        // Limpar nós de texto existentes
                        Array.from(element.childNodes).forEach(node => {
                            if (node.nodeType === Node.TEXT_NODE) {
                                element.removeChild(node);
                            }
                        });

                        // Readicionar texto traduzido
                        element.appendChild(document.createTextNode(` ${t[key]}`));
                    } else {
                        element.textContent = t[key];
                    }
                }
            }
        });

        document.querySelectorAll('[data-i18n-placeholder]').forEach(element => {
            const key = element.getAttribute('data-i18n-placeholder');
            if (t[key]) {
                element.setAttribute('placeholder', t[key]);
            }
        });
    }

    /**
     * Persiste o idioma escolhido na API.
     * @param {'pt'|'en'} lang
     * @returns {Promise<void>}
     */
    async syncWithBackend(lang) {
        try {
            await fetch('/api/settings/language', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ language: lang })
            });
        } catch (error) {
            console.error('Erro ao sincronizar idioma com backend:', error);
        }
    }

    /**
     * Retorna a traducao de uma chave no idioma atual.
     * @param {string} key
     * @returns {string}
     */
    get(key) {
        return translations[this.currentLang][key] || key;
    }
}
