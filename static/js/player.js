/* Persistent audio player: queue + shuffle/repeat + official-embed playback. */
import { api } from './api.js';
import { esc, fmtDur, toast } from './util.js';
import { I } from './icons.js';

const audio = document.getElementById('audio');
const $ = (id) => document.getElementById(id);
const els = {
  bar: $('player'), panel: $('embed-panel'), frame: $('embed-frame'),
  note: $('embed-note'), cover: $('p-cover'), title: $('p-title'), artist: $('p-artist'),
  like: $('p-like'), play: $('p-play'), prev: $('p-prev'), next: $('p-next'),
  back10: $('p-back10'), fwd10: $('p-fwd10'),
  shuffle: $('p-shuffle'), repeat: $('p-repeat'), seek: $('p-seek'),
  cur: $('p-cur'), dur: $('p-dur'), vol: $('p-vol'), mute: $('p-mute'), source: $('p-source'),
};

const state = {
  queue: [], order: [], pos: -1,
  shuffle: localStorage.getItem('tf-shuffle') === '1',
  repeat: localStorage.getItem('tf-repeat') || 'off', // off | all | one
  volume: parseFloat(localStorage.getItem('tf-vol') ?? '0.85'),
  muted: false,
  playRecorded: false,
  initialized: false,
};

function song() { return state.queue[state.order[state.pos]] || null; }

/* ---------- YouTube IFrame API: lets skip/seek work inside official embeds ---------- */
const yt = { player: null, ready: false, apiPromise: null };

function loadYtApi() {
  if (yt.apiPromise) return yt.apiPromise;
  yt.apiPromise = new Promise((resolve) => {
    if (window.YT && window.YT.Player) { resolve(window.YT); return; }
    const prev = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => { if (typeof prev === 'function') prev(); resolve(window.YT); };
    const sc = document.createElement('script');
    sc.src = 'https://www.youtube.com/iframe_api';
    sc.onerror = () => resolve(null);
    document.head.appendChild(sc);
    setTimeout(() => resolve(window.YT && window.YT.Player ? window.YT : null), 8000);
  });
  return yt.apiPromise;
}

function destroyYtPlayer() {
  if (yt.player) {
    try { yt.player.destroy(); } catch { /* ignore */ }
    yt.player = null;
  }
  yt.ready = false;
}

function onYtState(e) {
  const YT = window.YT;
  const s = song();
  if (!YT || !s) return;
  if (e.data === YT.PlayerState.PLAYING) {
    state.playing = true;
    setPlayIcon(true);
    if (!state.playRecorded) {
      state.playRecorded = true;
      api(`/api/songs/${s.id}/play`, { method: 'POST' }).catch(() => {});
    }
    announce();
  } else if (e.data === YT.PlayerState.PAUSED) {
    state.playing = false;
    setPlayIcon(false);
    announce();
  } else if (e.data === YT.PlayerState.ENDED) {
    Player.next(false);
  }
}

function rebuildOrder(currentIdx) {
  const idxs = state.queue.map((_, i) => i);
  if (!state.shuffle) { state.order = idxs; return; }
  const rest = idxs.filter((i) => i !== currentIdx);
  for (let i = rest.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [rest[i], rest[j]] = [rest[j], rest[i]];
  }
  state.order = currentIdx >= 0 ? [currentIdx, ...rest] : rest;
}

function iconBtnState() {
  els.shuffle.classList.toggle('active', state.shuffle);
  els.repeat.innerHTML = state.repeat === 'one' ? I.repeat1 : I.repeat;
  els.repeat.classList.toggle('active', state.repeat !== 'off');
  els.repeat.title = `Repeat: ${state.repeat}`;
}

function setPlayIcon(playing) {
  els.play.innerHTML = playing ? I.pause : I.play;
}

/* ---------- rendering ---------- */
function coverHtml(s) {
  if (s.cover) return `<img src="${esc(s.cover)}" alt="">`;
  const hue = [...(s.title || '')].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7) % 360;
  return `<div class="cover-grad" style="background:linear-gradient(135deg,hsl(${hue},60%,46%),hsl(${(hue + 55) % 360},72%,24%))"><span>${esc((s.title || '?').slice(0, 1).toUpperCase())}</span></div>`;
}

const SOURCE_LABEL = { upload: 'File', download: 'Download', youtube: 'YouTube', soundcloud: 'SoundCloud', ytdownload: 'YT MP3' };

function updateBar(s) {
  els.cover.innerHTML = coverHtml(s);
  els.title.textContent = s.title;
  els.artist.textContent = s.artist || '';
  els.like.innerHTML = s.liked ? I.heartFill : I.heart;
  els.like.classList.toggle('active', !!s.liked);
  const isEmbed = !!s.embed_url;
  els.source.textContent = SOURCE_LABEL[s.source] || s.source;
  els.source.classList.toggle('hidden', false);
  els.seek.disabled = isEmbed;
  els.cur.textContent = '0:00';
  els.dur.textContent = isEmbed ? '—' : fmtDur(s.duration);
  els.seek.value = 0;
  document.title = `${s.title} · TuneFlow`;
}

function announce() {
  const s = song();
  document.dispatchEvent(new CustomEvent('tf:playchange', { detail: { id: s && s.id, playing: state.playing } }));
  if (s && 'mediaSession' in navigator) {
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: s.title, artist: s.artist, album: s.album,
        artwork: s.cover ? [{ src: s.cover, sizes: '512x512' }] : [],
      });
    } catch { /* ignore */ }
  }
}

/* ---------- playback ---------- */
function clearEmbed() {
  destroyYtPlayer();
  els.frame.innerHTML = '';
  els.panel.classList.add('hidden');
}

function skipEmbed(delta, silent = false) {
  if (yt.player) {
    try {
      const cur = yt.player.getCurrentTime() || 0;
      const dur = yt.player.getDuration() || 0;
      yt.player.seekTo(Math.min(Math.max(0, cur + delta), dur > 0 ? dur : cur + delta), true);
      return;
    } catch { /* fall through */ }
  }
  if (!silent) toast('Use the official embed\u2019s own controls to seek on this track.');
}

function playEmbed(s) {
  audio.pause();
  audio.removeAttribute('src');
  destroyYtPlayer();
  state.playing = true;
  state.playRecorded = false;
  updateBar(s);
  setPlayIcon(true);
  announce();

  if (s.source === 'youtube') {
    const vid = (/embed\/([A-Za-z0-9_-]{11})/.exec(s.embed_url || '') || [])[1];
    els.note.innerHTML = `${esc(s.title)} — playing via the official YouTube embed. If it doesn't start, press play inside the player.`;
    els.panel.classList.remove('hidden');
    if (!vid) { // unexpected embed URL — fall back to a plain iframe
      els.frame.innerHTML = `<iframe src="${esc(s.embed_url)}" style="height:290px" allow="autoplay; encrypted-media; clipboard-write" frameborder="0" allowfullscreen></iframe>`;
      state.playRecorded = true;
      api(`/api/songs/${s.id}/play`, { method: 'POST' }).catch(() => {});
      return;
    }
    const target = document.createElement('div');
    els.frame.innerHTML = '';
    els.frame.appendChild(target);
    loadYtApi().then((YT) => {
      if (!YT || !target.isConnected) { // API unavailable or the track changed meanwhile
        if (target.isConnected && !yt.player) {
          els.frame.innerHTML = `<iframe src="${esc(s.embed_url)}" style="height:290px" allow="autoplay; encrypted-media; clipboard-write" frameborder="0" allowfullscreen></iframe>`;
          state.playRecorded = true;
          api(`/api/songs/${s.id}/play`, { method: 'POST' }).catch(() => {});
        }
        return;
      }
      yt.player = new YT.Player(target, {
        width: '100%',
        height: 290,
        videoId: vid,
        playerVars: { autoplay: 1, rel: 0 },
        events: {
          onReady: () => {
            yt.ready = true;
            try {
              const d = yt.player.getDuration();
              if (d) els.dur.textContent = fmtDur(d);
            } catch { /* ignore */ }
          },
          onStateChange: onYtState,
        },
      });
    });
    return;
  }

  // SoundCloud — official widget iframe (use the widget's own controls to seek)
  let src = s.embed_url;
  if (!/auto_play=true/.test(src)) src += (src.includes('?') ? '&' : '?') + 'auto_play=true';
  els.frame.innerHTML = `<iframe src="${esc(src)}" style="height:166px" allow="autoplay; clipboard-write" frameborder="0" allowfullscreen></iframe>`;
  els.note.innerHTML = `${esc(s.title)} — playing via the official SoundCloud embed. If it doesn't start, press play inside the player.`;
  els.panel.classList.remove('hidden');
  state.playRecorded = true;
  api(`/api/songs/${s.id}/play`, { method: 'POST' }).catch(() => {});
}

function playLocal(s) {
  clearEmbed();
  state.playRecorded = false;
  audio.src = s.stream;
  audio.volume = state.muted ? 0 : state.volume;
  updateBar(s);
  const p = audio.play();
  if (p) p.catch(() => setPlayIcon(false));
}

function loadAndPlay() {
  const s = song();
  if (!s) { stop(); return; }
  if (s.embed_url) playEmbed(s); else playLocal(s);
}

export function stop() {
  audio.pause();
  audio.removeAttribute('src');
  clearEmbed();
  state.pos = -1;
  state.playing = false;
  setPlayIcon(false);
  els.title.textContent = 'Nothing playing';
  els.artist.textContent = 'Pick a track to start listening';
  els.cover.innerHTML = '';
  els.source.classList.add('hidden');
  els.cur.textContent = '0:00';
  els.dur.textContent = '0:00';
  els.seek.value = 0;
  document.title = 'TuneFlow';
  announce();
}

export const Player = {
  init() {
    if (state.initialized) return;
    state.initialized = true;

    audio.volume = state.volume;
    els.vol.value = Math.round(state.volume * 100);

    audio.addEventListener('playing', () => {
      state.playing = true;
      setPlayIcon(true);
      const s = song();
      if (s && !state.playRecorded) {
        state.playRecorded = true;
        api(`/api/songs/${s.id}/play`, { method: 'POST' }).catch(() => {});
      }
      announce();
    });
    audio.addEventListener('pause', () => {
      const s = song();
      if (s && s.embed_url) return; // embed pause is controlled by the iframe
      state.playing = false;
      setPlayIcon(false);
      announce();
    });
    audio.addEventListener('timeupdate', () => {
      if (!audio.duration || !isFinite(audio.duration)) return;
      els.seek.value = Math.round((audio.currentTime / audio.duration) * 1000);
      els.cur.textContent = fmtDur(audio.currentTime);
      els.dur.textContent = fmtDur(audio.duration);
    });
    audio.addEventListener('ended', () => Player.next(false));
    audio.addEventListener('error', () => {
      const s = song();
      if (s && s.stream) toast(`Couldn't play "${s.title}" — the file may be missing.`, 'error');
      setPlayIcon(false);
    });

    els.play.onclick = () => Player.toggle();
    els.back10.onclick = () => Player.skip(-10);
    els.fwd10.onclick = () => Player.skip(10);
    els.prev.onclick = () => Player.prev();
    els.next.onclick = () => Player.next(true);
    els.shuffle.onclick = () => {
      state.shuffle = !state.shuffle;
      localStorage.setItem('tf-shuffle', state.shuffle ? '1' : '0');
      rebuildOrder(state.order[state.pos] ?? -1);
      iconBtnState();
      toast(state.shuffle ? 'Shuffle on' : 'Shuffle off');
    };
    els.repeat.onclick = () => {
      state.repeat = state.repeat === 'off' ? 'all' : state.repeat === 'all' ? 'one' : 'off';
      localStorage.setItem('tf-repeat', state.repeat);
      iconBtnState();
    };
    els.seek.oninput = () => {
      if (!audio.duration || !isFinite(audio.duration)) return;
      audio.currentTime = (els.seek.value / 1000) * audio.duration;
    };
    els.vol.oninput = () => {
      state.volume = els.vol.value / 100;
      state.muted = false;
      audio.volume = state.volume;
      localStorage.setItem('tf-vol', String(state.volume));
      els.mute.innerHTML = state.volume === 0 ? I.volMute : I.vol;
    };
    els.mute.onclick = () => {
      state.muted = !state.muted;
      audio.volume = state.muted ? 0 : state.volume;
      els.mute.innerHTML = state.muted ? I.volMute : I.vol;
    };
    els.like.onclick = () => {
      const s = song();
      if (s) document.dispatchEvent(new CustomEvent('tf:toggle-like', { detail: s }));
    };
    $('embed-close').innerHTML = I.x;
    $('embed-close').onclick = () => { clearEmbed(); };

    els.shuffle.innerHTML = I.shuffle;
    els.prev.innerHTML = I.prev;
    els.next.innerHTML = I.next;
    els.back10.innerHTML = I.back10;
    els.fwd10.innerHTML = I.fwd10;

    iconBtnState();
    setPlayIcon(false);
    els.mute.innerHTML = I.vol;

    // space = play/pause, ←/→ = skip 10s (when not typing)
    document.addEventListener('keydown', (e) => {
      const t = e.target;
      const typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable);
      if (e.code === 'Space' && !typing) {
        e.preventDefault();
        Player.toggle();
      }
      if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && !typing) {
        if (!song()) return;
        e.preventDefault();
        Player.skip(e.key === 'ArrowLeft' ? -10 : 10, true);
      }
    });

    if ('mediaSession' in navigator) {
      try {
        navigator.mediaSession.setActionHandler('play', () => Player.toggle());
        navigator.mediaSession.setActionHandler('pause', () => Player.toggle());
        navigator.mediaSession.setActionHandler('previoustrack', () => Player.prev());
        navigator.mediaSession.setActionHandler('nexttrack', () => Player.next(true));
      } catch { /* ignore */ }
    }
    els.bar.classList.remove('hidden');
  },

  /* Play `list` starting at the song whose id is `startId`. */
  play(list, startId) {
    if (!list || !list.length) return;
    state.queue = list.slice();
    let idx = 0;
    if (startId != null) {
      const byId = list.findIndex((s) => s.id === startId);
      idx = byId >= 0 ? byId : 0;
    }
    rebuildOrder(idx);
    state.pos = state.order.indexOf(idx);
    loadAndPlay();
  },

  toggle() {
    const s = song();
    if (!s) return;
    if (s.embed_url) {
      if (yt.player && yt.ready) {
        try {
          if (yt.player.getPlayerState() === window.YT.PlayerState.PLAYING) yt.player.pauseVideo();
          else yt.player.playVideo();
          return;
        } catch { /* fall through */ }
      }
      toast('This one plays in the official embed — use its own controls.');
      return;
    }
    if (!audio.src) { loadAndPlay(); return; }
    if (audio.paused) audio.play().catch(() => {}); else audio.pause();
  },

  next(manual) {
    const s = song();
    if (!s) return;
    if (!manual && state.repeat === 'one' && !s.embed_url) {
      audio.currentTime = 0;
      audio.play().catch(() => {});
      return;
    }
    if (state.pos + 1 < state.order.length) {
      state.pos += 1;
      loadAndPlay();
    } else if (state.repeat === 'all' && state.order.length) {
      state.pos = 0;
      loadAndPlay();
    } else {
      stop();
      toast('Queue finished.');
    }
  },

  prev() {
    const s = song();
    if (!s) return;
    if (!s.embed_url && audio.currentTime > 3) { audio.currentTime = 0; return; }
    if (state.pos > 0) { state.pos -= 1; loadAndPlay(); }
    else if (!s.embed_url) audio.currentTime = 0;
  },

  /* ±10 second skip; works on local files and (via the IFrame API) YouTube embeds. */
  skip(delta, silent = false) {
    const s = song();
    if (!s) return;
    if (s.embed_url) { skipEmbed(delta, silent); return; }
    if (!audio.src || !audio.duration || !isFinite(audio.duration)) return;
    audio.currentTime = Math.min(Math.max(0, audio.currentTime + delta), audio.duration);
    els.cur.textContent = fmtDur(audio.currentTime);
    els.seek.value = Math.round((audio.currentTime / audio.duration) * 1000);
  },

  currentSong: song,
  isPlaying: () => state.playing,
};

/* Keep the bar's heart in sync with likes toggled anywhere in the UI. */
document.addEventListener('tf:like-changed', (e) => {
  const s = song();
  if (s && e.detail && e.detail.id === s.id) {
    s.liked = e.detail.liked;
    els.like.innerHTML = s.liked ? I.heartFill : I.heart;
    els.like.classList.toggle('active', !!s.liked);
  }
});
