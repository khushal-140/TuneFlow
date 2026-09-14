/* Dashboard / home feed. */
import { api } from '../api.js';
import { esc, gradientFor } from '../util.js';
import { I } from '../icons.js';
import { songCard, playlistCard, section, emptyState } from '../ui.js';
import { Player } from '../player.js';
import { navigate } from '../router.js';

function greeting() {
  const h = new Date().getHours();
  if (h < 5) return 'Up late';
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}

export async function viewHome() {
  const view = document.getElementById('view');
  document.title = 'Home · TuneFlow';
  view.innerHTML = '<div class="skeleton-block"></div>';
  const data = await api('/api/home');
  const { stats } = data;

  if (!stats.songs) {
    view.innerHTML = `
      <div class="page">
        <h1 class="page-title">${greeting()}.</h1>
        <p class="muted lead">Your library is empty — let's put some music in it.</p>
        <div class="onboard-grid">
          <a class="onboard-card" href="#/upload">${I.upload}<h3>Upload audio</h3><p class="muted">Drop in MP3, FLAC, WAV, M4A… titles, artists and cover art are extracted automatically.</p></a>
          <a class="onboard-card" href="#/import">${I.link}<h3>Import a link</h3><p class="muted">Paste a YouTube or SoundCloud link to play through the official embed, or a direct audio URL.</p></a>
          <a class="onboard-card" href="#/assistant">${I.sparkles}<h3>Ask the assistant</h3><p class="muted">Once you have music, ask for “a 30-minute study playlist” — it reads your library.</p></a>
        </div>
      </div>`;
    return;
  }

  const statChips = `
    <div class="stat-row">
      <div class="stat"><b>${stats.songs}</b><span>songs</span></div>
      <div class="stat"><b>${stats.liked}</b><span>liked</span></div>
      <div class="stat"><b>${stats.playlists}</b><span>playlists</span></div>
      <div class="stat"><b>${stats.plays}</b><span>plays</span></div>
      <div class="stat"><b>${stats.minutes}</b><span>minutes listened</span></div>
    </div>`;

  const quick = `
    <div class="quick-row">
      <button class="quick" data-go="#/upload">${I.upload}<span>Upload</span></button>
      <button class="quick" data-go="#/import">${I.link}<span>Import link</span></button>
      <button class="quick accent" data-go="#/assistant">${I.sparkles}<span>Ask the AI</span></button>
    </div>`;

  const taste = (data.taste || []).map((t) =>
    `<span class="chip taste">${t.type === 'artist' ? I.user : I.music}<span>${esc(t.label)}</span></span>`).join('');

  const carouseel = (songs, { reason = false, id } = {}) =>
    `<div class="hscroll" ${id ? `id="${id}"` : ''}>${songs.map((s) => songCard(s, { reason })).join('')}</div>`;

  const tasteChips = data.rec_mode === 'personalized' && taste
    ? `<div class="taste-row"><span class="muted small">Your taste:</span>${taste}</div>` : '';

  view.innerHTML = `
  <div class="page">
    <div class="home-hero">
      <div>
        <h1 class="page-title">${greeting()}, ${esc(data.user ? data.user.username : '')}.</h1>
        <p class="muted lead">${data.rec_mode === 'personalized'
          ? 'Made for you from what you play and like.'
          : 'Play and like a few tracks and recommendations will start tuning themselves to you.'}</p>
      </div>
      ${quick}
    </div>
    ${statChips}
    ${data.recent.length ? section('Jump back in', carouseel(data.recent, { id: 'sec-recent' })) : ''}
    ${data.recommended.length ? section('Made for you', carouseel(data.recommended, { reason: true, id: 'sec-recs' })) : ''}
    ${tasteChips}
    ${data.playlists.length ? section('Your playlists', `<div class="hscroll">${data.playlists.map(playlistCard).join('')}</div>`) : ''}
    ${data.new_additions.length ? section('Recently added', carouseel(data.new_additions, { id: 'sec-new' })) : ''}
  </div>`;

  view.querySelectorAll('[data-go]').forEach((b) => { b.onclick = () => navigate(b.dataset.go); });
  view.querySelectorAll('[data-cardplay]').forEach((b) => {
    b.onclick = (e) => {
      e.preventDefault();
      const id = +b.dataset.cardplay;
      const card = b.closest('.hscroll');
      const list = [...card.querySelectorAll('.song-card')].map((c) => +c.dataset.id)
        .map((sid) => findSong(data, sid)).filter(Boolean);
      Player.play(list, id);
    };
  });
}

function findSong(data, id) {
  for (const key of ['recent', 'recommended', 'new_additions']) {
    const s = (data[key] || []).find((x) => x.id === id);
    if (s) return s;
  }
  return null;
}
