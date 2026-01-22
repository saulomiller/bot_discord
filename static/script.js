// static/script.js
// Integração frontend <-> FastAPI do bot.py
// Endpoints (existentes no bot.py): /api/status, /api/play, /api/pause, /api/resume, /api/skip, /api/set_token, /queue
// Referência: bot.py já expõe esses endpoints. :contentReference[oaicite:4]{index=4}

const statusIndicator = document.getElementById('status-indicator');
const statusText = document.getElementById('status-text');
const dot = statusIndicator.querySelector('.dot');

const songTitle = document.getElementById('song-title');
const songArtist = document.getElementById('song-artist');
const albumArt = document.getElementById('album-art-img');
const queueList = document.getElementById('queue-list');

const playBtn = document.getElementById('play-btn');
const pauseResumeBtn = document.getElementById('pause-resume-btn');
const skipBtn = document.getElementById('skip-btn');
const musicInput = document.getElementById('music-input');

const saveTokenBtn = document.getElementById('save-token-btn');
const tokenInput = document.getElementById('token-input');

const uploadPlaylistBtn = document.getElementById('upload-playlist-btn');
const playlistUpload = document.getElementById('playlist-upload');

let isPaused = false;

// Helper generic
async function apiFetch(path, opts = {}) {
  try {
    const res = await fetch(path, opts);
    if (!res.ok) {
      const txt = await res.text();
      throw new Error(`${res.status} ${res.statusText} - ${txt}`);
    }
    return await res.json().catch(()=> ({}));
  } catch (err) {
    console.error('API error', err);
    throw err;
  }
}

// Atualiza UI com /api/status
async function updateStatus() {
  try {
    const data = await apiFetch('/api/status');
    // Exibir estado de conexão básico
    const ready = data.is_ready;
    statusText.textContent = ready ? `Conectado como ${data.bot_user}` : 'Desconectado';
    dot.style.background = ready ? '#2ecc71' : '#ff6b6b';
    isPaused = !!data.is_paused;

    // Música atual
    if (data.current_song) {
      songTitle.textContent = data.current_song.title || 'Desconhecido';
      songArtist.textContent = data.current_song.channel || '—';
      if (data.current_song.thumbnail) albumArt.src = data.current_song.thumbnail;
    } else {
      songTitle.textContent = 'Nenhuma música tocando';
      songArtist.textContent = 'Use o campo abaixo para adicionar uma';
      albumArt.src = 'https://i.imgur.com/eF90msA.png';
    }

    // Fila
    queueList.innerHTML = '';
    if (data.queue && data.queue.length) {
      data.queue.forEach((q, idx) => {
        const li = document.createElement('li');
        li.className = 'queue-item';
        li.innerHTML = `<div><strong>${idx+1}.</strong> ${q.title || q}</div><small>${q.user||''} ${q.duration?'• '+q.duration:''}</small>`;
        queueList.appendChild(li);
      });
    } else {
      const li = document.createElement('li');
      li.className = 'queue-item';
      li.textContent = 'A fila está vazia.';
      queueList.appendChild(li);
    }

    // Atualiza botão pausar/retomar
    pauseResumeBtn.innerHTML = isPaused
        ? '<i class="fa-solid fa-play"></i>'
        : '<i class="fa-solid fa-pause"></i>';
    pauseResumeBtn.title = isPaused ? 'Retomar' : 'Pausar';

  } catch (err) {
    statusText.textContent = 'Erro ao conectar';
    dot.style.background = '#999';
    console.error(err);
  }
}

// Eventos UI
playBtn.addEventListener('click', async () => {
  const search = musicInput.value.trim();
  if (!search) return alert('Digite o nome ou URL da música.');
  playBtn.disabled = true;
  try {
    await apiFetch('/api/play', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({search})
    });
    musicInput.value = '';
    await updateStatus();
  } catch (err) {
    alert('Erro ao adicionar a música. Veja o console.');
  } finally { playBtn.disabled = false; }
});

pauseResumeBtn.addEventListener('click', async () => {
  pauseResumeBtn.disabled = true;
  try {
    if (isPaused) {
      await apiFetch('/api/resume', {method:'POST'});
    } else {
      await apiFetch('/api/pause', {method:'POST'});
    }
    await updateStatus();
  } catch (err) {
    alert('Erro ao alterar estado de reprodução.');
  } finally { pauseResumeBtn.disabled = false; }
});

skipBtn.addEventListener('click', async () => {
  skipBtn.disabled = true;
  try {
    await apiFetch('/api/skip', {method:'POST'});
    await updateStatus();
  } catch (err) {
    alert('Erro ao pular a música.');
  } finally { skipBtn.disabled = false; }
});

// Salvar token (ATENÇÃO: inseguro — usado apenas em rede local)
if (saveTokenBtn && tokenInput) {
    saveTokenBtn.addEventListener('click', async () => {
        const token = tokenInput.value;

        if (!token) {
            alert('Por favor, insira um token antes de salvar.');
            return;
        }

        // Feedback visual temporário
        const originalButtonText = saveTokenBtn.textContent;
        saveTokenBtn.textContent = 'Salvando...';
        saveTokenBtn.disabled = true;

        try {
            const result = await apiFetch('/api/set_token', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: token }),
            });
            // A API retorna uma mensagem de sucesso que podemos exibir
            alert(result.message || 'Token salvo com sucesso. O bot irá iniciar/reiniciar.');
        } catch (error) {
            console.error('Erro na requisição para salvar o token:', error);
            alert('Erro ao salvar o token. Verifique o console para mais detalhes.');
        } finally {
            // Restaura o botão
            saveTokenBtn.textContent = originalButtonText;
            saveTokenBtn.disabled = false;
        }
    });
}

// Upload playlist (simples): envia cada linha ao /api/play sequencialmente
uploadPlaylistBtn.addEventListener('click', async () => {
  const file = playlistUpload.files[0];
  if (!file) return alert('Escolha um arquivo .txt de playlist.');
  uploadPlaylistBtn.disabled = true;
  try {
    const text = await file.text();
    // cada linha não vazia vira um search
    const lines = text.split('\n').map(s=>s.trim()).filter(s=>s && !s.startsWith('#'));
    if (!lines.length) { alert('Playlist vazia.'); uploadPlaylistBtn.disabled=false; return; }
    // adiciona sequencialmente com pequenas pausas para evitar timeouts
    for (const line of lines) {
      await apiFetch('/api/play', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({search: line})
      });
      await new Promise(r => setTimeout(r, 300)); // throttle leve
    }
    alert(`Enviadas ${lines.length} entradas para a fila.`);
    await updateStatus();
  } catch (err) {
    console.error(err);
    alert('Erro ao enviar playlist.');
  } finally { uploadPlaylistBtn.disabled = false; }
});

// Polling periódico do status
updateStatus();
setInterval(updateStatus, 5000); // a cada 5s
