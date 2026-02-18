export const CONFIG = {
    API_BASE: '/api',
    POLLING_INTERVAL: 1500,  // Reduzido de 3000ms para 1500ms para atualização mais rápida
    ANIMATION: {
        SMOOTHING: 0.2,
        BAR_COUNT: 64
    },
    TOAST_DURATION: 4000,
    API_KEY: null  // Preenchido automaticamente em runtime via /api/get_api_key
};
