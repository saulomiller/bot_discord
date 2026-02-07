export const UI = {
    elements: {
        toastContainer: document.getElementById('toast-container'),
        sidebar: document.getElementById('settings-sidebar'),
        sidebarOverlay: document.getElementById('sidebar-overlay'),
        statusInfo: {
            text: document.getElementById('status-text'),
            dot: document.querySelector('#status-indicator .dot'),
            pill: document.getElementById('status-indicator')
        },
        player: {
            title: document.getElementById('song-title'),
            artist: document.getElementById('song-artist'),
            art: document.getElementById('album-art-img'),
            hero: document.querySelector('.card-hero'),
            playBtn: document.getElementById('pause-resume-btn'),
            volumeSlider: document.getElementById('volume-slider')
        },
        queue: document.getElementById('queue-list')
    },

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        let icon = 'fa-info-circle';
        if (type === 'success') icon = 'fa-check-circle';
        if (type === 'error') icon = 'fa-exclamation-circle';

        toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${message}</span>`;
        this.elements.toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('hide');
            toast.addEventListener('animationend', () => toast.remove());
        }, 4000);
    },

    toggleSidebar() {
        if (!this.elements.sidebar) return;
        const isOpen = this.elements.sidebar.classList.contains('open');

        if (isOpen) {
            this.elements.sidebar.classList.remove('open');
            this.elements.sidebarOverlay?.classList.remove('active');
        } else {
            this.elements.sidebar.classList.add('open');
            this.elements.sidebarOverlay?.classList.add('active');
        }
    },

    updateStatus(data, isPaused) {
        const { statusInfo, player, queue } = this.elements;
        const ready = data.is_ready;

        statusInfo.text.textContent = ready ? `Conectado` : 'Desconectado';
        statusInfo.dot.style.background = ready ? '#30d158' : '#ff453a';

        // Informações da Música
        if (data.current_song && data.current_song.title) {
            player.title.textContent = data.current_song.title;
            player.artist.textContent = data.current_song.channel || '—';
            if (data.current_song.thumbnail) player.art.src = data.current_song.thumbnail;
            else player.art.src = '/static/disc.png';

            if (!isPaused) player.hero.classList.add('playing');
            else player.hero.classList.remove('playing');
        } else {
            player.title.textContent = 'Nenhuma música';
            player.artist.textContent = 'Aguardando comando...';
            player.art.src = '/static/disc.png';
            player.hero.classList.remove('playing');
        }

        // Fila
        queue.innerHTML = '';
        if (data.queue && data.queue.length) {
            data.queue.forEach((q, idx) => {
                const li = document.createElement('li');
                li.className = 'queue-item';
                const title = q.title || q;
                const user = q.user || '';
                const dur = q.duration ? ` • ${q.duration}` : '';
                li.innerHTML = `<div><strong>${idx + 1}. ${title}</strong></div><small>${user}${dur}</small>`;
                queue.appendChild(li);
            });
        } else {
            queue.innerHTML = '<li class="queue-item queue-empty">A fila está vazia.</li>';
        }

        // Ícone do Botão Play
        player.playBtn.innerHTML = isPaused
            ? '<i class="fa-solid fa-play"></i>'
            : '<i class="fa-solid fa-pause"></i>';
        player.playBtn.title = isPaused ? 'Retomar' : 'Pausar';
    },

    setVolumeVisual(vol) {
        if (this.elements.player.volumeSlider) {
            this.elements.player.volumeSlider.value = vol;
        }
    },

    updatePlaylistList(playlists) {
        const listEl = document.getElementById('playlist-history-list');
        if (!listEl) return;

        if (!playlists || playlists.length === 0) {
            listEl.innerHTML = '<li class="empty-state">Nenhuma playlist salva.</li>';
            return;
        }

        listEl.innerHTML = playlists.map(name =>
            `<li class="playlist-item">
                <i class="fa-solid fa-music"></i>
                <span>${name}</span>
            </li>`
        ).join('');
    }
};
