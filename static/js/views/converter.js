/* MP3 Converter: paste a YouTube URL, convert to MP3 (yt-dlp + ffmpeg) into your library. */
import { api } from '../api.js';
import { esc, fmtDur, toast, openModal, closeModal } from '../util.js';
import { I } from '../icons.js';
import { songCard, emptyState, registerList } from '../ui.js';
import { Player } from '../player.js';

const JOB_KEY = 'tf-convert-job';
let pollTimer = null;

export async function viewConverter() {
  const view = document.getElementById('view');
  document.title = 'MP3 Converter · TuneFlow';

  view.innerHTML = `
  <div class="page narrow">
    <h1 class="page-title">MP3 Converter</h1>
    <p class="muted lead">Paste a YouTube link and TuneFlow converts it to a 192 kbps MP3 on your own server — tags and cover art embedded — then adds it straight to your library, offline and yours.</p>

    <div class="import-note">${I.shield}<span>Only download audio you have the rights to keep — your own uploads, Creative-Commons or licensed content. YouTube's terms restrict downloading other content.</span></div>

    <div id="cv-access" class="cv-access"></div>

    <form id="cv-form" class="import-bar">
      <div class="search-box grow">${I.link}<input id="cv-url" type="url" required placeholder="Paste a YouTube video URL"></div>
      <button class="btn btn-grad" type="submit" id="cv-detect">Detect</button>
    </form>
    <div id="cv-preview"></div>
    <div id="cv-progress"></div>

    <section class="section">
      <div class="section-head"><h2>Downloaded from YouTube</h2><span class="muted small" id="cv-count"></span></div>
      <div id="cv-downloads"><div class="skeleton-block"></div></div>
    </section>
  </div>`;

  const previewEl = view.querySelector('#cv-preview');
  const progressEl = view.querySelector('#cv-progress');
  const form = view.querySelector('#cv-form');
  const urlInput = view.querySelector('#cv-url');
  let currentPreview = null;

  loadDownloadList(view);
  resumeActiveJob(view, progressEl);
  renderAccess();

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const url = urlInput.value.trim();
    if (!url) return;
    previewEl.innerHTML = '<div class="skeleton-block"></div>';
    try {
      const res = await api('/api/convert/preview', { method: 'POST', body: { url } });
      currentPreview = res.preview;
      renderPreview(previewEl, currentPreview, progressEl);
    } catch (err) {
      previewEl.innerHTML = `<div class="import-note error">${I.x}<span>${esc(err.message)}</span></div>`;
      if (/not a bot|cookies/i.test(err.message)) {
        previewEl.insertAdjacentHTML('beforeend',
          `<div class="cv-fix-row"><button class="btn btn-grad sm" id="cv-fix-cookies">${I.shield}<span>Paste cookies now</span></button></div>`);
        previewEl.querySelector('#cv-fix-cookies').onclick = openCookieModal;
      }
    }
  });
}

function renderAccess() {
  const el = document.getElementById('cv-access');
  if (!el) return;
  api('/api/convert/cookies').then(({ set, source }) => {
    el.innerHTML = `
      <div class="cv-access-row">
        <span class="chip ${set ? 'ok' : 'warn'}">${set ? I.check : I.shield}
          <span>${set
            ? (source === 'ui' ? 'YouTube cookies active (saved on this server)' : 'YouTube cookies active (server environment)')
            : 'No YouTube cookies — cloud servers get blocked by YouTube\u2019s bot check'}</span>
        </span>
        <button class="btn btn-ghost sm" id="cv-cookies-btn">${set ? 'Update' : 'Configure'} cookies</button>
      </div>`;
    el.querySelector('#cv-cookies-btn').onclick = openCookieModal;
  }).catch(() => {});
}

async function openCookieModal() {
  let st = { set: false };
  try { st = await api('/api/convert/cookies'); } catch { /* ignore */ }
  const m = openModal(`
    <h3 class="modal-title">YouTube cookies</h3>
    <p class="muted small">Cloud servers (Render) are blocked by YouTube's bot check — your own PC is not.
    Export your browser's cookies for <b>youtube.com</b> using the free <b>"Get cookies.txt LOCALLY"</b>
    browser extension, then paste the whole file below. It is stored only on your own server, never sent anywhere else.</p>
    <textarea id="ck-content" class="cookie-box" placeholder="# Netscape HTTP Cookie File …" spellcheck="false"></textarea>
    <div class="modal-actions">
      ${st.set ? '<button class="btn btn-danger sm" data-clear>Remove saved cookies</button>' : ''}
      <button class="btn btn-ghost" data-x>Cancel</button>
      <button class="btn btn-grad" data-ok>Save cookies</button>
    </div>`);
  m.querySelector('[data-ok]').onclick = async () => {
    try {
      const res = await api('/api/convert/cookies', { method: 'POST', body: { content: m.querySelector('#ck-content').value } });
      closeModal();
      toast(res.message || 'Cookies saved.');
      renderAccess();
    } catch (e) { toast(e.message, 'error'); }
  };
  const clr = m.querySelector('[data-clear]');
  if (clr) clr.onclick = async () => {
    try {
      await api('/api/convert/cookies', { method: 'DELETE' });
      closeModal();
      toast('Cookies removed.');
      renderAccess();
    } catch (e) { toast(e.message, 'error'); }
  };
  m.querySelector('[data-x]').onclick = closeModal;
  m.querySelector('#ck-content').focus();
}

function renderPreview(previewEl, p, progressEl) {
  previewEl.innerHTML = `
  <div class="import-card">
    ${p.thumbnail ? `<img class="ic-thumb" src="${esc(p.thumbnail)}" alt="">` : ''}
    <div class="ic-main">
      <span class="chip">${I.download}<span>YouTube video · ${fmtDur(p.duration)} · ${esc(p.uploader || '')}</span></span>
      <label class="field">Title<input id="cv-title" value="${esc(p.title)}" maxlength="255"></label>
      <label class="field">Artist<input id="cv-artist" value="${esc(p.artist)}" maxlength="255"></label>
      <label class="field">Genre <span class="muted">(optional)</span><input id="cv-genre" placeholder="e.g. Gujarati, Lo-Fi, Rock" maxlength="64"></label>
      <label class="rights">
        <input type="checkbox" id="cv-rights">
        <span>${I.shield}<span>I confirm I have the rights to download and keep this audio on my personal server, and I understand it will be saved as an MP3 in my library.</span></span>
      </label>
    </div>
    <div class="up-actions"><button class="btn btn-grad" id="cv-go" disabled>${I.download}<span>Convert to MP3</span></button></div>
  </div>`;

  const rights = previewEl.querySelector('#cv-rights');
  const go = previewEl.querySelector('#cv-go');
  rights.addEventListener('change', () => { go.disabled = !rights.checked; });

  go.onclick = async () => {
    try {
      go.disabled = true;
      const res = await api('/api/convert/start', {
        method: 'POST',
        body: {
          url: p.webpage_url,
          rights_confirmed: rights.checked,
          title: previewEl.querySelector('#cv-title').value.trim(),
          artist: previewEl.querySelector('#cv-artist').value.trim(),
          genre: previewEl.querySelector('#cv-genre').value.trim(),
        },
      });
      localStorage.setItem(JOB_KEY, res.job_id);
      runProgress(progressEl, res.job_id);
    } catch (err) {
      toast(err.message, 'error');
      go.disabled = false;
    }
  };
}

function runProgress(progressEl, jobId) {
  const view = document.getElementById('view');
  const previewHolder = document.getElementById('cv-preview');
  if (previewHolder) previewHolder.innerHTML = '';
  progressEl.innerHTML = `
  <div class="import-card converting">
    <div class="ic-main">
      <span class="chip">${I.download}<span>Converting…</span></span>
      <div class="progress big"><div class="progress-bar" id="cv-bar" style="width:2%"></div></div>
      <div class="cv-stage muted small" id="cv-stage">Starting…</div>
    </div>
  </div>`;

  if (pollTimer) clearInterval(pollTimer);
  const tick = async () => {
    let st;
    try {
      st = await api(`/api/convert/status/${jobId}`);
    } catch {
      return; // transient network hiccup — keep polling
    }
    const bar = progressEl.querySelector('#cv-bar');
    const stage = progressEl.querySelector('#cv-stage');
    if (bar) bar.style.width = Math.max(2, st.percentage) + '%';
    if (stage) stage.textContent = `${st.stage} — ${Math.round(st.percentage)}%`;

    if (st.error) {
      clearInterval(pollTimer);
      pollTimer = null;
      localStorage.removeItem(JOB_KEY);
      progressEl.innerHTML = `<div class="import-note error">${I.x}<span>${esc(st.error)}</span></div>`;
      return;
    }
    if (st.done && st.song) {
      clearInterval(pollTimer);
      pollTimer = null;
      localStorage.removeItem(JOB_KEY);
      const s = st.song;
      progressEl.innerHTML = `
      <div class="import-card success">
        ${s.cover ? `<img class="cover medium" src="${esc(s.cover)}" alt="">` : ''}
        <div class="ic-main">
          <span class="chip ok">${I.check}<span>MP3 saved to your library — offline and tagged.</span></span>
          <div class="s-title big">${esc(s.title)}</div>
          <div class="s-artist muted">${esc(s.artist || '')} ${s.duration ? '· ' + fmtDur(s.duration) : ''}</div>
        </div>
        <div class="up-actions">
          <button class="btn btn-grad" id="cv-play">${I.play}<span>Play</span></button>
          <a class="btn btn-ghost" href="#/library">Open library</a>
        </div>
      </div>`;
      progressEl.querySelector('#cv-play').onclick = () => Player.play([s], s.id);
      document.dispatchEvent(new CustomEvent('tf:sidebar-refresh'));
      loadDownloadList(view);
      toast(`"${s.title}" converted and added to your library.`);
    }
  };
  tick();
  pollTimer = setInterval(tick, 900);
}

function resumeActiveJob(view, progressEl) {
  const jobId = localStorage.getItem(JOB_KEY);
  if (!jobId) return;
  api(`/api/convert/status/${jobId}`).then((st) => {
    if (st.done) { localStorage.removeItem(JOB_KEY); return; }
    runProgress(progressEl, jobId);
  }).catch(() => localStorage.removeItem(JOB_KEY));
}

async function loadDownloadList(view) {
  const wrap = view.querySelector('#cv-downloads');
  const count = view.querySelector('#cv-count');
  if (!wrap) return;
  try {
    const data = await api('/api/songs?source=ytdownload&sort=created_at&order=desc');
    registerList('converter-downloads', () => data.songs);
    if (count) count.textContent = data.total ? `${data.total} MP3${data.total === 1 ? '' : 's'} offline` : '';
    if (!data.total) {
      wrap.innerHTML = emptyState('No converted MP3s yet', 'Convert your first YouTube link above and it will appear here — stored on your server, playable offline.');
      return;
    }
    wrap.innerHTML = `<div class="hscroll">${data.songs.map((s) => songCard(s)).join('')}</div>`;
    wrap.querySelectorAll('[data-cardplay]').forEach((b) => {
      b.onclick = (e) => {
        e.preventDefault();
        Player.play(data.songs, +b.dataset.cardplay);
      };
    });
  } catch (err) {
    wrap.innerHTML = `<div class="import-note error">${I.x}<span>${esc(err.message)}</span></div>`;
  }
}
