export class RadioManager {
    constructor(api, ui) {
        this.api = api;
        this.ui = ui;
        this.radios = {};
        this.modal = null;
        this.radiosList = null;
    }

    async init() {
        this.modal = document.getElementById('radio-modal');
        this.radiosList = document.getElementById('radios-list');

        this.setupEventListeners();
        await this.loadRadios();
    }

    setupEventListeners() {
        // Botão adicionar rádio
        const addBtn = document.getElementById('add-radio-btn');
        if (addBtn) {
            addBtn.addEventListener('click', () => this.showAddModal());
        }

        // Botão cancelar modal
        const cancelBtn = document.getElementById('cancel-radio-btn');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => this.hideModal());
        }

        // Formulário de adicionar rádio
        const form = document.getElementById('radio-form');
        if (form) {
            form.addEventListener('submit', (e) => this.handleAddRadio(e));
        }

        // Fechar modal ao clicar fora
        if (this.modal) {
            this.modal.addEventListener('click', (e) => {
                if (e.target === this.modal) {
                    this.hideModal();
                }
            });
        }
    }

    async loadRadios() {
        try {
            const data = await this.api.getRadios();
            this.radios = data.radios || {};
            this.renderRadiosList();
        } catch (err) {
            console.error('Erro ao carregar rádios:', err);
            this.ui.showToast('Erro ao carregar rádios', 'error');
        }
    }

    renderRadiosList() {
        if (!this.radiosList) return;

        const radiosArray = Object.entries(this.radios);

        if (radiosArray.length === 0) {
            this.radiosList.innerHTML = '<li class="empty-state">Nenhuma rádio cadastrada</li>';
            return;
        }

        this.radiosList.innerHTML = radiosArray.map(([id, radio]) => `
            <li class="radio-item">
                <div class="radio-info">
                    <div class="radio-name">
                        <i class="fa-solid fa-radio"></i>
                        <strong>${this.escapeHtml(radio.name)}</strong>
                    </div>
                    <div class="radio-details">
                        <span class="radio-location">
                            <i class="fa-solid fa-location-dot"></i>
                            ${this.escapeHtml(radio.location)}
                        </span>
                        <span class="radio-description">${this.escapeHtml(radio.description)}</span>
                    </div>
                </div>
                <div class="radio-actions">
                    <button class="btn-icon play-radio-btn" data-radio-id="${id}" title="Tocar">
                        <i class="fa-solid fa-play"></i>
                    </button>
                    <button class="btn-icon remove-radio-btn" data-radio-id="${id}" title="Remover">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </li>
        `).join('');

        // Adicionar event listeners aos botões
        this.radiosList.querySelectorAll('.play-radio-btn').forEach(btn => {
            btn.addEventListener('click', () => this.playRadio(btn.dataset.radioId));
        });

        this.radiosList.querySelectorAll('.remove-radio-btn').forEach(btn => {
            btn.addEventListener('click', () => this.removeRadio(btn.dataset.radioId));
        });
    }

    showAddModal() {
        if (this.modal) {
            this.modal.classList.add('active');
            // Focar no primeiro input
            const firstInput = this.modal.querySelector('#radio-name');
            if (firstInput) firstInput.focus();
        }
    }

    hideModal() {
        if (this.modal) {
            this.modal.classList.remove('active');
            // Limpar formulário
            const form = document.getElementById('radio-form');
            if (form) form.reset();
        }
    }

    async handleAddRadio(e) {
        e.preventDefault();

        const nameInput = document.getElementById('radio-name');
        const urlInput = document.getElementById('radio-url');
        const locationInput = document.getElementById('radio-location');
        const descriptionInput = document.getElementById('radio-description');

        const radioData = {
            name: nameInput.value.trim(),
            url: urlInput.value.trim(),
            location: locationInput.value.trim() || 'Desconhecido',
            description: descriptionInput.value.trim() || 'Rádio personalizada'
        };

        if (!radioData.name || !radioData.url) {
            this.ui.showToast('Nome e URL são obrigatórios', 'error');
            return;
        }

        try {
            const result = await this.api.addRadio(radioData);
            this.radios = result.radios || {};
            this.renderRadiosList();
            this.hideModal();
            this.ui.showToast(result.message || 'Rádio adicionada!', 'success');
        } catch (err) {
            console.error('Erro ao adicionar rádio:', err);
            this.ui.showToast(err.message || 'Erro ao adicionar rádio', 'error');
        }
    }

    async playRadio(radioId) {
        try {
            const result = await this.api.playRadio(radioId);
            this.ui.showToast(result.message || 'Rádio iniciada!', 'success');
        } catch (err) {
            console.error('Erro ao tocar rádio:', err);
            this.ui.showToast(err.message || 'Erro ao tocar rádio', 'error');
        }
    }

    async removeRadio(radioId) {
        const radio = this.radios[radioId];
        if (!radio) return;

        if (!confirm(`Deseja realmente remover a rádio "${radio.name}"?`)) {
            return;
        }

        try {
            const result = await this.api.removeRadio(radioId);
            this.radios = result.radios || {};
            this.renderRadiosList();
            this.ui.showToast(result.message || 'Rádio removida!', 'success');
        } catch (err) {
            console.error('Erro ao remover rádio:', err);
            this.ui.showToast(err.message || 'Erro ao remover rádio', 'error');
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}
