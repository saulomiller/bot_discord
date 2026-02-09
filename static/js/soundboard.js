// soundboard.js - Gerenciador de Soundboard
export class SoundboardManager {
    constructor(api, ui, updateCallback) {
        this.api = api;
        this.ui = ui;
        this.updateCallback = updateCallback;  // Callback para atualizar status
        this.soundboard = [];
        this.currentGuildId = null;
    }

    async init(guildId) {
        this.currentGuildId = guildId;
        await this.loadSoundboard();
        this.setupEventListeners();
    }

    async loadSoundboard() {
        try {
            const data = await this.api.getSoundboard();
            this.soundboard = data.soundboard || [];
            this.render();
        } catch (error) {
            console.error('Erro ao carregar soundboard:', error);
            this.ui.showToast('Erro ao carregar soundboard', 'error');
        }
    }

    render() {
        const grid = document.getElementById('soundboard-grid');
        if (!grid) return;

        grid.innerHTML = '';

        if (this.soundboard.length === 0) {
            grid.innerHTML = '<p style="text-align: center; color: rgba(255,255,255,0.5); padding: 20px;">Nenhum efeito sonoro. Faça upload!</p>';
            return;
        }

        this.soundboard.forEach(sfx => {
            const card = document.createElement('div');
            card.className = `sfx-card${sfx.favorite ? ' favorite' : ''}`;
            card.innerHTML = `
                <i class="fa-solid fa-star sfx-favorite-icon${sfx.favorite ? ' active' : ''}" 
                   data-id="${sfx.id}" 
                   title="${sfx.favorite ? 'Remover dos favoritos' : 'Adicionar aos favoritos'}"></i>
                <div class="sfx-icon">🔊</div>
                <div class="sfx-name">${sfx.name}</div>
                <div class="sfx-volume-control">
                    <i class="fa-solid fa-volume-low" style="font-size: 12px;"></i>
                    <input type="range" 
                           class="sfx-volume-slider" 
                           data-id="${sfx.id}" 
                           min="0" 
                           max="2" 
                           step="0.1" 
                           value="${sfx.volume || 1.0}">
                    <span class="sfx-volume-value">${Math.round((sfx.volume || 1.0) * 100)}%</span>
                </div>
                <div class="sfx-actions">
                    <button class="sfx-test" data-id="${sfx.id}" title="Testar (ouvir no navegador)">
                        <i class="fa-solid fa-headphones"></i>
                    </button>
                    <button class="sfx-play" data-id="${sfx.id}" title="Tocar no Discord">
                        <i class="fa-solid fa-play"></i>
                    </button>
                    <button class="sfx-delete" data-id="${sfx.id}" title="Deletar">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            `;

            grid.appendChild(card);
        });
    }

    setupEventListeners() {
        // Upload button
        const uploadBtn = document.getElementById('upload-sfx-btn');
        if (uploadBtn) {
            uploadBtn.addEventListener('click', () => {
                document.getElementById('sfx-upload-modal').classList.add('active');
            });
        }

        // Close modal
        const closeBtn = document.getElementById('close-upload-modal');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                document.getElementById('sfx-upload-modal').classList.remove('active');
                this.resetUploadForm();
            });
        }

        // File preview
        const fileInput = document.getElementById('sfx-file');
        if (fileInput) {
            fileInput.addEventListener('change', (e) => {
                const file = e.target.files[0];
                if (file) {
                    this.previewAudio(file);
                }
            });
        }

        // Upload form
        const uploadForm = document.getElementById('sfx-upload-form');
        if (uploadForm) {
            uploadForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                await this.uploadSFX();
            });
        }

        // Event delegation para botões do grid
        const grid = document.getElementById('soundboard-grid');
        if (grid) {
            grid.addEventListener('click', async (e) => {
                const favoriteIcon = e.target.closest('.sfx-favorite-icon');
                const testBtn = e.target.closest('.sfx-test');
                const playBtn = e.target.closest('.sfx-play');
                const deleteBtn = e.target.closest('.sfx-delete');

                if (favoriteIcon) {
                    const sfxId = favoriteIcon.dataset.id;
                    const isFavorite = favoriteIcon.classList.contains('active');
                    await this.toggleFavorite(sfxId, !isFavorite);
                } else if (testBtn) {
                    const sfxId = testBtn.dataset.id;
                    await this.testSFX(sfxId);
                } else if (playBtn) {
                    const sfxId = playBtn.dataset.id;
                    await this.playSFX(sfxId);
                } else if (deleteBtn) {
                    const sfxId = deleteBtn.dataset.id;
                    await this.deleteSFX(sfxId);
                }
            });

            // Volume sliders
            grid.addEventListener('input', async (e) => {
                if (e.target.classList.contains('sfx-volume-slider')) {
                    const sfxId = e.target.dataset.id;
                    const volume = parseFloat(e.target.value);

                    // Atualizar display
                    const valueSpan = e.target.parentElement.querySelector('.sfx-volume-value');
                    if (valueSpan) {
                        valueSpan.textContent = `${Math.round(volume * 100)}%`;
                    }
                }
            });

            grid.addEventListener('change', async (e) => {
                if (e.target.classList.contains('sfx-volume-slider')) {
                    const sfxId = e.target.dataset.id;
                    const volume = parseFloat(e.target.value);
                    await this.updateVolume(sfxId, volume);
                }
            });
        }
    }

    previewAudio(file) {
        const preview = document.getElementById('audio-preview');
        const audio = document.getElementById('preview-audio');

        if (preview && audio) {
            const url = URL.createObjectURL(file);
            audio.src = url;
            preview.style.display = 'block';
        }
    }

    resetUploadForm() {
        const form = document.getElementById('sfx-upload-form');
        const preview = document.getElementById('audio-preview');
        const audio = document.getElementById('preview-audio');

        if (form) form.reset();
        if (preview) preview.style.display = 'none';
        if (audio) {
            audio.pause();
            audio.src = '';
        }
    }

    async uploadSFX() {
        const fileInput = document.getElementById('sfx-file');
        const file = fileInput.files[0];

        if (!file) {
            this.ui.showToast('Selecione um arquivo', 'error');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        try {
            await this.api.uploadSoundboard(formData);
            this.ui.showToast('Upload concluído!', 'success');
            await this.loadSoundboard();
            document.getElementById('sfx-upload-modal').classList.remove('active');
            this.resetUploadForm();
        } catch (error) {
            console.error('Erro no upload:', error);
            this.ui.showToast(error.message || 'Erro no upload', 'error');
        }
    }

    async testSFX(sfxId) {
        // Tocar localmente no navegador
        try {
            const audio = new Audio(`/data/soundboard/${sfxId}.mp3`);
            audio.play().catch(err => {
                console.error('Erro ao testar áudio:', err);
                this.ui.showToast('Erro ao reproduzir áudio', 'error');
            });
        } catch (error) {
            console.error('Erro ao testar SFX:', error);
            this.ui.showToast('Erro ao testar áudio', 'error');
        }
    }

    async playSFX(sfxId) {
        // Tocar no Discord
        if (!this.currentGuildId) {
            this.ui.showToast('Guild ID não configurado', 'error');
            return;
        }

        try {
            await this.api.playSoundboard(this.currentGuildId, sfxId);
            this.ui.showToast(`Tocando no Discord: ${sfxId}`, 'success');
            // Não precisa atualizar status pois soundboard não afeta current_song
        } catch (error) {
            console.error('Erro ao tocar SFX:', error);
            this.ui.showToast(error.message || 'Erro ao tocar efeito', 'error');
        }
    }

    async deleteSFX(sfxId) {
        if (!confirm(`Deletar "${sfxId}"?`)) return;

        try {
            await this.api.deleteSoundboard(sfxId);
            this.ui.showToast('Efeito deletado', 'success');
            await this.loadSoundboard();
        } catch (error) {
            console.error('Erro ao deletar:', error);
            this.ui.showToast('Erro ao deletar', 'error');
        }
    }

    async toggleFavorite(sfxId, favorite) {
        try {
            await this.api.toggleFavoriteSoundboard(sfxId, favorite);
            await this.loadSoundboard();
        } catch (error) {
            console.error('Erro ao atualizar favorito:', error);
            this.ui.showToast('Erro ao atualizar favorito', 'error');
        }
    }

    async updateVolume(sfxId, volume) {
        try {
            await this.api.updateVolumeSoundboard(sfxId, volume);
            // Não precisa recarregar, já atualizou o display
        } catch (error) {
            console.error('Erro ao atualizar volume:', error);
            this.ui.showToast('Erro ao atualizar volume', 'error');
        }
    }
}
