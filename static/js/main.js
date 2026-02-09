import { API } from './api.js';
import { UI } from './ui.js';
import { AudioReactiveBackground } from './visualizer.js';
import { RadioManager } from './radios.js';
import { SoundboardManager } from './soundboard.js';
import { CONFIG } from './config.js';

// Estado
let isPaused = false;
let isDraggingVolume = false;
let liquidBg; // Inicializar depois
let radioManager; // Gerenciador de rádios
let soundboardManager; // Gerenciador de soundboard

// --- Inicialização ---

async function updateStatusLoop() {
    try {
        const data = await API.getStatus();
        // console.log('Status Data:', data); // Debug
        isPaused = !!data.is_paused;

        UI.updateStatus(data, isPaused);

        if (liquidBg) {
            liquidBg.syncPlayState(!isPaused && data.is_ready, data.volume || 0.5);
        }

        if (!isDraggingVolume && typeof data.volume === 'number') {
            UI.setVolumeVisual(data.volume);
        }

        // Atualizar Guild ID do soundboard se disponível
        if (soundboardManager && data.guild_id) {
            soundboardManager.currentGuildId = data.guild_id;
        }
    } catch (err) {
        console.warn('Connection lost', err);
        // UI.showToast('Conexão perdida...', 'error');
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

    // Token Management
    const saveTokenBtn = document.getElementById('save-token-btn');
    if (saveTokenBtn) {
        saveTokenBtn.addEventListener('click', async () => {
            const tokenInput = document.getElementById('token-input');
            const token = tokenInput.value.trim();
            if (!token) return UI.showToast('Por favor, insira um token.', 'error');

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
                await API.startup(token || undefined); // Envia token se houver, ou a API usa o salvo
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
            if (!confirm('Deseja desligar o bot? A música irá parar.')) return;
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
            // Usa o estado global isPaused
            try {
                if (isPaused) {
                    await API.resume();
                    UI.showToast('Retomado', 'success');
                } else {
                    await API.pause();
                    UI.showToast('Pausado', 'info');
                }
                // Atualizar imediatamente após ação
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
                UI.showToast('Música pulada', 'success');
                // Atualizar imediatamente após pular
                setTimeout(() => updateStatusLoop(), 300);
            } catch (e) {
                UI.showToast(e.message, 'error');
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
                UI.showToast('Atualizado!', 'success');
            } catch (e) {
                UI.showToast('Erro ao atualizar', 'error');
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
            UI.showToast('Adicionado à fila!', 'success');
            musicInput.value = '';
            if (clearSearchBtn) clearSearchBtn.style.display = 'none';
            // Atualizar imediatamente após adicionar
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
            UI.showToast('Apenas arquivos .txt são permitidos!', 'error');
            return;
        }

        try {
            UI.showToast('Enviando playlist...', 'info');
            const result = await API.uploadPlaylist(file);
            UI.showToast(result.message || 'Playlist salva!', 'success');

            // Atualizar lista de playlists
            if (result.playlists) {
                UI.updatePlaylistList(result.playlists);
            }
        } catch (e) {
            UI.showToast(e.message || 'Erro ao enviar playlist', 'error');
        }
    }

    if (dropZone) {
        // Click para abrir seletor
        dropZone.addEventListener('click', () => {
            if (playlistUpload) playlistUpload.click();
        });

        // Drag & Drop
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
            // Limpar input para permitir re-upload do mesmo arquivo
            e.target.value = '';
        });
    }
}

// Início
document.addEventListener('DOMContentLoaded', () => {
    try {
        console.log('DOM Loaded, initializing...');
        liquidBg = new AudioReactiveBackground();
        console.log('Visualizer initialized');
    } catch (e) {
        console.error('Visualizer init failed:', e);
    }

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
        radioManager = new RadioManager(API, UI, updateStatusLoop);
        radioManager.init();
        console.log('RadioManager initialized');
    } catch (e) {
        console.error('RadioManager init failed:', e);
    }

    // Inicializar gerenciador de soundboard
    try {
        soundboardManager = new SoundboardManager(API, UI, updateStatusLoop);
        // Guild ID padrão - pode ser configurado dinamicamente
        soundboardManager.init(CONFIG.GUILD_ID || 0);
        console.log('SoundboardManager initialized');
    } catch (e) {
        console.error('SoundboardManager init failed:', e);
    }
});
