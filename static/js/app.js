/* App bootstrap: auth state, chrome (sidebar/topbar), route registration. */
import { api } from './api.js';
import { esc, toast } from './util.js';
import { I } from './icons.js';
import { register, render } from './router.js';
import { Player } from './player.js';
import { logoSvg } from './auth.js';
import { showAuth } from './auth.js';
import { viewHome } from './views/home.js';
import { viewLibrary } from './views/library.js';
import { viewPlaylists, viewPlaylistDetail } from './views/playlists.js';
import { viewLiked, viewHistory } from './views/collections.js';
import { viewAssistant } from './views/assistant.js';
import { viewUpload, viewImport } from './views/add.js';

let user = null;

/* ---------- routes ---------- */
register('', viewHome);
register('library', viewLibrary);
register('playlists', viewPlaylists);
register('playlist/:id', viewPlaylistDetail);
register('liked', viewLiked);
register('history', viewHistory);
register('assistant', viewAssistant);
register('upload', viewUpload);
register('import', viewImport);

/* ---------- chrome ---------- */
function renderSidebar() {
  const sb = document.getElementById('sidebar');
  sb.innerHTML = `
    <a class="brand" href="#/">${logoSvg()}<span>TuneFlow</span></a>
    <nav id="main-nav">
      <a href="#/">${I.home}<span>Home</span></a>
      <a href="#/library">${I.music}<span>Library</span></a>
      <a href="#/playlists">${I.playlist}<span>Playlists</span></a>
      <a href="#/liked">${I.heart}<span>Liked songs</span></a>
      <a href="#/history">${I.history}<span>History</span></a>
      <a href="#/assistant" class="nav-ai">${I.sparkles}<span>AI Assistant</span></a>
    </nav>
    <div class="side-actions">
      <a href="#/upload" class="btn btn-grad sm">${I.upload}<span>Upload</span></a>
      <a href="#/import" class="btn btn-ghost sm">${I.link}<span>Import link</span></a>
    </div>
    <div class="side-playlists">
      <div class="side-head">Your playlists</div>
      <div id="side-playlists"></div>
    </div>
    <div class="side-user">
      <div class="avatar">${esc((user?.username || '?')[0].toUpperCase())}</div>
      <div class="su-meta"><div class="su-name">${esc(user?.username || '')}</div><div class="muted tiny">Personal server</div></div>
      <button id="logout-btn" class="icon-btn" title="Log out">${I.logout}</button>
    </div>`;
  renderSidebarPlaylists();
  sb.querySelector('#logout-btn').onclick = async () => {
    try { await api('/api/auth/logout', { method: 'POST' }); } catch { /* ignore */ }
    location.reload();
  };
}

async function renderSidebarPlaylists() {
  const el = document.getElementById('side-playlists');
  if (!el || !user) return;
  try {
    const { playlists } = await api('/api/playlists');
    el.innerHTML = playlists.length
      ? playlists.map((p) => `<a href="#/playlist/${p.id}" title="${esc(p.name)}">${I.playlist}<span>${esc(p.name)}</span></a>`).join('')
      : '<span class="muted tiny pad">None yet</span>';
  } catch { /* ignore */ }
}

function renderTopbar() {
  const tb = document.getElementById('topbar');
  tb.innerHTML = `
    <button id="sb-toggle" class="icon-btn only-mobile">${I.menu}</button>
    <div class="search-box top">${I.search}<input id="global-q" type="search" placeholder="Search your library…"></div>
    <div class="top-right">
      <span class="chip tiny-chip">${I.shield}<span>Self-hosted</span></span>
    </div>`;
  const input = tb.querySelector('#global-q');
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const q = input.value.trim();
      location.hash = q ? `#/library?q=${encodeURIComponent(q)}` : '#/library';
    }
  });
  tb.querySelector('#sb-toggle').onclick = () => {
    document.getElementById('sidebar').classList.toggle('open');
  };
  document.getElementById('view').addEventListener('click', () => {
    document.getElementById('sidebar').classList.remove('open');
  });
}

/* ---------- auth state flow ---------- */
function enterApp() {
  document.body.classList.remove('logged-out');
  document.body.classList.add('logged-in');
  renderSidebar();
  renderTopbar();
  Player.init();
  if (!location.hash) location.hash = '#/';
  render();
}

function showLoggedOut() {
  user = null;
  document.body.classList.add('logged-out');
  document.body.classList.remove('logged-in');
  document.getElementById('sidebar').innerHTML = '';
  document.getElementById('topbar').innerHTML = '';
  const player = document.getElementById('player');
  player.classList.add('hidden');
  if (location.hash && location.hash !== '#/') location.hash = '#/';
  showAuth('login');
}

document.addEventListener('tf:auth-changed', (e) => {
  user = e.detail.user;
  toast(`Welcome, ${user.username}!`);
  enterApp();
});

document.addEventListener('tf:unauthorized', () => showLoggedOut());
document.addEventListener('tf:sidebar-refresh', () => { if (user) renderSidebarPlaylists(); });

/* ---------- boot ---------- */
(async function boot() {
  try {
    const me = await api('/api/me');
    user = me.user;
    enterApp();
  } catch {
    showLoggedOut();
  }
})();
