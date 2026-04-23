// Modulo: gerencia soundboard no frontend, incluindo listagem e acoes.

// soundboard.js - Gerenciador de Soundboard
/**
 * Servico de UI para gerenciamento de efeitos da soundboard.
 */
export class SoundboardManager {
    constructor(api, ui, updateCallback, translationManager) {
        this.api = api;
        this.ui = ui;
        this.updateCallback = updateCallback;
        this.tm = translationManager;
        this.soundboard = [];
        this.currentGuildId = null;
    }

    /**
     * Inicializa o modulo com o servidor ativo e listeners de tela.
     * @param {string|null} guildId
     * @returns {Promise<void>}
     */
    async init(guildId) {
        this.currentGuildId = guildId;
        await this.loadSoundboard();
        this.setupEventListeners();
    }

    /**
     * Carrega os efeitos cadastrados e atualiza a grade visual.
     * @returns {Promise<void>}
     */
    async loadSoundboard() {
        try {
            const data = await this.api.getSoundboard();
            this.soundboard = data.soundboard || [];
            this.render();
        } catch (error) {
            console.error('Erro ao carregar soundboard:', error);
            const errMsg = error?.message || 'Erro ao carregar soundboard';
            this.ui.showToast(errMsg, 'error');
        }
    }

    render() {
        const grid = document.getElementById('soundboard-grid');
        if (!grid) return;

        grid.innerHTML = '';

        if (this.soundboard.length === 0) {
            const emptyText = this.tm ? this.tm.get('no_sfx') : 'Nenhum efeito sonoro. Faça upload!';
            const empty = document.createElement('p');
            empty.className = 'empty-state';
            empty.textContent = emptyText;
            grid.appendChild(empty);
            return;
        }

        this.soundboard.forEach(sfx => {
            const card = document.createElement('div');
            card.className = `sfx-card${sfx.favorite ? ' favorite' : ''}`;
            const volume = typeof sfx.volume === 'number' ? sfx.volume : 1.0;
            const favTitle = sfx.favorite ? (this.tm ? this.tm.get('sfx_favorite_remove') : 'Remover dos favoritos') : (this.tm ? this.tm.get('sfx_favorite_add') : 'Adicionar aos favoritos');
            const testTitle = this.tm ? this.tm.get('sfx_test_title') : 'Testar (ouvir no navegador)';
            const playTitle = this.tm ? this.tm.get('sfx_play_discord_title') : 'Tocar no Discord';
            const deleteTitle = this.tm ? this.tm.get('sfx_delete_title') : 'Deletar';

            const favorite = document.createElement('i');
            favorite.className = `fa-solid fa-star sfx-favorite-icon${sfx.favorite ? ' active' : ''}`;
            favorite.dataset.id = String(sfx.id ?? '');
            favorite.title = favTitle;

            const icon = document.createElement('div');
            icon.className = 'sfx-icon';
            icon.textContent = '🔊';

            const name = document.createElement('div');
            name.className = 'sfx-name';
            name.textContent = String(sfx.name ?? '');

            const volumeControl = document.createElement('div');
            volumeControl.className = 'sfx-volume-control';

            const lowVolumeIcon = document.createElement('i');
            lowVolumeIcon.className = 'fa-solid fa-volume-low';
            lowVolumeIcon.style.fontSize = '12px';

            const slider = document.createElement('input');
            slider.type = 'range';
            slider.className = 'sfx-volume-slider';
            slider.dataset.id = String(sfx.id ?? '');
            slider.min = '0';
            slider.max = '2';
            slider.step = '0.1';
            slider.value = String(volume);

            const volumeValue = document.createElement('span');
            volumeValue.className = 'sfx-volume-value';
            volumeValue.textContent = `${Math.round(volume * 100)}%`;

            volumeControl.appendChild(lowVolumeIcon);
            volumeControl.appendChild(slider);
            volumeControl.appendChild(volumeValue);

            const actions = document.createElement('div');
            actions.className = 'sfx-actions';

            const testButton = document.createElement('button');
            testButton.className = 'sfx-test';
            testButton.dataset.id = String(sfx.id ?? '');
            testButton.title = testTitle;
            const testIcon = document.createElement('i');
            testIcon.className = 'fa-solid fa-headphones';
            testButton.appendChild(testIcon);

            const playButton = document.createElement('button');
            playButton.className = 'sfx-play';
            playButton.dataset.id = String(sfx.id ?? '');
            playButton.title = playTitle;
            const playIcon = document.createElement('i');
            playIcon.className = 'fa-solid fa-play';
            playButton.appendChild(playIcon);

            const deleteButton = document.createElement('button');
            deleteButton.className = 'sfx-delete';
            deleteButton.dataset.id = String(sfx.id ?? '');
            deleteButton.title = deleteTitle;
            const deleteIcon = document.createElement('i');
            deleteIcon.className = 'fa-solid fa-trash';
            deleteButton.appendChild(deleteIcon);

            actions.appendChild(testButton);
            actions.appendChild(playButton);
            actions.appendChild(deleteButton);

            card.appendChild(favorite);
            card.appendChild(icon);
            card.appendChild(name);
            card.appendChild(volumeControl);
            card.appendChild(actions);

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

    /**
     * Envia um novo efeito sonoro para upload.
     * @returns {Promise<void>}
     */
    async uploadSFX() {
        const fileInput = document.getElementById('sfx-file');
        const file = fileInput.files[0];

        if (!file) {
            this.ui.showToast(this.tm ? this.tm.get('sfx_select_file_toast') : 'Selecione um arquivo', 'error');
            return;
        }

        const formData = new FormData();
        formData.append('file', file, file.name);

        try {
            await this.api.uploadSoundboard(formData);
            this.ui.showToast(this.tm ? this.tm.get('sfx_upload_success_toast') : 'Upload concluído!', 'success');
            await this.loadSoundboard();
            document.getElementById('sfx-upload-modal').classList.remove('active');
            this.resetUploadForm();
        } catch (error) {
            console.error('Erro no upload:', error);
            this.ui.showToast(error.message || 'Erro no upload', 'error');
        }
    }

    /**
     * Reproduz um efeito localmente no navegador para pre-escuta.
     * @param {string} sfxId
     * @returns {Promise<void>}
     */
    async testSFX(sfxId) {
        // Tocar localmente no navegador
        try {
            // Buscar o SFX da lista local para obter a extensão correta
            const sfx = this.soundboard.find(s => s.id === sfxId);
            const filename = sfx && sfx.filename ? sfx.filename : `${sfxId}.mp3`;
            const audio = new Audio(`/api/soundboard/file/${encodeURIComponent(filename)}`);
            audio.play().catch(err => {
                console.error('Erro ao testar áudio:', err);
                const errMsg = this.tm ? this.tm.get('sfx_test_error_toast') : 'Erro ao reproduzir áudio';
                this.ui.showToast(errMsg, 'error');
            });
        } catch (error) {
            console.error('Erro ao testar SFX:', error);
            this.ui.showToast('Erro ao testar áudio', 'error');
        }
    }

    /**
     * Solicita reproducao do efeito no Discord.
     * @param {string} sfxId
     * @returns {Promise<void>}
     */
    async playSFX(sfxId) {
        // Tocar no Discord
        if (!this.currentGuildId) {
            const err = this.tm ? this.tm.get('guild_id_error') : 'Guild ID não configurado';
            this.ui.showToast(err, 'error');
            return;
        }

        try {
            await this.api.playSoundboard(this.currentGuildId, sfxId);
            const msg = this.tm ? this.tm.get('sfx_playing_discord_toast').replace('{name}', sfxId) : `Tocando no Discord: ${sfxId}`;
            this.ui.showToast(msg, 'success');
            // Não precisa atualizar status pois soundboard não afeta current_song
        } catch (error) {
            console.error('Erro ao tocar SFX:', error);
            this.ui.showToast(error.message || 'Erro ao tocar efeito', 'error');
        }
    }

    /**
     * Remove um efeito cadastrado apos confirmacao.
     * @param {string} sfxId
     * @returns {Promise<void>}
     */
    async deleteSFX(sfxId) {
        const confirmMsg = this.tm ? this.tm.get('sfx_delete_confirm').replace('{name}', sfxId) : `Deletar "${sfxId}"?`;
        if (!confirm(confirmMsg)) return;

        try {
            await this.api.deleteSoundboard(sfxId);
            this.ui.showToast(this.tm ? this.tm.get('sfx_deleted_toast') : 'Efeito deletado', 'success');
            await this.loadSoundboard();
        } catch (error) {
            console.error('Erro ao deletar:', error);
            this.ui.showToast('Erro ao deletar', 'error');
        }
    }

    /**
     * Marca ou desmarca um efeito como favorito.
     * @param {string} sfxId
     * @param {boolean} favorite
     * @returns {Promise<void>}
     */
    async toggleFavorite(sfxId, favorite) {
        try {
            await this.api.toggleFavoriteSoundboard(sfxId, favorite);
            await this.loadSoundboard();
        } catch (error) {
            console.error('Erro ao atualizar favorito:', error);
            this.ui.showToast('Erro ao atualizar favorito', 'error');
        }
    }

    /**
     * Persiste o volume padrao de um efeito sonoro.
     * @param {string} sfxId
     * @param {number} volume
     * @returns {Promise<void>}
     */
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
