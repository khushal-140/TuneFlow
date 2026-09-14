/* Shared UI components + like/menu actions used across views. */
import { api } from './api.js';
import { esc, fmtDur, fmtTotal, gradientFor, initials, toast, openMenu, openModal, closeModal, confirmModal } from './util.js';
import { I } from './icons.js';
import { Player } from './player.js';

export function coverHtml(song, cls = '') {
  if (song.cover) return `<div class="cover ${cls}"><img src="${esc(song.cover)}" loading="lazy" alt=""></div>`;
  return `<div class="cover ${cls} cover-grad" style="background:${gradientFor((song.title || '') + song.id)}"><span>${esc(initials(song.title))}</span></div>`;
}

const SOURCE_LABEL = { upload: 'File', download: 'Download', youtube: 'YouTube', soundcloud: 'SoundCloud' };

export function sourceBadge(song) {
  if (song.source === 'upload') return '';
  return `<span class="src-badge">${SOURCE_LABEL[song.source] || esc(song.source)}</span>`;
}

export function songRow(song, i, opts = {}) {
  const showAlbum = opts.showAlbum !== false;
  return `
  <div class="song-row" data-id="${song.id}" data-idx="${i}">
    <div class="s-idx"><span class="num">${i + 1}</span><span class="s-go">${I.play}</span></div>
    ${coverHtml(song, 'small')}
    <div class="s-main">
      <div class="s-title">${esc(song.title)} ${sourceBadge(song)}</div>
      <div class="s-artist">${esc(song.artist || '')}</div>
    </div>
    ${showAlbum ? `<div class="s-album muted">${esc(song.album || '')}</div>` : ''}
    ${song.genre ? `<div class="s-genre"><span class="chip">${esc(song.genre)}</span></div>` : '<div class="s-genre"></div>'}
    ${song.reason ? `<div class="s-reason muted">${esc(song.reason)}</div>` : '<div class="s-reason muted"></div>'}
    <div class="s-dur">${song.duration ? fmtDur(song.duration) : '—'}</div>
    <div class="s-actions">
      <button class="icon-btn heart${song.liked ? ' active' : ''}" data-like="${song.id}" title="Like">${song.liked ? I.heartFill : I.heart}</button>
      <button class="icon-btn" data-menu="${song.id}" title="More">${I.dots}</button>
    </div>
  </div>`;
}

export function listHead(opts = {}) {
  const showAlbum = opts.showAlbum !== false;
  return `
  <div class="song-row head">
    <div class="s-idx">#</div><div class="cover-spacer"></div>
    <div class="s-main">Title</div>
    ${showAlbum ? '<div class="s-album">Album</div>' : ''}
    <div class="s-genre">Genre</div>
    <div class="s-reason"></div>
    <div class="s-dur">Time</div>
    <div class="s-actions"></div>
  </div>`;
}

export function songCard(song, { reason = false } = {}) {
  return `
  <div class="song-card" data-id="${song.id}">
    <div class="sc-art">
      ${coverHtml(song, 'large')}
      <button class="sc-play" data-cardplay="${song.id}" title="Play">${I.play}</button>
      <button class="sc-heart icon-btn${song.liked ? ' active' : ''}" data-like="${song.id}" title="Like">${song.liked ? I.heartFill : I.heart}</button>
    </div>
    <div class="sc-title" title="${esc(song.title)}">${esc(song.title)}</div>
    <div class="sc-artist muted">${esc(song.artist || '')}</div>
    ${reason && song.reason ? `<div class="sc-reason muted">${esc(song.reason)}</div>` : ''}
  </div>`;
}

export function playlistCard(pl) {
  const covers = (pl.covers || []).slice(0, 4);
  let art;
  if (covers.length >= 4) {
    art = `<div class="pc-mosaic">${covers.map((c) => `<img src="${esc(c)}" loading="lazy" alt="">`).join('')}</div>`;
  } else if (covers.length) {
    art = `<div class="pc-mosaic one"><img src="${esc(covers[0])}" loading="lazy" alt=""></div>`;
  } else {
    art = `<div class="pc-mosaic grad" style="background:${gradientFor('pl' + pl.id)}"><span>${I.music}</span></div>`;
  }
  return `
  <a class="playlist-card" href="#/playlist/${pl.id}">
    <div class="pc-art">${art}<span class="pc-play">${I.play}</span></div>
    <div class="pc-name" title="${esc(pl.name)}">${esc(pl.name)}</div>
    <div class="pc-sub muted">${pl.song_count} song${pl.song_count === 1 ? '' : 's'}${pl.total_duration ? ' · ' + fmtTotal(pl.total_duration) : ''}</div>
  </a>`;
}

export function section(title, inner, { action = '' } = {}) {
  return `
  <section class="section">
    <div class="section-head"><h2>${esc(title)}</h2>${action}</div>
    ${inner}
  </section>`;
}

export function emptyState(title, sub, cta = '') {
  return `<div class="empty-state"><div class="es-art">${I.music}</div><h3>${esc(title)}</h3><p class="muted">${esc(sub)}</p>${cta}</div>`;
}

/* ---------- likes ---------- */
export async function toggleLike(song) {
  try {
    const res = await api(`/api/songs/${song.id}/like`, { method: 'POST' });
    song.liked = res.liked;
    document.querySelectorAll(`[data-like="${song.id}"]`).forEach((b) => {
      b.classList.toggle('active', res.liked);
      b.innerHTML = res.liked ? I.heartFill : I.heart;
    });
    document.dispatchEvent(new CustomEvent('tf:like-changed', { detail: { id: song.id, liked: res.liked } }));
    return res.liked;
  } catch (e) {
    toast(e.message, 'error');
    return song.liked;
  }
}

document.addEventListener('tf:toggle-like', (e) => toggleLike(e.detail));
document.addEventListener('click', (e) => {
  const likeBtn = e.target.closest('[data-like]');
  if (!likeBtn) return;
  e.preventDefault();
  e.stopPropagation();
  const id = +likeBtn.dataset.like;
  const song = findSongInLists(id);
  if (song) toggleLike(song);
});

/* Views register their current lists so menu handlers can find song objects. */
const liveLists = [];
const viewCleanups = [];

export function onViewCleanup(fn) {
  viewCleanups.push(fn);
}

document.addEventListener('tf:view-unmount', () => {
  while (viewCleanups.length) { try { viewCleanups.pop()(); } catch { /* ignore */ } }
});

export function registerList(name, getter) {
  const entry = { name, getter };
  liveLists.push(entry);
  onViewCleanup(() => {
    const i = liveLists.indexOf(entry);
    if (i >= 0) liveLists.splice(i, 1);
  });
}
function findSongInLists(id) {
  for (const l of liveLists) {
    const list = l.getter() || [];
    const s = list.find((x) => x && x.id === id);
    if (s) return s;
  }
  return null;
}

/* ---------- song context menu ---------- */
export function songMenu(song, anchor, opts = {}) {
  const items = [
    { label: 'Play', icon: I.play, onClick: () => Player.play(opts.list || [song], song.id) },
    { label: 'Add to playlist', icon: I.plus, onClick: () => addToPlaylistModal([song], opts.onChanged) },
    { label: 'Edit info', icon: I.edit, onClick: () => editSongModal(song, opts.onChanged) },
  ];
  if (opts.onRemove) items.push({ label: 'Remove from playlist', icon: I.x, onClick: () => opts.onRemove(song) });
  items.push({
    label: 'Delete from library', icon: I.trash, danger: true,
    onClick: async () => {
      const ok = await confirmModal({
        title: `Delete "${song.title}"?`,
        message: 'This removes the track, its history entries and playlist placements. This cannot be undone.',
        confirmText: 'Delete',
      });
      if (!ok) return;
      try {
        await api(`/api/songs/${song.id}`, { method: 'DELETE' });
        toast('Deleted from your library.');
        if (opts.onChanged) opts.onChanged();
      } catch (e) { toast(e.message, 'error'); }
    },
  });
  openMenu(anchor, items);
}

/* ---------- modals ---------- */
export function addToPlaylistModal(songs, onDone) {
  api('/api/playlists').then(({ playlists }) => {
    const m = openModal(`
      <h3 class="modal-title">Add ${songs.length > 1 ? songs.length + ' songs' : `"${esc(songs[0].title)}"`} to a playlist</h3>
      <div class="pick-list" id="ap-list"></div>
      <div class="modal-actions">
        <button class="btn btn-ghost" data-x>Cancel</button>
        <button class="btn btn-grad" data-new>${I.plus}<span>New playlist</span></button>
      </div>`);
    const list = m.querySelector('#ap-list');
    if (!playlists.length) list.innerHTML = '<p class="muted pad">No playlists yet — create your first one.</p>';
    else list.innerHTML = playlists.map((p) =>
      `<button class="pick-item" data-pid="${p.id}">${I.playlist}<span>${esc(p.name)}</span><span class="muted">${p.song_count}</span></button>`).join('');
    list.addEventListener('click', async (e) => {
      const b = e.target.closest('[data-pid]');
      if (!b) return;
      try {
        await api(`/api/playlists/${b.dataset.pid}/songs`, { method: 'POST', body: { song_ids: songs.map((s) => s.id) } });
        closeModal();
        toast(`Added to playlist.`);
        document.dispatchEvent(new CustomEvent('tf:sidebar-refresh'));
        if (onDone) onDone();
      } catch (err) { toast(err.message, 'error'); }
    });
    m.querySelector('[data-x]').onclick = closeModal;
    m.querySelector('[data-new]').onclick = () => newPlaylistModal(async (pl) => {
      try {
        await api(`/api/playlists/${pl.id}/songs`, { method: 'POST', body: { song_ids: songs.map((s) => s.id) } });
        toast(`Added ${songs.length} song${songs.length > 1 ? 's' : ''} to "${pl.name}".`);
        if (onDone) onDone();
      } catch (err) { toast(err.message, 'error'); }
    });
  }).catch((e) => toast(e.message, 'error'));
}

export function newPlaylistModal(onCreate) {
  const m = openModal(`
    <h3 class="modal-title">New playlist</h3>
    <label class="field">Name<input id="np-name" type="text" maxlength="120" placeholder="e.g. Late Night Focus"></label>
    <label class="field">Description <span class="muted">(optional)</span><input id="np-desc" type="text" maxlength="500" placeholder="What's this playlist for?"></label>
    <div class="modal-actions">
      <button class="btn btn-ghost" data-x>Cancel</button>
      <button class="btn btn-grad" data-ok>Create</button>
    </div>`, { small: true });
  const nameEl = m.querySelector('#np-name');
  nameEl.focus();
  const submit = async () => {
    const name = nameEl.value.trim();
    if (!name) { nameEl.classList.add('invalid'); return; }
    try {
      const res = await api('/api/playlists', { method: 'POST', body: { name, description: m.querySelector('#np-desc').value.trim() } });
      closeModal();
      document.dispatchEvent(new CustomEvent('tf:sidebar-refresh'));
      toast(`Playlist "${res.playlist.name}" created.`);
      if (onCreate) onCreate(res.playlist);
    } catch (e) { toast(e.message, 'error'); }
  };
  m.querySelector('[data-ok]').onclick = submit;
  m.querySelector('#np-desc').addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
  nameEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
  m.querySelector('[data-x]').onclick = closeModal;
}

export function editSongModal(song, onSaved) {
  const m = openModal(`
    <div class="edit-head">${coverHtml(song, 'medium')}<div><h3 class="modal-title">Edit info</h3><p class="muted">Tags extracted from the file — tweak anything.</p></div></div>
    <label class="field">Title<input id="es-title" type="text" value="${esc(song.title)}" maxlength="255"></label>
    <label class="field">Artist<input id="es-artist" type="text" value="${esc(song.artist || '')}" maxlength="255"></label>
    <label class="field">Album<input id="es-album" type="text" value="${esc(song.album || '')}" maxlength="255"></label>
    <label class="field">Genre<input id="es-genre" type="text" value="${esc(song.genre || '')}" maxlength="64"></label>
    <div class="modal-actions">
      <button class="btn btn-ghost" data-x>Cancel</button>
      <button class="btn btn-grad" data-ok>Save</button>
    </div>`);
  const submit = async () => {
    const title = m.querySelector('#es-title').value.trim();
    if (!title) { m.querySelector('#es-title').classList.add('invalid'); return; }
    try {
      await api(`/api/songs/${song.id}`, {
        method: 'PATCH',
        body: {
          title,
          artist: m.querySelector('#es-artist').value.trim(),
          album: m.querySelector('#es-album').value.trim(),
          genre: m.querySelector('#es-genre').value.trim(),
        },
      });
      closeModal();
      toast('Track info updated.');
      if (onSaved) onSaved();
    } catch (e) { toast(e.message, 'error'); }
  };
  m.querySelector('[data-ok]').onclick = submit;
  m.querySelector('[data-x]').onclick = closeModal;
}

/* ---------- song list wiring ---------- */
export function bindSongList(root, getList, opts = {}) {
  root.addEventListener('click', (e) => {
    const menuBtn = e.target.closest('[data-menu]');
    if (menuBtn) {
      e.preventDefault();
      const id = +menuBtn.dataset.menu;
      const song = (getList() || []).find((s) => s.id === id);
      if (song) songMenu(song, menuBtn, { ...opts, list: getList() });
      return;
    }
    const likeBtn = e.target.closest('[data-like]');
    if (likeBtn) return; // handled globally
    const row = e.target.closest('.song-row:not(.head)');
    if (!row) return;
    const id = +row.dataset.id;
    const list = getList() || [];
    const song = list.find((s) => s.id === id);
    if (song) Player.play(list, id);
  });

  // reflect playing state
  const listener = (e) => {
    root.querySelectorAll('.song-row.playing').forEach((r) => r.classList.remove('playing'));
    if (e.detail && e.detail.id && e.detail.playing) {
      const row = root.querySelector(`.song-row[data-id="${e.detail.id}"]`);
      if (row) row.classList.add('playing');
    }
  };
  document.addEventListener('tf:playchange', listener);
  onViewCleanup(() => document.removeEventListener('tf:playchange', listener));
}
