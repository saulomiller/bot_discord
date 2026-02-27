// Modulo: gerencia radios no frontend, incluindo CRUD e reproducao.

// radios.js - Gerenciador de Rádios
/**
 * Servico de UI para gerenciamento de radios no dashboard.
 */
export class RadioManager {
    constructor(api, ui, updateCallback, translationManager, getGuildId) {
        this.api = api;
        this.ui = ui;
        this.updateCallback = updateCallback;
        this.tm = translationManager;
        this.getGuildId = getGuildId;
        this.radios = [];
    }

    /**
     * Inicializa o modulo de radios, carregando dados e listeners.
     * @returns {Promise<void>}
     */
    async init() {
        await this.loadRadios();
        this.setupEventListeners();
    }

    /**
     * Carrega radios cadastradas a partir da API e renderiza a lista.
     * @returns {Promise<void>}
     */
    async loadRadios() {
        try {
            const data = await this.api.getRadios();
            this.radios = data.radios || [];
            this.render();
        } catch (error) {
            console.error('Erro ao carregar rádios:', error);
        }
    }

    render() {
        const list = document.getElementById('radios-list');
        if (!list) return;

        list.innerHTML = '';

        if (this.radios.length === 0) {
            const emptyText = this.tm ? this.tm.get('no_radios') : 'Nenhuma rádio disponível';
            list.innerHTML = `<li style="text-align: center; color: rgba(255,255,255,0.5); padding: 20px;">${emptyText}</li>`;
            return;
        }

        this.radios.forEach(radio => {
            const li = document.createElement('li');
            li.className = 'radio-item';
            li.innerHTML = `
                <div class="radio-info">
                    <strong>${radio.name}</strong>
                    ${radio.location ? `<span class="radio-location">${radio.location}</span>` : ''}
                </div>
                <div class="radio-actions">
                    <button class="btn-small radio-play" data-id="${radio.id}">
                        <i class="fa-solid fa-play"></i>
                    </button>
                    ${radio.custom ? `<button class="btn-small danger radio-delete" data-id="${radio.id}">
                        <i class="fa-solid fa-trash"></i>
                    </button>` : ''}
                </div>
            `;
            list.appendChild(li);
        });
    }

    setupEventListeners() {
        // Botão adicionar rádio
        const addBtn = document.getElementById('add-radio-btn');
        if (addBtn) {
            addBtn.addEventListener('click', () => {
                document.getElementById('radio-modal').classList.add('active');
            });
        }

        // Fechar modal
        const cancelBtn = document.getElementById('cancel-radio-btn');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => {
                document.getElementById('radio-modal').classList.remove('active');
            });
        }

        // Form submit
        const form = document.getElementById('radio-form');
        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                await this.addRadio();
            });
        }

        // Event delegation para botões
        const list = document.getElementById('radios-list');
        if (list) {
            list.addEventListener('click', async (e) => {
                const playBtn = e.target.closest('.radio-play');
                const deleteBtn = e.target.closest('.radio-delete');

                if (playBtn) {
                    const radioId = playBtn.dataset.id;
                    await this.playRadio(radioId);
                } else if (deleteBtn) {
                    const radioId = deleteBtn.dataset.id;
                    await this.deleteRadio(radioId);
                }
            });
        }
    }

    /**
     * Envia os dados do formulario para criar uma nova radio.
     * @returns {Promise<void>}
     */
    async addRadio() {
        const name = document.getElementById('radio-name').value;
        const url = document.getElementById('radio-url').value;
        const location = document.getElementById('radio-location').value;
        const description = document.getElementById('radio-description').value;

        try {
            await this.api.addRadio({ name, url, location, description });
            this.ui.showToast(this.tm ? this.tm.get('radio_added_toast') : 'Rádio adicionada!', 'success');
            await this.loadRadios();
            document.getElementById('radio-modal').classList.remove('active');
            document.getElementById('radio-form').reset();
        } catch (error) {
            console.error('Erro ao adicionar rádio:', error);
            this.ui.showToast(error.message || 'Erro ao adicionar rádio', 'error');
        }
    }

    /**
     * Solicita reproducao de uma radio no servidor selecionado.
     * @param {string} radioId
     * @returns {Promise<void>}
     */
    async playRadio(radioId) {
        const guildId = this.getGuildId ? this.getGuildId() : null;
        if (!guildId) {
            this.ui.showToast(this.tm ? this.tm.get('guild_id_error') : 'Guild ID não configurado', 'error');
            return;
        }

        try {
            await this.api.playRadio(radioId, guildId);
            this.ui.showToast(this.tm ? this.tm.get('radio_playing_toast') : `Tocando rádio...`, 'success');
            // Atualizar imediatamente após tocar rádio
            if (this.updateCallback) {
                setTimeout(() => this.updateCallback(), 500);
            }
        } catch (error) {
            console.error('Erro ao tocar rádio:', error);
            this.ui.showToast(error.message || 'Erro ao tocar rádio', 'error');
        }
    }

    /**
     * Remove uma radio customizada apos confirmacao do usuario.
     * @param {string} radioId
     * @returns {Promise<void>}
     */
    async deleteRadio(radioId) {
        const confirmMsg = this.tm ? this.tm.get('radio_delete_confirm') : 'Deletar esta rádio?';
        if (!confirm(confirmMsg)) return;

        try {
            await this.api.removeRadio(radioId);
            this.ui.showToast(this.tm ? this.tm.get('radio_removed_toast') : 'Rádio removida', 'success');
            await this.loadRadios();
        } catch (error) {
            console.error('Erro ao deletar rádio:', error);
            const err = this.tm ? this.tm.get('radio_delete_error') : 'Erro ao deletar rádio';
            this.ui.showToast(err, 'error');
        }
    }
}
