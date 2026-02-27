// Modulo: disponibiliza utilitarios de frontend como formatacao e debounce.

/**
 * Converte segundos para formato m:ss.
 * @param {number} seconds
 * @returns {string}
 */
export function formatTime(seconds) {
    if (!seconds) return '0:00';
    const min = Math.floor(seconds / 60);
    const sec = Math.floor(seconds % 60);
    return `${min}:${sec.toString().padStart(2, '0')}`;
}

/**
 * Cria uma funcao com atraso para reduzir chamadas repetidas.
 * @param {Function} func
 * @param {number} wait
 * @returns {Function}
 */
export function debounce(func, wait) {
    let timeout;
    return function (...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}
