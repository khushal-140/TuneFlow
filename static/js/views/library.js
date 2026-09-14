/* Library: search, filter, sort over the user's songs. */
import { api } from '../api.js';
import { esc, debounce } from '../util.js';
import { I } from '../icons.js';
import { songRow, listHead, emptyState, bindSongList, registerList } from '../ui.js';

const state = { q: '', genre: '', artist: '', sort: 'created_at', order: 'desc', songs: [] };

export async function viewLibrary(_params, query = {}) {
  const view = document.getElementById('view');
  document.title = 'Library · TuneFlow';
  if (query.q !== undefined) state.q = query.q;

  view.innerHTML = `
  <div class="page">
    <div class="page-head">
      <h1 class="page-title">Your library</h1>
      <div class="toolbar">
        <div class="search-box">${I.search}<input id="lib-q" type="search" placeholder="Search songs, artists, albums…" value="${esc(state.q)}"></div>
        <select id="lib-genre" class="select"><option value="">All genres</option></select>
        <select id="lib-artist" class="select"><option value="">All artists</option></select>
        <select id="lib-sort" class="select">
          <option value="created_at">Recently added</option>
          <option value="title">Title</option>
          <option value="artist">Artist</option>
          <option value="album">Album</option>
          <option value="play_count">Most played</option>
          <option value="duration">Duration</option>
        </select>
        <button id="lib-order" class="icon-btn" title="Toggle sort direction"></button>
      </div>
    </div>
    <div id="lib-count" class="muted small pad-y"></div>
    <div id="lib-list" class="song-list">${listHead()}</div>
  </div>`;

  const q = view.querySelector('#lib-q');
  const genreSel = view.querySelector('#lib-genre');
  const artistSel = view.querySelector('#lib-artist');
  const sortSel = view.querySelector('#lib-sort');
  const orderBtn = view.querySelector('#lib-order');
  sortSel.value = state.sort;

  const orderIcon = () => { orderBtn.textContent = state.order === 'desc' ? '↓' : '↑'; };
  orderIcon();

  api('/api/songs/facets').then(({ genres, artists }) => {
    if (!document.body.contains(genreSel)) return;
    genreSel.innerHTML = '<option value="">All genres</option>' + genres.map((g) => `<option ${g === state.genre ? 'selected' : ''}>${esc(g)}</option>`).join('');
    artistSel.innerHTML = '<option value="">All artists</option>' + artists.map((a) => `<option ${a === state.artist ? 'selected' : ''}>${esc(a)}</option>`).join('');
  }).catch(() => {});

  async function fetchList() {
    const params = new URLSearchParams();
    if (state.q) params.set('q', state.q);
    if (state.genre) params.set('genre', state.genre);
    if (state.artist) params.set('artist', state.artist);
    params.set('sort', state.sort);
    params.set('order', state.order);
    const data = await api('/api/songs?' + params.toString());
    if (!document.body.contains(q)) return;
    state.songs = data.songs;
    view.querySelector('#lib-count').textContent =
      `${data.total} song${data.total === 1 ? '' : 's'}` +
      (state.q ? ` matching “${state.q}”` : '');
    const list = view.querySelector('#lib-list');
    if (!data.total) {
      list.innerHTML = emptyState('Nothing here', state.q || state.genre || state.artist
        ? 'No songs match those filters — try clearing them.'
        : 'Your library is empty. Upload some audio or import a link to get started.');
      return;
    }
    list.innerHTML = listHead() + data.songs.map((s, i) => songRow(s, i)).join('');
  }

  const rerun = () => fetchList();
  q.addEventListener('input', debounce(() => { state.q = q.value.trim(); rerun(); }, 250));
  genreSel.addEventListener('change', () => { state.genre = genreSel.value; rerun(); });
  artistSel.addEventListener('change', () => { state.artist = artistSel.value; rerun(); });
  sortSel.addEventListener('change', () => {
    state.sort = sortSel.value;
    state.order = ['title', 'artist', 'album'].includes(state.sort) ? 'asc' : 'desc';
    orderIcon();
    rerun();
  });
  orderBtn.addEventListener('click', () => { state.order = state.order === 'desc' ? 'asc' : 'desc'; orderIcon(); rerun(); });

  registerList('library', () => state.songs);
  bindSongList(view.querySelector('#lib-list'), () => state.songs, { onChanged: rerun });

  await rerun();
  q.focus();
}
