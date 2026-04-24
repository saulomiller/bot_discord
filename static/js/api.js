// Modulo: encapsula chamadas HTTP da interface para a API do bot.

import { CONFIG } from './config.js';

let apiKeyInitPromise = null;

/**
 * Inicializa e cacheia a API key usada em rotas protegidas.
 * @returns {Promise<string|null>}
 */
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

/**
 * Monta headers HTTP padrao incluindo autenticacao quando disponivel.
 * @param {Record<string, string>} [extra={}]
 * @param {{json?: boolean}} [options={}]
 * @returns {Record<string, string>}
 */
function buildAuthHeaders(extra = {}, options = {}) {
    const headers = { ...extra };
    if (options.json && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
    }
    if (CONFIG.API_KEY) {
        headers['X-API-Key'] = CONFIG.API_KEY;
    }
    return headers;
}

/**
 * Executa chamada em rota protegida, garantindo que a API key esteja carregada.
 * @param {string} path
 * @param {RequestInit} [opts={}]
 * @returns {Promise<any>}
 */
async function apiFetchProtected(path, opts = {}) {
    await apiKeyReady;
    const headers = buildAuthHeaders(opts.headers || {});
    return apiFetch(path, { ...opts, headers });
}

/**
 * Executa uma chamada HTTP e normaliza erros da API.
 * @param {string} path
 * @param {RequestInit} [opts={}]
 * @returns {Promise<any>}
 */
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
        console.warn('API unavailable or request failed', err);
        throw err;
    }
}

/**
 * Adiciona o parametro guild_id na URL quando informado.
 * @param {string} path
 * @param {string|null|undefined} guildId
 * @returns {string}
 */
function withGuildQuery(path, guildId) {
    if (guildId === null || guildId === undefined || guildId === '') return path;
    const separator = path.includes('?') ? '&' : '?';
    return `${path}${separator}guild_id=${encodeURIComponent(guildId)}`;
}

/**
 * Cliente de API consumido pelo dashboard web.
 */
export const API = {
    getGuilds: () => apiFetch(`${CONFIG.API_BASE}/guilds`),
    getStatus: (guildId = null) => apiFetch(withGuildQuery(`${CONFIG.API_BASE}/status`, guildId)),
    play: (search, guildId = null) => apiFetchProtected(withGuildQuery(`${CONFIG.API_BASE}/play`, guildId), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ search })
    }),
    pause: (guildId = null) => apiFetchProtected(withGuildQuery(`${CONFIG.API_BASE}/pause`, guildId), { method: 'POST' }),
    resume: (guildId = null) => apiFetchProtected(withGuildQuery(`${CONFIG.API_BASE}/resume`, guildId), { method: 'POST' }),
    skip: (guildId = null) => apiFetchProtected(withGuildQuery(`${CONFIG.API_BASE}/skip`, guildId), { method: 'POST' }),
    removePlaylist: (guildId = null) => apiFetchProtected(withGuildQuery(`${CONFIG.API_BASE}/removeplaylist`, guildId), { method: 'POST' }),
    setVolume: (level, guildId = null) => apiFetchProtected(withGuildQuery(`${CONFIG.API_BASE}/volume`, guildId), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level })
    }),

    // Protected routes (require X-API-Key)
    setToken: async (token) => {
        await apiKeyReady;
        return apiFetch(`${CONFIG.API_BASE}/set_token`, {
            method: 'POST',
            headers: buildAuthHeaders({}, { json: true }),
            body: JSON.stringify({ token })
        });
    },
    startup: async (token) => {
        await apiKeyReady;
        return apiFetch(`${CONFIG.API_BASE}/startup`, {
            method: 'POST',
            headers: buildAuthHeaders({}, { json: true }),
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
    setLanguage: async (language) => {
        await apiKeyReady;
        return apiFetch(`${CONFIG.API_BASE}/settings/language`, {
            method: 'POST',
            headers: buildAuthHeaders({}, { json: true }),
            body: JSON.stringify({ language })
        });
    },

    uploadPlaylist: async (file) => {
        const reader = new FileReader();
        return new Promise((resolve, reject) => {
            reader.onload = async (e) => {
                try {
                    const content = e.target.result;
                    const res = await apiFetchProtected(`${CONFIG.API_BASE}/upload_playlist`, {
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
    addRadio: (radioData) => apiFetchProtected(`${CONFIG.API_BASE}/radios/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(radioData)
    }),
    removeRadio: (radioId) => apiFetchProtected(`${CONFIG.API_BASE}/radios/remove`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ radio_id: radioId })
    }),
    playRadio: (radioId, guildId = null) => apiFetchProtected(`${CONFIG.API_BASE}/radios/play`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            radio_id: radioId,
            ...(guildId !== null && guildId !== undefined && guildId !== '' ? { guild_id: String(guildId) } : {}),
        })
    }),

    // Soundboard Management
    getSoundboard: () => apiFetch(`${CONFIG.API_BASE}/soundboard`),
    uploadSoundboard: async (formData) => {
        return apiFetchProtected(`${CONFIG.API_BASE}/soundboard/upload`, {
            method: 'POST',
            body: formData
        });
    },
    playSoundboard: (guildId, sfxId) => apiFetchProtected(`${CONFIG.API_BASE}/soundboard/play`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ guild_id: guildId, sfx_id: sfxId })
    }),
    deleteSoundboard: (sfxId) => apiFetchProtected(`${CONFIG.API_BASE}/soundboard/${sfxId}`, {
        method: 'DELETE'
    }),
    toggleFavoriteSoundboard: (sfxId, favorite) => apiFetchProtected(`${CONFIG.API_BASE}/soundboard/${sfxId}/favorite`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sfx_id: sfxId, favorite })
    }),
    updateVolumeSoundboard: (sfxId, volume) => apiFetchProtected(`${CONFIG.API_BASE}/soundboard/${sfxId}/volume`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sfx_id: sfxId, volume })
    })
};

export default API;
if (typeof window !== 'undefined' && !window.API) {
    window.API = API;
}
