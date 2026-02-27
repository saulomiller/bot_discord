import { CONFIG } from './config.js';

let apiKeyInitPromise = null;

async function initApiKey() {
    if (CONFIG.API_KEY) return CONFIG.API_KEY;
    if (apiKeyInitPromise) return apiKeyInitPromise;

    apiKeyInitPromise = (async () => {
        try {
            const res = await fetch('/api/get_api_key');
            if (res.ok) {
                const data = await res.json();
                CONFIG.API_KEY = data.api_key;
            }
        } catch (e) {
            console.warn('Não foi possível obter a API Key. Rotas protegidas podem falhar.', e);
        }
        return CONFIG.API_KEY;
    })();

    return apiKeyInitPromise;
}

const apiKeyReady = initApiKey();

function buildAuthHeaders(extra = {}) {
    const headers = { 'Content-Type': 'application/json', ...extra };
    if (CONFIG.API_KEY) {
        headers['X-API-Key'] = CONFIG.API_KEY;
    }
    return headers;
}

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

function withGuildQuery(path, guildId) {
    if (guildId === null || guildId === undefined || guildId === '') return path;
    const separator = path.includes('?') ? '&' : '?';
    return `${path}${separator}guild_id=${encodeURIComponent(guildId)}`;
}

export const API = {
    getGuilds: () => apiFetch(`${CONFIG.API_BASE}/guilds`),
    getStatus: (guildId = null) => apiFetch(withGuildQuery(`${CONFIG.API_BASE}/status`, guildId)),
    play: (search, guildId = null) => apiFetch(withGuildQuery(`${CONFIG.API_BASE}/play`, guildId), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ search })
    }),
    pause: (guildId = null) => apiFetch(withGuildQuery(`${CONFIG.API_BASE}/pause`, guildId), { method: 'POST' }),
    resume: (guildId = null) => apiFetch(withGuildQuery(`${CONFIG.API_BASE}/resume`, guildId), { method: 'POST' }),
    skip: (guildId = null) => apiFetch(withGuildQuery(`${CONFIG.API_BASE}/skip`, guildId), { method: 'POST' }),
    removePlaylist: (guildId = null) => apiFetch(withGuildQuery(`${CONFIG.API_BASE}/removeplaylist`, guildId), { method: 'POST' }),
    setVolume: (level, guildId = null) => apiFetch(withGuildQuery(`${CONFIG.API_BASE}/volume`, guildId), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level })
    }),

    // Protected routes (require X-API-Key)
    setToken: async (token) => {
        await apiKeyReady;
        return apiFetch(`${CONFIG.API_BASE}/set_token`, {
            method: 'POST',
            headers: buildAuthHeaders(),
            body: JSON.stringify({ token })
        });
    },
    startup: async (token) => {
        await apiKeyReady;
        return apiFetch(`${CONFIG.API_BASE}/startup`, {
            method: 'POST',
            headers: buildAuthHeaders(),
            body: JSON.stringify({ token })
        });
    },
    restart: async () => {
        await apiKeyReady;
        return apiFetch(`${CONFIG.API_BASE}/restart`, {
            method: 'POST',
            headers: buildAuthHeaders()
        });
    },
    shutdown: async () => {
        await apiKeyReady;
        return apiFetch(`${CONFIG.API_BASE}/shutdown`, {
            method: 'POST',
            headers: buildAuthHeaders()
        });
    },

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
                            file: content,
                            filename: file.name,
                            encoding: 'plain'
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
    playRadio: (radioId, guildId = null) => apiFetch(`${CONFIG.API_BASE}/radios/play`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            radio_id: radioId,
            ...(guildId !== null && guildId !== undefined && guildId !== '' ? { guild_id: Number(guildId) } : {}),
        })
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

export default API;
if (typeof window !== 'undefined' && !window.API) {
    window.API = API;
}
