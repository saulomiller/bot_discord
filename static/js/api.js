import { CONFIG } from './config.js';

export async function apiFetch(path, opts = {}) {
    try {
        const res = await fetch(path, opts);
        if (!res.ok) {
            let errorMsg = res.statusText;
            try {
                const errJson = await res.json();
                if (errJson.detail) errorMsg = errJson.detail;
            } catch (e) { }
            throw new Error(errorMsg);
        }
        return await res.json().catch(() => ({}));
    } catch (err) {
        console.error('API error', err);
        throw err;
    }
}

export const API = {
    getStatus: () => apiFetch(`${CONFIG.API_BASE}/status`),
    play: (search) => apiFetch(`${CONFIG.API_BASE}/play`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ search })
    }),
    pause: () => apiFetch(`${CONFIG.API_BASE}/pause`, { method: 'POST' }),
    resume: () => apiFetch(`${CONFIG.API_BASE}/resume`, { method: 'POST' }),
    skip: () => apiFetch(`${CONFIG.API_BASE}/skip`, { method: 'POST' }),
    setVolume: (level) => apiFetch(`${CONFIG.API_BASE}/volume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level })
    }),
    setToken: (token) => apiFetch(`${CONFIG.API_BASE}/set_token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token })
    }),
    startup: (token) => apiFetch(`${CONFIG.API_BASE}/startup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token })
    }),
    restart: () => apiFetch(`${CONFIG.API_BASE}/restart`, { method: 'POST' }),
    shutdown: () => apiFetch(`${CONFIG.API_BASE}/shutdown`, { method: 'POST' }),
    uploadPlaylist: async (file) => {
        const reader = new FileReader();
        return new Promise((resolve, reject) => {
            reader.onload = async (e) => {
                try {
                    const content = e.target.result;
                    const res = await apiFetch(`${CONFIG.API_BASE}/upload_playlist`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            file: btoa(unescape(encodeURIComponent(content))),
                            filename: file.name
                        })
                    });
                    resolve(res);
                } catch (err) {
                    reject(err);
                }
            };
            reader.onerror = reject;
            reader.readAsText(file);
        });
    },
    getPlaylists: () => apiFetch(`${CONFIG.API_BASE}/playlists`),

    // Radio Management
    getRadios: () => apiFetch(`${CONFIG.API_BASE}/radios`),
    addRadio: (radioData) => apiFetch(`${CONFIG.API_BASE}/radios/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(radioData)
    }),
    removeRadio: (radioId) => apiFetch(`${CONFIG.API_BASE}/radios/remove`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ radio_id: radioId })
    }),
    playRadio: (radioId) => apiFetch(`${CONFIG.API_BASE}/radios/play`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ radio_id: radioId })
    }),

    // Soundboard Management
    getSoundboard: () => apiFetch(`${CONFIG.API_BASE}/soundboard`),
    uploadSoundboard: async (formData) => {
        const res = await fetch(`${CONFIG.API_BASE}/soundboard/upload`, {
            method: 'POST',
            body: formData
        });
        if (!res.ok) {
            const error = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(error.detail || 'Erro no upload');
        }
        return await res.json();
    },
    playSoundboard: (guildId, sfxId) => apiFetch(`${CONFIG.API_BASE}/soundboard/play`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ guild_id: guildId, sfx_id: sfxId })
    }),
    deleteSoundboard: (sfxId) => apiFetch(`${CONFIG.API_BASE}/soundboard/${sfxId}`, {
        method: 'DELETE'
    }),
    toggleFavoriteSoundboard: (sfxId, favorite) => apiFetch(`${CONFIG.API_BASE}/soundboard/${sfxId}/favorite`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sfx_id: sfxId, favorite })
    }),
    updateVolumeSoundboard: (sfxId, volume) => apiFetch(`${CONFIG.API_BASE}/soundboard/${sfxId}/volume`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sfx_id: sfxId, volume })
    })
};
