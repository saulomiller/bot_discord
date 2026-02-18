import { API } from './api.js';
import { UI } from './ui.js';
import { AudioReactiveBackground } from './visualizer.js';
import { RadioManager } from './radios.js';
import { SoundboardManager } from './soundboard.js';
import { CONFIG } from './config.js';
import { TranslationManager } from './translations.js';

// Estado
let isPaused = false;
let isDraggingVolume = false;
let liquidBg; // Inicializar depois
let radioManager; // Gerenciador de rádios
let soundboardManager; // Gerenciador de soundboard
let translationManager; // Gerenciador de traduções

// --- Inicialização ---

async function updateStatusLoop() {
    try {
        const data = await API.getStatus();
        isPaused = !!data.is_paused;

        UI.updateStatus(data, isPaused);

        if (data.language && translationManager && translationManager.currentLang !== data.language) {
            if (!localStorage.getItem('app_language')) {
                translationManager.setLanguage(data.language);
            }
        }

        if (liquidBg) {
            liquidBg.syncPlayState(!isPaused && data.is_ready, data.volume || 0.5);
        }

        // Sincronizar volume slider com o servidor (apenas se não estiver arrastando)
        if (!isDraggingVolume && typeof data.volume === 'number') {
            UI.setVolumeVisual(data.volume);
        }

        // Atualizar Guild ID do soundboard se disponível
        if (soundboardManager && data.guild_id) {
            soundboardManager.currentGuildId = data.guild_id;
        }
    } catch (err) {
        console.warn('Connection lost', err);
    }
}

// --- Event Listeners ---
function setupEventListeners() {
    // Toggle Sidebar
    const toggleBtn = document.getElementById('sidebar-toggle');
    const closeSidebarBtn = document.getElementById('close-sidebar');
    const overlay = document.getElementById('sidebar-overlay');

    if (toggleBtn) toggleBtn.addEventListener('click', () => UI.toggleSidebar());
    if (closeSidebarBtn) closeSidebarBtn.addEventListener('click', () => UI.toggleSidebar());
    if (overlay) overlay.addEventListener('click', () => UI.toggleSidebar());

    // Language Selector (Novo Design com Botões)
    const langBtns = document.querySelectorAll('.lang-btn');
    if (langBtns.length > 0 && translationManager) {
        // Marcar o botão inicial baseado no idioma atual
        langBtns.forEach(btn => {
            if (btn.dataset.lang === translationManager.currentLang) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }

            btn.addEventListener('click', () => {
                const newLang = btn.dataset.lang;
                if (newLang === translationManager.currentLang) return;

                // UI Update
                langBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');

                // Logic Update
                translationManager.setLanguage(newLang);
            });
        });
    }

    // Token Management
    const saveTokenBtn = document.getElementById('save-token-btn');
    if (saveTokenBtn) {
        saveTokenBtn.addEventListener('click', async () => {
            const tokenInput = document.getElementById('token-input');
            const token = tokenInput.value.trim();
            if (!token) return UI.showToast(translationManager.get('error_search'), 'error');

            try {
                await API.setToken(token);
                UI.showToast('Token salvo! Reiniciando bot...', 'success');
                tokenInput.value = '';
            } catch (e) {
                UI.showToast(e.message, 'error');
            }
        });
    }

    // Bot Control
    const initBtn = document.getElementById('init-token-btn');
    if (initBtn) {
        initBtn.addEventListener('click', async () => {
            const tokenInput = document.getElementById('token-input');
            const token = tokenInput.value.trim();
            try {
                await API.startup(token || undefined);
                UI.showToast('Inicializando bot...', 'success');
            } catch (e) {
                UI.showToast(e.message, 'error');
            }
        });
    }

    const restartBtn = document.getElementById('restart-bot-btn');
    if (restartBtn) {
        restartBtn.addEventListener('click', async () => {
            if (!confirm('Deseja realmente reiniciar o bot?')) return;
            try {
                await API.restart();
                UI.showToast('Reiniciando sistema...', 'info');
            } catch (e) {
                UI.showToast(e.message, 'error');
            }
        });
    }

    const shutdownBtn = document.getElementById('shutdown-bot-btn');
    if (shutdownBtn) {
        shutdownBtn.addEventListener('click', async () => {
            if (!confirm(translationManager.get('confirm_shutdown'))) return;
            try {
                await API.shutdown();
                UI.showToast('Bot desligado.', 'error');
            } catch (e) {
                UI.showToast(e.message, 'error');
            }
        });
    }

    // Media Controls
    const playPauseBtn = document.getElementById('pause-resume-btn');
    if (playPauseBtn) {
        playPauseBtn.addEventListener('click', async () => {
            try {
                if (isPaused) {
                    await API.resume();
                    UI.showToast('Retomado', 'success');
                    isPaused = false;
                } else {
                    await API.pause();
                    UI.showToast('Pausado', 'info');
                    isPaused = true;
                }

                try {
                    const playerEl = UI.elements.player;
                    if (playerEl && playerEl.playBtn) {
                        playerEl.playBtn.innerHTML = isPaused ? '<i class="fa-solid fa-play"></i>' : '<i class="fa-solid fa-pause"></i>';
                        const titleKey = isPaused ? 'resume' : 'paused';
                        playerEl.playBtn.title = translationManager ? translationManager.get(titleKey) : (isPaused ? 'Retomar' : 'Pausar');
                    }
                } catch (e) { }

                setTimeout(() => updateStatusLoop(), 300);
            } catch (e) {
                UI.showToast(e.message, 'error');
            }
        });
    }

    const skipBtn = document.getElementById('skip-btn');
    if (skipBtn) {
        skipBtn.addEventListener('click', async () => {
            try {
                await API.skip();
                UI.showToast(translationManager.get('skip_toast'), 'success');
                setTimeout(() => updateStatusLoop(), 300);
            } catch (e) {
                UI.showToast(e.message, 'error');
            }
        });
    }

    const skipPlaylistBtn = document.getElementById('skip-playlist-btn');
    if (skipPlaylistBtn) {
        skipPlaylistBtn.addEventListener('click', async () => {
            if (!confirm('Deseja remover as músicas da playlist da fila?')) return;

            try {
                const res = await API.removePlaylist();
                UI.showToast(res.message || 'Playlist removida da fila', 'success');
                setTimeout(() => updateStatusLoop(), 300);
            } catch (e) {
                UI.showToast(e.message || 'Erro ao remover playlist', 'error');
            }
        });
    }

    // Botão de Atualização Manual
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', async () => {
            const icon = refreshBtn.querySelector('i');
            icon.classList.add('fa-spin');
            try {
                await updateStatusLoop();
                UI.showToast(translationManager.get('success_update'), 'success');
            } catch (e) {
                UI.showToast(translationManager.get('error_update'), 'error');
            } finally {
                setTimeout(() => icon.classList.remove('fa-spin'), 500);
            }
        });
    }

    // Music Input
    const musicInput = document.getElementById('music-input');
    const playInputBtn = document.getElementById('play-btn');
    const clearSearchBtn = document.getElementById('clear-search-btn');

    async function handlePlay() {
        if (!musicInput) return;
        const query = musicInput.value.trim();
        if (!query) return;

        try {
            await API.play(query);
            UI.showToast(translationManager.get('added_to_queue_toast'), 'success');
            musicInput.value = '';
            if (clearSearchBtn) clearSearchBtn.style.display = 'none';
            setTimeout(() => updateStatusLoop(), 500);
        } catch (e) {
            UI.showToast(e.message, 'error');
        }
    }

    if (playInputBtn) {
        playInputBtn.addEventListener('click', handlePlay);
    }

    if (musicInput) {
        musicInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') handlePlay();
        });

        musicInput.addEventListener('input', (e) => {
            if (clearSearchBtn) {
                clearSearchBtn.style.display = e.target.value.trim() ? 'block' : 'none';
            }
        });
    }

    if (clearSearchBtn) {
        clearSearchBtn.addEventListener('click', () => {
            if (musicInput) {
                musicInput.value = '';
                musicInput.focus();
            }
            clearSearchBtn.style.display = 'none';
        });
    }

    // Playlist Upload
    const dropZone = document.getElementById('drop-zone');
    const playlistUpload = document.getElementById('playlist-upload');

    async function handleFileUpload(file) {
        if (!file) return;

        if (!file.name.endsWith('.txt')) {
            UI.showToast(translationManager.get('txt_only_error'), 'error');
            return;
        }

        try {
            UI.showToast('Enviando playlist...', 'info');
            const result = await API.uploadPlaylist(file);
            UI.showToast(result.message || 'Playlist salva!', 'success');

            if (result.playlists) {
                UI.updatePlaylistList(result.playlists);
            }
        } catch (e) {
            UI.showToast(e.message || 'Erro ao enviar playlist', 'error');
        }
    }

    if (dropZone) {
        dropZone.addEventListener('click', () => {
            if (playlistUpload) playlistUpload.click();
        });

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');

            const files = e.dataTransfer.files;
            if (files.length > 0) {
                handleFileUpload(files[0]);
            }
        });
    }

    if (playlistUpload) {
        playlistUpload.addEventListener('change', (e) => {
            const files = e.target.files;
            if (files.length > 0) {
                handleFileUpload(files[0]);
            }
            e.target.value = '';
        });
    }

    // Volume Slider — envia setVolume ao soltar o slider
    const volumeSlider = document.getElementById('volume-slider');
    if (volumeSlider) {
        volumeSlider.addEventListener('mousedown', () => { isDraggingVolume = true; });
        volumeSlider.addEventListener('touchstart', () => { isDraggingVolume = true; }, { passive: true });

        volumeSlider.addEventListener('mouseup', async () => {
            isDraggingVolume = false;
            const vol = parseFloat(volumeSlider.value);
            try {
                await API.setVolume(vol);
            } catch (e) {
                UI.showToast(e.message, 'error');
            }
        });

        volumeSlider.addEventListener('touchend', async () => {
            isDraggingVolume = false;
            const vol = parseFloat(volumeSlider.value);
            try {
                await API.setVolume(vol);
            } catch (e) {
                UI.showToast(e.message, 'error');
            }
        });
    }
}

// Início
document.addEventListener('DOMContentLoaded', () => {
    // 1. Inicializar traduções imediatamente
    try {
        translationManager = new TranslationManager();
        UI.setTranslationManager(translationManager);
        console.log('TranslationManager initialized');
    } catch (e) {
        console.error('TranslationManager init failed:', e);
    }

    // 2. Inicializar visualizer
    try {
        console.log('DOM Loaded, initializing visualizer...');
        liquidBg = new AudioReactiveBackground();
    } catch (e) {
        console.error('Visualizer init failed:', e);
    }

    // 3. Setup UI e Handlers
    setupEventListeners();
    updateStatusLoop();
    setInterval(updateStatusLoop, CONFIG.POLLING_INTERVAL);

    // Carregar lista de playlists
    API.getPlaylists().then(data => {
        if (data.playlists) {
            UI.updatePlaylistList(data.playlists);
        }
    }).catch(err => {
        console.warn('Erro ao carregar playlists:', err);
    });

    // Inicializar gerenciador de rádios
    try {
        radioManager = new RadioManager(API, UI, updateStatusLoop, translationManager);
        radioManager.init();
        console.log('RadioManager initialized');
    } catch (e) {
        console.error('RadioManager init failed:', e);
    }

    // Inicializar gerenciador de soundboard
    try {
        soundboardManager = new SoundboardManager(API, UI, updateStatusLoop, translationManager);
        // Guild ID padrão - será atualizado dinamicamente via /api/status
        soundboardManager.init(0);
        console.log('SoundboardManager initialized');
    } catch (e) {
        console.error('SoundboardManager init failed:', e);
    }
});
