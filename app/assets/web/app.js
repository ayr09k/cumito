/* Cumito · Liquid — la ventana del modo normal.
   Todo lo que se ve es el diseño del lienzo; la música y los datos vienen de
   Python por QWebChannel ("cumito"). Python manda eventos con
   cumito.event(tipo, json) y esta página le pide cosas con cumito.send(...). */
'use strict';

/* ======================= puente con Python ======================= */
let B = null;
const Q = [];
function send(action, kw) { if (B) B.send(action, JSON.stringify(kw || {})); else Q.push([action, kw]); }
function winCmd(cmd) { if (B) B.win_cmd(cmd); }
function save(key, val) { if (B) B.save(key, JSON.stringify(val)); }
function doSearch(q, limit, offset, kind) { if (B) B.search(q, limit, offset, kind); }

/* ======================= utilidades ======================= */
const $ = (id) => document.getElementById(id);
const W = $('win');
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const cls = (name, on) => W.classList.toggle(name, !!on);
const has = (name) => W.classList.contains(name);
function fmt(s) { s = Math.max(0, Math.floor(s || 0)); const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, x = s % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(x).padStart(2, '0'); }
function bgUrl(u) { return u ? "url('" + String(u).replace(/'/g, '%27') + "')" : ''; }
const PEOPLE = ['#4FB4D8', '#D1517A', '#8E6CF2', '#3DBE7A', '#F2A33A', '#1F5FBF', '#E0457B', '#22A699'];
function pcolor(name) { if (!name) return '#8E6CF2'; if (name === 'Cumito') return '#8E6CF2'; let n = 0; for (const c of name) n += c.codePointAt(0); return PEOPLE[n % PEOPLE.length]; }
function initial(name) { return esc((name || '?').trim().charAt(0).toUpperCase()); }
const FALLBACK = ['linear-gradient(135deg,#E0457B,#6C4CF5)', 'linear-gradient(135deg,#22A699,#1F5FBF)', 'linear-gradient(135deg,#F7A35C,#6C4CF5)', 'linear-gradient(135deg,#B8323A,#3A2D6B)', 'linear-gradient(135deg,#E87AA4,#5A3FC0)'];
function coverStyle(url, seed) {
  if (url) return 'background-image:' + bgUrl(url) + (/\/(hq|mq|sd)default\.jpg/.test(url) ? ';background-size:auto 134%' : '');
  let n = 0; for (const c of String(seed || 'x')) n += c.codePointAt(0);
  return 'background-image:' + FALLBACK[n % FALLBACK.length];
}
const I = {
  back: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M14 6l-6 6 6 6"/></svg>',
  x: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round"><path d="M7 7l10 10M17 7L7 17"/></svg>',
  clock: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,.6)" stroke-width="2.4" stroke-linecap="round"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/></svg>',
  play: '<svg width="13" height="13" viewBox="0 0 24 24" fill="#141318"><path d="M8 5.6v12.8a.8.8 0 0 0 1.2.7l10-6.4a.8.8 0 0 0 0-1.4l-10-6.4A.8.8 0 0 0 8 5.6z"/></svg>',
  playw: '<svg width="15" height="15" viewBox="0 0 24 24" fill="#fff"><path d="M8 5.6v12.8a.8.8 0 0 0 1.2.7l10-6.4a.8.8 0 0 0 0-1.4l-10-6.4A.8.8 0 0 0 8 5.6z"/></svg>',
  pausew: '<svg width="15" height="15" viewBox="0 0 24 24" fill="#fff"><rect x="6" y="5" width="4.2" height="14" rx="1.6"/><rect x="13.8" y="5" width="4.2" height="14" rx="1.6"/></svg>',
  grip: '<svg width="12" height="18" viewBox="0 0 12 18" fill="rgba(255,255,255,.45)"><circle cx="3" cy="4" r="1.4"/><circle cx="9" cy="4" r="1.4"/><circle cx="3" cy="9" r="1.4"/><circle cx="9" cy="9" r="1.4"/><circle cx="3" cy="14" r="1.4"/><circle cx="9" cy="14" r="1.4"/></svg>',
  shuffle: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7h3.5c2 0 3.2 1 4.3 2.6l2.4 3.8c1.1 1.6 2.3 2.6 4.3 2.6H21M3 17h3.5c1.4 0 2.4-.5 3.2-1.3M13.3 8.3c.8-.8 1.8-1.3 3.2-1.3H21M18 4l3 3-3 3M18 14l3 3-3 3"/></svg>',
  plus: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.3" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  img: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="4.5" width="17" height="15" rx="3"/><circle cx="9" cy="10" r="1.6"/><path d="M4 17l5-4.5 3.5 3 3-2.5L20 17"/></svg>',
  trash: '<svg class="trash" width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="#FF6B70" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12M10.5 11v5M13.5 11v5"/></svg>',
  power: '<svg class="trash" width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="#FF6B70" stroke-width="2" stroke-linecap="round"><path d="M12 4v7.5M7.3 7.2a7 7 0 1 0 9.4 0"/></svg>',
};

/* ======================= estado ======================= */
const S = {
  st: { now_playing: null, queue: [], recent: [], members: [], features: [] },
  connected: true, me: null, recentSearches: [], visual: {}, scale: 1,
  elapsed: 0, elapsedAt: performance.now(),
  albums: [], albumsRev: null, acts: [], covers: {}, asked: {},
  lastReaction: null, firstState: true,
};
const feat = (f) => S.connected && (S.st.features || []).includes(f);

/* ======================= eventos de Python ======================= */
function onEvent(type, json) {
  let d = {};
  try { d = JSON.parse(json || '{}'); } catch (e) { return; }
  const h = HANDLERS[type];
  if (h) { try { h(d); } catch (e) { console.error(type, e); } }
}
const HANDLERS = {
  config(d) {
    S.me = d.name || null; S.recentSearches = d.recent_searches || []; S.visual = d.visual || {}; S.scale = d.scale || 1;
    S.version = d.version || '';
    renderHome();
  },
  connected(ok) { S.connected = !!ok; if (!ok) { S.st = Object.assign({}, S.st, { now_playing: null, queue: [] }); } renderAll(); },
  state(st) { applyState(st); },
  search_results(d) { onResults(d); },
  playlist_preview(d) { showPreview(d); },
  activity_list(d) { S.acts = (d.entries || []).slice(-150); S.actsLoaded = true; renderFeed(); renderHome(); },
  status(d) { renderStatus(d); },
  lyrics(d) { onLyrics(d); },
  stats(d) { renderWrapped(d); },
  albums(d) { S.albums = d.albums || []; renderHome(); if (P.open === 'albums' && AL.view === 'grid') renderAlbums(); if ($('card2').dataset.kind === 'picker') openPicker(true); },
  album(d) { onAlbum(d.album); },
  album_cover(d) { if (d.cover && d.data) { S.covers[d.cover] = 'data:image/jpeg;base64,' + d.data; renderHome(); if (P.open === 'albums') renderAlbums(true); } },
  album_added(d) { onAlbumAdded(d); },
  error(d) { toast(d.message || 'Algo salió mal'); AL.saving = false; },
  update(d) { renderBanner(d); },
  cover_picked(d) { if (d.b64) { AL.edit.cover = d.b64; AL.edit.remove = false; renderAlbums(); } else if (d.error) toast(d.error); },
};

/* ======================= estado que llega ======================= */
function applyState(st) {
  const prev = S.st;
  const prevNp = prev.now_playing || {};
  S.st = Object.assign({}, prev, st);
  S.connected = true;
  const np = S.st.now_playing;
  if (np) {
    S.elapsed = +np.elapsed || 0; S.elapsedAt = performance.now();
  }
  renderAll(prevNp);
  // reacciones de otros
  const r = S.st.reaction;
  if (r && r.id != null && r.id !== S.lastReaction) {
    const first = S.lastReaction === null;
    S.lastReaction = r.id;
    if (!(first && Date.now() / 1000 - (r.ts || 0) > 8)) floatReaction(r.emoji, r.who);
  }
  // actividad nueva (aviso arriba)
  const a = S.st.activity_last;
  if (a && a.id != null) {
    const key = a.id + '|' + a.text;
    if (key !== S.lastActKey) {
      const isNew = S.lastActKey && a.id !== +String(S.lastActKey).split('|')[0];
      const first = !S.lastActKey;
      S.lastActKey = key;
      S.acts = S.acts.filter((x) => x.id !== a.id).concat([a]).slice(-150);
      if (isNew || (first && Date.now() / 1000 - (a.ts || 0) < 15)) ticker(a);
      if (P.open === 'activity') renderFeed();
    }
  }
  // discos: si cambiaron, se vuelven a pedir
  if (S.st.albums_rev != null && S.st.albums_rev !== S.albumsRev) {
    S.albumsRev = S.st.albums_rev;
    if (feat('albums')) {
      send('album_list');
      if (P.open === 'albums' && AL.view === 'page' && AL.cur) send('album_get', { id: AL.cur.id });
    }
  }
  if (S.firstState && feat('albums')) { S.firstState = false; send('activity_list'); }
  if (P.open === 'lyrics') lyricsFollow();
  updateAddedTiles();
}

function renderAll(prevNp) {
  const np = S.connected ? S.st.now_playing : null;
  cls('is-home', !np);
  cls('has-now', !!np);
  cls('is-playing', !!np && !np.paused);
  cls('is-paused', !np || !!np.paused);
  cls('offline', !S.connected);
  cls('has-v2', feat('shuffle'));
  cls('can-seek', feat('seek') && np && np.duration);
  cls('no-albums', !feat('albums'));
  if (!np) { closeSheet(); setIdle(false); }
  if (!np && P.open === 'lyrics') closePanel();
  renderNow(prevNp || {});
  renderHome();
  renderQueue();
  renderFeatures();
}

/* ======================= ahora sonando ======================= */
let artA = true;
function setArt(url) {
  const cur = artA ? $('art') : $('art2');
  const nxt = artA ? $('art2') : $('art');
  if (cur.dataset.url === (url || '')) return;
  nxt.style.backgroundImage = url ? bgUrl(url) : FALLBACK[0];
  nxt.style.backgroundSize = url && /\/(hq|mq|sd)default\.jpg/.test(url) ? 'auto 134%' : 'cover';
  nxt.dataset.url = url || '';
  nxt.classList.remove('next');
  cur.classList.add('next');
  artA = !artA;
}
function renderNow(prevNp) {
  const np = S.connected ? S.st.now_playing : null;
  if (!np) { $('trun').textContent = 'Nada sonando'; return; }
  setArt(np.art_url);
  $('thumb').style.cssText = coverStyle(np.art_url, np.title);
  const title = np.title || 'Sin título';
  if ($('trun').dataset.t !== title) {
    $('trun').dataset.t = title;
    $('twrap').classList.remove('scroll');
    $('trun').textContent = title;
    requestAnimationFrame(() => {
      const wrap = $('twrap');
      if ($('trun').scrollWidth > wrap.clientWidth + 2) {
        wrap.classList.add('scroll');
        $('trun').innerHTML = esc(title) + '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;' + esc(title) + '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;';
      }
    });
  }
  let artist = np.uploader || '';
  const who = np.radio ? 'la radio' : np.who;
  if (who && who !== S.me) artist = artist ? artist + ' · puso ' + who : 'puso ' + who;
  $('artist').textContent = artist;
  $('it').textContent = title;
  $('ia').textContent = np.uploader || '';
  $('mpt').textContent = title;
  $('mpa').textContent = np.uploader || '';
  $('mpc').style.cssText = coverStyle(np.art_url, np.title) + ';width:38px;height:38px;border-radius:11px;box-shadow:none';
  $('mpp').innerHTML = np.paused ? I.playw : I.pausew;
  $('ttot').textContent = fmt(np.duration);
  if (prevNp.title !== np.title) $('fill').style.transition = 'none';
  tickProgress(true);
  requestAnimationFrame(() => { $('fill').style.transition = ''; });
}
function curElapsed() {
  const np = S.st.now_playing;
  if (!np) return 0;
  let e = S.elapsed + (np.paused ? 0 : (performance.now() - S.elapsedAt) / 1000);
  if (np.duration) e = Math.min(e, np.duration);
  return e;
}
function tickProgress(force) {
  const np = S.connected ? S.st.now_playing : null;
  if (!np || SEEK.drag) return;
  const e = curElapsed();
  $('tel').textContent = fmt(e);
  const pct = np.duration ? Math.min(100, e / np.duration * 100) : 0;
  $('fill').style.width = pct.toFixed(2) + '%';
  $('knob').style.left = pct.toFixed(2) + '%';
}
setInterval(() => { if (!document.hidden) tickProgress(); }, 1000);

function renderFeatures() {
  const np = S.st.now_playing;
  $('heart').classList.toggle('hide', !feat('albums'));
  $('bshuffle').classList.toggle('hide', !feat('shuffle'));
  $('brepeat').classList.toggle('hide', !feat('repeat'));
  $('breact').classList.toggle('hide', !feat('react'));
  $('blyrics').classList.toggle('hide', !feat('lyrics'));
  const rep = S.st.repeat || 'off';
  $('brepeat').classList.toggle('on', rep !== 'off');
  $('rone').classList.toggle('hide', rep !== 'one');
  $('brepeat').title = { off: 'Repetir', all: 'Repitiendo toda la lista', one: 'Repitiendo esta canción' }[rep] || 'Repetir';
  $('bprev').disabled = !feat('prev') || !(np || S.st.can_prev);
}

/* adelantar: tocar o arrastrar la barra */
const SEEK = { drag: false, f: 0 };
(function () {
  const bar = $('bar');
  const fAt = (x) => { const r = bar.getBoundingClientRect(); return Math.max(0, Math.min(1, (x - r.left) / r.width)); };
  const show = (f) => {
    const np = S.st.now_playing || {};
    $('fill').style.width = (f * 100).toFixed(2) + '%';
    $('knob').style.left = (f * 100).toFixed(2) + '%';
    $('tel').textContent = fmt(f * (np.duration || 0));
  };
  bar.addEventListener('pointerdown', (e) => {
    if (!has('can-seek')) return;
    e.preventDefault(); e.stopPropagation();
    SEEK.drag = true; bar.classList.add('drag'); bar.setPointerCapture(e.pointerId);
    SEEK.f = fAt(e.clientX); show(SEEK.f);
  });
  bar.addEventListener('pointermove', (e) => { if (SEEK.drag) { SEEK.f = fAt(e.clientX); show(SEEK.f); } });
  const end = () => {
    if (!SEEK.drag) return;
    SEEK.drag = false; bar.classList.remove('drag');
    const np = S.st.now_playing;
    if (np && np.duration) seekTo(SEEK.f * np.duration);
  };
  bar.addEventListener('pointerup', end);
  bar.addEventListener('pointercancel', end);
})();
function seekTo(sec) {
  const np = S.st.now_playing;
  if (!np || !feat('seek')) return;
  S.elapsed = sec; S.elapsedAt = performance.now();
  tickProgress(true);
  send('seek', { pos: Math.round(sec * 10) / 10 });
  if (P.open === 'lyrics') lyricsFollow();
}

/* ======================= aviso de actividad arriba ======================= */
let tkTimer = null;
function ticker(a) {
  const box = $('ticker');
  const el = document.createElement('div');
  el.className = 'tk';
  const what = (a.text || '') + (a.title ? ': ' + a.title : '');
  el.innerHTML = '<span class="av" style="background:' + pcolor(a.who) + '">' + initial(a.who) + '</span><b>' + esc(a.who) + '</b><span class="ell">' + esc(what) + '</span>';
  box.querySelectorAll('.tk').forEach((x) => { x.classList.remove('on'); setTimeout(() => x.remove(), 500); });
  box.appendChild(el);
  $('logo').style.transition = 'opacity .3s'; $('logo').style.opacity = '0';
  requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add('on')));
  clearTimeout(tkTimer);
  tkTimer = setTimeout(() => { el.classList.remove('on'); setTimeout(() => el.remove(), 500); $('logo').style.opacity = '1'; }, 4000);
}

/* ======================= inicio ======================= */
function renderHome() {
  const h = new Date().getHours();
  const greet = h >= 5 && h < 12 ? 'Buenos días' : (h >= 12 && h < 19 ? 'Buenas tardes' : 'Buenas noches');
  $('greet').textContent = S.connected ? (S.me ? greet + ', ' + S.me : greet) : 'Cumito';
  $('htitle').textContent = S.connected ? '¿Qué escucharemos hoy?' : 'Buscando a Cumito…';
  $('hsub').classList.toggle('hide', S.connected);
  $('hsub').textContent = 'No se pudo conectar con el servidor. Reintentando solo.';
  // quién está conectado
  const names = S.st.members || [];
  const others = names.filter((n) => n !== S.me);
  const hasMe = names.includes(S.me);
  let txt;
  if (!others.length) txt = hasMe ? 'Solo tú por ahora' : 'Nadie conectado';
  else {
    const list = others.length > 3 ? others.slice(0, 2).concat([(others.length - 2) + ' más']) : others.slice();
    if (hasMe) list.push('tú');
    txt = list.length === 1 ? list[0] : list.slice(0, -1).join(', ') + ' y ' + list[list.length - 1];
  }
  const shown = others.slice(0, 3).concat(hasMe ? [S.me] : []);
  const avs = shown.map((n) => '<span style="background:' + pcolor(n) + '">' + (n === S.me ? 'T' : initial(n)) + '</span>').join('');
  const sig = names.join('|') + S.me;
  if ($('members').dataset.sig !== sig) {
    $('members').dataset.sig = sig;
    $('members').innerHTML = (avs ? '<div class="avs">' + avs + '</div>' : '') + '<span style="font-size:11px;font-weight:700;color:rgba(244,242,250,.65)">' + esc(txt) + '</span>' + (names.length ? '<span class="live" style="width:7px;height:7px;border-radius:4px;background:#3DDC84"></span>' : '');
  }
  // lo último que sonó
  const recent = S.st.recent || [];
  const rsig = recent.map((r) => r.webpage_url).join('|');
  if ($('recentCards').dataset.sig !== rsig) {
    $('recentCards').dataset.sig = rsig;
    $('recentCards').innerHTML = recent.map((r, i) =>
      '<button class="card" type="button" style="width:112px" data-play="' + esc(r.webpage_url) + '" title="Ponerla otra vez">' +
      '<div class="cv" style="width:112px;height:112px;border-radius:18px;' + coverStyle(r.art_url, r.title) + ';box-shadow:0 12px 24px -12px rgba(0,0,0,.6)"><span class="playdot">' + I.play + '</span></div>' +
      '<div class="ell" style="font-size:12px;font-weight:800;margin-top:7px">' + esc(r.title) + '</div>' +
      '<div class="ell" style="font-size:10.5px;font-weight:600;color:rgba(244,242,250,.55)">' + esc(r.uploader || '') + '</div></button>').join('');
  }
  $('recentEmpty').classList.toggle('hide', !!recent.length);
  // discos
  const showAlb = feat('albums');
  $('hdiscos').classList.toggle('hide', !showAlb);
  if (showAlb) {
    const al = S.albums.slice(0, 4);
    const asig = al.map((a) => [a.id, a.name, a.count, a.color, a.cover, !!S.covers[a.cover]].join(',')).join('|');
    if ($('homeAlbums').dataset.sig !== asig) {
      $('homeAlbums').dataset.sig = asig;
      $('homeAlbums').innerHTML = al.length ? al.map((a) => {
        const light = isLight(a.color || '#8E6CF2');
        const fg = light ? '#3A2400' : '#FFFFFF';
        const sub = light ? 'rgba(58,36,0,.7)' : 'rgba(255,255,255,.75)';
        const ph = a.cover ? (S.covers[a.cover] ? '<span class="ph" style="background-image:url(' + S.covers[a.cover] + ')"></span>' : askCover(a.cover)) : '';
        return '<button class="card in" type="button" data-album="' + a.id + '"><div class="cv dcard" style="background-color:' + esc(a.color || '#8E6CF2') + '">' + ph +
          '<span class="n" style="color:' + fg + '">' + esc(a.name) + '</span><span class="s" style="color:' + sub + '">' + (a.owner ? 'de ' + esc(a.owner) + ' · ' : '') + plural(a.count, 'canción', 'canciones') + '</span></div></button>';
      }).join('') : '<div class="tip" style="grid-column:span 2">Todavía no hay discos. Arma el primero con tus canciones favoritas.</div>';
    }
    $('allAlbums').classList.toggle('hide', S.albums.length <= 4);
  }
  // actividad
  const acts = S.acts.slice(-3).reverse();
  $('hact').classList.toggle('hide', !acts.length || !S.connected);
  const actsig = acts.map((a) => a.id + a.text).join('|');
  if ($('homeAct').dataset.sig !== actsig) {
    $('homeAct').dataset.sig = actsig;
    $('homeAct').innerHTML = acts.map((a) => '<div class="actl"><span class="av" style="background:' + pcolor(a.who) + '">' + initial(a.who) + '</span><span class="ell"><b>' + esc(a.who) + '</b> ' + esc(a.text) + (a.title ? ': ' + esc(a.title) : '') + '</span></div>').join('');
  }
  $('pword').textContent = has('is-home') ? 'Buscar canción o pegar un link' : 'Buscar';
}
function plural(n, one, many) { n = n || 0; return n + ' ' + (n === 1 ? one : many); }
function isLight(hex) { const c = parseInt(String(hex).slice(1), 16); const r = (c >> 16) & 255, g = (c >> 8) & 255, b = c & 255; return (0.299 * r + 0.587 * g + 0.114 * b) > 165; }
function askCover(h) { if (h && !S.asked[h]) { S.asked[h] = 1; send('album_cover', { cover: h }); } return ''; }

/* ======================= la lista (hoja) ======================= */
function openSheet() { if (has('is-home') || has('is-search') || has('is-panel')) return; cls('is-sheet', true); setIdle(false); renderQueue(true); }
function closeSheet() { cls('is-sheet', false); }
const QS = { seen: new Set(), flash: {}, sig: null };
function renderQueue(force) {
  if (DRAG.on) return;
  const q = S.st.queue || [];
  const np = S.st.now_playing;
  const now = Date.now();
  q.forEach((t) => {
    const prep = t.prepared !== undefined ? t.prepared : t.ready;
    if (prep) { if (QS.seen.has(t.uid)) { QS.seen.delete(t.uid); QS.flash[t.uid] = now + 2000; } }
    else QS.seen.add(t.uid);
  });
  $('bclear').disabled = !q.length;
  const sig = JSON.stringify([np && [np.title, np.paused], q.map((t) => [t.uid, t.prepared, t.loading, t.art_url, t.title])]);
  if (sig === QS.sig && !force) return;
  QS.sig = sig;
  const ready = q.filter((t) => t.prepared !== undefined ? t.prepared : t.ready);
  const pend = q.filter((t) => !(t.prepared !== undefined ? t.prepared : t.ready));
  let h = '';
  if (np) h += '<div class="qnow"><span class="qc thumb" style="width:38px;height:38px;border-radius:10px;box-shadow:none;' + coverStyle(np.art_url, np.title) + '"></span><span style="flex:1;min-width:0"><span class="lab">SONANDO AHORA</span><span class="ell" style="display:block;font-size:13px;font-weight:800">' + esc(np.title) + '</span></span><span class="eqm"><i></i><i></i><i></i></span></div>';
  if (!q.length) h += '<div class="qempty">La lista está vacía.<br>Busca algo para que siga la música.</div>';
  if (ready.length) {
    h += '<div class="ready"><div class="ready-t">LISTAS PARA SONAR · arrastra para ordenar</div><div id="readyBox">';
    ready.forEach((t, i) => {
      h += '<div class="qrow row' + ((QS.flash[t.uid] || 0) > now ? ' flash' : '') + '" data-uid="' + t.uid + '" style="animation-delay:' + (0.12 + i * 0.06) + 's" title="Tócala para ponerla ya · arrástrala para cambiar el orden">' +
        '<span class="qc" style="' + coverStyle(t.art_url, t.title) + '"></span>' +
        '<span style="flex:1;min-width:0"><span class="qt ell">' + esc(t.title) + '</span><span class="qa ell">' + esc(t.uploader || '') + (t.who && t.who !== S.me ? ' · ' + esc(t.who === 'Radio' ? 'radio' : t.who) : '') + '</span></span>' +
        '<span class="qd">' + (t.duration ? fmt(t.duration) : '') + '</span>' +
        '<button class="btn qx" type="button" title="Quitar" data-remove="' + t.uid + '">' + I.x + '</button>' +
        '<span class="grip">' + I.grip + '</span></div>';
    });
    h += '</div></div>';
  }
  if (pend.length) {
    h += '<div class="divider"><span></span><b>SIN PREPARAR · ' + pend.length + '</b><span></span></div>';
    pend.forEach((t, i) => {
      h += '<div class="qrow row pend' + (t.loading ? ' loading' : '') + '" data-prep="' + t.uid + '" style="animation-delay:' + (0.34 + Math.min(i, 8) * 0.06) + 's">' +
        '<span class="qc"></span><span style="flex:1;min-width:0"><span class="qt ell">' + esc(t.title) + '</span><span class="qa">' + (t.loading ? 'Preparándola…' : 'Tócala para prepararla') + '</span></span>' +
        '<span class="qd">' + (t.duration ? fmt(t.duration) : '') + '</span>' +
        '<button class="btn qx" type="button" title="Quitar" data-remove="' + t.uid + '">' + I.x + '</button></div>';
    });
  }
  const sc = $('qscroll').scrollTop;
  $('qscroll').innerHTML = h;
  $('qscroll').scrollTop = sc;
  if (!has('is-sheet')) $('qscroll').querySelectorAll('.qrow').forEach((r) => (r.style.animation = 'none'));
}
function qIndex(uid) { return (S.st.queue || []).findIndex((t) => t.uid === uid); }
function qcmd(action, uid) { send(action, { index: qIndex(uid), uid: uid }); }

/* arrastrar para reordenar (solo las listas) */
const DRAG = { on: false };
(function () {
  const box = () => $('readyBox');
  let start = null;
  $('qscroll').addEventListener('pointerdown', (e) => {
    const row = e.target.closest('#readyBox .qrow');
    if (!row || e.target.closest('.qx') || e.button !== 0) return;
    start = { row: row, x: e.clientX, y: e.clientY, id: e.pointerId, t: Date.now() };
  });
  window.addEventListener('pointermove', (e) => {
    if (start && !DRAG.on && (Math.abs(e.clientY - start.y) > 5)) begin(e);
    if (DRAG.on) move(e);
  });
  window.addEventListener('pointerup', (e) => {
    if (DRAG.on) { finish(false); start = null; return; }
    if (start && Math.abs(e.clientY - start.y) <= 5 && start.row.contains(e.target)) qcmd('play_index', +start.row.dataset.uid);
    start = null;
  });
  window.addEventListener('keydown', (e) => { if (e.key === 'Escape' && DRAG.on) { finish(true); start = null; e.stopPropagation(); } }, true);
  function begin(e) {
    const rows = Array.from(box().children);
    const r = start.row.getBoundingClientRect();
    const wr = W.getBoundingClientRect();
    DRAG.on = true; DRAG.rows = rows; DRAG.from = rows.indexOf(start.row); DRAG.to = DRAG.from;
    DRAG.h = r.height; DRAG.dy = e.clientY - r.top;
    DRAG.top0 = rows.map((x) => x.getBoundingClientRect().top);
    const lift = start.row.cloneNode(true);
    lift.classList.add('lift'); lift.style.width = r.width + 'px'; lift.style.left = (r.left - wr.left) + 'px'; lift.style.top = (r.top - wr.top) + 'px';
    W.appendChild(lift); DRAG.lift = lift; DRAG.wtop = wr.top;
    start.row.classList.add('ghost');
    document.body.style.cursor = 'grabbing';
  }
  function move(e) {
    DRAG.lift.style.top = (e.clientY - DRAG.dy - DRAG.wtop) + 'px';
    const y = e.clientY - DRAG.dy + DRAG.h / 2;
    let to = 0;
    DRAG.top0.forEach((t, i) => { if (y > t + DRAG.h / 2) to = i; });
    to = Math.max(0, Math.min(DRAG.rows.length - 1, to));
    DRAG.to = to;
    DRAG.rows.forEach((row, i) => {
      let off = 0;
      if (i !== DRAG.from) {
        if (DRAG.from < to && i > DRAG.from && i <= to) off = -DRAG.h;
        if (DRAG.from > to && i < DRAG.from && i >= to) off = DRAG.h;
      }
      row.style.transform = off ? 'translateY(' + off + 'px)' : '';
    });
    // si llega al borde, la lista se mueve sola
    const sc = $('qscroll').getBoundingClientRect();
    if (e.clientY < sc.top + 30) $('qscroll').scrollTop -= 8;
    if (e.clientY > sc.bottom - 30) $('qscroll').scrollTop += 8;
  }
  function finish(cancel) {
    const uid = +DRAG.rows[DRAG.from].dataset.uid;
    const to = DRAG.to, from = DRAG.from;
    DRAG.lift.remove();
    DRAG.rows.forEach((r) => { r.style.transform = ''; r.classList.remove('ghost'); });
    DRAG.on = false;
    document.body.style.cursor = '';
    if (!cancel && to !== from) {
      // se ve al instante; el servidor confirma
      const q = S.st.queue.slice();
      const readyUids = DRAG.rows.map((r) => +r.dataset.uid);
      const moved = readyUids.splice(from, 1)[0];
      readyUids.splice(to, 0, moved);
      const byUid = {}; q.forEach((t) => (byUid[t.uid] = t));
      S.st.queue = readyUids.map((u) => byUid[u]).concat(q.filter((t) => !readyUids.includes(t.uid)));
      send('queue_move', { uid: uid, to: to });
    }
    QS.sig = null;
    renderQueue(true);
    $('qscroll').querySelectorAll('.qrow').forEach((r) => (r.style.animation = 'none'));
  }
})();

/* ======================= buscador ======================= */
const SR = { kind: 'music', phase: 'home', query: null, results: [], count: 0, added: {}, more: false, preview: null };
function openSearch() {
  if (has('is-search')) return;
  closeSheet(); closePanel(true); setIdle(false); hideReactions();
  cls('is-search', true);
  if (!$('q').value.trim()) { SR.phase = 'home'; renderSearch(); }
  setTimeout(() => { $('q').focus(); $('q').select(); }, 260);
}
function closeSearch() {
  if (!has('is-search')) return;
  cls('is-search', false);
  $('q').blur();
  closePreview(true);
  setTimeout(() => { if (!has('is-search')) { $('q').value = ''; SR.phase = 'home'; SR.added = {}; renderSearch(); } }, 500);
}
function setKind(kind) {
  if (kind === SR.kind) return;
  const tabs = $('stabs');
  tabs.parentElement.classList.toggle('to-right', kind === 'all');
  tabs.parentElement.classList.toggle('to-left', kind !== 'all');
  SR.kind = kind;
  const ind = tabs.querySelector('.ind');
  ind.style.left = kind === 'music' ? '0px' : '92px';
  ind.style.right = kind === 'music' ? '86px' : '8px';
  tabs.querySelectorAll('.tab').forEach((t) => t.classList.toggle('on', t.dataset.kind === kind));
  if (SR.query && (SR.phase === 'results' || SR.phase === 'loading')) runSearch(SR.query);
}
function isLink(q) { return /^(https?:\/\/|www\.|youtu\.be\/|youtube\.com\/|soundcloud\.com\/|open\.spotify\.com\/|spotify:)/i.test(q); }
function submitSearch() {
  let q = $('q').value.trim();
  if (!q) return;
  if (isLink(q)) {
    if (!/^(https?:|spotify:)/i.test(q)) q = 'https://' + q;
    const low = q.toLowerCase();
    if (low.includes('list=') || (low.includes('soundcloud.com') && low.includes('/sets/')) || /spotify.*(playlist|album)/.test(low)) {
      SR.preview = { url: q, loading: true };
      SR.phase = 'loading'; SR.loadingText = 'Abriendo playlist…'; renderSearch();
      send('playlist_preview', { url: q });
      return;
    }
    send('play', { query: q });
    toast('Agregando…');
    closeSearch();
    return;
  }
  const rs = [q].concat(S.recentSearches.filter((x) => x.toLowerCase() !== q.toLowerCase())).slice(0, 6);
  S.recentSearches = rs; save('recent_searches', rs);
  runSearch(q);
}
function runSearch(q) {
  SR.query = q; SR.results = []; SR.added = {}; SR.count = 0; SR.phase = 'loading'; SR.loadingText = null;
  renderSearch();
  doSearch(q, 8, 0, SR.kind);
}
function onResults(d) {
  if (!has('is-search') || d.query !== SR.query) return;
  if (d.kind && d.kind !== SR.kind) return;
  const off = +d.offset || 0;
  const res = d.results || [];
  if (off === 0) SR.results = res; else SR.results = SR.results.concat(res);
  SR.more = res.length >= (off === 0 ? 8 : 6);
  SR.moreLoading = false;
  SR.phase = 'results';
  renderSearch(off);
}
function renderSearch(appendFrom) {
  const v = $('sview');
  let h = '';
  if (SR.phase === 'home') {
    if (S.recentSearches.length) {
      h += '<div class="in2 sec-t" style="margin-top:22px;font-size:10px;color:rgba(244,242,250,.55);animation-delay:.18s">BÚSQUEDAS RECIENTES</div><div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px">';
      S.recentSearches.forEach((t, k) => { h += '<button class="btn chip in2" type="button" data-chip="' + esc(t) + '" style="animation-delay:' + (0.2 + k * 0.05) + 's">' + I.clock + esc(t) + '</button>'; });
      h += '</div>';
    }
    const last = (S.st.recent || []).slice(0, 4);
    if (last.length) {
      h += '<div class="in2 sec-t" style="margin-top:22px;font-size:10px;color:rgba(244,242,250,.55);animation-delay:.34s">LO ÚLTIMO QUE SONÓ</div><div style="margin-top:6px;display:flex;flex-direction:column;gap:2px">';
      last.forEach((r, k) => {
        h += '<button class="row in2" type="button" data-play="' + esc(r.webpage_url) + '" style="display:flex;align-items:center;gap:10px;padding:6px;animation-delay:' + (0.4 + k * 0.06) + 's">' +
          '<span style="width:40px;height:40px;border-radius:10px;flex:none;' + coverStyle(r.art_url, r.title) + ';background-size:cover"></span>' +
          '<span style="flex:1;min-width:0"><span class="ell" style="display:block;font-size:13px;font-weight:700">' + esc(r.title) + '</span><span class="ell" style="display:block;font-size:11px;font-weight:600;color:rgba(244,242,250,.5)">' + esc(r.uploader || '') + '</span></span>' +
          '<span style="font-size:11px;font-weight:800;color:#C9B4F8">Poner</span></button>';
      });
      h += '</div>';
    }
    h += '<div class="in2 tip" style="margin-top:18px;animation-delay:.4s">Escribe y aprieta Enter, o toca una búsqueda reciente. También puedes pegar el link de una canción o de una playlist (de YouTube o Spotify).</div>';
    v.innerHTML = h;
    return;
  }
  if (SR.phase === 'loading') {
    if (SR.loadingText) { v.innerHTML = '<div class="hopper"><img src="../cumito_feliz.png" alt=""><span>' + esc(SR.loadingText) + '</span></div>'; return; }
    h = '<div class="grid2" style="margin-top:16px">';
    for (let i = 0; i < 4; i++) h += '<div><div class="sk" style="height:150px"></div><div class="sk" style="height:12px;width:80%;margin-top:9px;border-radius:6px"></div><div class="sk" style="height:10px;width:50%;margin-top:6px;border-radius:5px"></div></div>';
    v.innerHTML = h + '</div>';
    return;
  }
  if (!SR.results.length) { v.innerHTML = '<div class="tip" style="text-align:center;margin-top:60px;font-size:12.5px">No encontré nada con eso.<br>Prueba escribiéndolo de otra forma.</div>'; return; }
  if (appendFrom && $('sgrid')) {
    const grid = $('sgrid');
    SR.results.slice(appendFrom).forEach((r, k) => grid.insertAdjacentHTML('beforeend', tileHtml(r, appendFrom + k, k)));
  } else {
    h = '<div class="grid2" id="sgrid" style="margin-top:16px">' + SR.results.map((r, i) => tileHtml(r, i, i)).join('') + '</div>';
    h += '<button class="btn glass more" type="button" id="smore" data-act="more">Buscar más</button>';
    v.innerHTML = h;
  }
  const more = $('smore');
  if (more) { more.classList.toggle('hide', !SR.more); more.textContent = SR.moreLoading ? 'Buscando…' : 'Buscar más'; more.disabled = !!SR.moreLoading; if (more.parentElement !== v) v.appendChild(more); else v.appendChild(more); }
}
function tileHtml(r, i, k) {
  const st = SR.added[i];
  return '<button class="tile ' + (st ? st.phase : '') + '" type="button" data-tile="' + i + '" style="animation-delay:' + (k * 0.07) + 's">' +
    '<div class="art2" style="' + coverStyle(r.art_url, r.title) + '"><div class="liq"></div>' +
    '<div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px">' +
    '<div style="position:relative;width:34px;height:34px;display:flex;align-items:center;justify-content:center"><div class="spin" style="position:absolute"></div>' +
    '<svg class="chk" style="position:absolute" width="34" height="34" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="11" fill="rgba(255,255,255,.18)"/><path d="M7 12.5l3.2 3.2L17 9" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg></div>' +
    '<span class="lbl" style="font-size:12px;font-weight:800;color:#fff">' + (st && st.phase === 'added' ? 'Añadido' : (st && st.phase === 'failed' ? 'No se pudo' : 'Añadiendo…')) + '</span></div>' +
    '<span class="badge">Añadido · #' + (st ? st.pos : '') + ' en la lista</span></div>' +
    '<div class="ell" style="font-size:12.5px;font-weight:800;margin-top:8px">' + esc(r.title) + '</div>' +
    '<div class="ell" style="font-size:10.5px;font-weight:600;color:rgba(244,242,250,.55)">' + esc(r.uploader || '') + (r.duration ? ' · ' + fmt(r.duration) : '') + '</div></button>';
}
function addTile(i) {
  const r = SR.results[i];
  if (!r || SR.added[i]) return;
  const req = 'r' + Date.now().toString(36) + i;
  SR.added[i] = { phase: 'adding', req: req, t: Date.now() };
  refreshTile(i);
  send('play', { query: r.webpage_url, req: req });
  setTimeout(() => { const a = SR.added[i]; if (a && a.req === req && a.phase === 'adding') { a.phase = 'failed'; refreshTile(i); setTimeout(() => { if (SR.added[i] === a) { delete SR.added[i]; refreshTile(i); } }, 2500); } }, 40000);
}
function refreshTile(i) {
  const el = document.querySelector('[data-tile="' + i + '"]');
  if (!el) return;
  const tmp = document.createElement('div');
  tmp.innerHTML = tileHtml(SR.results[i], i, 0);
  const n = tmp.firstChild; n.style.animation = 'none';
  el.replaceWith(n);
}
function updateAddedTiles() {
  const q = S.st.queue || [];
  const np = S.st.now_playing;
  Object.keys(SR.added).forEach((i) => {
    const a = SR.added[i];
    if (a.phase !== 'adding') return;
    let pos = null;
    if (np && np.req === a.req) pos = 0;
    q.forEach((t, k) => { if (t.req === a.req) pos = k + 1; });
    if (pos !== null) {
      const el = document.querySelector('[data-tile="' + i + '"]');
      const wait = Math.max(0, 1100 - (Date.now() - a.t));   // que el líquido alcance a subir
      setTimeout(() => { a.phase = 'added'; a.pos = pos === 0 ? 'ya' : pos; refreshTile(i); const e2 = document.querySelector('[data-tile="' + i + '"] .badge'); if (e2 && pos === 0) e2.textContent = 'Sonando ahora'; }, wait);
    }
  });
}

/* vista previa de playlist (la hoja con las cartas) */
function showPreview(d) {
  if (!SR.preview || d.url !== SR.preview.url) return;
  SR.preview = d;
  const e = d.entries || [];
  SR.phase = 'home'; renderSearch();
  const name = d.title || 'Playlist';
  const url = (d.url || '').toLowerCase();
  const single = url.includes('v=') || url.includes('youtu.be/');
  let h = '<span style="align-self:center;display:block;width:38px;height:5px;border-radius:3px;background:rgba(255,255,255,.35)"></span>';
  if (!e.length) {
    h += '<div style="font-size:18px;font-weight:800;margin-top:14px;text-align:center">No pude abrir esa playlist</div><div class="tip" style="text-align:center;margin-top:6px">' + esc(d.error || 'Puede que sea privada o que el link esté incompleto.') + '</div><div style="flex:1"></div>' +
      '<div style="display:flex;gap:9px;margin-top:12px">' + (single ? '<button class="btn secb" type="button" data-act="pvSingle">Solo esta canción</button>' : '') + '<button class="btn secb" type="button" data-act="pvClose">Volver</button></div>';
  } else {
    const c = e.slice(0, 3).map((x) => x.art_url);
    h += '<div style="font-size:18px;font-weight:800;margin-top:14px;text-align:center">¿Quieres poner esta playlist?</div>' +
      '<div style="display:flex;justify-content:center;margin-top:18px"><div class="cards">' +
      '<div class="cd c1" style="' + coverStyle(c[1], name + 1) + '"></div><div class="cd c2" style="' + coverStyle(c[2], name + 2) + '"></div>' +
      '<div class="cd c3" style="' + coverStyle(c[0], name) + ';display:flex;flex-direction:column;justify-content:flex-end;padding:12px">' +
      '<span style="position:relative;z-index:1;font-size:14px;font-weight:800;text-shadow:0 1px 6px rgba(0,0,0,.6)" class="ell">' + esc(name) + '</span>' +
      '<span style="position:relative;z-index:1;font-size:10.5px;font-weight:700;color:rgba(255,255,255,.9);text-shadow:0 1px 6px rgba(0,0,0,.6)">' + plural(e.length, 'canción', 'canciones') + '</span></div></div></div>' +
      '<div class="sec-t" style="margin-top:18px;font-size:10px;color:rgba(244,242,250,.55)">CANCIONES</div>' +
      '<div style="flex:1;min-height:0;overflow-y:auto;margin-top:6px">' +
      e.map((x, i) => '<div class="pvrow" style="animation-delay:' + (0.45 + Math.min(i, 12) * 0.05) + 's"><span style="width:20px;font-size:11px;font-weight:800;color:rgba(244,242,250,.4);text-align:right;flex:none">' + (i + 1) + '</span><span style="flex:1;min-width:0"><span class="ell" style="display:block;font-size:12.5px;font-weight:700">' + esc(x.title) + '</span><span class="ell" style="display:block;font-size:10.5px;font-weight:600;color:rgba(244,242,250,.5)">' + esc(x.uploader || '') + '</span></span><span style="font-size:10.5px;font-weight:700;color:rgba(244,242,250,.4);flex:none">' + (x.duration ? fmt(x.duration) : '') + '</span></div>').join('') +
      '</div><div style="display:flex;flex-direction:column;gap:9px;margin-top:12px">' +
      '<button class="btn prim" type="button" data-act="pvAdd" style="flex:none;height:46px;border-radius:23px;font-size:14px;width:100%">Añadir ' + (e.length === 1 ? 'la canción' : 'las ' + e.length) + '</button>' +
      '<div style="display:flex;gap:9px">' + (single ? '<button class="btn secb" type="button" data-act="pvSingle">Solo esta canción</button>' : '') +
      holdBtn2('No gracias', 'pvNo') + '</div></div>';
  }
  $('pvs').innerHTML = h;
  $('pvdone').textContent = plural(e.length, 'canción agregada', 'canciones agregadas');
  $('pv').className = 'pv';
  void $('pv').offsetWidth;
  $('pv').classList.add('on');
}
function closePreview(instant) {
  const pv = $('pv');
  if (!pv.classList.contains('on')) return;
  pv.classList.remove('on', 'adding', 'done');
  SR.preview = null;
}
function previewAccept(single) {
  if (!SR.preview) return;
  send('play', single ? { query: SR.preview.url } : { query: SR.preview.url, as_playlist: true });
  const pv = $('pv');
  if (single) { closePreview(); toast('Agregando la canción…'); closeSearch(); return; }
  pv.classList.add('adding');
  setTimeout(() => pv.classList.add('done'), 260);
  setTimeout(() => { closePreview(); closeSearch(); }, 2600);
}

/* ======================= mantener presionado (borrar / apagar / no gracias) ======================= */
function holdBtn2(text, act) {
  return '<button class="btn hold2" type="button" data-hold="' + act + '"><svg width="100%" height="44" viewBox="0 0 152 44" preserveAspectRatio="none"><rect class="ring" pathLength="400" x="1.5" y="1.5" width="149" height="41" rx="20.5" fill="none" stroke="#FF5A5F" stroke-width="2.6"/></svg><span>' + esc(text) + '</span></button>';
}
const HOLD = { el: null, t: null, at: 0 };
document.addEventListener('pointerdown', (e) => {
  const b = e.target.closest('[data-hold]');
  if (!b || e.button !== 0) return;
  e.preventDefault();
  HOLD.el = b; HOLD.at = Date.now();
  b.classList.add('holding'); b.classList.remove('nudge');
  const span = b.querySelector('span'); if (span && !b.dataset.txt) b.dataset.txt = span.textContent;
  if (span) span.textContent = b.classList.contains('hold') ? 'Sigue presionando…' : 'Mantén…';
  clearTimeout(HOLD.t);
  HOLD.t = setTimeout(() => {
    b.classList.remove('holding'); b.classList.add('boom');
    const act = b.dataset.hold;
    HOLD.el = null;
    setTimeout(() => { b.classList.remove('boom'); if (span) span.textContent = b.dataset.txt; holdDone(act); }, 300);
  }, 2000);
});
function holdCancel() {
  const b = HOLD.el;
  if (!b) return;
  clearTimeout(HOLD.t);
  const quick = Date.now() - HOLD.at < 350;
  b.classList.remove('holding');
  const span = b.querySelector('span');
  if (span) span.textContent = quick ? 'Mantén presionado' : b.dataset.txt;
  if (quick) { b.classList.add('nudge'); setTimeout(() => { b.classList.remove('nudge'); if (span) span.textContent = b.dataset.txt; }, 1300); }
  HOLD.el = null;
}
document.addEventListener('pointerup', holdCancel);
document.addEventListener('pointercancel', holdCancel);
document.addEventListener('pointerout', (e) => { if (HOLD.el && e.target === HOLD.el && !HOLD.el.contains(e.relatedTarget)) holdCancel(); });
let confirmCb = null;
function askConfirm(title, msg, btn, icon, cb) {
  confirmCb = cb;
  $('confirm').innerHTML = (icon === 'power' ? I.power : I.trash) +
    '<div style="font-size:18px;font-weight:800;margin-top:10px">' + esc(title) + '</div>' +
    '<div style="font-size:12px;font-weight:600;color:rgba(244,242,250,.6);margin-top:6px;line-height:1.4">' + esc(msg) + '</div>' +
    '<button class="btn hold" type="button" data-hold="confirm" style="margin-top:18px"><svg width="260" height="46" viewBox="0 0 260 46"><path class="ring" pathLength="563" d="M130 1.5H237A21.5 21.5 0 0 1 237 44.5H23A21.5 21.5 0 0 1 23 1.5Z" fill="none" stroke="#FF5A5F" stroke-width="2.6"/></svg><span>' + esc(btn) + '</span></button>' +
    '<button class="btn" type="button" data-act="cancelConfirm" style="margin-top:6px;height:36px;padding:0 18px;border-radius:18px;color:rgba(244,242,250,.65);font-size:12.5px;font-weight:800">Cancelar</button>';
  $('veil').classList.add('on'); $('confirm').classList.add('on');
  $('veil').dataset.for = 'confirm';
}
function closeConfirm() { $('confirm').classList.remove('on'); hideVeil(); confirmCb = null; }
function hideVeil() { if (!$('confirm').classList.contains('on') && !$('card2').classList.contains('on')) $('veil').classList.remove('on'); }
function holdDone(act) {
  if (act === 'confirm') { const cb = confirmCb; closeConfirm(); if (cb) cb(); }
  else if (act === 'pvNo') { closePreview(); $('q').value = ''; SR.phase = 'home'; renderSearch(); }
  else if (act === 'albumDelete') albumDelete();
}

/* ======================= avisitos ======================= */
let toastT = null;
function toast(text, ms) {
  const t = $('toast');
  t.textContent = text;
  t.classList.add('on');
  clearTimeout(toastT);
  toastT = setTimeout(() => t.classList.remove('on'), ms || 2200);
}

/* ======================= hojas (paneles) ======================= */
const P = { open: null };
function openPanel(name) {
  closeSearch(); closeSheet(); setIdle(false); hideReactions();
  if (P.open && P.open !== name) { const old = $('p-' + P.open); old.classList.remove('open'); }
  P.open = name;
  cls('is-panel', true);
  const el = $('p-' + name);
  el.classList.remove('closing');
  void el.offsetWidth;
  el.classList.add('open');
  if (name === 'status') statusStart();
}
function closePanel(instant) {
  if (!P.open) return;
  const el = $('p-' + P.open);
  if (P.open === 'status') statusStop();
  if (P.open === 'lyrics') lyricsStop();
  el.classList.remove('open');
  if (!instant) { el.classList.add('closing'); setTimeout(() => el.classList.remove('closing'), 460); }
  P.open = null;
  cls('is-panel', false);
}

/* ---------- opciones: la rueda ---------- */
const IC = {
  chat: 'M5 6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v6a2.5 2.5 0 0 1-2.5 2.5H11l-4 3.5V15A2.5 2.5 0 0 1 5 12.5zM9 9.5h6',
  pulse: 'M3 12h4l2.5-6 4 12 2.5-6H21',
  sparkle: 'M12 3.5l1.9 5.1 5.1 1.9-5.1 1.9L12 17.5l-1.9-5.1L5 10.5l5.1-1.9zM18.5 16v4M16.5 18h4',
  streamer: 'M7 8v8M10.5 5v14M14 9v6M17.5 7v10',
  server: 'M6 4.5h12a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2a2 2 0 0 1 2-2zM6 13.5h12a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2a2 2 0 0 1 2-2zM8 7.5h.01M8 16.5h.01',
  user: 'M12 5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7zM5 19.5c1.2-3.2 3.9-5 7-5s5.8 1.8 7 5',
  power: 'M12 4v7.5M7.3 7.2a7 7 0 1 0 9.4 0',
  back: 'M10 6l-6 6 6 6M4 12h16',
  resize: 'M14 4h6v6M10 20H4v-6M20 4l-6.5 6.5M4 20l6.5-6.5',
  disc: 'M12 3.5a8.5 8.5 0 1 1 0 17 8.5 8.5 0 0 1 0-17zM12 9.4a2.6 2.6 0 1 1 0 5.2 2.6 2.6 0 0 1 0-5.2z',
  chart: 'M5 20V11M10 20V5M15 20v-7M20 20V8',
  wave: 'M3 12h2l2-5 3 10 3-12 3 12 2-5h3',
  timer: 'M19.5 14.5A8 8 0 1 1 9.5 4.4a6.3 6.3 0 0 0 10 10.1zM16 4v3M14.5 5.5h3',
  radio: 'M12 10a2 2 0 1 1 0 4 2 2 0 0 1 0-4zM8.2 15.8a5.4 5.4 0 0 1 0-7.6M15.8 8.2a5.4 5.4 0 0 1 0 7.6M5.3 18.7a9.5 9.5 0 0 1 0-13.4M18.7 5.3a9.5 9.5 0 0 1 0 13.4',
  shuffle: 'M3 7h3.5c2 0 3.2 1 4.3 2.6l2.4 3.8c1.1 1.6 2.3 2.6 4.3 2.6H21M3 17h3.5c1.4 0 2.4-.5 3.2-1.3M13.3 8.3c.8-.8 1.8-1.3 3.2-1.3H21M18 4l3 3-3 3M18 14l3 3-3 3',
  keyboard: 'M4.5 6h15a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-15a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2zM6 10h.01M10 10h.01M14 10h.01M18 10h.01M7.5 14h9',
  discord: 'M8.5 6.3A13 13 0 0 0 5 7.5C3 10.6 2.5 13.6 2.8 16.6A13 13 0 0 0 7 18.7l1-1.7M15.5 6.3A13 13 0 0 1 19 7.5c2 3.1 2.5 6.1 2.2 9.1a13 13 0 0 1-4.2 2.1l-1-1.7M7.5 16.3c2.9 1.3 6.1 1.3 9 0M9 12.5h.01M15 12.5h.01',
  x: 'M7 7l10 10M17 7L7 17',
};
const OPT = { menu: 'main', sel: 0, last: {}, pop: '', wheelAt: 0 };
const TITLES = { main: 'Opciones', apariencia: 'Apariencia', size: 'Tamaño', musica: 'Música', sleep: 'Temporizador', conexiones: 'Teclado y Discord' };
const PARENT = { apariencia: 'main', size: 'apariencia', musica: 'main', sleep: 'musica', conexiones: 'main' };
const R = 300, CX = 286 + R, CY = 205, STEP = Math.asin(50 / R);
function onoff(b) { return b ? 'Encendido' : 'Apagado'; }
function sleepHint(short) {
  const sl = S.st.sleep || {};
  if (sl.eot) return short ? 'Al terminar' : 'Al terminar esta canción';
  if (sl.at) return 'Se apaga en ' + Math.max(1, Math.ceil((sl.at - Date.now() / 1000) / 60)) + ' min';
  return short ? '' : 'Apagado';
}
function optItems() {
  const m = OPT.menu, v = S.visual || {};
  const back = { key: 'back', label: 'Volver', icon: 'back' };
  if (m === 'apariencia') return [back, { key: 'menu:size', label: 'Tamaño de Cumito', icon: 'resize', hint: Math.round((S.scale || 1) * 100) + '%' }];
  if (m === 'size') return [back].concat([1, 0.9, 0.8, 0.7].map((x) => ({ key: 'scale:' + x, label: Math.round(x * 100) + '%', icon: 'resize', hint: Math.abs(x - (S.scale || 1)) < 0.01 ? 'Actual' : '' })));
  if (m === 'musica') {
    const it = [back];
    if (feat('sleep')) it.push({ key: 'menu:sleep', label: 'Temporizador', icon: 'timer', hint: sleepHint() });
    if (feat('radio')) it.push({ key: 'radio', label: 'Radio al acabarse la lista', icon: 'radio', hint: onoff(S.st.radio) });
    if (feat('normalize')) it.push({ key: 'normalize', label: 'Volumen parejo', icon: 'wave', hint: onoff(S.st.normalize) });
    if (feat('shuffle')) it.push({ key: 'shuffle', label: 'Mezclar la lista', icon: 'shuffle' });
    return it;
  }
  if (m === 'sleep') {
    const sl = S.st.sleep || {};
    return [back].concat([[15, 'En 15 minutos'], [30, 'En 30 minutos'], [45, 'En 45 minutos'], [60, 'En 1 hora'], [90, 'En 1 hora y media']].map((x) => ({ key: 'sleep:' + x[0], label: x[1], icon: 'timer' })))
      .concat([{ key: 'sleep:eot', label: 'Al terminar esta canción', icon: 'timer', hint: sl.eot ? 'Puesto' : '' },
        { key: 'sleep:0', label: 'Quitar temporizador', icon: 'x', hint: (sl.at || sl.eot) ? '' : 'No hay' }]);
  }
  if (m === 'conexiones') return [back,
    { key: 'media_keys', label: 'Teclas multimedia', icon: 'keyboard', hint: onoff(v.media_keys !== false) },
    { key: 'presence', label: 'Mostrar en Discord', icon: 'discord', hint: onoff(v.presence !== false) }];
  const it = [];
  if (feat('albums')) it.push({ key: 'albums', label: 'Discos', icon: 'disc' });
  if (feat('stats')) it.push({ key: 'wrapped', label: 'Tu Wrapped', icon: 'chart' });
  if (feat('sleep') || feat('radio') || feat('normalize')) it.push({ key: 'menu:musica', label: 'Música', icon: 'wave', hint: sleepHint(true) });
  it.push({ key: 'activity', label: 'Actividad', icon: 'chat' },
    { key: 'status', label: 'Estado del servidor', icon: 'pulse' },
    { key: 'menu:apariencia', label: 'Apariencia', icon: 'sparkle' },
    { key: 'streamer', label: 'Modo streamer', icon: 'streamer', hint: 'Más liviano, para OBS' },
    { key: 'menu:conexiones', label: 'Teclado y Discord', icon: 'keyboard' },
    { key: 'server', label: 'Cambiar servidor', icon: 'server' },
    { key: 'name', label: 'Cambiar mi nombre', icon: 'user' },
    { key: 'power', label: 'Apagar Cumito', icon: 'power', danger: true });
  return it;
}
const ICON_CACHE = {};
function iconUrl(name, color) {
  const k = name + color;
  if (!ICON_CACHE[k]) {
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="' + color + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="' + IC[name] + '"/></svg>';
    ICON_CACHE[k] = "url('data:image/svg+xml;base64," + btoa(svg) + "')";
  }
  return ICON_CACHE[k];
}
let AC = null;
function tick() {
  try {
    if (!AC) AC = new (window.AudioContext || window.webkitAudioContext)();
    const t = AC.currentTime, o = AC.createOscillator(), g = AC.createGain();
    o.type = 'triangle'; o.frequency.setValueAtTime(2900, t);
    g.gain.setValueAtTime(0.06, t); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.03);
    o.connect(g); g.connect(AC.destination); o.start(t); o.stop(t + 0.035);
  } catch (e) {}
}
function openOptions() {
  OPT.menu = 'main';
  const items = optItems();
  const lastKey = OPT.last.main;
  OPT.sel = Math.max(0, items.findIndex((x) => x.key === lastKey));
  openPanel('options');
  renderOptions(true);
}
function renderOptions(newTitle) {
  const list = optItems();
  OPT.sel = Math.max(0, Math.min(list.length - 1, OPT.sel));
  if (newTitle) $('optTitle').innerHTML = '<div class="ttl"><div class="big">' + esc(TITLES[OPT.menu] || 'Opciones') + '</div><div class="sm">Gira la rueda del mouse\ny toca la que quieras</div></div>';
  const box = $('witems');
  const html = list.map((it, i) => {
    const d = i - OPT.sel;
    const th = d * STEP;
    const ax = CX - R * Math.cos(th);
    const ay = CY + R * Math.sin(th);
    const near = Math.max(0, 1 - Math.abs(d));
    const bx = 32 + 10 * near;
    const gap = 40 + 14 * near;
    const right = ax - gap + bx / 2;
    const o = Math.abs(d) > 4.2 ? 0 : Math.max(0.12, 1 - 0.2 * Math.abs(d));
    const stroke = i === OPT.sel ? '#18171C' : (it.danger ? '#FF8C8C' : '#F2F0F7');
    return '<button class="it ' + (i === OPT.sel ? 'sel ' : '') + (it.danger ? 'danger' : '') + '" type="button" data-wi="' + i + '" style="transform:translate(' + (right - 290).toFixed(1) + 'px,' + (ay - 22).toFixed(1) + 'px);opacity:' + o.toFixed(2) + (o === 0 ? ';pointer-events:none' : '') + '">' +
      '<span class="lb">' + esc(it.label) + '<span class="hn ' + (OPT.pop === it.key ? 'pop' : '') + '">' + esc(it.hint || '') + '</span></span>' +
      '<span class="bx"><i class="wi" style="background-image:' + iconUrl(it.icon, stroke) + '"></i></span></button>';
  });
  // se reutilizan los botones para que se deslicen (no se rehacen)
  if (box.children.length === list.length && !newTitle) {
    const tmp = document.createElement('div');
    tmp.innerHTML = html.join('');
    Array.from(tmp.children).forEach((n, i) => {
      const old = box.children[i];
      old.className = n.className; old.setAttribute('style', n.getAttribute('style')); old.innerHTML = n.innerHTML;
    });
  } else box.innerHTML = html.join('');
  OPT.pop = '';
}
function optGo(i) {
  const n = optItems().length;
  i = Math.max(0, Math.min(n - 1, i));
  if (i !== OPT.sel) { tick(); OPT.sel = i; renderOptions(false); }
}
function optOpen(menu, selKey) {
  tick();
  OPT.menu = menu;
  const list = optItems();
  let i = selKey ? list.findIndex((x) => x.key === selKey) : -1;
  if (i < 0) i = list.length > 1 && list[0].key === 'back' ? 1 : 0;
  OPT.sel = i;
  renderOptions(true);
}
function optBack() {
  if (OPT.menu === 'main') { closePanel(); return; }
  const from = OPT.menu;
  optOpen(PARENT[from] || 'main', 'menu:' + from);
}
function optAct(it) {
  const k = it.key;
  if (OPT.menu === 'main') OPT.last.main = k;
  if (k === 'back') return optBack();
  if (k.startsWith('menu:')) return optOpen(k.slice(5));
  if (k.startsWith('scale:')) { const v = parseFloat(k.slice(6)); if (Math.abs(v - (S.scale || 1)) < 0.01) return optBack(); toast('Cumito se reinicia con el tamaño nuevo…'); setTimeout(() => winCmd('scale:' + v), 600); return; }
  if (k.startsWith('sleep:')) {
    const v = k.slice(6);
    if (v === 'eot') { send('sleep', { end_of_track: true }); toast('Cumito se apaga al terminar esta canción 🌙'); }
    else if (v === '0') { send('sleep', { minutes: 0 }); toast('Temporizador quitado'); }
    else { send('sleep', { minutes: +v }); toast('Cumito se apaga en ' + v + ' minutos 🌙'); }
    closePanel(); return;
  }
  if (k === 'radio' || k === 'normalize') {
    const now = !S.st[k]; S.st[k] = now;
    send(k === 'radio' ? 'set_radio' : 'set_normalize', { on: now });
    OPT.pop = k; renderOptions(false); return;
  }
  if (k === 'media_keys' || k === 'presence') {
    S.visual[k] = S.visual[k] === false; save('visual', S.visual);
    OPT.pop = k; renderOptions(false); return;
  }
  if (k === 'shuffle') { closePanel(); shuffle(); return; }
  if (k === 'albums') return openAlbums();
  if (k === 'wrapped') return openWrapped();
  if (k === 'activity') return openActivity();
  if (k === 'status') return openPanel('status');
  if (k === 'streamer') { toast('Pasando al modo streamer…'); setTimeout(() => winCmd('streamer'), 500); return; }
  if (k === 'server') return prompt2('Dirección del servidor', 'Déjalo vacío para volver al de siempre.', S.server || '', 'host_address');
  if (k === 'name') return prompt2('¿Cómo quieres que te vean?', 'Así te ven los demás en Cumito.', S.me || '', 'display_name');
  if (k === 'power') { closePanel(); askConfirm('¿Apagar a Cumito?', 'Se detiene la música, se borra la lista y Cumito sale del canal de voz.', 'Mantén presionado para apagar', 'power', () => send('stop_and_leave')); }
}
$('wheel').addEventListener('wheel', (e) => {
  e.preventDefault();
  const now = Date.now();
  if (now - OPT.wheelAt < 90) return;
  OPT.wheelAt = now;
  optGo(OPT.sel + (e.deltaY > 0 ? 1 : -1));
}, { passive: false });
$('witems').addEventListener('click', (e) => {
  const b = e.target.closest('[data-wi]');
  if (!b) return;
  const i = +b.dataset.wi;
  if (i === OPT.sel) optAct(optItems()[i]); else optGo(i);
});

/* ---------- escribir algo (nombre / servidor) ---------- */
function prompt2(title, sub, value, key) {
  closePanel();
  $('card2').dataset.kind = 'prompt';
  $('card2').style.top = '150px';
  $('card2').innerHTML = '<div style="font-size:17px;font-weight:800">' + esc(title) + '</div><div class="tip" style="margin-top:4px">' + esc(sub) + '</div>' +
    '<input class="inp" id="p2in" style="margin-top:14px" value="' + esc(value) + '" maxlength="60">' +
    '<div style="display:flex;gap:9px;margin-top:14px"><button class="btn secb" type="button" data-act="card2Close">Cancelar</button><button class="btn prim" type="button" data-act="p2save" data-key="' + key + '">Guardar</button></div>';
  $('veil').classList.add('on'); $('card2').classList.add('on');
  setTimeout(() => { $('p2in').focus(); $('p2in').select(); }, 200);
}
function closeCard2() { $('card2').classList.remove('on'); $('card2').dataset.kind = ''; hideVeil(); }
function p2save(key) {
  const v = $('p2in').value.trim();
  if (key === 'display_name' && !v) return;
  save(key, v);
  if (key === 'display_name') { S.me = v; renderHome(); toast('Listo, ahora te ven como ' + v); }
  else toast('Conectando al servidor…');
  closeCard2();
}

/* ---------- actividad (chat) ---------- */
function openActivity() { openPanel('activity'); send('activity_list'); renderFeed(); }
function dayLabel(ts) {
  const d = new Date(ts * 1000), n = new Date();
  const k = (x) => x.getFullYear() + '-' + x.getMonth() + '-' + x.getDate();
  if (k(d) === k(n)) return 'HOY';
  const y = new Date(n.getTime() - 86400000);
  if (k(d) === k(y)) return 'AYER';
  return d.toLocaleDateString('es', { day: 'numeric', month: 'long' }).toUpperCase();
}
function hm(ts) { return new Date(ts * 1000).toLocaleTimeString('es', { hour: 'numeric', minute: '2-digit' }); }
function renderFeed() {
  if (P.open !== 'activity') return;
  const list = S.acts;
  let h = '', lastDay = null, prevWho = null, prevTs = 0;
  if (!list.length) h = '<div class="tip" style="text-align:center;margin-top:60px">Todavía no hay actividad.</div>';
  list.forEach((m, i) => {
    const day = dayLabel(m.ts || 0);
    if (day !== lastDay) { h += '<span class="day">' + day + '</span>'; lastDay = day; prevWho = null; }
    const grouped = prevWho === m.who && (m.ts - prevTs) < 600;
    const bot = m.who === 'Cumito';
    h += '<div class="msg" style="margin-top:' + (grouped ? '0' : '8px') + ';animation-delay:' + (i > list.length - 8 ? (0.1 + (i - list.length + 8) * 0.06) : 0) + 's">' +
      '<span class="av" style="background:' + pcolor(m.who) + ';opacity:' + (grouped ? 0 : 1) + '">' + initial(m.who) + '</span><div style="flex:1;min-width:0">' +
      (grouped ? '' : '<div style="display:flex;align-items:baseline;gap:6px;margin-bottom:3px"><span class="who" style="color:' + pcolor(m.who) + ';filter:brightness(1.45)">' + esc(m.who) + '</span><span class="tm">' + hm(m.ts || 0) + '</span></div>') +
      '<div class="bub' + (bot ? ' bot' : '') + '"><span class="tx">' + esc(cap(m.text)) + '</span>' +
      (m.title ? '<span class="song"><span class="c" style="' + coverStyle(m.art, m.title) + '"></span><span style="min-width:0"><span class="ell" style="display:block;font-size:11.5px;font-weight:800">' + esc(m.title) + '</span><span class="ell" style="display:block;font-size:10.5px;font-weight:600;color:rgba(244,242,250,.55)">' + esc(m.sub || '') + '</span></span></span>' : '') +
      '</div></div></div>';
    prevWho = m.who; prevTs = m.ts;
  });
  const body = $('feed');
  body.innerHTML = h;
  const sc = body.parentElement;
  requestAnimationFrame(() => (sc.scrollTop = sc.scrollHeight));
}
function cap(s) { s = String(s || ''); return s.charAt(0).toUpperCase() + s.slice(1); }

/* ---------- estado del servidor ---------- */
let stT = null, stLast = 0, stOpened = 0;
function statusStart() { stOpened = Date.now(); send('status'); clearInterval(stT); stT = setInterval(() => { send('status'); if (Date.now() - (stLast || stOpened) > 6500) { $('slive').innerHTML = '<span style="width:6px;height:6px;border-radius:3px;background:#F2B23A"></span>Sin respuesta'; $('slive').style.color = '#F2B23A'; } }, 2000); if (!stLast) $('status').innerHTML = '<div class="tip" style="text-align:center;margin-top:60px">Preguntándole a la VM…</div>'; }
function statusStop() { clearInterval(stT); }
function bytes(n) { n = n || 0; if (n >= 1e9) return (n / 1e9).toFixed(1) + ' GB'; return Math.round(n / 1e6) + ' MB'; }
function dur(s) { s = Math.floor(s || 0); const d = Math.floor(s / 86400), h = Math.floor(s / 3600) % 24, m = Math.floor(s / 60) % 60; return d ? d + ' d ' + h + ' h' : (h ? h + ' h ' + m + ' min' : m + ' min'); }
function lvlc(p) { return p < 60 ? '#3DDC84' : (p < 85 ? '#F2B23A' : '#FF5A5F'); }
function spath(vals, h, close) {
  const n = 90, w = 306;
  vals = (vals || []).slice(-n);
  if (!vals.length) return '';
  let d = '';
  vals.forEach((v, i) => { d += (i ? 'L' : 'M') + (w * (i + n - vals.length) / (n - 1)).toFixed(1) + ' ' + (h - h * Math.min(100, v) / 100 + 0.5).toFixed(1); });
  if (close) d += 'L306 78L' + (w * (n - vals.length) / (n - 1)).toFixed(1) + ' 78Z';
  return d;
}
function renderStatus(d) {
  stLast = Date.now();
  $('slive').innerHTML = '<span class="dot" style="width:6px;height:6px;border-radius:3px;background:#3DDC84"></span>En vivo · cada 2 s';
  $('slive').style.color = '#3DDC84';
  if (P.open !== 'status') return;
  const C = 194.8;
  const cpu = Math.round(d.cpu || 0);
  const mem = d.mem || {}, disk = d.disk || {}, dc = d.discord || {}, q = d.queue || {}, hl = d.helpers || {}, v = d.versions || {};
  const memp = mem.total ? Math.round(100 * mem.used / mem.total) : 0;
  const diskp = disk.total ? Math.round(100 * disk.used / disk.total) : 0;
  const hist = d.cpu_hist || [], st = d.steal_hist || [];
  const avg = hist.slice(-15).reduce((a, b) => a + b, 0) / Math.max(1, hist.slice(-15).length);
  const steal = Math.round(d.steal || 0);
  const problems = [], warns = [];
  if (!dc.ready) problems.push('Cumito no está conectado a Discord.');
  if (memp > 92) problems.push('La memoria está casi llena.');
  if (avg > 90) warns.push('El procesador está al máximo.');
  if (st.slice(-15).reduce((a, b) => a + b, 0) / 15 > 25) warns.push('Oracle está limitando la VM (es gratis y tiene un tope).');
  if (q.failed) warns.push('Algunas canciones no se pudieron preparar.');
  const now = d.time || Date.now() / 1000;
  if ((d.logs || []).some((x) => x.lvl === 'ERROR' && now - (x.t || 0) < 300)) warns.push('Hubo errores en los últimos 5 minutos (mira el registro).');
  const bad = problems.length, warn = !bad && warns.length;
  const bt = bad ? 'Con problemas' : (warn ? 'Un poco cargado' : 'Todo bien');
  const bs = (problems.concat(warns)).join(' ') || 'La VM responde normal.';
  const bc = bad ? ['rgba(255,90,95,.12)', 'rgba(255,90,95,.45)', '#FF5A5F'] : (warn ? ['rgba(242,178,58,.12)', 'rgba(242,178,58,.45)', '#F2B23A'] : ['rgba(61,220,132,.11)', 'rgba(61,220,132,.42)', '#3DDC84']);
  const rings = [{ name: 'Procesador', pct: cpu, sub: (d.cores || 1) + (d.cores === 1 ? ' núcleo' : ' núcleos') },
    { name: 'Memoria', pct: memp, sub: bytes(mem.used) + ' de ' + bytes(mem.total) },
    { name: 'Disco', pct: diskp, sub: bytes(disk.used) + ' de ' + bytes(disk.total) }];
  const tiles = [
    { k: 'DISCORD', v: dc.ready ? 'Conectado' : 'Desconectado', s: dc.ready ? (dc.ping != null ? 'ping ' + dc.ping + ' ms' : '') : 'reconectando…', c: dc.ready ? '#3DDC84' : '#FF5A5F' },
    { k: 'CANAL DE VOZ', v: dc.voice || 'Fuera del canal', s: d.playing || 'nada sonando' },
    { k: 'APPS CONECTADAS', v: String(d.listeners || 0), s: (d.listeners === 1 ? 'persona' : 'personas') },
    { k: 'LISTA', v: plural(q.total, 'canción', 'canciones'), s: (q.prepared || 0) + ' listas' + (q.loading ? ' · ' + q.loading + ' preparando' : '') + (q.failed ? ' · ' + q.failed + ' con error' : ''), c: q.failed ? '#F2B23A' : '#fff' },
    { k: 'CUMITO ENCENDIDO', v: dur(d.uptime_bot), s: 'VM: ' + dur(d.uptime_vm) },
    { k: 'MEMORIA DE CUMITO', v: bytes((d.bot_rss || 0) + (hl.rss || 0)), s: (hl.n || 0) + ' ayudante(s)' },
    { k: 'VERSIÓN DEL SERVIDOR', v: v.server || '?', s: d.update_pending ? 'actualización esperando' : 'al día' },
    { k: 'YT-DLP', v: v.yt_dlp || '?', s: '' },
  ];
  if (d.lanes) {
    const L = d.lanes;
    tiles.push({ k: 'AYUDANTE URGENTE', v: L.urgent.busy ? 'Trabajando' : 'Libre', s: L.urgent.done + ' hechos' + (L.urgent.ms != null ? ' · ' + (L.urgent.ms / 1000).toFixed(1) + ' s' : '') });
    tiles.push({ k: 'AYUDANTE DE FONDO', v: L.background.busy ? 'Trabajando' : 'Libre', s: L.background.done + ' hechos' + (L.background.ms != null ? ' · ' + (L.background.ms / 1000).toFixed(1) + ' s' : '') });
  }
  const first = !$('status').dataset.ok;
  const anim = (cl, delay) => first ? ' class="' + cl + ' in" style="animation-delay:' + delay + 's;' : ' class="' + cl + '" style="';
  let h = '<div' + anim('es-banner', .2) + 'background:' + bc[0] + ';border:1px solid ' + bc[1] + '"><span style="width:11px;height:11px;border-radius:6px;margin-top:3px;flex:none;background:' + bc[2] + '"></span><div><div style="font-size:14px;font-weight:800">' + bt + '</div><div style="font-size:10.5px;font-weight:600;color:rgba(244,242,250,.65)">' + esc(bs) + '</div></div></div>';
  h += '<div' + anim('', .28) + 'display:flex;justify-content:space-between;padding:0 2px">' + rings.map((r) => '<div style="width:98px;display:flex;flex-direction:column;align-items:center"><div style="position:relative;width:74px;height:74px"><svg width="74" height="74" viewBox="0 0 74 74" style="transform:rotate(-90deg)"><circle cx="37" cy="37" r="31" fill="none" stroke="rgba(255,255,255,.1)" stroke-width="7"/><circle class="arc" data-ring="' + r.name + '" cx="37" cy="37" r="31" fill="none" stroke="' + lvlc(r.pct) + '" stroke-width="7" stroke-linecap="round" stroke-dasharray="194.8" stroke-dashoffset="' + (first ? C : (C - C * r.pct / 100)).toFixed(1) + '"/></svg><span style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:800">' + r.pct + '%</span></div><span style="font-size:10.5px;font-weight:800;margin-top:6px">' + r.name + '</span><span style="font-size:9.5px;font-weight:600;color:rgba(244,242,250,.5)">' + esc(r.sub) + '</span></div>').join('') + '</div>';
  h += '<div' + anim('', .36) + 'border-radius:14px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);padding:10px 12px"><div style="display:flex;justify-content:space-between;font-size:9.5px;font-weight:800;letter-spacing:.8px;color:rgba(244,242,250,.6)"><span>PROCESADOR · ÚLTIMOS 3 MIN</span><span style="color:#FF8A8F">' + (steal >= 5 ? 'Oracle limitando ' + steal + '%' : '') + '</span></div>' +
    '<svg width="306" height="78" viewBox="0 0 306 78" style="display:block;margin-top:8px"><defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8E6CF2" stop-opacity=".5"/><stop offset="1" stop-color="#8E6CF2" stop-opacity="0"/></linearGradient></defs><path d="M0 0.5H306M0 39H306M0 77.5H306" stroke="rgba(255,255,255,.07)" stroke-dasharray="3 4"/><path d="' + spath(hist, 77, true) + '" fill="url(#ag)"/><path d="' + spath(hist, 77, false) + '" fill="none" stroke="#C9B4F8" stroke-width="1.8" stroke-linejoin="round"/><path d="' + spath(st, 77, false) + '" fill="none" stroke="rgba(255,90,95,.8)" stroke-width="1.2" stroke-dasharray="3 3"/></svg></div>';
  h += '<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px">' + tiles.map((t, i) => '<div' + anim('tileS', (0.44 + i * 0.04).toFixed(2)) + '"><div class="k">' + t.k + '</div><div class="v ell" style="color:' + (t.c || '#fff') + '">' + esc(t.v) + '</div><div class="s ell">' + esc(t.s) + '</div></div>').join('') + '</div>';
  h += '<div' + anim('', .7) + 'font-size:9.5px;font-weight:800;letter-spacing:1px;color:rgba(244,242,250,.55);margin-top:4px">REGISTRO</div>';
  const logs = (d.logs || []).slice(-12).reverse();
  h += logs.map((l, i) => {
    const c = l.lvl === 'ERROR' ? '#FF5A5F' : (l.lvl === 'WARNING' ? '#F2B23A' : '#9A97A6');
    const lv = l.lvl === 'WARNING' ? 'AVISO' : (l.lvl === 'ERROR' ? 'ERROR' : 'INFO');
    return '<div' + anim('', (0.76 + i * 0.05).toFixed(2)) + 'display:flex;gap:7px;align-items:flex-start"><span style="font-family:Consolas,ui-monospace,monospace;font-size:10px;color:rgba(255,255,255,.45);flex:none">' + new Date((l.t || 0) * 1000).toLocaleTimeString('es', { hour12: false }) + '</span><span style="border:1px solid ' + c + ';color:' + c + ';border-radius:6px;font-size:8.5px;font-weight:800;padding:0 4px;flex:none">' + lv + '</span><span style="flex:1;font-size:10.5px;color:rgba(255,255,255,.82);word-break:break-word">' + esc(l.msg) + '</span></div>';
  }).join('');
  $('status').innerHTML = h;
  $('status').dataset.ok = '1';
  if (first) requestAnimationFrame(() => requestAnimationFrame(() => rings.forEach((r) => { const el = document.querySelector('[data-ring="' + r.name + '"]'); if (el) el.setAttribute('stroke-dashoffset', (C - C * r.pct / 100).toFixed(1)); })));
}

/* ---------- karaoke ---------- */
const LY = { key: null, lines: [], plain: false, cur: -1, timer: null, retry: 0, manualUntil: 0 };
function parseLrc(text) {
  const out = [];
  String(text || '').split(/\r?\n/).forEach((raw) => {
    const st = [...raw.matchAll(/\[(\d+):(\d+(?:[.:]\d+)?)\]/g)];
    if (!st.length) return;
    const words = raw.replace(/\[(\d+):(\d+(?:[.:]\d+)?)\]/g, '').trim();
    st.forEach((m) => out.push([+m[1] * 60 + parseFloat(m[2].replace(':', '.')), words]));
  });
  return out.sort((a, b) => a[0] - b[0]);
}
function openLyrics() {
  const np = S.st.now_playing;
  if (!np) return;
  openPanel('lyrics');
  lyricsFollow(true);
}
function lyMsg(t) { $('lymsg').textContent = t; $('lymsg').classList.toggle('hide', !t); if (t) $('lyin').innerHTML = ''; }
function lyricsFollow(force) {
  const np = S.st.now_playing;
  if (!np) { lyMsg('Nada sonando'); return; }
  const key = np.webpage_url || np.title;
  if (key !== LY.key || force && !LY.lines.length && !LY.plain) {
    if (key !== LY.key) { LY.key = key; LY.lines = []; LY.plain = false; LY.cur = -1; LY.retry = 0; lyMsg('Buscando la letra…'); $('lycredit').classList.add('hide'); }
    $('lyT').textContent = np.title || 'Letra';
    $('lyA').textContent = np.uploader || '';
    send('lyrics');
  }
  lyricsTimer();
}
function onLyrics(d) {
  const np = S.st.now_playing || {};
  if (d.webpage_url && np.webpage_url && d.webpage_url !== np.webpage_url) return;
  if (d.pending && LY.retry < 6) { LY.retry++; lyMsg('Preparando la canción…'); setTimeout(() => { if (P.open === 'lyrics') send('lyrics'); }, 2500); return; }
  LY.lines = parseLrc(d.synced);
  LY.plain = !LY.lines.length;
  LY.cur = -1;
  if (d.instrumental) { lyMsg('♪  Instrumental  ♪'); return; }
  if (!LY.lines.length && !d.plain) { lyMsg('No encontré la letra de esta canción'); $('lycredit').classList.add('hide'); return; }
  lyMsg('');
  const lines = LY.lines.length ? LY.lines : String(d.plain).split(/\r?\n/).map((l) => [null, l]);
  $('lyr').classList.toggle('plain', LY.plain);
  $('lyin').innerHTML = lines.map((l, i) => '<p class="ln" data-li="' + i + '">' + (esc(l[1]) || '♪') + '</p>').join('');
  $('lyin').style.transform = 'translateY(' + ($('lyr').clientHeight * 0.36) + 'px)';
  $('lycredit').classList.remove('hide');
  $('lycredit').textContent = LY.plain ? 'Letras: LRCLIB · esta no trae tiempos' : 'Letras: LRCLIB · toca una línea para ir ahí';
  lyricsStep();
}
function lyricsTimer() {
  clearInterval(LY.timer);
  const np = S.st.now_playing;
  if (P.open === 'lyrics' && np && !np.paused && LY.lines.length) LY.timer = setInterval(lyricsStep, 100);
  lyricsStep();
}
function lyricsStop() { clearInterval(LY.timer); }
function lyricsStep() {
  if (!LY.lines.length) return;
  const t = curElapsed();
  let idx = -1;
  for (let i = 0; i < LY.lines.length; i++) { if (LY.lines[i][0] <= t + 0.15) idx = i; else break; }
  const box = $('lyin');
  const els = box.children;
  if (idx !== LY.cur) {
    LY.cur = idx;
    for (let i = 0; i < els.length; i++) { els[i].classList.toggle('cur', i === idx); els[i].classList.toggle('past', i < idx); if (i !== idx) els[i].style.removeProperty('--f'); }
    if (Date.now() > LY.manualUntil) lyScrollTo(idx);
  }
  if (idx >= 0 && els[idx]) {
    const t0 = LY.lines[idx][0], t1 = idx + 1 < LY.lines.length ? LY.lines[idx + 1][0] : t0 + 5;
    const f = Math.max(0, Math.min(1, (t - t0) / Math.min(Math.max(0.6, t1 - t0), 8)));
    els[idx].style.setProperty('--f', (f * 100).toFixed(1) + '%');
  }
}
function lyScrollTo(idx) {
  const box = $('lyin'), el = box.children[Math.max(0, idx)];
  if (!el) return;
  const anchor = $('lyr').clientHeight * 0.36;
  box.style.transform = 'translateY(' + (anchor - el.offsetTop - el.offsetHeight / 2) + 'px)';
}
$('lyr').addEventListener('wheel', (e) => {
  e.preventDefault();
  const box = $('lyin');
  const m = /translateY\((-?[\d.]+)px\)/.exec(box.style.transform || '');
  const y = (m ? parseFloat(m[1]) : 0) - e.deltaY * 0.6;
  box.style.transition = 'transform .25s var(--out)';
  box.style.transform = 'translateY(' + y + 'px)';
  setTimeout(() => (box.style.transition = ''), 260);
  LY.manualUntil = Date.now() + 4000;
  clearTimeout(LY.back);
  LY.back = setTimeout(() => lyScrollTo(LY.cur), 4100);
}, { passive: false });
$('lyin').addEventListener('click', (e) => {
  const p = e.target.closest('[data-li]');
  if (!p || LY.plain) return;
  const l = LY.lines[+p.dataset.li];
  if (l) { LY.manualUntil = 0; seekTo(l[0]); }
});

/* ---------- Discos ---------- */
const AL = { view: 'grid', cur: null, edit: null, addAfter: false, saving: false };
const COLORS = ['#8E6CF2', '#E0457B', '#F2A33A', '#3DBE7A', '#4FB4D8', '#1F5FBF', '#D1517A', '#2B2838'];
function sleeveHtml(a, size, coverOverride) {
  const cov = coverOverride !== undefined ? coverOverride : (a.cover ? (S.covers[a.cover] || (askCover(a.cover), null)) : null);
  const arts = (a.arts || []).filter(Boolean);
  let inside = '';
  if (cov) inside = '';
  else if (arts.length >= 4) inside = '<div class="mz">' + arts.slice(0, 4).map((u) => '<i style="background-image:' + bgUrl(u) + '"></i>').join('') + '</div>';
  else if (arts.length) inside = '<div class="mz" style="grid-template-columns:1fr"><i style="background-image:' + bgUrl(arts[0]) + '"></i></div>';
  else inside = '<span class="nm" style="font-size:' + Math.max(9, Math.round(size * 0.1)) + 'px">' + esc(a.name || '') + '</span>';
  const col = a.color || '#8E6CF2';
  const bg = cov ? 'background-image:url(' + cov + ')' : 'background:linear-gradient(135deg,' + col + ',' + shade(col, -0.45) + ')';
  return '<div class="sleeve" style="width:' + Math.round(size * 1.33) + 'px;height:' + size + 'px;--lab:' + esc(col) + '">' +
    '<div class="vin" style="left:' + Math.round(size * 0.37) + 'px;width:' + Math.round(size * 0.94) + 'px;height:' + Math.round(size * 0.94) + 'px"></div>' +
    '<div class="slv" style="width:' + size + 'px;height:' + size + 'px;' + bg + '">' + inside + '</div></div>';
}
function shade(hex, k) { const c = parseInt(String(hex).slice(1), 16); let r = (c >> 16) & 255, g = (c >> 8) & 255, b = c & 255; r = Math.round(r * (1 + k)); g = Math.round(g * (1 + k)); b = Math.round(b * (1 + k)); return 'rgb(' + [r, g, b].map((x) => Math.max(0, Math.min(255, x))).join(',') + ')'; }
function openAlbums(view) {
  openPanel('albums');
  if (view !== 'keep') { AL.view = 'grid'; AL.cur = null; }
  send('album_list');
  renderAlbums();
}
function renderAlbums(soft) {
  const body = $('albody');
  $('alEdit').classList.toggle('hide', AL.view !== 'page');
  if (AL.view === 'grid') {
    $('alT').textContent = 'Discos';
    $('alS').textContent = S.albums.length ? plural(S.albums.length, 'disco', 'discos') + ' del grupo' : 'Los álbumes del grupo';
    body.innerHTML = '<div class="agrid">' +
      '<button class="card atile' + (soft ? '' : ' in') + '" type="button" data-act="newAlbum"><div class="newtile" style="width:112px;height:112px">' + I.plus + 'Nuevo disco</div><div class="n">&nbsp;</div></button>' +
      S.albums.map((a, i) => '<button class="card atile' + (soft ? '' : ' in') + '" type="button" data-album="' + a.id + '" style="animation-delay:' + (0.06 * (i + 1)) + 's">' + sleeveHtml(a, 112) +
        '<div class="n ell">' + esc(a.name) + '</div><div class="s ell">' + plural(a.count, 'canción', 'canciones') + (a.owner ? ' · de ' + esc(a.owner) : '') + '</div></button>').join('') + '</div>';
    return;
  }
  if (AL.view === 'page') {
    const a = AL.cur;
    $('alT').textContent = a.name || 'Disco';
    $('alS').textContent = 'Disco del grupo';
    const n = a.count || 0;
    const bits = [];
    if (a.owner) bits.push('de ' + a.owner);
    bits.push(plural(n, 'canción', 'canciones'));
    if (a.duration) { const m = Math.floor(a.duration / 60); bits.push(m >= 60 ? Math.floor(m / 60) + ' h ' + (m % 60) + ' min' : m + ' min'); }
    const tracks = a.tracks || [];
    body.innerHTML = '<div class="big-sleeve in" style="width:' + Math.round(168 * 1.33) + 'px">' + sleeveHtml(a, 168) + '</div>' +
      '<div class="aname in" style="animation-delay:.06s">' + esc(a.name) + '</div><div class="asub in" style="animation-delay:.1s">' + esc(bits.join(' · ')) + '</div>' +
      '<div class="in" style="display:flex;gap:9px;margin-top:14px;animation-delay:.14s"><button class="btn prim" type="button" data-act="albumPlay"' + (n ? '' : ' disabled') + '>' + I.playw + 'Reproducir</button><button class="btn secb" type="button" data-act="albumShuffle"' + (n > 1 ? '' : ' disabled') + '>' + I.shuffle + 'Aleatorio</button></div>' +
      '<div style="margin-top:12px;display:flex;flex-direction:column;gap:2px">' +
      (a.tracks === undefined ? '<div class="tip" style="text-align:center;padding:20px">Cargando…</div>' : '') +
      tracks.map((t, i) => '<div class="qrow row in" data-atrack="' + i + '" style="animation-delay:' + (0.18 + Math.min(i, 10) * 0.05) + 's" title="Tócala para agregarla a la lista"><span class="qc" style="' + coverStyle(t.art_url, t.title) + '"></span><span style="flex:1;min-width:0"><span class="qt ell">' + esc(t.title) + '</span><span class="qa ell">' + esc(t.uploader || '') + '</span></span><span class="qd">' + (t.duration ? fmt(t.duration) : '') + '</span><button class="btn qx" type="button" title="Quitar del disco" data-aremove="' + t.id + '">' + I.x + '</button></div>').join('') +
      (a.tracks && !tracks.length ? '<div class="tip" style="text-align:center;padding:20px 10px">Todavía no tiene canciones.<br>Toca el corazón ♡ en lo que suena para guardarla aquí.</div>' : '') +
      '</div><div style="display:flex;justify-content:center;margin:16px 0 20px">' +
      '<button class="btn hold" type="button" data-hold="albumDelete" style="width:220px;height:40px"><svg width="220" height="40" viewBox="0 0 220 40"><rect class="ring" pathLength="563" x="1.3" y="1.3" width="217.4" height="37.4" rx="18.7" fill="none" stroke="#FF5A5F" stroke-width="2.6"/></svg><span>Borrar el disco</span></button></div>';
    return;
  }
  // editor
  const e = AL.edit;
  $('alT').textContent = e.id ? 'Editar disco' : 'Nuevo disco';
  $('alS').textContent = e.id ? (e.name || '') : 'Ponle nombre, color y portada';
  const fake = { name: e.name || 'Nuevo disco', color: e.color, arts: e.arts || [], cover: e.remove ? null : e.coverHash };
  const cov = e.cover ? 'data:image/jpeg;base64,' + e.cover : undefined;
  body.innerHTML = '<div style="display:flex;justify-content:center;margin-top:6px" id="edPrev">' + sleeveHtml(fake, 140, cov) + '</div>' +
    '<div style="display:flex;justify-content:center;gap:8px;margin-top:12px"><button class="btn secb" type="button" data-act="pickCover" style="flex:none;padding:0 14px;height:36px">' + I.img + 'Elegir portada</button>' +
    ((e.cover || (e.coverHash && !e.remove)) ? '<button class="btn secb" type="button" data-act="noCover" style="flex:none;padding:0 14px;height:36px">Quitar</button>' : '') + '</div>' +
    '<div class="lbl2">NOMBRE</div><input class="inp" id="edName" maxlength="40" placeholder="Ej. Para el carro, Viernes, Los clásicos…" value="' + esc(e.name || '') + '">' +
    '<div class="lbl2">COLOR</div><div class="swatches">' + COLORS.map((c) => '<button class="btn swatch' + (c === e.color ? ' on' : '') + '" type="button" data-color="' + c + '" style="background:' + c + '"></button>').join('') + '</div>' +
    '<button class="btn prim" type="button" data-act="albumSave" style="width:100%;flex:none;margin:20px 0 20px;height:46px;border-radius:23px;font-size:14px"' + (AL.saving ? ' disabled' : '') + '>' + (e.id ? 'Guardar' : (AL.addAfter ? 'Crear y guardar la canción' : 'Crear disco')) + '</button>';
  const inp = $('edName');
  inp.addEventListener('input', () => { e.name = inp.value; $('edPrev').innerHTML = sleeveHtml({ name: e.name || 'Nuevo disco', color: e.color, arts: e.arts || [], cover: e.remove ? null : e.coverHash }, 140, e.cover ? 'data:image/jpeg;base64,' + e.cover : undefined); });
  inp.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') albumSave(); });
}
function openAlbum(id) {
  const a = S.albums.find((x) => x.id === id);
  if (!a) return;
  if (P.open !== 'albums') openAlbums('keep');
  AL.view = 'page'; AL.cur = Object.assign({}, a, { tracks: undefined });
  renderAlbums();
  send('album_get', { id: id });
}
function onAlbum(a) {
  AL.saving = false;
  if (!a) { if (AL.view === 'page') { AL.view = 'grid'; renderAlbums(); } return; }
  if (AL.view === 'edit' && AL.addAfter && !AL.edit.id) { AL.addAfter = false; send('album_add', { id: a.id, current: true }); }
  if (AL.view === 'edit' || (AL.view === 'page' && AL.cur && AL.cur.id === a.id)) {
    AL.view = 'page'; AL.cur = a;
    if (P.open === 'albums') renderAlbums();
  }
}
function albumsBack() {
  if (AL.view === 'edit') { if (AL.edit.id && AL.cur) { AL.view = 'page'; } else AL.view = 'grid'; renderAlbums(); return; }
  if (AL.view === 'page') { AL.view = 'grid'; AL.cur = null; renderAlbums(); return; }
  closePanel();
}
function openEditor(album, addAfter) {
  if (P.open !== 'albums') openAlbums('keep');
  AL.view = 'edit'; AL.addAfter = !!addAfter; AL.saving = false;
  AL.edit = album ? { id: album.id, name: album.name, color: album.color || COLORS[0], coverHash: album.cover, arts: album.arts, cover: null, remove: false }
    : { id: null, name: '', color: COLORS[S.albums.length % COLORS.length], cover: null, remove: false };
  renderAlbums();
  setTimeout(() => { const i = $('edName'); if (i) i.focus(); }, 300);
}
function albumSave() {
  const e = AL.edit;
  const name = ($('edName').value || '').trim();
  if (!name) { $('edName').focus(); toast('Ponle un nombre al disco'); return; }
  AL.saving = true;
  if (e.id) {
    const kw = { id: e.id, name: name, color: e.color };
    if (e.cover) kw.cover_b64 = e.cover; else if (e.remove) kw.remove_cover = true;
    send('album_update', kw);
  } else {
    const kw = { name: name, color: e.color };
    if (e.cover) kw.cover_b64 = e.cover;
    send('album_create', kw);
  }
  e.name = name;
  setTimeout(() => { AL.saving = false; }, 5000);
  const b = document.querySelector('[data-act="albumSave"]'); if (b) b.disabled = true;
}
function albumDelete() {
  if (!AL.cur) return;
  send('album_delete', { id: AL.cur.id });
  toast('Borraste «' + AL.cur.name + '»');
  AL.view = 'grid'; AL.cur = null;
  renderAlbums();
}
function onAlbumAdded(d) {
  const a = S.albums.find((x) => x.id === d.id);
  const name = (a && a.name) || 'el disco';
  if (d.added) {
    toast('Guardada en «' + name + '» 💜');
    cls('is-liked', false); void W.offsetWidth; cls('is-liked', true);
    setTimeout(() => cls('is-liked', false), 1800);
  } else toast('Ya estaba en «' + name + '»');
}
/* el corazón: elegir en qué disco guardar */
function openPicker(refresh) {
  const np = S.st.now_playing;
  if (!np) return;
  if (!refresh) send('album_list');
  hideReactions();
  const c = $('card2');
  c.dataset.kind = 'picker';
  c.style.top = '110px';
  c.innerHTML = '<div style="font-size:16px;font-weight:800">Guardar en un disco</div><div class="tip ell" style="margin-top:2px">' + esc(np.title) + '</div>' +
    '<div style="display:flex;flex-direction:column;gap:2px;margin-top:10px;max-height:300px;overflow-y:auto">' +
    (S.albums.length ? S.albums.map((a) => '<button class="row prow" type="button" data-pick="' + a.id + '">' + sleeveHtml(a, 38) + '<span style="flex:1;min-width:0;text-align:left"><span class="ell" style="display:block;font-size:12.5px;font-weight:800">' + esc(a.name) + '</span><span style="display:block;font-size:10.5px;font-weight:600;color:rgba(244,242,250,.5)">' + plural(a.count, 'canción', 'canciones') + '</span></span></button>').join('')
      : '<div class="tip" style="padding:10px 4px">Todavía no hay discos. ¡Crea el primero!</div>') +
    '</div><button class="btn secb" type="button" data-act="pickNew" style="width:100%;margin-top:12px;flex:none">' + I.plus.replace('width="24" height="24"', 'width="15" height="15"') + 'Nuevo disco</button>';
  $('veil').classList.add('on'); c.classList.add('on');
}

/* ---------- Wrapped ---------- */
const WR = { period: 'month', mine: false, data: null };
const PERIODS = [['week', 'Semana'], ['month', 'Mes'], ['year', 'Año'], ['all', 'Siempre']];
function openWrapped() { openPanel('wrapped'); loadWrapped(); }
function loadWrapped(p) {
  if (p) { const old = PERIODS.findIndex((x) => x[0] === WR.period), nw = PERIODS.findIndex((x) => x[0] === p); WR.dir = nw > old ? 'go-r' : 'go-l'; WR.period = p; }
  const kw = { period: WR.period };
  if (WR.mine && S.me) kw.who = S.me;
  send('stats', kw);
  renderWrapped(null);
}
function renderWrapped(d) {
  if (d) { if (d.period && d.period !== WR.period) return; WR.data = d; }
  if (P.open !== 'wrapped') return;
  d = WR.data && WR.data.period === WR.period ? WR.data : null;
  const idx = PERIODS.findIndex((x) => x[0] === WR.period);
  const left = 4 + idx * 56, right = (8 + PERIODS.length * 50 + (PERIODS.length - 1) * 6) - left - 50;
  let h = '<div style="display:flex;align-items:center;gap:8px;margin:2px 0 12px"><div class="ptabs ' + (WR.dir || 'go-r') + '" id="ptabs"><span class="ti" style="left:' + left + 'px;right:' + right + 'px"></span>' +
    PERIODS.map((p) => '<button class="btn tb' + (p[0] === WR.period ? ' on' : '') + '" type="button" data-period="' + p[0] + '">' + p[1] + '</button>').join('') + '</div><span style="flex:1"></span>' +
    '<span style="font-size:10px;font-weight:800;color:rgba(244,242,250,.65);white-space:nowrap">Solo yo</span><button class="btn sw ' + (WR.mine ? 'on' : 'off') + '" type="button" data-act="wrMine" aria-label="Solo yo"><span class="knob2" style="left:' + (WR.mine ? 20 : 3) + 'px;right:' + (WR.mine ? 3 : 20) + 'px"></span></button></div>';
  if (!d) { $('wbody').innerHTML = h + '<div class="sk" style="height:132px;border-radius:22px"></div><div class="sk" style="height:46px;margin-top:12px"></div><div class="sk" style="height:46px;margin-top:8px"></div>'; return; }
  const title = { week: 'Esta semana', month: 'Este mes', year: 'Este año', all: 'Desde siempre' }[WR.period] + (WR.mine ? ' · solo tú' : '');
  h += '<div class="hero in"><div class="k">' + title + '</div><div class="big">' + (d.minutes || 0).toLocaleString('es') + '</div><div class="u">minutos escuchados</div><div class="s">' + plural(d.plays, 'canción', 'canciones') + ' · ' + plural(d.days, 'día', 'días') + ' con música' + (d.skipped ? ' · ' + d.skipped + ' saltadas' : '') + '</div></div>';
  if (!d.plays) { $('wbody').innerHTML = h + '<div class="tip" style="text-align:center;margin-top:30px">Todavía no hay nada que contar en este tiempo.<br>¡Pongan música!</div>'; return; }
  h += '<div class="sec-t in" style="margin-top:18px;animation-delay:.1s">LO MÁS ESCUCHADO</div><div style="margin-top:6px">' +
    (d.top_songs || []).slice(0, 5).map((s, i) => '<div class="trow in" style="animation-delay:' + (0.14 + i * 0.06) + 's"><span class="r">' + (i + 1) + '</span><span class="c" style="' + coverStyle(s.art_url, s.title) + '"></span><span style="flex:1;min-width:0"><span class="ell" style="display:block;font-size:12.5px;font-weight:800">' + esc(s.title) + '</span><span class="ell" style="display:block;font-size:10.5px;font-weight:600;color:rgba(244,242,250,.55)">' + esc(s.uploader || '') + '</span></span><span style="font-size:10.5px;font-weight:800;color:#C9B4F8;flex:none">' + plural(s.plays, 'vez', 'veces') + '</span></div>').join('') + '</div>';
  const arts = (d.top_artists || []).slice(0, 6);
  if (arts.length) h += '<div class="sec-t in" style="margin-top:16px;animation-delay:.4s">ARTISTAS</div><div class="in" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;animation-delay:.44s">' + arts.map((a, i) => '<span class="chip" style="display:flex;align-items:center;' + (i === 0 ? 'background:rgba(142,108,242,.3);border-color:rgba(142,108,242,.6)' : '') + '"><b style="color:#C9B4F8">' + (i + 1) + '</b>' + esc(a.name) + '</span>').join('') + '</div>';
  const people = (d.top_people || []).slice(0, 6);
  if (people.length && !WR.mine) {
    const top = people[0].plays || 1;
    h += '<div class="sec-t in" style="margin-top:16px;animation-delay:.5s">QUIÉN PUSO MÁS</div><div style="margin-top:6px">' + people.map((p, i) => '<div class="pbar in" style="animation-delay:' + (0.54 + i * 0.05) + 's"><span class="av" style="background:' + pcolor(p.name) + '">' + initial(p.name) + '</span><span class="nm ell">' + esc(p.name) + '</span><span class="tr"><i style="width:' + Math.max(4, 100 * p.plays / top) + '%;background:' + pcolor(p.name) + ';animation-delay:' + (0.6 + i * 0.05) + 's"></i></span><span class="v">' + p.plays + '</span></div>').join('') + '</div>';
  }
  const hrs = d.hours || [];
  if (hrs.some((x) => x)) {
    const mx = Math.max.apply(null, hrs) || 1, best = hrs.indexOf(mx);
    const hn = best === 0 ? '12 a. m.' : (best < 12 ? best + ' a. m.' : (best === 12 ? '12 p. m.' : (best - 12) + ' p. m.'));
    h += '<div class="sec-t in" style="margin-top:16px;animation-delay:.7s">A QUÉ HORA SUENA CUMITO</div><div class="hours in" style="margin-top:10px;animation-delay:.72s">' + hrs.map((v, i) => '<i class="' + (i === best ? 'top' : '') + '" style="height:' + Math.max(4, 64 * v / mx) + 'px;animation-delay:' + (0.74 + i * 0.015) + 's;' + (v ? '' : 'opacity:.35') + '"></i>').join('') + '</div>' +
      '<div style="display:flex;justify-content:space-between;font-size:9px;font-weight:700;color:rgba(244,242,250,.4);margin-top:4px"><span>12 a. m.</span><span>6 a. m.</span><span>12 p. m.</span><span>6 p. m.</span><span>11 p. m.</span></div>' +
      '<div class="in" style="font-size:12px;font-weight:700;color:rgba(244,242,250,.75);margin-top:8px;animation-delay:.9s">La hora favorita: las ' + hn + '</div>';
  }
  $('wbody').innerHTML = h;
}

/* ---------- reacciones ---------- */
const EMOJIS = ['🔥', '💜', '😂', '🕺', '👏', '😭'];
$('rbar').innerHTML = EMOJIS.map((e) => '<button class="btn" type="button" data-emoji="' + e + '">' + e + '</button>').join('');
function toggleReactions() { $('rbar').classList.toggle('on'); }
function hideReactions() { $('rbar').classList.remove('on'); }
function floatReaction(emoji, who) {
  if (document.hidden) return;
  const el = document.createElement('div');
  el.className = 'floater';
  el.innerHTML = '<span class="e">' + esc(emoji || '💜') + '</span><span class="w">' + esc((who || '').slice(0, 14)) + '</span>';
  el.style.left = (60 + Math.random() * 200) + 'px';
  el.style.top = '330px';
  el.style.setProperty('--dx', (Math.random() * 70 - 35).toFixed(0) + 'px');
  W.appendChild(el);
  setTimeout(() => el.remove(), 2200);
}

/* ---------- mezclar / repetir ---------- */
function shuffle() {
  if ((S.st.queue || []).length < 2) { toast('Hacen falta al menos 2 canciones en la lista'); return; }
  send('shuffle'); toast('Lista mezclada 🔀');
}
function cycleRepeat() {
  const nx = { off: 'all', all: 'one', one: 'off' }[S.st.repeat || 'off'] || 'off';
  S.st.repeat = nx; renderFeatures();
  send('set_repeat', { mode: nx });
  toast({ off: 'Sin repetir', all: 'Repetir toda la lista', one: 'Repetir esta canción' }[nx], 1400);
}

/* ---------- aviso de actualización ---------- */
function renderBanner(d) {
  const b = $('banner');
  if (!d || d.state === 'hide') { b.classList.remove('on'); return; }
  let h = '<div style="flex:1;min-width:0">';
  if (d.state === 'available') h += '<div class="t">Hay una versión nueva de Cumito</div><div class="s">Versión ' + esc(d.version || '') + '</div></div><button class="btn go" type="button" data-act="update">Actualizar</button><button class="btn" type="button" data-act="bannerClose" style="width:28px;height:28px;border-radius:14px;background:rgba(255,255,255,.12)">' + I.x + '</button>';
  else if (d.state === 'progress') h += '<div class="t">Bajando la actualización…</div><div class="pr"><i style="width:' + Math.round((d.f || 0) * 100) + '%"></i></div></div>';
  else if (d.state === 'installing') h += '<div class="t">Instalando…</div><div class="s">Cumito se vuelve a abrir solo.</div></div>';
  else if (d.state === 'failed') h += '<div class="t">No se pudo actualizar</div><div class="s ell">' + esc(d.message || 'Inténtalo más tarde.') + '</div></div><button class="btn go" type="button" data-act="update">Reintentar</button>';
  b.innerHTML = h;
  b.classList.add('on');
}

/* ======================= modo "solo portada" ======================= */
let lastPoke = Date.now();
function setIdle(on) { cls('is-idle', on); }
document.addEventListener('mousemove', () => { lastPoke = Date.now(); if (has('is-idle')) setIdle(false); });
document.addEventListener('mousedown', () => { lastPoke = Date.now(); });
setInterval(() => {
  if (document.hidden) return;
  const busy = !has('is-playing') || has('is-search') || has('is-sheet') || has('is-panel') || $('veil').classList.contains('on') || $('rbar').classList.contains('on') || $('banner').classList.contains('on') || DRAG.on || SEEK.drag;
  if (busy) { lastPoke = Date.now(); if (has('is-idle')) setIdle(false); return; }
  if (!has('is-idle') && Date.now() - lastPoke > 8000) setIdle(true);
}, 500);

/* ======================= clics ======================= */
const ACT = {
  options: openOptions, minimize: () => winCmd('minimize'), close: () => winCmd('close'),
  sheet: () => (has('is-sheet') ? closeSheet() : openSheet()),
  toggle: () => { const np = S.st.now_playing; if (!np) return; send(np.paused ? 'resume' : 'pause'); np.paused = !np.paused; S.elapsed = curElapsed(); S.elapsedAt = performance.now(); renderAll(); },
  next: () => send('skip'), prev: () => send('prev'), shuffle: shuffle, repeat: cycleRepeat,
  heart: () => openPicker(false), lyrics: openLyrics, react: toggleReactions,
  openSearch: openSearch, closeSearch: closeSearch, more: () => { if (SR.moreLoading || !SR.query) return; SR.moreLoading = true; renderSearch(SR.results.length); doSearch(SR.query, 6, SR.results.length, SR.kind); },
  clear: () => { const n = (S.st.queue || []).length; if (!n) return; askConfirm('¿Seguro que quieres borrar TODO?', 'Se van a quitar ' + (n === 1 ? 'la canción' : 'las ' + n + ' canciones') + ' de la lista. Lo que está sonando ahora sigue sonando.', 'Mantén presionado para borrar', 'trash', () => { send('queue_clear'); toast('Lista borrada'); }); },
  cancelConfirm: closeConfirm, closePanel: () => closePanel(), optBack: optBack,
  albums: () => openAlbums(), newAlbum: () => openEditor(null, false), albumsBack: albumsBack,
  albumEdit: () => AL.cur && openEditor(AL.cur), albumPlay: () => { send('album_play', { id: AL.cur.id, shuffle: false }); toast('Poniendo «' + AL.cur.name + '»'); },
  albumShuffle: () => { send('album_play', { id: AL.cur.id, shuffle: true }); toast('Poniendo «' + AL.cur.name + '» en aleatorio'); },
  albumSave: albumSave, pickCover: () => B && B.pick_cover(), noCover: () => { AL.edit.cover = null; AL.edit.remove = true; renderAlbums(); },
  pickNew: () => { closeCard2(); openEditor(null, true); }, card2Close: closeCard2,
  p2save: (b) => p2save(b.dataset.key), pvAdd: () => previewAccept(false), pvSingle: () => previewAccept(true), pvClose: () => { closePreview(); $('q').value = ''; SR.phase = 'home'; renderSearch(); },
  activity: openActivity, update: () => winCmd('update'), bannerClose: () => $('banner').classList.remove('on'),
  wrMine: () => { WR.mine = !WR.mine; loadWrapped(); },
};
W.addEventListener('click', (e) => {
  const a = e.target.closest('[data-act]');
  if (a && W.contains(a) && !a.disabled) { const f = ACT[a.dataset.act]; if (f) { e.stopPropagation(); f(a); } return; }
  let t;
  if ((t = e.target.closest('[data-play]'))) { send('play', { query: t.dataset.play }); toast('Agregando…'); if (has('is-search')) closeSearch(); return; }
  if ((t = e.target.closest('[data-chip]'))) { $('q').value = t.dataset.chip; submitSearch(); return; }
  if ((t = e.target.closest('[data-tile]'))) { addTile(+t.dataset.tile); return; }
  if ((t = e.target.closest('[data-kind]'))) { setKind(t.dataset.kind); return; }
  if ((t = e.target.closest('[data-remove]'))) { e.stopPropagation(); qcmd('queue_remove', +t.dataset.remove); return; }
  if ((t = e.target.closest('[data-prep]'))) { qcmd('prepare', +t.dataset.prep); toast('Preparándola…', 1400); return; }
  if ((t = e.target.closest('[data-album]'))) { openAlbum(+t.dataset.album); return; }
  if ((t = e.target.closest('[data-aremove]'))) { e.stopPropagation(); send('album_remove', { id: AL.cur.id, track_id: +t.dataset.aremove }); return; }
  if ((t = e.target.closest('[data-atrack]'))) { const tr = (AL.cur.tracks || [])[+t.dataset.atrack]; if (tr) { send('play', { query: tr.webpage_url }); toast('Agregando «' + tr.title + '»'); } return; }
  if ((t = e.target.closest('[data-color]'))) { AL.edit.color = t.dataset.color; renderAlbums(); return; }
  if ((t = e.target.closest('[data-pick]'))) { send('album_add', { id: +t.dataset.pick, current: true }); closeCard2(); return; }
  if ((t = e.target.closest('[data-period]'))) { loadWrapped(t.dataset.period); return; }
  if ((t = e.target.closest('[data-emoji]'))) { send('react', { emoji: t.dataset.emoji }); hideReactions(); return; }
  if (e.target === $('dim')) { closeSearch(); return; }
  if (e.target === $('veil')) { if ($('confirm').classList.contains('on')) closeConfirm(); else closeCard2(); return; }
  if (!e.target.closest('#rbar') && !e.target.closest('#breact')) hideReactions();
});
$('mascotb').addEventListener('click', () => { const h = $('home'); h.classList.remove('hop'); void h.offsetWidth; h.classList.add('hop'); setTimeout(() => h.classList.remove('hop'), 950); });
$('q').addEventListener('keydown', (e) => { if (e.key === 'Enter') submitSearch(); });
$('q').addEventListener('input', () => { if (!$('q').value.trim() && SR.phase !== 'home') { SR.phase = 'home'; SR.query = null; renderSearch(); } });

/* rueda: en "ahora sonando" abre/cierra la lista */
W.addEventListener('wheel', (e) => {
  if (has('is-home') || has('is-search') || has('is-panel')) return;
  if (!has('is-sheet') && e.deltaY > 0 && !e.target.closest('.sheet')) { openSheet(); return; }
  if (has('is-sheet') && e.deltaY < 0 && $('qscroll').scrollTop <= 0) closeSheet();
}, { passive: true });

/* arrastrar la ventana desde el fondo o la barra de arriba */
W.addEventListener('mousedown', (e) => {
  if (e.button !== 0) return;
  const t = e.target;
  const bg = t === W || t.id === 'drag' || t.closest('#drag') || t.classList.contains('art') || t.classList.contains('homebg') || t.classList.contains('blob') || t.classList.contains('doodles') && !t.closest('.panel') || t.classList.contains('scrim-t') || t.classList.contains('scrim-b') || t.id === 'home' || t.classList.contains('idlecap');
  if (bg && !has('is-search')) winCmd('drag');
});

/* Esc */
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  if ($('confirm').classList.contains('on')) return closeConfirm();
  if ($('card2').classList.contains('on')) return closeCard2();
  if ($('pv').classList.contains('on')) return ACT.pvClose();
  if ($('rbar').classList.contains('on')) return hideReactions();
  if (has('is-search')) return closeSearch();
  if (P.open === 'options') return optBack();
  if (P.open === 'albums') return albumsBack();
  if (P.open) return closePanel();
  if (has('is-sheet')) return closeSheet();
});
document.addEventListener('keydown', (e) => {
  if (P.open !== 'options') return;
  if (e.key === 'ArrowDown') optGo(OPT.sel + 1);
  else if (e.key === 'ArrowUp') optGo(OPT.sel - 1);
  else if (e.key === 'Enter') optAct(optItems()[OPT.sel]);
});
document.addEventListener('contextmenu', (e) => e.preventDefault());

/* ======================= arranque ======================= */
renderAll();
renderSearch();
if (window.qt && window.qt.webChannelTransport) {
  new QWebChannel(qt.webChannelTransport, (ch) => {
    B = ch.objects.cumito;
    B.event.connect(onEvent);
    Q.splice(0).forEach((x) => send(x[0], x[1]));
    B.ready();
  });
} else {
  // sin Python (pruebas en el navegador): demo.js hace de servidor
  window.CUMITO_TEST = { onEvent: onEvent, setBridge: (b) => { B = b; } };
}
