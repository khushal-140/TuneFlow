/* Shared helpers: escaping, formatting, toasts, modals, popovers. */

export function esc(s) {
  return String(s ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

export function fmtDur(s) {
  if (!s || s <= 0) return '—';
  const m = Math.floor(s / 60);
  const ss = Math.floor(s % 60);
  return `${m}:${String(ss).padStart(2, '0')}`;
}

export function fmtTotal(s) {
  if (!s || s <= 0) return '0 min';
  const m = Math.round(s / 60);
  return m >= 60 ? `${Math.floor(m / 60)} hr ${m % 60} min` : `${m} min`;
}

export function fmtSize(bytes) {
  if (bytes == null) return '';
  if (bytes > 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  if (bytes > 1024) return (bytes / 1024).toFixed(0) + ' KB';
  return bytes + ' B';
}

export function relTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 604800) return `${Math.floor(s / 86400)}d ago`;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export function debounce(fn, ms = 250) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

export function hashHue(str) {
  let h = 0;
  for (const c of String(str)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return h % 360;
}

export function gradientFor(seed) {
  const h = hashHue(seed);
  return `linear-gradient(135deg, hsl(${h}, 60%, 46%), hsl(${(h + 55) % 360}, 72%, 24%))`;
}

export function initials(name) {
  const words = String(name || '?').trim().split(/\s+/).filter(Boolean);
  return words.slice(0, 2).map((w) => w[0].toUpperCase()).join('') || '?';
}

/* ---------- toasts ---------- */
export function toast(msg, type = 'info') {
  const root = document.getElementById('toast-root');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  root.appendChild(t);
  requestAnimationFrame(() => t.classList.add('show'));
  setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 350); }, 3400);
}

/* ---------- modal ---------- */
let modalKeyHandler = null;

export function openModal(html, { small = false } = {}) {
  closeModal();
  const root = document.getElementById('modal-root');
  root.innerHTML = `<div class="modal-backdrop"><div class="modal${small ? ' small' : ''}" role="dialog" aria-modal="true">${html}</div></div>`;
  root.classList.add('open');
  const backdrop = root.querySelector('.modal-backdrop');
  backdrop.addEventListener('mousedown', (e) => { if (e.target === backdrop) closeModal(); });
  modalKeyHandler = (e) => { if (e.key === 'Escape') closeModal(); };
  document.addEventListener('keydown', modalKeyHandler);
  return root.querySelector('.modal');
}

export function closeModal() {
  const root = document.getElementById('modal-root');
  root.classList.remove('open');
  root.innerHTML = '';
  if (modalKeyHandler) { document.removeEventListener('keydown', modalKeyHandler); modalKeyHandler = null; }
}

export function confirmModal({ title, message = '', confirmText = 'Delete', danger = true }) {
  return new Promise((resolve) => {
    const m = openModal(`
      <h3 class="modal-title">${esc(title)}</h3>
      <p class="muted">${esc(message)}</p>
      <div class="modal-actions">
        <button class="btn btn-ghost" data-x>Cancel</button>
        <button class="btn ${danger ? 'btn-danger' : 'btn-grad'}" data-ok>${esc(confirmText)}</button>
      </div>`, { small: true });
    m.querySelector('[data-x]').onclick = () => { closeModal(); resolve(false); };
    m.querySelector('[data-ok]').onclick = () => { closeModal(); resolve(true); };
  });
}

/* ---------- popover menu ---------- */
let popEl = null;
let popOutside = null;
let popKey = null;

export function closeMenu() {
  if (popEl) { popEl.remove(); popEl = null; }
  if (popOutside) { document.removeEventListener('mousedown', popOutside); popOutside = null; }
  if (popKey) { document.removeEventListener('keydown', popKey); popKey = null; }
}

export function openMenu(anchor, items) {
  closeMenu();
  const root = document.getElementById('popover-root');
  popEl = document.createElement('div');
  popEl.className = 'popover';
  popEl.innerHTML = items.map((it, i) =>
    `<button class="pop-item${it.danger ? ' danger' : ''}" data-i="${i}">${it.icon || ''}<span>${esc(it.label)}</span></button>`).join('');
  root.appendChild(popEl);
  const rect = anchor.getBoundingClientRect();
  const pw = 230;
  let x = Math.max(8, Math.min(window.innerWidth - pw - 8, rect.right - pw));
  let y = rect.bottom + 6;
  if (y + popEl.offsetHeight > window.innerHeight - 8) y = rect.top - popEl.offsetHeight - 6;
  popEl.style.left = x + 'px';
  popEl.style.top = y + 'px';

  popOutside = (e) => { if (popEl && !popEl.contains(e.target)) closeMenu(); };
  popKey = (e) => { if (e.key === 'Escape') closeMenu(); };
  setTimeout(() => {
    document.addEventListener('mousedown', popOutside);
    document.addEventListener('keydown', popKey);
  });
  popEl.addEventListener('click', (e) => {
    const b = e.target.closest('[data-i]');
    if (!b) return;
    const item = items[+b.dataset.i];
    closeMenu();
    item.onClick();
  });
}
