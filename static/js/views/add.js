/* Smart upload (drag & drop + progress) and smart link import. */
import { api } from '../api.js';
import { esc, fmtDur, fmtSize, gradientFor, toast } from '../util.js';
import { I } from '../icons.js';
import { coverHtml } from '../ui.js';
import { navigate } from '../router.js';
import { Player } from '../player.js';

/* ---------------- Upload ---------------- */
export async function viewUpload() {
  const view = document.getElementById('view');
  document.title = 'Upload · TuneFlow';

  view.innerHTML = `
  <div class="page narrow">
    <h1 class="page-title">Smart upload</h1>
    <p class="muted lead">Drop audio files and TuneFlow extracts title, artist, album, genre, duration and cover art automatically — then you can tweak anything.</p>
    <div id="dropzone" class="dropzone">
      ${I.upload}
      <h3>Drag & drop audio files here</h3>
      <p class="muted">MP3 · FLAC · WAV · M4A · OGG · OPUS · WMA — up to 200 MB each</p>
      <button class="btn btn-grad" id="pick-btn">Choose files</button>
      <input id="file-input" type="file" multiple accept=".mp3,.m4a,.mp4,.flac,.wav,.ogg,.oga,.opus,.aac,.wma,audio/*" class="visually-hidden">
    </div>
    <div id="upload-results"></div>
  </div>`;

  const dz = view.querySelector('#dropzone');
  const input = view.querySelector('#file-input');
  const results = view.querySelector('#upload-results');

  view.querySelector('#pick-btn').onclick = () => input.click();
  dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('drag'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
  dz.addEventListener('drop', (e) => {
    e.preventDefault();
    dz.classList.remove('drag');
    handleFiles([...e.dataTransfer.files]);
  });
  input.addEventListener('change', () => { handleFiles([...input.files]); input.value = ''; });

  function xhrUpload(file, onProgress) {
    return new Promise((resolve, reject) => {
      const fd = new FormData();
      fd.append('file', file, file.name);
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/upload');
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
      xhr.onload = () => {
        try {
          const data = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) resolve(data);
          else reject(new Error(data.error || 'Upload failed.'));
        } catch { reject(new Error('Upload failed.')); }
      };
      xhr.onerror = () => reject(new Error('Network error during upload.'));
      xhr.send(fd);
    });
  }

  async function handleFiles(files) {
    if (!files.length) return;
    for (const file of files) {
      const rowId = 'up-' + Math.random().toString(36).slice(2);
      results.insertAdjacentHTML('beforeend', `
        <div class="up-row" id="${rowId}">
          <div class="up-name">${I.music}<span>${esc(file.name)}</span><span class="muted small">${fmtSize(file.size)}</span></div>
          <div class="progress"><div class="progress-bar" style="width:0%"></div></div>
          <div class="up-status muted small">Uploading…</div>
        </div>`);
      const rowEl = document.getElementById(rowId);
      const bar = rowEl.querySelector('.progress-bar');
      try {
        const data = await xhrUpload(file, (p) => { bar.style.width = Math.round(p * 100) + '%'; });
        rowEl.remove();
        if (data.errors && data.errors.length) data.errors.forEach((e) => toast(e, 'error'));
        (data.songs || []).forEach((song) => results.insertAdjacentHTML('beforeend', resultCard(song)));
        wireResultCards();
        if (data.songs && data.songs.length) {
          document.dispatchEvent(new CustomEvent('tf:sidebar-refresh'));
          toast(`Extracted metadata from ${file.name}.`);
        }
      } catch (e) {
        rowEl.querySelector('.progress').remove();
        rowEl.querySelector('.up-status').textContent = e.message;
        rowEl.classList.add('failed');
      }
    }
  }

  function resultCard(song) {
    return `
    <div class="up-card" data-id="${song.id}">
      ${coverHtml(song, 'medium')}
      <div class="up-fields">
        <div class="up-tagline">${I.check}<span>Added to library — extracted tags below, edit anything:</span></div>
        <div class="field-grid">
          <label class="field">Title<input data-f="title" value="${esc(song.title)}"></label>
          <label class="field">Artist<input data-f="artist" value="${esc(song.artist || '')}"></label>
          <label class="field">Album<input data-f="album" value="${esc(song.album || '')}"></label>
          <label class="field">Genre<input data-f="genre" value="${esc(song.genre || '')}"></label>
        </div>
        <div class="up-meta muted small">${song.duration ? fmtDur(song.duration) : ''} ${song.source === 'upload' ? '' : ''}</div>
      </div>
      <div class="up-actions">
        <button class="btn btn-ghost sm" data-play>${I.play}<span>Play</span></button>
        <button class="btn btn-grad sm" data-save>Save</button>
      </div>
    </div>`;
  }

  function wireResultCards() {
    results.querySelectorAll('.up-card').forEach((card) => {
      if (card.dataset.wired) return;
      card.dataset.wired = '1';
      const id = +card.dataset.id;
      const song = { id, title: card.querySelector('[data-f="title"]').value, cover: card.querySelector('img')?.getAttribute('src') || null };
      card.querySelector('[data-play]').onclick = async () => {
        try {
          const data = await api(`/api/songs?q=&sort=created_at&order=desc`);
          const fresh = data.songs.find((s) => s.id === id);
          if (fresh) Player.play([fresh], id);
        } catch (e) { toast(e.message, 'error'); }
      };
      card.querySelector('[data-save]').onclick = async () => {
        try {
          await api(`/api/songs/${id}`, {
            method: 'PATCH',
            body: {
              title: card.querySelector('[data-f="title"]').value.trim(),
              artist: card.querySelector('[data-f="artist"]').value.trim(),
              album: card.querySelector('[data-f="album"]').value.trim(),
              genre: card.querySelector('[data-f="genre"]').value.trim(),
            },
          });
          toast('Saved.');
          card.querySelector('[data-save]').textContent = 'Saved ✓';
        } catch (e) { toast(e.message, 'error'); }
      };
    });
  }
}

/* ---------------- Import ---------------- */
export async function viewImport() {
  const view = document.getElementById('view');
  document.title = 'Import a link · TuneFlow';

  view.innerHTML = `
  <div class="page narrow">
    <h1 class="page-title">Import from a link</h1>
    <p class="muted lead">YouTube and SoundCloud links play through their official embeds — nothing is pirated or downloaded. Direct audio URLs are downloaded to your server after you confirm you have the rights.</p>
    <form id="import-form" class="import-bar">
      <div class="search-box grow">${I.link}<input id="import-url" type="url" required placeholder="Paste a YouTube / SoundCloud / direct audio URL"></div>
      <button class="btn btn-grad" type="submit">Detect</button>
    </form>
    <div id="import-preview"></div>
  </div>`;

  const form = view.querySelector('#import-form');
  const urlInput = view.querySelector('#import-url');
  const preview = view.querySelector('#import-preview');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const url = urlInput.value.trim();
    if (!url) return;
    preview.innerHTML = '<div class="skeleton-block"></div>';
    try {
      const res = await api('/api/import/preview', { method: 'POST', body: { url } });
      renderPreview(res);
    } catch (err) {
      preview.innerHTML = `<div class="import-note error">${I.x}<span>${esc(err.message)}</span></div>`;
    }
  });

  function renderPreview({ kind, info, url }) {
    if (kind === 'youtube' || kind === 'soundcloud') {
      const label = kind === 'youtube' ? 'YouTube' : 'SoundCloud';
      preview.innerHTML = `
      <div class="import-card">
        ${info.thumbnail ? `<img class="ic-thumb" src="${esc(info.thumbnail)}" alt="">` : ''}
        <div class="ic-main">
          <span class="chip">${I.embed}<span>Official ${label} embed</span></span>
          <label class="field">Title<input id="im-title" value="${esc(info.title || `Untitled ${label} track`)}"></label>
          <label class="field">Artist / channel<input id="im-artist" value="${esc(info.artist || label)}"></label>
          <div class="import-note">${I.shield}<span>Plays through ${label}'s official player. The audio is never downloaded or stored.</span></div>
        </div>
        <div class="up-actions"><button class="btn btn-grad" id="im-go">${I.plus}<span>Add to library</span></button></div>
      </div>`;
      preview.querySelector('#im-go').onclick = async () => {
        await confirmImport(url, {
          title: preview.querySelector('#im-title').value.trim(),
          artist: preview.querySelector('#im-artist').value.trim(),
        }, `${label} embed added — find it in your library.`);
      };
      return;
    }

    // direct audio
    preview.innerHTML = `
    <div class="import-card">
      <div class="ic-main">
        <span class="chip">${I.download}<span>Direct audio file</span></span>
        <div class="file-line muted">${esc(info.filename || url)} ${info.size ? '· ' + fmtSize(info.size) : ''} ${info.content_type ? '· ' + esc(info.content_type) : ''}</div>
        <label class="field">Title <span class="muted">(optional)</span><input id="im-title" placeholder="Leave empty to use file tags"></label>
        <label class="field">Artist <span class="muted">(optional)</span><input id="im-artist" placeholder="Leave empty to use file tags"></label>
        <label class="rights">
          <input type="checkbox" id="im-rights">
          <span>${I.shield}<span>I confirm I have the rights to download and keep a copy of this audio on my own server.</span></span>
        </label>
      </div>
      <div class="up-actions"><button class="btn btn-grad" id="im-go" disabled>${I.download}<span>Download & add</span></button></div>
    </div>`;
    const cb = preview.querySelector('#im-rights');
    const go = preview.querySelector('#im-go');
    cb.addEventListener('change', () => { go.disabled = !cb.checked; });
    go.onclick = async () => {
      await confirmImport(url, {
        rights_confirmed: cb.checked,
        title: preview.querySelector('#im-title').value.trim(),
        artist: preview.querySelector('#im-artist').value.trim(),
      }, 'Downloaded and added to your library.');
    };
  }

  async function confirmImport(url, body, successMsg) {
    try {
      const res = await api('/api/import/confirm', { method: 'POST', body: { url, ...body } });
      const song = res.song;
      document.dispatchEvent(new CustomEvent('tf:sidebar-refresh'));
      preview.innerHTML = `
      <div class="import-card success">
        ${coverHtml(song, 'medium')}
        <div class="ic-main">
          <span class="chip ok">${I.check}<span>${esc(res.note || successMsg)}</span></span>
          <div class="s-title big">${esc(song.title)}</div>
          <div class="s-artist muted">${esc(song.artist || '')}</div>
        </div>
        <div class="up-actions">
          <button class="btn btn-grad" id="im-play">${I.play}<span>Play</span></button>
          <a class="btn btn-ghost" href="#/library">Open library</a>
        </div>
      </div>`;
      preview.querySelector('#im-play').onclick = () => Player.play([song], song.id);
      toast(res.note || successMsg);
    } catch (err) {
      toast(err.message, 'error');
    }
  }
}
