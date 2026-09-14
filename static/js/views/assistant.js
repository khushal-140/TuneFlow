/* AI assistant: chat UI over the rule-based library search. */
import { api } from '../api.js';
import { esc, fmtDur, gradientFor, toast } from '../util.js';
import { I } from '../icons.js';
import { Player } from '../player.js';
import { coverHtml } from '../ui.js';

const log = [];   // {role:'user'|'ai', text?, tracks?, playlist_name?, saved?}
let examplesLoaded = false;

export async function viewAssistant() {
  const view = document.getElementById('view');
  document.title = 'AI Assistant · TuneFlow';

  view.innerHTML = `
  <div class="page chat-page">
    <div class="chat-head">
      <div class="chat-orb">${I.sparkles}</div>
      <div>
        <h1 class="page-title">Assistant</h1>
        <p class="muted small">Understands moods, activities and durations — and searches only <b>your</b> library. No external AI, just smart parsing.</p>
      </div>
    </div>
    <div id="chat-log" class="chat-log"></div>
    <div class="chat-suggest" id="chat-suggest"></div>
    <form id="chat-form" class="chat-input">
      <input id="chat-text" type="text" autocomplete="off" placeholder="e.g. Make me a 30-minute study playlist">
      <button class="btn btn-grad" type="submit" title="Send">${I.send}</button>
    </form>
  </div>`;

  const logEl = view.querySelector('#chat-log');
  const suggestEl = view.querySelector('#chat-suggest');
  const input = view.querySelector('#chat-text');

  if (!examplesLoaded) {
    try {
      const { examples } = await api('/api/assistant/examples');
      suggestEl.innerHTML = examples.map((x) => `<button class="chip suggest">${esc(x)}</button>`).join('');
      suggestEl.querySelectorAll('.suggest').forEach((b) => {
        b.onclick = () => { input.value = b.textContent; send(); };
      });
      examplesLoaded = true;
    } catch { /* ignore */ }
  }

  function renderLog() {
    if (!log.length) {
      logEl.innerHTML = `<div class="chat-ai"><div class="bubble">Hi! Tell me what you feel like hearing — a mood, an activity, an artist, or a length like "30 minutes" — and I'll build it from your library.</div></div>`;
      return;
    }
    logEl.innerHTML = log.map((m) => m.role === 'user'
      ? `<div class="chat-user"><div class="bubble">${esc(m.text)}</div></div>`
      : aiBubble(m)).join('');
    logEl.scrollTop = logEl.scrollHeight;
  }

  function aiBubble(m) {
    const tracks = (m.tracks || []).map((s, i) => `
      <button class="mini-track" data-play="${s.id}">
        ${coverHtml(s, 'tiny')}
        <span class="mt-main"><span class="s-title">${esc(s.title)}</span><span class="s-artist muted">${esc(s.artist || '')}</span></span>
        <span class="muted small">${s.duration ? fmtDur(s.duration) : 'embed'}</span>
        <span class="mt-play">${I.play}</span>
      </button>`).join('');
    const saveBtn = m.tracks && m.tracks.length
      ? `<div class="bubble-actions">
           <button class="btn btn-ghost sm" data-playall>${I.play}<span>Play all</span></button>
           <button class="btn btn-grad sm" data-save ${m.saved ? 'disabled' : ''}>${I.plus}<span>${m.saved ? 'Saved' : `Save as “${esc(m.playlist_name || 'My Mix')}”`}</span></button>
         </div>`
      : '';
    return `<div class="chat-ai"><div class="bubble"><p>${esc(m.text)}</p>${tracks ? `<div class="mt-list">${tracks}</div>` : ''}${saveBtn}</div></div>`;
  }

  async function send(presetText) {
    const text = (presetText || input.value).trim();
    if (!text) return;
    input.value = '';
    log.push({ role: 'user', text });
    log.push({ role: 'typing' });
    renderLog();
    const t0 = Date.now();
    try {
      const res = await api('/api/assistant', { method: 'POST', body: { message: text } });
      const wait = Math.max(0, 450 - (Date.now() - t0));
      setTimeout(() => {
        log.pop(); // typing
        log.push({ role: 'ai', text: res.reply, tracks: res.tracks, playlist_name: res.playlist_name });
        renderLog();
        wireBubble(res);
      }, wait);
    } catch (e) {
      log.pop();
      log.push({ role: 'ai', text: e.message || 'Something went wrong.' });
      renderLog();
    }
  }

  function wireBubble(res) {
    const bubbles = logEl.querySelectorAll('.chat-ai .bubble');
    const bubble = bubbles[bubbles.length - 1];
    if (!bubble) return;
    bubble.querySelectorAll('[data-play]').forEach((b) => {
      b.onclick = () => Player.play(res.tracks, +b.dataset.play);
    });
    const playAll = bubble.querySelector('[data-playall]');
    if (playAll) playAll.onclick = () => { if (res.tracks.length) Player.play(res.tracks, res.tracks[0].id); };
    const save = bubble.querySelector('[data-save]');
    if (save && !res.saved) {
      save.onclick = async () => {
        try {
          const created = await api('/api/playlists', { method: 'POST', body: { name: res.playlist_name || 'My Mix' } });
          await api(`/api/playlists/${created.playlist.id}/songs`, { method: 'POST', body: { song_ids: res.tracks.map((s) => s.id) } });
          res.saved = true;
          save.disabled = true;
          save.innerHTML = `${I.check}<span>Saved</span>`;
          document.dispatchEvent(new CustomEvent('tf:sidebar-refresh'));
          toast(`Saved "${created.playlist.name}" with ${res.tracks.length} songs.`);
        } catch (e) { toast(e.message, 'error'); }
      };
    }
  }

  view.querySelector('#chat-form').addEventListener('submit', (e) => { e.preventDefault(); send(); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });
  renderLog();
  input.focus();
}
