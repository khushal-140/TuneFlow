/* Minimal hash router: #/library, #/playlist/3, #/library?q=term ... */

const routes = [];
export const current = { path: '#/', params: {}, query: {} };

export function register(pattern, handler) {
  const parts = pattern.replace(/^#\/?/, '').split('/').filter(Boolean);
  routes.push({ parts, handler });
}

export function navigate(hash) {
  if ((location.hash || '#/') === hash) render();
  else location.hash = hash;
}

export function refresh() { return render(); }

function parseHash() {
  const h = location.hash || '#/';
  const [pathPart, queryPart] = h.slice(1).split('?');
  const segs = pathPart.split('/').filter(Boolean);
  const query = {};
  new URLSearchParams(queryPart || '').forEach((v, k) => { query[k] = v; });
  return { segs, query };
}

export async function render() {
  if (document.body.classList.contains('logged-out')) return;
  const { segs, query } = parseHash();
  const view = document.getElementById('view');

  for (const r of routes) {
    if (r.parts.length !== segs.length) continue;
    const params = {};
    let ok = true;
    for (let i = 0; i < r.parts.length; i++) {
      if (r.parts[i].startsWith(':')) params[r.parts[i].slice(1)] = decodeURIComponent(segs[i]);
      else if (r.parts[i] !== segs[i]) { ok = false; break; }
    }
    if (!ok) continue;
    current.path = location.hash || '#/';
    current.params = params;
    current.query = query;
    document.dispatchEvent(new CustomEvent('tf:view-unmount'));
    try {
      await r.handler(params, query);
    } catch (err) {
      if (err && err.status === 401) {
        document.dispatchEvent(new CustomEvent('tf:unauthorized'));
        return;
      }
      console.error(err);
      view.innerHTML = `<div class="empty-state"><h3>Something went wrong</h3><p class="muted">${String(err && err.message || err)}</p></div>`;
    }
    const v = document.getElementById('view');
    if (v) v.scrollTop = 0;
    markActiveNav(current.path);
    return;
  }
  view.innerHTML = `<div class="empty-state"><h3>Page not found</h3><p class="muted">That page doesn't exist. <a href="#/">Go home</a>.</p></div>`;
}

function markActiveNav(path) {
  const seg = path.replace(/^#\//, '').split('?')[0];
  document.querySelectorAll('#sidebar nav a').forEach((a) => {
    const href = a.getAttribute('href').replace(/^#\//, '');
    a.classList.toggle('active', href === seg || (href === '' && seg === ''));
  });
}

window.addEventListener('hashchange', () => render());
