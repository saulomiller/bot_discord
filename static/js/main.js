import { API } from './api.js';
import { UI } from './ui.js';
import { AudioReactiveBackground } from './visualizer.js';
import { CONFIG } from './config.js';

// Estado
let isPaused = false;
let isDraggingVolume = false;
let liquidBg; // Inicializar depois

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
    } catch (err) {
        console.warn('Connection lost', err);
        // UI.showToast('Conexão perdida...', 'error');
    }
}

// ... (EventListeners omitted for brevity, verify they are correct) ...

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
});
