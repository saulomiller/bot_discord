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
    shutdown: () => apiFetch(`${CONFIG.API_BASE}/shutdown`, { method: 'POST' })
};
