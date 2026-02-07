import { API } from './api.js';
import { UI } from './ui.js';
import { AudioReactiveBackground } from './visualizer.js';
import { CONFIG } from './config.js';

// Estado
let isPaused = false;
let isDraggingVolume = false;
const liquidBg = new AudioReactiveBackground();

// --- Inicialização ---

async function updateStatusLoop() {
    try {
        const data = await API.getStatus();
        isPaused = !!data.is_paused;

        UI.updateStatus(data, isPaused);
        liquidBg.syncPlayState(!isPaused && data.is_ready, data.volume || 0.5);

        if (!isDraggingVolume && typeof data.volume === 'number') {
            UI.setVolumeVisual(data.volume);
        }
    } catch (err) {
        console.warn('Connection lost', err);
        // UI.showToast('Conexão perdida...', 'error');
    }
}

// --- Configuração de Event Listeners ---

function setupEventListeners() {
    // Barra Lateral
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const closeSidebarBtn = document.getElementById('close-sidebar');
    const sidebarOverlay = document.getElementById('sidebar-overlay');

    if (sidebarToggle) sidebarToggle.onclick = () => UI.toggleSidebar();
    if (closeSidebarBtn) closeSidebarBtn.onclick = () => UI.toggleSidebar();
    if (sidebarOverlay) sidebarOverlay.onclick = () => UI.toggleSidebar();

    // Controles do Player
    const playBtn = document.getElementById('play-btn');
    const musicInput = document.getElementById('music-input');
    const pauseResumeBtn = document.getElementById('pause-resume-btn');
    const skipBtn = document.getElementById('skip-btn');
    const volumeSlider = document.getElementById('volume-slider');
    const clearSearchBtn = document.getElementById('clear-search-btn');

    // Lógica de Busca
    musicInput.oninput = () => {
        clearSearchBtn.style.display = musicInput.value ? 'block' : 'none';
    };

    clearSearchBtn.onclick = () => {
        musicInput.value = '';
        clearSearchBtn.style.display = 'none';
        musicInput.focus();
    };

    musicInput.onkeypress = (e) => {
        if (e.key === 'Enter') playBtn.click();
    };

    playBtn.onclick = async () => {
        const search = musicInput.value.trim();
        if (!search) return UI.showToast('Digite algo!', 'error');

        playBtn.disabled = true;
        UI.showToast(`Buscando: ${search}...`, 'info');

        try {
            await API.play(search);
            musicInput.value = '';
            clearSearchBtn.style.display = 'none';
            UI.showToast('Adicionado à fila!', 'success');
            await updateStatusLoop();
        } catch (err) {
            UI.showToast(`Erro: ${err.message}`, 'error');
        } finally {
            playBtn.disabled = false;
        }
    };

    pauseResumeBtn.onclick = async () => {
        pauseResumeBtn.disabled = true;
        try {
            if (isPaused) await API.resume();
            else await API.pause();
            await updateStatusLoop();
        } catch (err) {
            UI.showToast('Erro ao alternar reprodução', 'error');
        } finally {
            pauseResumeBtn.disabled = false;
        }
    };

    skipBtn.onclick = async () => {
        skipBtn.disabled = true;
        try {
            await API.skip();
            UI.showToast('Música pulada!', 'success');
            setTimeout(updateStatusLoop, 1000);
        } catch (err) {
            UI.showToast('Erro ao pular', 'error');
        } finally {
            skipBtn.disabled = false;
        }
    };

    // Volume
    if (volumeSlider) {
        volumeSlider.onmousedown = () => isDraggingVolume = true;
        volumeSlider.onmouseup = async () => {
            isDraggingVolume = false;
            const vol = parseFloat(volumeSlider.value);
            try {
                await API.setVolume(vol);
                UI.showToast(`Volume: ${Math.round(vol * 100)}%`, 'info');
            } catch (e) {
                UI.showToast('Erro ao ajustar volume', 'error');
            }
        };
    }

    // Atalhos de Teclado
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT') return;

        const prevent = () => { e.preventDefault(); };

        switch (e.code) {
            case 'Space': prevent(); pauseResumeBtn.click(); break;
            case 'ArrowRight': prevent(); skipBtn.click(); break;
            case 'ArrowUp':
                if (volumeSlider) {
                    prevent();
                    volumeSlider.value = Math.min(1, parseFloat(volumeSlider.value) + 0.05);
                    volumeSlider.dispatchEvent(new Event('mouseup'));
                }
                break;
            case 'ArrowDown':
                if (volumeSlider) {
                    prevent();
                    volumeSlider.value = Math.max(0, parseFloat(volumeSlider.value) - 0.05);
                    volumeSlider.dispatchEvent(new Event('mouseup'));
                }
                break;
        }
    });
}

// Início
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    updateStatusLoop();
    setInterval(updateStatusLoop, CONFIG.POLLING_INTERVAL);
});
