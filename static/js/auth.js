/* Auth screen: sign in / create account. Dispatches tf:auth-changed on success. */
import { api } from './api.js';
import { esc, toast } from './util.js';
import { I } from './icons.js';

export function showAuth(mode = 'login') {
  const view = document.getElementById('view');
  document.title = 'Welcome · TuneFlow';

  view.innerHTML = `
  <div class="auth-wrap">
    <div class="auth-brand">
      <div class="brand big">${logoSvg()}<span>TuneFlow</span></div>
      <h1>Your music.<br>Your server.<br><span class="grad-text">Your rules.</span></h1>
      <p class="muted">A self-hosted home for the music you actually own — upload files, import links, and let the assistant and recommender learn your taste.</p>
      <ul class="auth-feats">
        <li>${I.upload}<span>Smart upload extracts tags & cover art</span></li>
        <li>${I.link}<span>YouTube & SoundCloud via official embeds</span></li>
        <li>${I.sparkles}<span>Ask for “a 30-minute study playlist”</span></li>
        <li>${I.heart}<span>Recommendations built from what you love</span></li>
      </ul>
    </div>
    <div class="auth-card">
      <div class="auth-tabs">
        <button class="auth-tab ${mode === 'login' ? 'active' : ''}" data-mode="login">Sign in</button>
        <button class="auth-tab ${mode === 'register' ? 'active' : ''}" data-mode="register">Create account</button>
      </div>
      <form id="auth-form">
        ${mode === 'register' ? `
        <label class="field">Username<input name="username" type="text" autocomplete="username" placeholder="your-handle"></label>
        <label class="field">Email<input name="email" type="email" autocomplete="email" placeholder="you@example.com"></label>` : `
        <label class="field">Username or email<input name="identifier" type="text" autocomplete="username" placeholder="demo"></label>`}
        <label class="field">Password<input name="password" type="password" autocomplete="${mode === 'login' ? 'current-password' : 'new-password'}" placeholder="••••••••"></label>
        <div id="auth-error" class="form-error hidden"></div>
        <button class="btn btn-grad lg wide" type="submit">${mode === 'login' ? 'Sign in' : 'Create account'}</button>
      </form>
      ${mode === 'login' ? `
      <button class="demo-hint" id="demo-fill">${I.sparkles}<span>Try the demo account — <b>demo / demo123</b> (tap to fill)</span></button>` : ''}
    </div>
  </div>`;

  view.querySelectorAll('.auth-tab').forEach((b) => {
    b.onclick = () => showAuth(b.dataset.mode);
  });
  const fill = view.querySelector('#demo-fill');
  if (fill) fill.onclick = () => {
    view.querySelector('[name="identifier"]').value = 'demo';
    view.querySelector('[name="password"]').value = 'demo123';
    view.querySelector('#auth-form').requestSubmit();
  };

  view.querySelector('#auth-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = Object.fromEntries(fd.entries());
    const errEl = view.querySelector('#auth-error');
    errEl.classList.add('hidden');
    try {
      const path = mode === 'login' ? '/api/auth/login' : '/api/auth/register';
      const res = await api(path, { method: 'POST', body });
      document.dispatchEvent(new CustomEvent('tf:auth-changed', { detail: { user: res.user } }));
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove('hidden');
    }
  });
}

export function logoSvg() {
  return `<svg viewBox="0 0 32 32" width="34" height="34" aria-hidden="true">
    <defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#8b5cf6"/><stop offset="1" stop-color="#d946ef"/>
    </linearGradient></defs>
    <rect x="1" y="1" width="30" height="30" rx="9" fill="url(#lg)"/>
    <g stroke="#fff" stroke-width="2.4" stroke-linecap="round">
      <line x1="9" y1="12" x2="9" y2="20"/>
      <line x1="13.5" y1="8" x2="13.5" y2="24"/>
      <line x1="18" y1="11" x2="18" y2="21"/>
      <line x1="22.5" y1="13.5" x2="22.5" y2="18.5"/>
    </g>
  </svg>`;
}
