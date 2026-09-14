/* Liked songs + listening history. */
import { api } from '../api.js';
import { esc, relTime } from '../util.js';
import { I } from '../icons.js';
import { songRow, listHead, emptyState, bindSongList, registerList, coverHtml } from '../ui.js';
import { Player } from '../player.js';
import { refresh } from '../router.js';

export async function viewLiked() {
  const view = document.getElementById('view');
  document.title = 'Liked songs · TuneFlow';
  view.innerHTML = '<div class="skeleton-block"></div>';
  const { songs } = await api('/api/likes');
  const hue = 340;

  view.innerHTML = `
  <div class="page">
    <div class="pl-hero" style="background:linear-gradient(135deg, hsl(${hue},60%,34%), hsl(${(hue + 50) % 360},60%,14%))">
      <div class="pl-hero-art liked">${I.heartFill}</div>
      <div class="pl-hero-meta">
        <span class="small caps">Collection</span>
        <h1>Liked songs</h1>
        <p class="muted">Everything you've hearted, in one place.</p>
        <div class="muted small">${songs.length} song${songs.length === 1 ? '' : 's'}</div>
      </div>
      <div class="pl-hero-actions">
        <button id="lk-play" class="btn btn-grad lg" ${songs.length ? '' : 'disabled'}>${I.play}<span>Play</span></button>
      </div>
    </div>
    <div id="lk-list" class="song-list">
      ${songs.length ? listHead() + songs.map((s, i) => songRow(s, i)).join('') : emptyState('No liked songs yet', 'Tap the heart on any track and it lands here.')}
    </div>
  </div>`;

  registerList('liked', () => songs);
  bindSongList(view.querySelector('#lk-list'), () => songs, { onChanged: () => refresh() });
  view.querySelector('#lk-play').onclick = () => { if (songs.length) Player.play(songs, songs[0].id); };
}

export async function viewHistory() {
  const view = document.getElementById('view');
  document.title = 'History · TuneFlow';
  view.innerHTML = '<div class="skeleton-block"></div>';
  const { history } = await api('/api/history?limit=200');

  view.innerHTML = `
  <div class="page">
    <div class="page-head"><h1 class="page-title">Listening history</h1>
      <span class="muted small">${history.length ? 'Your last ' + history.length + ' plays' : ''}</span></div>
    <div id="h-list" class="history-list">
      ${history.length ? history.map((h) => historyRow(h)).join('')
        : emptyState('Nothing played yet', 'Play something and your history will build up here — it also feeds the recommender.')}
    </div>
  </div>`;

  registerList('history', () => history.map((h) => h.song).filter(Boolean));
  const list = view.querySelector('#h-list');
  list.addEventListener('click', (e) => {
    const row = e.target.closest('.h-row');
    if (!row || e.target.closest('[data-like]') || e.target.closest('[data-menu]')) return;
    const id = +row.dataset.id;
    const songs = history.map((h) => h.song).filter(Boolean);
    if (songs.some((s) => s.id === id)) Player.play(songs, id);
  });
  list.addEventListener('click', (e) => {
    const menuBtn = e.target.closest('[data-menu]');
    if (!menuBtn) return;
    e.preventDefault();
    const id = +menuBtn.dataset.menu;
    const song = history.map((h) => h.song).find((s) => s && s.id === id);
    if (!song) return;
    import('../ui.js').then(({ songMenu }) => songMenu(song, menuBtn, { list: history.map((h) => h.song).filter(Boolean), onChanged: () => refresh() }));
  });
}

function historyRow(h) {
  const s = h.song;
  if (!s) return '';
  return `
  <div class="h-row song-row" data-id="${s.id}">
    <div class="h-time muted small">${I.clock}<span>${esc(relTime(h.played_at))}</span></div>
    ${coverHtml(s, 'small')}
    <div class="s-main">
      <div class="s-title">${esc(s.title)}</div>
      <div class="s-artist">${esc(s.artist || '')}</div>
    </div>
    <div class="s-genre">${s.genre ? `<span class="chip">${esc(s.genre)}</span>` : ''}</div>
    <div class="s-dur">${s.duration ? fmt(s.duration) : '—'}</div>
    <div class="s-actions">
      <button class="icon-btn heart${s.liked ? ' active' : ''}" data-like="${s.id}">${s.liked ? I.heartFill : I.heart}</button>
      <button class="icon-btn" data-menu="${s.id}">${I.dots}</button>
    </div>
  </div>`;
}

function fmt(s) {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}
