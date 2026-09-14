/* Playlists: grid of all playlists + single playlist detail. */
import { api } from '../api.js';
import { esc, fmtTotal, gradientFor, confirmModal, toast } from '../util.js';
import { I } from '../icons.js';
import { songRow, listHead, playlistCard, emptyState, bindSongList, registerList, newPlaylistModal, songMenu } from '../ui.js';
import { Player } from '../player.js';
import { navigate, refresh, current } from '../router.js';

export async function viewPlaylists() {
  const view = document.getElementById('view');
  document.title = 'Playlists · TuneFlow';
  view.innerHTML = '<div class="skeleton-block"></div>';
  const { playlists } = await api('/api/playlists');

  view.innerHTML = `
  <div class="page">
    <div class="page-head">
      <h1 class="page-title">Your playlists</h1>
      <button id="pl-new" class="btn btn-grad">${I.plus}<span>New playlist</span></button>
    </div>
    ${playlists.length
      ? `<div class="pl-grid">${playlists.map(playlistCard).join('')}</div>`
      : emptyState('No playlists yet', 'Group your music into collections for every mood and moment.',
          '<button class="btn btn-grad" id="pl-empty-new">Create your first playlist</button>')}
  </div>`;

  const openNew = () => newPlaylistModal(() => refresh());
  view.querySelector('#pl-new').onclick = openNew;
  const emptyBtn = view.querySelector('#pl-empty-new');
  if (emptyBtn) emptyBtn.onclick = openNew;
}

export async function viewPlaylistDetail(params) {
  const view = document.getElementById('view');
  const view_root = view;
  view.innerHTML = '<div class="skeleton-block"></div>';
  let pl;
  try {
    pl = (await api(`/api/playlists/${params.id}`)).playlist;
  } catch (e) {
    view.innerHTML = emptyState('Playlist not found', 'It may have been deleted.', '<a class="btn btn-ghost" href="#/playlists">Back to playlists</a>');
    return;
  }
  document.title = `${pl.name} · TuneFlow`;
  const hue = [...pl.name].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 5) % 360;

  view_root.innerHTML = `
  <div class="page">
    <div class="pl-hero" style="background:linear-gradient(135deg, hsl(${hue},55%,32%), hsl(${(hue + 60) % 360},60%,14%))">
      <div class="pl-hero-art" style="background:${gradientFor('pl' + pl.id)}">${I.music}</div>
      <div class="pl-hero-meta">
        <span class="small caps">Playlist</span>
        <h1 id="pl-name" title="Click to rename">${esc(pl.name)}</h1>
        <p class="muted" id="pl-desc">${esc(pl.description || '')}</p>
        <div class="muted small">${pl.song_count} song${pl.song_count === 1 ? '' : 's'} · ${fmtTotal(pl.total_duration)}</div>
      </div>
      <div class="pl-hero-actions">
        <button id="pl-play" class="btn btn-grad lg" ${pl.songs.length ? '' : 'disabled'}>${I.play}<span>Play</span></button>
        <button id="pl-add" class="btn btn-ghost lg">${I.plus}<span>Add songs</span></button>
        <button id="pl-menu" class="icon-btn lg">${I.dots}</button>
      </div>
    </div>
    <div id="pl-list" class="song-list">${pl.songs.length ? listHead() + pl.songs.map((s, i) => songRow(s, i)).join('') : emptyState('Empty playlist', 'Add songs from your library to fill this one.')}</div>
  </div>`;

  registerList('playlist', () => pl.songs);
  bindSongList(view.querySelector('#pl-list'), () => pl.songs, {
    onChanged: () => refresh(),
    onRemove: async (song) => {
      await api(`/api/playlists/${pl.id}/songs/${song.id}`, { method: 'DELETE' });
      toast('Removed from playlist.');
      refresh();
    },
  });

  view.querySelector('#pl-play').onclick = () => { if (pl.songs.length) Player.play(pl.songs, pl.songs[0].id); };

  view.querySelector('#pl-add').onclick = () => addSongsToPlaylistModal(pl, () => refresh());

  view.querySelector('#pl-menu').onclick = (e) => {
    import('../util.js').then(({ openMenu }) => {
      openMenu(e.currentTarget, [
        { label: 'Rename / describe', icon: I.edit, onClick: () => editPlaylistModal(pl, () => refresh()) },
        {
          label: 'Delete playlist', icon: I.trash, danger: true,
          onClick: async () => {
            const ok = await confirmModal({ title: `Delete "${pl.name}"?`, message: 'The songs stay in your library — only the playlist goes away.' });
            if (!ok) return;
            await api(`/api/playlists/${pl.id}`, { method: 'DELETE' });
            toast('Playlist deleted.');
            document.dispatchEvent(new CustomEvent('tf:sidebar-refresh'));
            navigate('#/playlists');
          },
        },
      ]);
    });
  };

  view.querySelector('#pl-name').onclick = () => editPlaylistModal(pl, () => refresh());
}

function editPlaylistModal(pl, onSaved) {
  import('../ui.js').then(({ openModal, closeModal }) => {
    const m = openModal(`
      <h3 class="modal-title">Edit playlist</h3>
      <label class="field">Name<input id="ep-name" type="text" maxlength="120" value="${esc(pl.name)}"></label>
      <label class="field">Description<input id="ep-desc" type="text" maxlength="500" value="${esc(pl.description || '')}"></label>
      <div class="modal-actions">
        <button class="btn btn-ghost" data-x>Cancel</button>
        <button class="btn btn-grad" data-ok>Save</button>
      </div>`, { small: true });
    m.querySelector('[data-ok]').onclick = async () => {
      const name = m.querySelector('#ep-name').value.trim();
      if (!name) return;
      try {
        await api(`/api/playlists/${pl.id}`, { method: 'PATCH', body: { name, description: m.querySelector('#ep-desc').value.trim() } });
        closeModal();
        document.dispatchEvent(new CustomEvent('tf:sidebar-refresh'));
        if (onSaved) onSaved();
      } catch (e) { toast(e.message, 'error'); }
    };
    m.querySelector('[data-x]').onclick = closeModal;
  });
}

export async function addSongsToPlaylistModal(pl, onDone) {
  const { openModal, closeModal, toast: t } = await import('../util.js');
  const { songRow: row } = await import('../ui.js');
  const data = await api('/api/songs?sort=title&order=asc');
  const inPlaylist = new Set(pl.songs.map((s) => s.id));
  const m = openModal(`
    <h3 class="modal-title">Add songs to "${esc(pl.name)}"</h3>
    <div class="search-box modal-search">${I.search}<input id="ap-q" type="search" placeholder="Search your library…"></div>
    <div class="pick-list tall" id="ap-songs"></div>
    <div class="modal-actions"><button class="btn btn-ghost" data-x>Done</button></div>`);

  const list = m.querySelector('#ap-songs');
  const render = (q) => {
    const songs = data.songs.filter((s) => !q || (s.title + ' ' + s.artist).toLowerCase().includes(q));
    if (!songs.length) { list.innerHTML = '<p class="muted pad">No matches.</p>'; return; }
    list.innerHTML = songs.map((s) => `
      <div class="pick-item song" data-id="${s.id}">
        ${s.cover ? `<img class="cover tiny" src="${esc(s.cover)}" alt="">` : `<div class="cover tiny cover-grad" style="background:${gradientFor((s.title || '') + s.id)}"><span>${esc((s.title || '?')[0].toUpperCase())}</span></div>`}
        <div class="pick-main"><div class="s-title">${esc(s.title)}</div><div class="s-artist muted">${esc(s.artist || '')}</div></div>
        ${inPlaylist.has(s.id)
          ? `<span class="chip ok">${I.check}<span>In playlist</span></span>`
          : `<button class="btn btn-ghost sm" data-add="${s.id}">${I.plus}<span>Add</span></button>`}
      </div>`).join('');
  };
  render('');
  m.querySelector('#ap-q').addEventListener('input', (e) => render(e.target.value.trim().toLowerCase()));
  list.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-add]');
    if (!b) return;
    try {
      await api(`/api/playlists/${pl.id}/songs`, { method: 'POST', body: { song_id: +b.dataset.add } });
      inPlaylist.add(+b.dataset.add);
      render(m.querySelector('#ap-q').value.trim().toLowerCase());
      document.dispatchEvent(new CustomEvent('tf:sidebar-refresh'));
      t('Added.');
      if (onDone) onDone();
    } catch (err) { t(err.message, 'error'); }
  });
  m.querySelector('[data-x]').onclick = () => { closeModal(); };
}
