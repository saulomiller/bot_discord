export const UI = {
    tm: null,

    setTranslationManager(tm) {
        this.tm = tm;
    },

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
        queue: document.getElementById('queue-list'),
        progress: {
            container: document.getElementById('progress-container'),
            fill: document.getElementById('progress-fill'),
            current: document.getElementById('current-time'),
            total: document.getElementById('total-time')
        }
    },

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        let icon = 'fa-info-circle';
        if (type === 'success') icon = 'fa-check-circle';
        if (type === 'error') icon = 'fa-exclamation-circle';

        toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${message}</span>`;
        this.elements.toastContainer?.appendChild(toast);

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

    formatTime(seconds) {
        if (!seconds) return '0:00';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    },

    updateStatus(data, isPaused) {
        const { statusInfo, player, queue, progress } = this.elements;
        const ready = !!data.is_ready;
        const statusKey = ready ? 'status_connected' : 'status_disconnected';
        const hasCurrentSong = !!(data.current_song && data.current_song.title);

        if (statusInfo.text) {
            statusInfo.text.textContent = this.tm ? this.tm.get(statusKey) : (ready ? 'Conectado' : 'Desconectado');
        }
        if (statusInfo.dot) {
            statusInfo.dot.style.background = ready ? '#30d158' : '#ff453a';
        }

        if (hasCurrentSong) {
            if (player.title) player.title.textContent = data.current_song.title;
            if (player.artist) player.artist.textContent = data.current_song.channel || '-';
            if (player.art) {
                player.art.src = data.current_song.thumbnail || '/static/disc.png';
            }
            if (player.hero) {
                if (!isPaused) player.hero.classList.add('playing');
                else player.hero.classList.remove('playing');
            }

            const percent = data.progress?.percent || 0;
            const current = data.progress?.current || 0;
            const duration = data.progress?.duration || 0;
            const showProgress = duration > 0;

            if (progress.container) progress.container.style.display = showProgress ? 'block' : 'none';
            if (progress.fill) {
                progress.fill.style.width = `${percent}%`;
                progress.fill.setAttribute('aria-valuenow', Math.round(percent));
                progress.fill.textContent = percent > 5 ? `${Math.round(percent)}%` : '';
            }
            if (progress.current) progress.current.textContent = this.formatTime(current);
            if (progress.total) progress.total.textContent = this.formatTime(duration);
        } else {
            if (player.title) {
                player.title.textContent = this.tm ? this.tm.get('no_song') : 'Nenhuma música';
            }
            if (player.artist) {
                player.artist.textContent = this.tm ? this.tm.get('waiting') : 'Aguardando comando...';
            }
            if (player.art) player.art.src = '/static/disc.png';
            if (player.hero) player.hero.classList.remove('playing');

            if (progress.container) progress.container.style.display = 'none';
            if (progress.fill) {
                progress.fill.style.width = '0%';
                progress.fill.setAttribute('aria-valuenow', '0');
                progress.fill.textContent = '';
            }
            if (progress.current) progress.current.textContent = '0:00';
            if (progress.total) progress.total.textContent = '0:00';
        }

        if (queue) {
            queue.innerHTML = '';
            if (data.queue && data.queue.length) {
                data.queue.forEach((q, idx) => {
                    const li = document.createElement('li');
                    li.className = 'queue-item';

                    const title = q.title || q;
                    const user = q.user || '';
                    const dur = q.duration ? ` - ${q.duration}` : '';

                    const titleWrap = document.createElement('div');
                    const strong = document.createElement('strong');
                    strong.textContent = `${idx + 1}. ${title}`;
                    titleWrap.appendChild(strong);

                    const meta = document.createElement('small');
                    meta.textContent = `${user}${dur}`;

                    li.appendChild(titleWrap);
                    li.appendChild(meta);
                    queue.appendChild(li);
                });
            } else {
                const emptyText = this.tm ? this.tm.get('queue_empty') : 'A fila está vazia.';
                const li = document.createElement('li');
                li.className = 'queue-item queue-empty';
                li.textContent = emptyText;
                queue.appendChild(li);
            }
        }

        if (player.playBtn) {
            const showPauseIcon = hasCurrentSong && !isPaused;
            player.playBtn.innerHTML = showPauseIcon
                ? '<i class="fa-solid fa-pause"></i>'
                : '<i class="fa-solid fa-play"></i>';

            const titleKey = hasCurrentSong ? (isPaused ? 'resume' : 'paused') : 'resume';
            player.playBtn.title = this.tm ? this.tm.get(titleKey) : (showPauseIcon ? 'Pausar' : 'Retomar');
        }
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
            const emptyKey = 'empty_playlists';
            const emptyText = this.tm ? this.tm.get(emptyKey) : 'Nenhuma playlist salva.';
            listEl.innerHTML = `<li class="empty-state">${emptyText}</li>`;
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
