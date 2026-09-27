/* App bootstrap: auth state, chrome (sidebar/topbar), route registration. */
import { api } from './api.js';
import { esc, toast, openMenu, debounce } from './util.js';
import { coverHtml } from './ui.js';
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
import { viewConverter } from './views/converter.js';

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
register('converter', viewConverter);

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
      <a href="#/converter" class="nav-cv">${I.download}<span>MP3 Converter</span></a>
    </nav>
    <div class="side-actions">
      <a href="#/upload" class="btn btn-grad sm">${I.upload}<span>Upload</span></a>
      <a href="#/import" class="btn btn-ghost sm">${I.link}<span>Import link</span></a>
    </div>
    <div class="side-playlists">
      <div class="side-head">Your playlists</div>
      <div id="side-playlists"></div>
    </div>
    <div class="side-user" id="account-chip" role="button" tabindex="0" title="Account">
      <div class="avatar">${esc((user?.username || '?')[0].toUpperCase())}</div>
      <div class="su-meta">
        <div class="su-name">${esc(user?.username || '')}</div>
        <div class="su-mail">${esc(user?.email || 'Personal server')}</div>
      </div>
      <span class="su-chev">${I.chevron}</span>
    </div>`;
  renderSidebarPlaylists();
  const chip = sb.querySelector('#account-chip');
  chip.onclick = () => openAccountMenu(chip);
  chip.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openAccountMenu(chip); }
  });
}

function openAccountMenu(anchor) {
  const created = user?.created_at
    ? new Date(user.created_at).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })
    : null;
  openMenu(anchor, [
    {
      label: 'Log out', icon: I.logout,
      onClick: async () => {
        try { await api('/api/auth/logout', { method: 'POST' }); } catch { /* ignore */ }
        location.reload();
      },
    },
  ], {
    header: `
      <div class="pop-header">
        <div class="avatar">${esc((user?.username || '?')[0].toUpperCase())}</div>
        <div class="pop-h-meta">
          <div class="pop-h-name">${esc(user?.username || '')}</div>
          <div class="pop-h-mail">${esc(user?.email || 'Personal server')}</div>
          ${created ? `<div class="pop-h-since">Listening since ${created}</div>` : ''}
        </div>
      </div>`,
  });
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
    <div class="search-box top suggest-wrap">${I.search}<input id="global-q" type="search" placeholder="Search your library…" autocomplete="off"><div id="search-suggest" class="suggest-pop hidden"></div></div>
    <div class="top-right">
      <button id="theme-toggle" class="icon-btn" title="Switch theme"></button>
      <span class="chip tiny-chip">${I.shield}<span>Self-hosted</span></span>
    </div>`;
  const input = tb.querySelector('#global-q');

  const themeBtn = tb.querySelector('#theme-toggle');
  const syncThemeBtn = () => {
    const light = document.documentElement.classList.contains('light');
    themeBtn.innerHTML = light ? I.moon : I.sun;
    themeBtn.title = light ? 'Switch to dark mode' : 'Switch to light mode';
  };
  syncThemeBtn();
  themeBtn.onclick = () => {
    const light = document.documentElement.classList.toggle('light');
    try { localStorage.setItem('tf-theme', light ? 'light' : 'dark'); } catch { /* ignore */ }
    syncThemeBtn();
    toast(light ? 'Light mode on' : 'Dark mode on');
  };
  /* --- live search suggestions --- */
  const box = tb.querySelector('.search-box.top');
  const pop = tb.querySelector('#search-suggest');
  let suggList = [];
  let suggActive = -1;
  let suggToken = 0;

  const closeSuggest = () => {
    pop.classList.add('hidden');
    pop.innerHTML = '';
    suggActive = -1;
    suggList = [];
  };

  const goLibrary = () => {
    const q = input.value.trim();
    location.hash = q ? `#/library?q=${encodeURIComponent(q)}` : '#/library';
    closeSuggest();
  };

  const pick = (i) => {
    const s = suggList[i];
    if (!s) return;
    const queue = suggList.slice(); // snapshot before closeSuggest clears the list
    closeSuggest();
    Player.play(queue, s.id);
    toast(`Playing "${s.title}"`);
  };

  const hl = (text, q) => {
    const t = String(text || '');
    const idx = t.toLowerCase().indexOf(q.toLowerCase());
    if (idx < 0) return esc(t);
    return esc(t.slice(0, idx)) + '<span class="sg-hl">' + esc(t.slice(idx, idx + q.length)) + '</span>' + esc(t.slice(idx + q.length));
  };

  const runSuggest = debounce(async () => {
    const q = input.value.trim();
    const token = ++suggToken;
    if (q.length < 2) { closeSuggest(); return; }
    let suggestions = [];
    try {
      ({ suggestions } = await api(`/api/songs/suggest?q=${encodeURIComponent(q)}&limit=7`));
    } catch { closeSuggest(); return; }
    if (token !== suggToken) return; // a newer keystroke already answered
    suggList = suggestions;
    if (!suggestions.length) {
      pop.innerHTML = `<div class="sg-empty">No matches for “${esc(q)}” in your library</div>`;
      pop.classList.remove('hidden');
      suggActive = -1;
      return;
    }
    pop.innerHTML = suggestions.map((s, i) => `
      <button class="suggest-item" data-i="${i}">
        ${coverHtml(s, 'tiny')}
        <span class="sg-main">
          <span class="sg-title">${hl(s.title, q)}</span>
          <span class="sg-sub">${hl(s.artist, q)} <span class="sg-tag">${esc(s.match)}</span></span>
        </span>
        <span class="sg-play">${I.play}</span>
      </button>`).join('')
      + `<button class="sg-see-all" data-seeall>See all results for “${esc(q)}”</button>`;
    pop.classList.remove('hidden');
    suggActive = -1;
    pop.querySelectorAll('.suggest-item').forEach((b) => { b.onclick = () => pick(+b.dataset.i); });
    pop.querySelector('[data-seeall]').onclick = goLibrary;
  }, 170);

  input.addEventListener('input', runSuggest);
  input.addEventListener('focus', () => { if (input.value.trim().length >= 2 && suggList.length) pop.classList.remove('hidden'); });
  input.addEventListener('keydown', (e) => {
    const open = !pop.classList.contains('hidden');
    if (e.key === 'Escape' && open) { closeSuggest(); return; }
    if (!open) {
      if (e.key === 'Enter') goLibrary();
      return;
    }
    const items = pop.querySelectorAll('.suggest-item');
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!items.length) return;
      suggActive = e.key === 'ArrowDown'
        ? (suggActive + 1) % items.length
        : (suggActive - 1 + items.length) % items.length;
      items.forEach((el, i) => el.classList.toggle('active', i === suggActive));
      items[suggActive].scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (suggActive >= 0 && items[suggActive]) pick(suggActive);
      else goLibrary();
    }
  });
  document.addEventListener('mousedown', (e) => {
    if (!box.contains(e.target)) closeSuggest();
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
