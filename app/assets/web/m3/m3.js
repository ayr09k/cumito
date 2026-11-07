/* Cumito 3.0 para el celular ("Nebulosa").

   Dos formas de entrar:
   - LAPAJA: controlas lo que suena en el Discord del grupo (como siempre).
   - Modo solo: tu música suena en TU celular. El servidor la manda como una
     transmisión continua (ver servidor/cumito_bot/solostream.py), así sigue
     sonando con la pantalla apagada.

   Todo en un archivo: conexión, el reproductor del modo solo (E), y las
   pantallas (inicio, buscar, discos, tú, artista, álbum/playlist/mix,
   reproductor, playlist, sala, letra). */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (s) => {
    s = Math.max(0, Math.floor(+s || 0));
    const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, ss = String(s % 60).padStart(2, '0');
    return h ? h + ':' + String(m).padStart(2, '0') + ':' + ss : m + ':' + ss;
  };
  const LS = {
    get(k, d) { try { const v = localStorage.getItem('cumito.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('cumito.' + k, JSON.stringify(v)); } catch (e) {} },
  };
  const bgi = (u) => (u ? "background-image:url('" + String(u).replace(/'/g, '%27') + "')" : '');
  // portadas en grande para los fondos (las listas usan las chiquitas, que cargan rápido).
  // YouTube Music deja pedir el tamaño; en YouTube se pide la máxima y, si no existe, queda la normal debajo.
  const q = (u) => "url('" + String(u).replace(/'/g, '%27') + "')";
  function hiUrl(u, yt) {
    if (!u) return null;
    u = String(u);
    if (/googleusercontent\.com|ggpht\.com/.test(u) && /=w\d+-h\d+/.test(u)) return u.replace(/=w\d+-h\d+/, '=w1200-h1200');
    const m = yt && u.match(/^(https:\/\/i\d?\.ytimg\.com\/vi(?:_webp)?\/[\w-]+\/)(?:hq|mq|sd)default\.(jpg|webp)/);
    return m ? m[1] + 'maxresdefault.' + m[2] : null;
  }
  const bgHi = (u) => { const h = hiUrl(u, false); return u ? 'background-image:' + (h ? q(h) + ',' : '') + q(u) : ''; };
  const PAL = ['#E8618C', '#3A9BDC', '#F2A33A', '#4FBF7A', '#B07CF2', '#E0563B', '#2EC4B6', '#D9A21B'];
  const pcolor = (n) => { let h = 0; for (const c of String(n || '')) h = (h * 31 + c.charCodeAt(0)) >>> 0; return PAL[h % PAL.length]; };
  const initial = (n) => (String(n || '?').trim()[0] || '?').toUpperCase();
  const isUrl = (q) => /^https?:\/\//i.test(q) || /^(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com|open\.spotify\.com|soundcloud\.com)\//i.test(q);
  const isList = (q) => /[?&]list=|\/playlist|spotify\.com\/(playlist|album)\//i.test(q);
  if (/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)) document.documentElement.classList.add('touch');
  const STANDALONE = navigator.standalone === true || (window.matchMedia && matchMedia('(display-mode: standalone)').matches);
  const SCR = { gap: 0, sb: 0 };
  function measure() {
    const root = document.documentElement;
    const probe = document.createElement('div');
    probe.style.cssText = 'position:fixed;visibility:hidden;padding-bottom:env(safe-area-inset-bottom,0px)';
    document.body.appendChild(probe);
    SCR.sb = parseFloat(getComputedStyle(probe).paddingBottom) || 0;
    probe.remove();
    const portrait = innerHeight > innerWidth;
    const full = portrait ? Math.max(screen.height, screen.width) : Math.min(screen.height, screen.width);
    const gap = STANDALONE ? Math.round(full - innerHeight) : 0;
    const focused = document.activeElement && /INPUT|TEXTAREA/.test(document.activeElement.tagName);
    if (!focused) SCR.gap = gap > 4 && gap < 140 ? gap : 0;
    root.style.setProperty('--gap', SCR.gap + 'px');
    root.classList.toggle('vgap', SCR.gap > 20 && SCR.gap < 140);
    // el ajuste se activa solo cuando confirmemos los números en un iPhone de verdad
    root.classList.toggle('gapfix', SCR.gap > 0 && LS.get('gapfix', false));
  }
  window.addEventListener('resize', () => setTimeout(measure, 120));
  window.addEventListener('orientationchange', () => setTimeout(measure, 400));

  const I = {
    home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linejoin="round"><path d="M4 11l8-6.5 8 6.5V20h-5v-5h-6v5H4z"/></svg>',
    homeF: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M4 11l8-6.5 8 6.5V20h-5v-5h-6v5H4z"/></svg>',
    search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg>',
    disc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1"><circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="2.5"/></svg>',
    user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"><circle cx="12" cy="9" r="4"/><path d="M4.5 20c1.5-3.5 4.3-5 7.5-5s6 1.5 7.5 5"/></svg>',
    play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 4.5v15l12-7.5z"/></svg>',
    pause: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg>',
    next: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M16 5h2v14h-2zM4 5v14l11-7z"/></svg>',
    prev: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h2v14H6zM20 5v14L9 12z"/></svg>',
    shuf: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/></svg>',
    rep: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 2l4 4-4 4"/><path d="M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4"/><path d="M21 13v2a3 3 0 0 1-3 3H3"/></svg>',
    rep1: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 2l4 4-4 4"/><path d="M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4"/><path d="M21 13v2a3 3 0 0 1-3 3H3"/><path d="M11 10h1.5v5" stroke-width="1.8"/></svg>',
    down: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 9l6 6 6-6"/></svg>',
    back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M15 5l-7 7 7 7"/></svg>',
    chev: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M9 5l7 7-7 7"/></svg>',
    heart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20.5s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.6a4.3 4.3 0 0 1 7.5 2.7c0 5.6-7.5 10.2-7.5 10.2z"/></svg>',
    heartF: '<svg viewBox="0 0 24 24" fill="#FF9EC4"><path d="M12 20.5s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.6a4.3 4.3 0 0 1 7.5 2.7c0 5.6-7.5 10.2-7.5 10.2z"/></svg>',
    plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M7 7l10 10M17 7L7 17"/></svg>',
    grip: '<svg viewBox="0 0 12 18" fill="currentColor"><circle cx="3" cy="4" r="1.4"/><circle cx="9" cy="4" r="1.4"/><circle cx="3" cy="9" r="1.4"/><circle cx="9" cy="9" r="1.4"/><circle cx="3" cy="14" r="1.4"/><circle cx="9" cy="14" r="1.4"/></svg>',
    list: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M4 6h12M4 12h12M4 18h8M18 15v6l4-3z"/></svg>',
    phones: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 15v-3a7.5 7.5 0 0 1 15 0v3"/><rect x="3.5" y="14" width="4" height="6" rx="1.6"/><rect x="16.5" y="14" width="4" height="6" rx="1.6"/></svg>',
    swap: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4L3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7"/></svg>',
    pen: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4L19 9l-4-4L4 16z"/></svg>',
    chart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M5 20V11M12 20V5M19 20v-7"/></svg>',
    cpu: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>',
    img: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><circle cx="9" cy="10" r="1.8"/><path d="M4 17l5-4.5 4 3.5 3-2.5 4 3.5"/></svg>',
    note: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M9 17.5a3 3 0 1 1-2-2.8V4l12-2v12.5a3 3 0 1 1-2-2.8V6.4L9 7.8z"/></svg>',
    link: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/></svg>',
  };

  /* ======================= estado ======================= */
  const S = {
    me: LS.get('name', ''), conn: false, mode: null,
    g: {}, gAt: performance.now(),
    tab: 'home', stack: [], homeFilter: 'all',
    search: { q: '', kind: 'all', res: null, loading: false, key: '' },
    feed: { data: LS.get('m3.feed', null), at: 0, key: '', loading: false },
    albums: [], covers: {}, asked: {}, discPage: null,
    lyr: { key: null, lines: null, plain: null, found: false, loading: false },
    stats: null, statsPeriod: 'month', statsMine: false, status: null,
    playerOpen: false, sheet: null, recent: LS.get('recent', []),
  };

  /* ======================= conexión ======================= */
  let ws = null, wsWait = 1000, wsTimer = null, wsAlive = false;
  function connect() {
    if (!S.me || (ws && ws.readyState <= 1)) return;
    clearTimeout(wsTimer);
    ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
    ws.onopen = () => { wsAlive = true; wsWait = 1000; ws.send(JSON.stringify({ type: 'hello', name: S.me })); S.conn = true; onConnected(); };
    ws.onmessage = (m) => { let d; try { d = JSON.parse(m.data); } catch (e) { return; } onMsg(d); };
    ws.onclose = () => {
      if (wsAlive) { S.conn = false; render(); }
      wsAlive = false; ws = null;
      wsTimer = setTimeout(connect, wsWait);
      wsWait = Math.min(wsWait * 2, 15000);
    };
    ws.onerror = () => { try { ws.close(); } catch (e) {} };
  }
  function cmd(action, kw) {
    if (ws && ws.readyState === 1) ws.send(JSON.stringify(Object.assign({ type: 'command', action: action }, kw || {})));
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !ws && S.me) { wsWait = 1000; connect(); } });
  function feat(f) { return (S.g.features || []).includes(f); }

  function onConnected() {
    cmd('album_list');
    if (E.on && E.cur) { E.report(false); E.sendPlan(); }
    render();
  }

  const MSG = {
    state(d) {
      const prevRev = S.g.albums_rev;
      S.g = Object.assign({}, S.g, d); S.gAt = performance.now(); S.conn = true;
      if (d.albums_rev !== undefined && d.albums_rev !== prevRev) cmd('album_list');
      E.onGroup();
      render();
    },
    cat_results(d) { if (d.query !== S.search.q || d.kind !== S.search.kind) return; S.search.res = d; S.search.loading = false; renderScreen(); },
    cat_error(d) { if (d.action === 'cat_search') { S.search.loading = false; S.search.res = { error: true }; } if (d.action === 'home_feed') S.feed.loading = false; toast(d.message || 'No pude cargar eso'); renderScreen(); },
    artist(d) { const p = top(); if (p && p.type === 'artist' && p.id === d.id) { p.data = d; renderScreen(); } },
    artist_songs(d) { const p = top(); if (p && p.type === 'list' && p.kind === 'artistSongs' && p.id === d.id) { p.tracks = d.tracks || []; p.loading = false; renderScreen(); } },
    yt_album(d) { const p = top(); if (p && p.type === 'list' && p.kind === 'album' && p.id === d.id) { Object.assign(p, { title: d.title, sub: [d.artist, d.year].filter(Boolean).join(' · '), art: d.art_url, tracks: d.tracks || [], loading: false }); renderScreen(); } },
    yt_playlist(d) { const p = top(); if (p && p.type === 'list' && p.kind === 'playlist' && p.url === d.url) { p.tracks = d.tracks || []; if (d.name) p.title = d.name; p.art = p.art || (p.tracks[0] && p.tracks[0].art_url); p.loading = false; renderScreen(); } },
    home_feed(d) { S.feed.data = d; S.feed.at = Date.now(); S.feed.loading = false; LS.set('m3.feed', d); renderScreen(); },
    albums(d) { S.albums = d.albums || []; renderScreen(); if (S.sheet === 'picker') openPicker(S.pickMeta, true); },
    album(d) {
      const a = d.album;
      if (!a) return;
      if (S.pendingAdd && S.pendingAdd.name === a.name) { cmd('album_add', { id: a.id, tracks: [S.pendingAdd.meta] }); S.pendingAdd = null; toast('Guardada en «' + a.name + '»'); }
      const p = top();
      if (p && p.type === 'list' && p.kind === 'disc' && p.id === a.id) { Object.assign(p, { title: a.name, sub: 'Disco de ' + (a.owner || '') + ' · ' + (a.count || 0) + ' canciones', tracks: a.tracks || [], disc: a, loading: false }); renderScreen(); }
    },
    album_cover(d) { if (d.cover && d.data) { S.covers[d.cover] = 'data:image/jpeg;base64,' + d.data; renderScreen(); } },
    album_added(d) { if (d && (d.added || d.ok !== false)) toast(d.message || 'Guardada en el disco'); },
    lyrics(d) { onLyrics(d); },
    stats(d) { S.stats = d; renderScreen(); },
    status(d) { S.status = d; renderScreen(); },
    error(d) { toast(d.message || 'Algo salió mal'); },
    solo_stream(d) { E.onStream(d); },
    solo_seg(d) { E.onSeg(d); },
    solo_plan_add(d) { E.onPlanAdd(d); },
    solo_end(d) { E.onEnd(d); },
    solo_tracks(d) { E.onTracks(d); },
    recs(d) { E.onRecs(d); },
  };
  function onMsg(d) {
    const h = MSG[d.type] || (d.type && d.type !== 'state' && !('now_playing' in d) ? null : MSG.state);
    if (h) try { h(d); } catch (e) { console.error(e); }
  }

  /* ======================= el reproductor del modo solo ======================= */
  const E = (function () {
    const SILENT = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';
    const audio = new Audio();
    audio.preload = 'auto';
    audio.setAttribute('playsinline', '');
    const isSilent = () => !audio.src || audio.src === SILENT || audio.src.startsWith('data:');
    let nextUid = 1, reqN = 0, planT = null, lastRe = 0, reTries = 0;
    const meta = (t) => ({ title: t.title, uploader: t.uploader, duration: t.duration, art_url: t.art_url, webpage_url: t.webpage_url });
    const mk = (m, extra) => Object.assign({ uid: nextUid++, title: m.title || 'Cargando…', uploader: m.uploader || '', duration: m.duration || 0, art_url: m.art_url || null, webpage_url: m.webpage_url }, extra || {});
    const shuffleArr = (a) => { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
    const X = {
      on: false, q: [], cur: null, played: [], repeat: 'off', radio: LS.get('solo.radio', true), follow: null,
      want: false, ended: false, startAt: 0, sid: null, stream: null, endAnnounced: false,
      hist: LS.get('solo.hist', []), unlocked: false, audio: audio, meta: meta,
    };
    const slog = (ev, extra) => cmd('solo_log', Object.assign({ ev: ev, hidden: document.hidden, t: (X.cur && X.cur.title) || null }, extra || {}));
    function plan() { return (X.follow ? [X.cur] : [X.cur].concat(X.q)).filter(Boolean).map((t) => Object.assign(meta(t), { uid: t.uid })); }
    function opts() { return { repeat: X.follow ? 'off' : X.repeat, radio: !!(X.radio && !X.follow), with: X.follow || null }; }
    X.sendPlan = function () {
      clearTimeout(planT);
      planT = setTimeout(() => { if (X.sid && X.stream) cmd('solo_plan', Object.assign({ sid: X.sid, items: plan() }, opts())); }, 250);
    };
    function curSeg() {
      const st = X.stream;
      if (!st || !st.segs.length) return null;
      const t = audio.currentTime + 0.05;
      let sg = null;
      for (const x of st.segs) if (x.t0 <= t) sg = x;
      return sg;
    }
    X.elapsed = function () {
      const sg = curSeg();
      if (sg && X.cur && sg.uid === X.cur.uid && !isSilent()) return Math.max(0, sg.base + audio.currentTime - sg.t0);
      return X.startAt || 0;
    };
    const findUid = (uid) => (X.cur && X.cur.uid === uid ? X.cur : X.q.find((t) => t.uid === uid) || null);
    const pushPlayed = (t) => { X.played.push(t); if (X.played.length > 60) X.played.shift(); };
    function changed() { save(); media(); render(); }
    function playFrom(t, pos, keepFollow) {
      if (!t) return;
      if (!feat('solo_stream')) { toast('El servidor se está actualizando. Prueba en un minuto'); return; }
      if (X.cur && X.cur !== t && !X.q.includes(X.cur)) pushPlayed(X.cur);
      X.cur = t; X.want = true; X.ended = false; X.startAt = pos || 0;
      if (!keepFollow) X.follow = null;
      addHist(t);
      X.stream = null; X.endAnnounced = false;
      if (!isSilent()) audio.pause();
      cmd('solo_play', Object.assign({ sid: X.sid, req: ++reqN, items: plan(), uid: t.uid, pos: pos || 0 }, opts()));
      changed();
    }
    X.onStream = function (d) {
      if (d.req !== reqN) return;
      X.sid = d.sid; X.stream = { id: d.stream, segs: [] }; X.endAnnounced = false;
      audio.src = d.url;
      if (X.want) audio.play().catch((err) => {
        slog('play-fail', { err: String(err && err.name) });
        if (document.hidden) { X.pendingPlay = true; return; }
        X.want = false; changed(); toast('Toca ▶ para empezar');
      });
    };
    X.onSeg = function (d) {
      if (!X.stream || d.stream !== X.stream.id) return;
      if (!d.t0) X.stream.segs = [];
      X.stream.segs.push({ uid: d.uid, t0: d.t0, base: d.base });
      const t = findUid(d.uid);
      if (t && d.item) ['title', 'uploader', 'duration', 'art_url'].forEach((k) => { if (d.item[k] && (!t[k] || t[k] === 'Cargando…')) t[k] = d.item[k]; });
      reTries = 0;
      sync();
      changed();
    };
    X.onPlanAdd = function (d) {
      if (d.sid !== X.sid) return;
      (d.items || []).forEach((it) => { if (!findUid(it.uid)) X.q.push(mk(it, { uid: it.uid, radio: true })); });
      changed();
    };
    X.onEnd = function (d) { if (X.stream && d.stream === X.stream.id) X.endAnnounced = true; };
    function sync() {
      const sg = curSeg();
      if (!sg || (X.cur && sg.uid === X.cur.uid)) return;
      const i = X.q.findIndex((t) => t.uid === sg.uid);
      if (i < 0) return;
      const skipped = X.q.splice(0, i);
      const t = X.q.shift();
      if (X.cur) { if (X.repeat === 'all') X.q.push(X.cur); else pushPlayed(X.cur); }
      skipped.forEach(pushPlayed);
      X.cur = t;
      addHist(t);
      changed();
      X.sendPlan();
    }
    function next(manual) {
      if (manual) X.follow = null;
      const t = X.q.shift();
      if (!t) {
        if (X.radio && X.cur) { fetchRadio(X.cur, true, false); if (manual) toast('Buscando parecidas…'); }
        else stopAtEnd();
        return;
      }
      if (X.repeat === 'all' && X.cur) X.q.push(X.cur);
      playFrom(t, 0, false);
    }
    function stopAtEnd() {
      X.want = false; X.ended = true;
      if (!isSilent()) audio.pause();
      if (X.sid) cmd('solo_stop', { sid: X.sid });
      X.report(false); changed();
    }
    function prev() {
      X.follow = null;
      if (X.elapsed() > 5 || !X.played.length) { playFrom(X.cur, 0, false); return; }
      const p = X.played.pop();
      if (X.cur) X.q.unshift(X.cur);
      X.cur = null;
      playFrom(p, 0, false);
    }
    X.add = function (list, now, startIdx) {
      const items = (list || []).filter((m) => m && m.webpage_url).map((m) => mk(m, { radio: !!m.radio }));
      if (!items.length) return;
      if (now) {
        const i = Math.max(0, Math.min(items.length - 1, startIdx || 0));
        X.q = items.slice(i + 1).concat(X.q.filter(() => false));   // escuchar una lista: reemplaza lo que seguía
        X.follow = null;
        playFrom(items[i], 0, false);
        return;
      }
      X.q.push.apply(X.q, items);
      if (!X.cur || (X.ended && !X.want)) playFrom(X.q.shift(), 0, false);
      else { X.sendPlan(); changed(); }
    };
    X.playNext = function (m) {   // tocar una canción suelta: suena ya y lo demás sigue después
      const t = mk(m);
      if (X.cur && !X.ended) pushPlayed(X.cur);
      X.cur = null;
      playFrom(t, 0, false);
    };
    // radio y "Generar recomendaciones"
    let radioBusy = false, radioStart = false, radioForce = false;
    function fetchRadio(seed, startAfter, force) {
      if (!seed || !seed.webpage_url || radioBusy) return;
      radioBusy = true; radioStart = startAfter; radioForce = !!force;
      cmd('recs', { seeds: [seed.webpage_url], tag: 'radio' });
      setTimeout(() => { radioBusy = false; }, 20000);
    }
    X.onRecs = function (d) {
      if (d.tag !== 'radio') return;
      radioBusy = false; S.qgen = false;
      if (!X.radio && !radioForce) return changed();
      const seen = new Set([X.cur].concat(X.q, X.played.slice(-40)).filter(Boolean).map((t) => t.webpage_url));
      const add = (d.items || []).filter((t) => !seen.has(t.webpage_url)).slice(0, 8);
      if (!add.length) { if (radioForce) toast('No encontré parecidas a esta'); return changed(); }
      radioForce = false;
      X.q.push.apply(X.q, add.map((m) => mk(m, { radio: true })));
      if (radioStart && !X.follow) next(false); else { X.sendPlan(); changed(); }
    };
    X.radioFrom = function (seed) {
      X.radio = true; LS.set('solo.radio', true);
      X.q = [];
      X.playNext(seed);
      toast('Radio de «' + (seed.uploader || seed.title || 'esta canción') + '»');
    };
    X.onTracks = function (d) {
      if (d.error) toast(d.error);
      if (!(d.tracks || []).length) { if (!d.error) toast('No encontré eso'); return; }
      X.add(d.tracks, d.now);
      if (d.name || d.tracks.length > 1) toast(d.tracks.length + ' canciones' + (d.name ? ' de «' + d.name + '»' : ''));
    };
    // lo que tocan en la app
    X.handle = function (a, kw) {
      kw = kw || {};
      switch (a) {
        case 'pause': X.want = false; audio.pause(); if (X.sid) cmd('solo_pause', { sid: X.sid, elapsed: X.elapsed() }); changed(); return;
        case 'resume':
          if (!X.cur) return;
          unlock();
          if (X.ended || !X.stream || isSilent()) { playFrom(X.cur, X.ended ? 0 : X.elapsed(), true); return; }
          X.want = true;
          audio.play().catch(() => playFrom(X.cur, X.elapsed(), true));
          cmd('solo_resume', { sid: X.sid, elapsed: X.elapsed() });
          changed(); return;
        case 'skip': next(true); return;
        case 'prev': prev(); return;
        case 'seek': if (X.cur) { if (X.want || X.stream) playFrom(X.cur, Math.max(0, +kw.pos || 0), false); else { X.startAt = Math.max(0, +kw.pos || 0); changed(); } } return;
        case 'set_repeat': X.repeat = ['off', 'all', 'one'].includes(kw.mode) ? kw.mode : 'off'; X.sendPlan(); changed(); return;
        case 'shuffle': shuffleArr(X.q); X.sendPlan(); changed(); toast('Lista mezclada'); return;
        case 'set_radio': X.radio = !!kw.on; LS.set('solo.radio', X.radio); X.sendPlan(); changed(); return;
        case 'radio_now': if (X.cur) fetchRadio(X.cur, false, true); return;
        case 'queue_remove': { const i = X.q.findIndex((t) => t.uid === kw.uid); if (i >= 0) X.q.splice(i, 1); emptied(); X.sendPlan(); changed(); return; }
        case 'queue_move': {
          const i = X.q.findIndex((t) => t.uid === kw.uid);
          if (i >= 0) { const [t] = X.q.splice(i, 1); X.q.splice(Math.max(0, Math.min(X.q.length, +kw.to || 0)), 0, t); }
          X.sendPlan(); changed(); return;
        }
        case 'queue_clear': X.q = []; emptied(); X.sendPlan(); changed(); return;
        case 'play_index': { const i = X.q.findIndex((t) => t.uid === kw.uid); if (i >= 0) { const [t] = X.q.splice(i, 1); playFrom(t, 0, false); } return; }
      }
    };
    function emptied() { if (!X.q.length && X.radio) { X.radio = false; LS.set('solo.radio', false); toast('Vaciaste la lista: la radio se apagó'); } }
    // escuchar con alguien (salas)
    X.follow = null;
    X.followTo = function (id) {
      if (X.follow === id) { X.follow = null; toast('Saliste de la sala'); X.sendPlan(); changed(); return; }
      if (!X.follow && X.cur && !X.ended) X.before = { cur: X.cur, pos: X.elapsed(), want: X.want };
      X.follow = id;
      unlock();
      syncFollow(true);
      changed();
    };
    X.leaveRoom = function () {
      if (!X.follow) return;
      const who = X.follow;
      X.follow = null;
      toast('Saliste de la sala de ' + (who === '@discord' ? 'LAPAJA' : who) + ' · sigues con tu música');
      const b = X.before; X.before = null;
      const roomTrack = X.cur;
      if (b && b.cur) {
        X.cur = null;
        playFrom(b.cur, b.pos, false);
        if (!b.want) X.handle('pause');
      } else if (X.q.length) { X.cur = null; next(false); }
      else { X.sendPlan(); changed(); }
      X.played = X.played.filter((t) => t !== roomTrack && !(b && t === b.cur));
    };
    function syncFollow(force) {
      const tg = roomHosts().find((x) => x.id === X.follow);
      if (!tg) {
        if (X.follow) { toast((X.follow === '@discord' ? 'LAPAJA' : X.follow) + ' dejó de escuchar'); X.follow = null; changed(); }
        return;
      }
      const url = tg.track.webpage_url;
      if (!X.cur || X.cur.webpage_url !== url) playFrom(mk(meta(tg.track), { room: true }), tg.elapsed, true);
      else if (force && Math.abs(X.elapsed() - tg.elapsed) > 5) playFrom(X.cur, tg.elapsed, true);
      if (tg.paused && X.want) { X.want = false; audio.pause(); if (X.sid) cmd('solo_pause', { sid: X.sid, elapsed: X.elapsed() }); changed(); }
      else if (!tg.paused && !X.want && X.cur && !force) X.handle('resume');
    }
    X.onGroup = function () { if (X.on && X.follow) syncFollow(false); };
    X.report = function (started) {
      if (!X.on) return;
      const c = X.cur;
      if (!c || X.ended) { cmd('solo_status', { track: null }); return; }
      cmd('solo_status', { track: meta(c), elapsed: X.elapsed(), paused: !X.want, started: !!started, with: X.follow || null });
    };
    setInterval(() => { if (X.on && X.cur && X.want) X.report(false); }, 45000);
    X.enter = function () { X.on = true; unlock(); if (X.cur) X.report(false); };
    X.leave = function () {
      if (!X.on) return;
      cmd('solo_status', { track: null });
      if (X.sid) cmd('solo_stop', { sid: X.sid });
      X.on = false; X.want = false; X.follow = null; X.stream = null;
      if (!isSilent()) audio.pause();
      media();
    };
    // historial (para "Lo último que escuchaste" y los mixes)
    function addHist(t) {
      if (!t.webpage_url || String(t.webpage_url).startsWith('busca:')) return;
      X.hist = [Object.assign(meta(t), { radio: !!(t.radio || t.room) })].concat(X.hist.filter((x) => x.webpage_url !== t.webpage_url)).slice(0, 40);
      LS.set('solo.hist', X.hist);
    }
    // pantalla de bloqueo y audífonos
    const MS = 'mediaSession' in navigator ? navigator.mediaSession : null;
    if (MS) {
      const h = (k, f) => { try { MS.setActionHandler(k, f); } catch (e) {} };
      h('play', () => X.handle('resume'));
      h('pause', () => X.handle('pause'));
      h('nexttrack', () => X.handle('skip'));
      h('previoustrack', () => X.handle('prev'));
      h('seekto', (d) => X.handle('seek', { pos: d.seekTime }));
    }
    let msKey = null;
    function media() {
      if (!MS) return;
      const c = X.on ? X.cur : null;
      try {
        if (!c) { MS.metadata = null; MS.playbackState = 'none'; return; }
        const key = c.uid + '|' + c.title + '|' + c.art_url;
        if (msKey !== key) {
          msKey = key;
          MS.metadata = new MediaMetadata({ title: c.title || '', artist: c.uploader || '', album: 'Cumito', artwork: c.art_url ? [{ src: c.art_url, sizes: '512x512', type: 'image/jpeg' }] : [] });
        }
        MS.playbackState = X.want ? 'playing' : 'paused';
        if (MS.setPositionState && c.duration) MS.setPositionState({ duration: c.duration, position: Math.min(c.duration, X.elapsed()), playbackRate: 1 });
      } catch (e) {}
    }
    // eventos del audio
    audio.addEventListener('playing', () => {
      if (isSilent() || !X.on) return;
      if (!X.want) { X.want = true; if (X.sid) cmd('solo_resume', { sid: X.sid, elapsed: X.elapsed() }); changed(); } else media();
    });
    audio.addEventListener('pause', () => {
      if (isSilent() || !X.on || audio.ended || !X.want || !X.stream) return;
      setTimeout(() => {
        if (!audio.paused || !X.want || audio.ended || audio.readyState < 2) return;
        X.want = false; if (X.sid) cmd('solo_pause', { sid: X.sid, elapsed: X.elapsed() }); changed();
      }, 400);
    });
    function reconnect(why) {
      if (!X.cur || !X.want) return;
      if (Date.now() - lastRe < 4000 || reTries >= 4) {
        if (reTries >= 4) { slog('give-up', { why: why }); X.want = false; changed(); toast('Se cortó la música. Toca ▶ para seguir'); }
        return;
      }
      lastRe = Date.now(); reTries++;
      slog('reconnect', { why: why, at: Math.round(X.elapsed()) });
      sync();
      playFrom(X.cur, X.elapsed(), true);
    }
    audio.addEventListener('ended', () => {
      if (isSilent() || !X.on) return;
      sync();
      if (!X.endAnnounced && X.want) return reconnect('ended');
      if (X.follow) {
        X.want = false; changed();
        const c = X.cur, who = X.follow;
        setTimeout(() => { if (X.follow === who && X.cur === c) { X.follow = null; toast('Se cortó la sala: sigo con tu lista'); next(false); } }, 7000);
        return;
      }
      X.want = false; X.ended = true; X.report(false); changed();
    });
    audio.addEventListener('error', () => { if (!isSilent() && X.on && X.stream) reconnect('error'); });
    document.addEventListener('visibilitychange', () => {
      if (document.hidden || !X.on || !X.cur) return;
      sync();
      if (X.pendingPlay && X.want) { X.pendingPlay = false; audio.play().catch(() => playFrom(X.cur, X.elapsed(), true)); return; }
      render();
    });
    let lastTick = 0;
    audio.addEventListener('timeupdate', () => {
      if (isSilent() || !X.on) return;
      const now = performance.now();
      if (now - lastTick < 700) return;
      lastTick = now;
      sync();
      saveSoon();
    });
    function unlock() {
      if (X.unlocked) return;
      X.unlocked = true;
      if (audio.src && !isSilent()) return;
      audio.src = SILENT;
      audio.play().then(() => { if (isSilent()) audio.pause(); }).catch(() => { X.unlocked = false; });
    }
    X.unlock = unlock;
    document.addEventListener('touchend', () => { if (X.on && !X.unlocked) unlock(); }, { passive: true });
    // seguir donde quedó
    let saveT = null;
    function save() {
      LS.set('solo.sess', { cur: X.cur ? meta(X.cur) : null, at: X.elapsed(), q: X.q.slice(0, 200).map((t) => Object.assign(meta(t), { radio: !!t.radio })), repeat: X.repeat });
    }
    function saveSoon() { if (!saveT) saveT = setTimeout(() => { saveT = null; save(); }, 4000); }
    const sess = LS.get('solo.sess', null);
    if (sess && sess.cur && sess.cur.webpage_url) {
      X.cur = mk(sess.cur); X.startAt = sess.at || 0;
      X.q = (sess.q || []).map((m) => mk(m, { radio: m.radio }));
      X.repeat = sess.repeat || 'off';
    }
    X.view = function () {
      const c = X.cur;
      return {
        np: c ? { title: c.title, uploader: c.uploader, art_url: c.art_url, webpage_url: c.webpage_url, duration: c.duration || 0, paused: !X.want, elapsed: X.elapsed() } : null,
        queue: X.q.map((t) => ({ uid: t.uid, title: t.title, uploader: t.uploader, art_url: t.art_url, duration: t.duration, radio: !!t.radio, ready: true })),
        repeat: X.repeat, radio: X.radio, canPrev: X.played.length > 0 || X.elapsed() > 5,
      };
    };
    return X;
  })();

  /* ======================= lo que suena (según el modo) ======================= */
  function gElapsed() {
    const np = S.g.now_playing;
    if (!np) return 0;
    return (+np.elapsed || 0) + (np.paused ? 0 : (performance.now() - S.gAt) / 1000);
  }
  function PV() {
    if (S.mode === 'solo') return E.view();
    const np = S.g.now_playing;
    return {
      np: np ? Object.assign({}, np, { elapsed: Math.min(np.duration || 1e9, gElapsed()) }) : null,
      queue: (S.g.queue || []).map((t) => Object.assign({}, t, { ready: t.prepared !== undefined ? t.prepared : t.ready, radio: t.who === 'Radio' })),
      repeat: S.g.repeat || 'off', radio: !!S.g.radio, canPrev: !!S.g.can_prev,
    };
  }
  // un solo lugar para "hacer" cosas: en modo solo lo atiende E, en LAPAJA el bot
  function act(a, kw) {
    kw = kw || {};
    if (S.mode === 'solo') return E.handle(a, kw);
    if (['queue_remove', 'play_index', 'prepare'].includes(a)) { const q = S.g.queue || []; kw.index = q.findIndex((t) => t.uid === kw.uid); }
    cmd(a, kw);
  }
  function playTracks(list, idx, shuffle) {
    list = (list || []).filter((t) => t && t.webpage_url);
    if (!list.length) return;
    if (shuffle) { list = list.slice(); for (let i = list.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [list[i], list[j]] = [list[j], list[i]]; } idx = 0; }
    if (S.mode === 'solo') { E.add(list, true, idx || 0); return; }
    const from = list.slice(idx || 0).slice(0, 40);
    from.forEach((t) => cmd('play', { query: t.webpage_url }));
    toast(from.length === 1 ? 'Agregada a LAPAJA' : from.length + ' canciones agregadas a LAPAJA');
  }
  function playOne(m) {
    if (S.mode === 'solo') { E.playNext(m); return; }
    cmd('play', { query: m.webpage_url }); toast('Agregada a LAPAJA');
  }
  function addOne(m) {
    if (S.mode === 'solo') { E.add([m], false); toast('Agregada a tu lista'); return; }
    cmd('play', { query: m.webpage_url }); toast('Agregada a LAPAJA');
  }
  function playLink(q) {
    if (S.mode === 'solo') cmd('solo_add', { query: q, as_playlist: isList(q), now: true });
    else cmd('play', { query: q, as_playlist: isList(q) });
    toast(isList(q) ? 'Abriendo la playlist…' : 'Abriendo el link…');
  }

  /* ======================= salas (escuchar con alguien) ======================= */
  function roomHosts() {
    const out = [];
    const np = S.g.now_playing;
    if (np && np.webpage_url) out.push({ id: '@discord', who: 'LAPAJA', by: np.who, track: np, paused: !!np.paused, elapsed: gElapsed() });
    (S.g.listening || []).forEach((e) => {
      if (!e.webpage_url || e.with) return;
      out.push({ id: e.who, who: e.who, track: e, paused: !!e.paused, elapsed: (+e.elapsed || 0) + (e.paused ? 0 : Math.max(0, Date.now() / 1000 - (e.at || 0))) });
    });
    return out;
  }
  function roomMembers(id) {
    const m = [];
    if (id === '@discord') (S.g.voice_members || []).forEach((n) => m.push({ name: n, host: false, discord: true }));
    else m.push({ name: id, host: true });
    (S.g.listening || []).forEach((e) => { if (e.with === id && !m.some((x) => x.name === e.who)) m.push({ name: e.who }); });
    if (E.on && E.follow === id && !m.some((x) => x.name === S.me)) m.push({ name: S.me, me: true });
    m.forEach((x) => { if (x.name === S.me) x.me = true; });
    return m;
  }
  // la sala en la que estoy (siguiendo a alguien, o la mía si me siguen)
  function myRoom() {
    if (S.mode !== 'solo') return null;
    if (E.follow) return E.follow;
    if ((S.g.listening || []).some((e) => e.with === S.me)) return S.me;
    return null;
  }
  function rooms() {
    return roomHosts().filter((h) => h.id !== S.me).map((h) => ({ host: h, members: roomMembers(h.id) }));
  }

  /* ======================= navegación ======================= */
  const top = () => S.stack[S.stack.length - 1] || null;
  function push(p) { S.stack.push(p); $('screen').scrollTop = 0; renderScreen(true); }
  function pop() { S.stack.pop(); renderScreen(true); }
  function goTab(t) {
    if (S.tab === t && !S.stack.length) { $('screen').scrollTo({ top: 0, behavior: 'smooth' }); return; }
    S.tab = t; S.stack = []; $('screen').scrollTop = 0;
    if (t === 'home') loadFeed(false);
    if (t === 'tu' && !S.stats) cmd('stats', { period: S.statsPeriod, who: S.statsMine ? S.me : null });
    render(true);
    if (t === 'search') setTimeout(() => { const i = $('sq'); if (i && !S.search.q) i.focus(); }, 300);
  }
  function openArtist(id, name, art) { if (!id) return; push({ type: 'artist', id: id, name: name, art: art, data: null }); cmd('artist', { id: id }); }
  function openAlbum(id, title, art) { push({ type: 'list', kind: 'album', id: id, title: title || 'Álbum', art: art, tracks: [], loading: true }); cmd('yt_album', { id: id }); }
  function openPlaylist(url, title, art) { push({ type: 'list', kind: 'playlist', url: url, title: title || 'Playlist', art: art, tracks: [], loading: true, sub: 'Playlist de YouTube' }); cmd('yt_playlist', { url: url }); }
  function openMix(i) { const m = ((S.feed.data || {}).mixes || [])[i]; if (!m) return; push({ type: 'list', kind: 'mix', title: m.title, sub: m.genre + ' · ' + m.tracks.length + ' canciones', art: m.art_url, tracks: m.tracks, k: 'MIX' }); }
  function openDisc(a) { push({ type: 'list', kind: 'disc', id: a.id, title: a.name, sub: 'Disco de ' + (a.owner || '') , art: discArt(a), tracks: [], loading: true, disc: a, k: 'DISCO' }); cmd('album_get', { id: a.id }); }

  /* ======================= inicio: mixes ======================= */
  function feedSeeds() {
    let src = S.mode === 'solo' ? E.hist.filter((t) => !t.radio) : (S.g.recent || []);
    if (!src.length) src = S.mode === 'solo' ? (S.g.recent || []) : E.hist.filter((t) => !t.radio);
    return src.slice(0, 5).map((t) => ({ title: t.title, uploader: t.uploader, webpage_url: t.webpage_url, art_url: t.art_url, duration: t.duration }));
  }
  function loadFeed(force) {
    if (!S.conn) return;
    const seeds = feedSeeds();
    const key = seeds.map((s) => s.webpage_url).join('|');
    if (!seeds.length) return;
    if (!force && S.feed.key === key && Date.now() - S.feed.at < 30 * 60 * 1000) return;
    if (S.feed.loading && !force) return;
    S.feed.key = key; S.feed.loading = true;
    cmd('home_feed', { seeds: seeds });
    setTimeout(() => { if (S.feed.loading) { S.feed.loading = false; renderScreen(); } }, 90000);
  }

  /* ======================= pantallas ======================= */
  function greet() { const h = new Date().getHours(); return h < 12 ? 'Buenos días' : h < 19 ? 'Buenas tardes' : 'Buenas noches'; }
  function cardHtml(t, act2, opts) {
    opts = opts || {};
    return '<button class="card' + (opts.cls ? ' ' + opts.cls : '') + '" type="button" ' + act2 + '>' +
      '<span class="cv' + (opts.round ? ' round' : '') + '" style="' + bgi(t.art_url) + '">' + (opts.noplay ? '' : '<span class="pdot">' + I.play + '</span>') + '</span>' +
      '<span class="ct">' + esc(t.title || t.name) + '</span>' + (opts.sub !== '' ? '<span class="cs ell">' + esc(opts.sub != null ? opts.sub : (t.uploader || t.artist || '')) + '</span>' : '') + '</button>';
  }
  function songRow(t, i, opts) {
    opts = opts || {};
    const np = PV().np;
    const playing = np && np.webpage_url === t.webpage_url;
    return '<div class="row' + (playing ? ' playing' : '') + (t.video ? ' vid' : '') + '">' +
      (opts.num ? '<span class="rn' + (i < 3 ? ' hot' : '') + '">' + (i + 1) + '</span>' : '') +
      '<button type="button" style="display:flex;align-items:center;gap:12px;flex:1;min-width:0;text-align:left" data-a="' + (opts.act || 'rowPlay') + '" data-i="' + i + '">' +
      '<span class="rc' + (t.video ? ' wide' : '') + '" style="' + bgi(t.art_url) + '"></span><span style="flex:1;min-width:0"><span class="rt ell">' + (playing ? '<span class="eq' + (np.paused ? ' off' : '') + '" style="margin-right:7px;color:var(--lil)"><i></i><i></i><i></i></span>' : '') + esc(t.title) + '</span>' +
      '<span class="ra ell">' + esc(opts.sub ? opts.sub(t) : (t.uploader || '')) + (t.duration ? ' · ' + fmt(t.duration) : '') + '</span></span></button>' +
      (opts.remove ? '<button class="rb" type="button" aria-label="Quitar" data-a="' + opts.remove + '" data-i="' + i + '">' + I.x + '</button>' : '') +
      '<button class="rb" type="button" aria-label="Guardar en un disco" data-a="heartRow" data-i="' + i + '">' + I.heart + '</button>' +
      '<button class="rb add" type="button" aria-label="Agregar a la lista" data-a="addRow" data-i="' + i + '">' + I.plus + '</button></div>';
  }
  function skelRows(n) { let h = '<div class="rows">'; for (let i = 0; i < n; i++) h += '<div class="row"><span class="rc skel"></span><span style="flex:1"><span class="skel" style="display:block;height:13px;width:60%"></span><span class="skel" style="display:block;height:11px;width:35%;margin-top:7px"></span></span></div>'; return h + '</div>'; }
  function skelCards(n, round) { let h = '<div class="hs">'; for (let i = 0; i < n; i++) h += '<span class="card"><span class="cv skel' + (round ? ' round' : '') + '"></span><span class="skel" style="display:block;height:12px;width:80%;margin-top:9px"></span></span>'; return h + '</div>'; }

  // las listas que se muestran guardan sus canciones aquí (para data-i)
  let ROWS = [];
  function rowsCtx(list) { ROWS = list || []; }

  function scHome() {
    const f = S.homeFilter;
    const feed = S.feed.data || {};
    const mixes = feed.mixes || [];
    let h = '<div class="pg"><div class="top"><div style="min-width:0"><div class="kicker">' + (S.mode === 'solo' ? 'Modo solo' : 'LAPAJA') + (S.conn ? '' : ' · conectando…') + '</div>' +
      '<h1 class="h1">' + greet() + (S.me ? ', ' + esc(S.me) : '') + '</h1></div>' +
      '<button class="av" type="button" data-a="tab" data-t="tu" style="background:' + pcolor(S.me) + '" aria-label="Tu perfil">' + esc(initial(S.me)) + '</button></div>';
    h += '<div class="chips" style="margin-top:16px">' + [['all', 'Para ti'], ['mixes', 'Mixes'], ['radios', 'Radios'], ['playlists', 'Playlists'], ['salas', 'Salas']]
      .map((c) => '<button class="chip' + (f === c[0] ? ' on' : '') + '" type="button" data-a="hfilter" data-f="' + c[0] + '">' + c[1] + '</button>').join('') + '</div>';
    const show = (k) => f === 'all' || f === k;
    // lo que suena en LAPAJA (modo grupo)
    const gnp = S.g.now_playing;
    if (S.mode !== 'solo' && f === 'all') {
      if (gnp) h += '<div class="sec"><button class="hero" type="button" data-a="openPlayer" style="height:150px;background:#2a1d4d"><span class="hbg" style="' + bgi(gnp.art_url) + '"></span><span class="hart" style="' + bgi(gnp.art_url) + ';width:96px;height:96px"></span>' +
        '<span class="htx"><span class="hk">SONANDO EN LAPAJA</span><span class="ht" style="font-size:22px">' + esc(gnp.title) + '</span><span class="hs2">' + esc(gnp.uploader || '') + (gnp.who ? ' · la puso ' + esc(gnp.who) : '') + '</span></span></button></div>';
      else h += '<div class="sec"><p class="tip">No está sonando nada en LAPAJA. Busca algo y suena para todos.</p></div>';
    }
    // salas abiertas
    const rs = rooms();
    if (show('salas') && rs.length) {
      h += '<div class="sec"><div class="sec-h"><h2 class="h2">Salas abiertas</h2></div><div class="hs">' + rs.map((r) => roomCard(r)).join('') + '</div></div>';
    } else if (f === 'salas') h += '<div class="sec"><p class="tip">Nadie está escuchando ahora. Cuando alguien ponga música en su modo solo o en LAPAJA, su sala sale aquí.</p></div>';
    // mixes
    if (show('mixes')) {
      if (mixes.length) {
        const m = mixes[0];
        h += '<div class="sec"><button class="hero" type="button" data-a="mix" data-i="0"><span class="hbg" style="' + bgi(m.art_url) + '"></span><span class="hart" style="' + bgi(m.art_url) + '"></span>' +
          '<span class="htx"><span class="hk">MIX DE HOY</span><span class="ht">' + esc(m.title) + '</span><span class="hs2">' + esc(m.genre) + ' · empieza con ' + esc(m.seed || (m.tracks[0] || {}).title || '') + '</span></span>' +
          '<span class="hp" data-a="mixPlay" data-i="0">' + I.play + '</span></button></div>';
        if (mixes.length > 1) h += '<div class="sec"><div class="sec-h"><h2 class="h2">Tus mixes</h2></div><div class="hs">' + mixes.map((x, i) => i ? cardHtml({ title: x.title, art_url: x.art_url }, 'data-a="mix" data-i="' + i + '"', { sub: x.genre + ' · ' + x.tracks.length + ' canciones' }) : '').join('') + '</div></div>';
      } else if (S.feed.loading) h += '<div class="sec"><div class="hero skel" style="box-shadow:none"></div></div>';
      else if (!feedSeeds().length) h += '<div class="sec"><p class="tip">Escucha unas canciones y aquí te armo mixes según lo que te gusta.</p></div>';
    }
    if (show('radios') && (feed.radios || []).length) {
      h += '<div class="sec"><div class="sec-h"><h2 class="h2">Radios de tus artistas</h2></div><div class="hs">' + feed.radios.map((r, i) =>
        '<button class="card art" type="button" data-a="artistRadio" data-i="' + i + '"><span class="radio-av" style="' + bgi(r.art_url) + '">' + (r.art_url ? '' : esc(initial(r.name))) + '</span><span class="ct" style="text-align:center">' + esc(r.name) + '</span></button>').join('') + '</div></div>';
    } else if (show('radios') && S.feed.loading) h += '<div class="sec">' + skelCards(4, true) + '</div>';
    if (show('playlists') && (feed.playlists || []).length) {
      h += '<div class="sec"><div class="sec-h"><h2 class="h2">Playlists que te van</h2></div><div class="hs">' + feed.playlists.map((p, i) => cardHtml(p, 'data-a="feedPl" data-i="' + i + '"', { sub: p.author || 'Playlist', noplay: true })).join('') + '</div></div>';
    }
    if (f === 'all') {
      const rec = S.mode === 'solo' ? E.hist.slice(0, 12) : (S.g.recent || []).slice(0, 12);
      if (rec.length) {
        S.homeRec = rec;
        h += '<div class="sec"><div class="sec-h"><h2 class="h2">' + (S.mode === 'solo' ? 'Lo último que escuchaste' : 'Lo último que sonó') + '</h2></div><div class="hs">' + rec.map((t, i) => cardHtml(t, 'data-a="recPlay" data-i="' + i + '"', { cls: 'sm' })).join('') + '</div></div>';
      }
      if (S.albums.length) h += '<div class="sec"><div class="sec-h"><h2 class="h2">Discos del grupo</h2><button class="link" type="button" data-a="tab" data-t="discos">Ver todos</button></div><div class="hs">' +
        S.albums.slice(0, 8).map((a, i) => '<button class="card sm" type="button" data-a="discOpen" data-i="' + i + '"><span class="cv" style="' + discStyle(a) + '"></span><span class="ct">' + esc(a.name) + '</span><span class="cs">' + (a.count || 0) + ' canciones</span></button>').join('') + '</div></div>';
    }
    return h + '</div>';
  }
  function roomCard(r) {
    const hst = r.host, dc = hst.id === '@discord';
    const inIt = E.on && E.follow === hst.id;
    const mem = r.members;
    return '<div class="rcard"><span class="rh"><span class="ell" style="min-width:0">' + (dc ? 'LAPAJA · Discord' : 'Sala de ' + esc(hst.who)) + '</span><span class="eq' + (hst.paused ? ' off' : '') + '" style="color:var(--green)"><i></i><i></i><i></i></span></span>' +
      '<span class="rm"><span class="rcv" style="' + bgi(hst.track.art_url) + '"></span><span style="min-width:0;flex:1"><span class="ell" style="font-size:13.5px;font-weight:800">' + esc(hst.track.title) + '</span><span class="ell" style="font-size:11.5px;font-weight:600;color:var(--mut)">' + esc(hst.track.uploader || '') + (dc && hst.by ? ' · la puso ' + esc(hst.by) : '') + '</span></span></span>' +
      '<span style="display:flex;align-items:center;justify-content:space-between">' + stackHtml(mem, 4) + '<span style="font-size:11.5px;font-weight:700;color:var(--mut)">' + (mem.length ? mem.length + (dc ? ' en la llamada' : ' adentro') : '') + '</span></span>' +
      '<button class="pill ' + (inIt ? 'on' : 'p') + '" type="button" data-a="room" data-id="' + esc(hst.id) + '">' + (inIt ? '<span class="eq"><i></i><i></i><i></i></span> Estás aquí · ver sala' : 'Entrar a la sala') + '</button></div>';
  }
  function stackHtml(mem, n) {
    return '<span class="stack">' + mem.slice(0, n).map((m) => '<span class="av" style="background:' + (m.discord && !m.name ? '#5865F2' : pcolor(m.name)) + (m.host ? ';border-color:var(--lil)' : '') + '">' + esc(initial(m.name)) + '</span>').join('') +
      (mem.length > n ? '<span class="av" style="background:rgba(255,255,255,.16)">+' + (mem.length - n) + '</span>' : '') + '</span>';
  }

  function scSearch() {
    const s = S.search;
    let h = '<div class="pg"><div class="pad"><h1 class="h1">Buscar</h1></div>' +
      '<label class="sbox">' + I.search + '<span class="hide">Buscar</span><input id="sq" type="search" enterkeyhint="search" autocomplete="off" autocorrect="off" spellcheck="false" placeholder="Canción, artista, playlist o link" value="' + esc(s.q) + '">' +
      (s.q ? '<button class="x" type="button" data-a="sclear" aria-label="Borrar">' + I.x.replace('<svg', '<svg width="14" height="14"') + '</button>' : '') + '</label>' +
      '<div class="chips" style="margin-top:14px">' + [['all', 'Todo'], ['songs', 'Canciones'], ['videos', 'Videos'], ['artists', 'Artistas'], ['playlists', 'Playlists'], ['albums', 'Álbumes']]
        .map((c) => '<button class="chip' + (s.kind === c[0] ? ' on' : '') + '" type="button" data-a="skind" data-k="' + c[0] + '">' + c[1] + '</button>').join('') + '</div>';
    h += '<div id="sres">' + searchBody() + '</div>';
    return h + '</div>';
  }
  function searchBody() {
    const s = S.search;
    let h = '';
    if (!s.q) {
      if (S.recent.length) h += '<div class="sec"><div class="sec-h"><h2 class="h2">Buscaste hace poco</h2></div><div class="rows">' + S.recent.slice(0, 8).map((q, i) =>
        '<button class="row" type="button" data-a="srecent" data-i="' + i + '"><span class="rc" style="display:flex;align-items:center;justify-content:center;background:var(--glass2)">' + I.search.replace('<svg', '<svg width="18" height="18"') + '</span><span class="rt ell" style="flex:1">' + esc(q) + '</span></button>').join('') + '</div></div>';
      else h += '<div class="sec"><p class="tip">Busca por canción, artista, álbum o playlist. También puedes pegar un link de YouTube o Spotify.</p></div>';
      return h;
    }
    if (isUrl(s.q)) {
      return '<div class="sec"><button class="topres" type="button" data-a="slink"><span class="cv" style="display:flex;align-items:center;justify-content:center;background:var(--vio);width:64px;border-radius:18px">' + I.link.replace('<svg', '<svg width="26" height="26"') + '</span>' +
        '<span style="flex:1;min-width:0"><span style="display:block;font-size:10.5px;font-weight:800;letter-spacing:1.1px;color:var(--lil)">LINK</span><span class="ell" style="font-size:16px;font-weight:800">' + (isList(s.q) ? 'Poner la playlist' : 'Poner esta canción') + '</span><span class="ell" style="font-size:12px;color:var(--mut)">' + esc(s.q) + '</span></span></button></div>';
    }
    if (s.loading && !s.res) return '<div class="sec">' + skelRows(6) + '</div>';
    const r = s.res || {};
    if (r.error) return '<div class="sec"><p class="tip">No pude buscar ahora. Prueba otra vez en un momento.</p></div>';
    if (s.kind === 'all') {
      const songs = r.songs || [], vids = r.videos || [];
      rowsCtx(songs.slice(0, 5).concat(vids));
      if (r.top) {
        const t = r.top;
        if (t.type === 'artist') h += '<div class="sec"><button class="topres" type="button" data-a="topres"><span class="cv round" style="' + bgi(t.art_url) + '"></span><span style="flex:1;min-width:0"><span style="display:block;font-size:10.5px;font-weight:800;letter-spacing:1.1px;color:var(--lil)">MEJOR RESULTADO · ARTISTA</span><span class="disp ell" style="font-size:24px">' + esc(t.name) + '</span><span style="font-size:12px;font-weight:600;color:var(--mut)">Populares, álbumes y su radio</span></span>' + I.chev.replace('<svg', '<svg width="18" height="18"') + '</button></div>';
        else if (t.type === 'song') h += '<div class="sec"><button class="topres" type="button" data-a="topres"><span class="cv" style="' + bgi(t.art_url) + '"></span><span style="flex:1;min-width:0"><span style="display:block;font-size:10.5px;font-weight:800;letter-spacing:1.1px;color:var(--lil)">MEJOR RESULTADO · CANCIÓN</span><span class="disp ell" style="font-size:22px">' + esc(t.title) + '</span><span class="ell" style="font-size:12px;font-weight:600;color:var(--mut)">' + esc(t.uploader || '') + '</span></span><span class="rb add" style="width:48px;height:48px;border-radius:24px">' + I.play + '</span></button></div>';
        else if (t.type === 'album' || t.type === 'playlist') h += '<div class="sec"><button class="topres" type="button" data-a="topres"><span class="cv" style="' + bgi(t.art_url) + '"></span><span style="flex:1;min-width:0"><span style="display:block;font-size:10.5px;font-weight:800;letter-spacing:1.1px;color:var(--lil)">MEJOR RESULTADO · ' + (t.type === 'album' ? 'ÁLBUM' : 'PLAYLIST') + '</span><span class="disp ell" style="font-size:22px">' + esc(t.title) + '</span><span class="ell" style="font-size:12px;font-weight:600;color:var(--mut)">' + esc(t.artist || t.author || '') + '</span></span>' + I.chev.replace('<svg', '<svg width="18" height="18"') + '</button></div>';
      }
      if (songs.length) h += '<div class="sec"><div class="sec-h"><h2 class="h2">Canciones</h2><button class="link" type="button" data-a="skind" data-k="songs">Ver más</button></div><div class="rows">' + songs.slice(0, 5).map((t, i) => songRow(t, i)).join('') + '</div></div>';
      const off = Math.min(5, songs.length);
      if (vids.length) h += '<div class="sec"><div class="sec-h"><h2 class="h2">Videos de YouTube</h2><button class="link" type="button" data-a="skind" data-k="videos">Ver más</button></div><div class="rows">' + vids.map((t, i) => songRow(t, off + i)).join('') + '</div></div>';
      if ((r.artists || []).length) h += '<div class="sec"><div class="sec-h"><h2 class="h2">Artistas</h2></div><div class="hs">' + r.artists.map((a, i) => cardHtml({ title: a.name, art_url: a.art_url }, 'data-a="sArtist" data-i="' + i + '"', { round: true, sub: 'Artista', noplay: true, cls: 'sm' })).join('') + '</div></div>';
      if ((r.playlists || []).length) h += '<div class="sec"><div class="sec-h"><h2 class="h2">Playlists de YouTube</h2></div><div class="hs">' + r.playlists.map((p, i) => cardHtml(p, 'data-a="sPl" data-i="' + i + '"', { sub: (p.author || 'Playlist') + (p.count ? ' · ' + p.count : ''), noplay: true })).join('') + '</div></div>';
      if ((r.albums || []).length) h += '<div class="sec"><div class="sec-h"><h2 class="h2">Álbumes</h2></div><div class="hs">' + r.albums.map((a, i) => cardHtml(a, 'data-a="sAlbum" data-i="' + i + '"', { sub: [a.artist, a.year].filter(Boolean).join(' · '), noplay: true })).join('') + '</div></div>';
      if (!h) h = '<div class="sec"><p class="tip">No encontré nada con eso.</p></div>';
      return h;
    }
    const list = r.results || [];
    if (!list.length) return '<div class="sec"><p class="tip">' + (s.loading ? 'Buscando…' : 'No encontré nada con eso.') + '</p></div>';
    if (s.kind === 'songs' || s.kind === 'videos') { rowsCtx(list); return '<div class="sec"><div class="rows">' + list.map((t, i) => songRow(t, i)).join('') + '</div></div>'; }
    if (s.kind === 'artists') return '<div class="sec"><div class="rows">' + list.map((a, i) => '<button class="row" type="button" data-a="sArtist" data-i="' + i + '"><span class="rc" style="border-radius:50%;' + bgi(a.art_url) + '"></span><span style="flex:1;min-width:0"><span class="rt ell">' + esc(a.name) + '</span><span class="ra">Artista</span></span>' + I.chev.replace('<svg', '<svg width="18" height="18" style="color:var(--mut)"') + '</button>').join('') + '</div></div>';
    return '<div class="sec"><div class="dgrid">' + list.map((p, i) => cardHtml(p, 'data-a="' + (s.kind === 'albums' ? 'sAlbum' : 'sPl') + '" data-i="' + i + '"', { sub: s.kind === 'albums' ? [p.artist, p.year].filter(Boolean).join(' · ') : (p.author || 'Playlist') + (p.count ? ' · ' + p.count : ''), noplay: true, cls: 'grid' })).join('').replace(/class="card grid"/g, 'class="card" style="width:auto"') + '</div></div>';
  }
  let sT = null;
  function doSearch(now) {
    const s = S.search;
    clearTimeout(sT);
    const q = s.q.trim();
    if (!q || isUrl(q)) { s.res = null; s.loading = false; updSearch(); return; }
    sT = setTimeout(() => {
      s.loading = true; s.res = null; updSearch();
      cmd('cat_search', { query: q, kind: s.kind });
      S.recent = [q].concat(S.recent.filter((x) => x.toLowerCase() !== q.toLowerCase())).slice(0, 12);
      LS.set('recent', S.recent);
      setTimeout(() => { if (s.loading && s.q.trim() === q) { s.loading = false; updSearch(); } }, 25000);
    }, now ? 0 : 500);
  }
  function updSearch() { const b = $('sres'); if (b && S.tab === 'search' && !S.stack.length) b.innerHTML = searchBody(); else renderScreen(); }

  function discArt(a) { return a.cover ? (S.covers[a.cover] || (askCover(a.cover), null)) : ((a.arts || [])[0] || null); }
  function askCover(h) { if (h && !S.asked[h]) { S.asked[h] = 1; cmd('album_cover', { cover: h }); } }
  function discStyle(a) {
    if (a.cover) { const c = S.covers[a.cover]; askCover(a.cover); if (c) return bgi(c); }
    const arts = a.arts || [];
    if (arts.length) return bgi(arts[0]);
    return 'background:linear-gradient(150deg,' + (a.color || '#8E6CF2') + ',#1B1035)';
  }
  function scDiscos() {
    let h = '<div class="pg"><div class="top"><h1 class="h1">Discos</h1><button class="pill g" type="button" data-a="discNew">' + I.plus + 'Nuevo</button></div>' +
      '<p class="tip" style="margin-top:6px">Los discos son del grupo: cualquiera agrega canciones con el corazón.</p><div class="sec"><div class="dgrid">';
    h += S.albums.map((a, i) => {
      const c = a.cover ? S.covers[a.cover] : null;
      if (a.cover) askCover(a.cover);
      const arts = (a.arts || []).slice(0, 4);
      const inner = c ? '<span class="cover" style="' + bgi(c) + '"></span>' : arts.length >= 4 ? '<span class="cover">' + arts.map((x) => '<i style="' + bgi(x) + '"></i>').join('') + '</span>' : '<span class="cover" style="' + discStyle(a) + '"></span>';
      return '<button class="disc" type="button" data-a="discOpen" data-i="' + i + '" style="--dc:' + esc(a.color || '#C9B4F8') + '"><span class="sleeve"><span class="vin"></span>' + inner + '</span><span class="dn ell">' + esc(a.name) + '</span><span class="do">' + esc(a.owner || '') + ' · ' + (a.count || 0) + ' canciones</span></button>';
    }).join('');
    h += '<button class="disc" type="button" data-a="discNew"><span class="newdisc">' + I.plus.replace('<svg', '<svg width="26" height="26"') + 'Nuevo disco</span></button>';
    return h + '</div></div></div>';
  }

  function scTu() {
    const st = S.stats;
    let h = '<div class="pg"><div class="top" style="justify-content:flex-start;gap:14px"><span class="av" style="width:64px;height:64px;font-size:26px;background:' + pcolor(S.me) + '">' + esc(initial(S.me)) + '</span>' +
      '<span><span class="h1" style="display:block;font-size:26px">' + esc(S.me || 'Tú') + '</span><span class="kicker">' + (S.mode === 'solo' ? 'Escuchando en modo solo' : 'Conectado a LAPAJA') + '</span></span></div>';
    h += '<div class="sec"><button class="opt" type="button" data-a="entry"><span class="oi">' + I.swap + '</span><span style="flex:1"><b>Cambiar de modo</b><small>' + (S.mode === 'solo' ? 'Pasar a LAPAJA (Discord)' : 'Pasar al modo solo') + '</small></span>' + I.chev.replace('<svg', '<svg width="16" height="16" style="color:var(--mut)"') + '</button>' +
      '<button class="opt" type="button" data-a="rename"><span class="oi">' + I.pen + '</span><span style="flex:1"><b>Cambiar mi nombre</b><small>Así te ven los demás</small></span></button>' +
      '<label class="opt"><span class="oi">' + I.phones + '</span><span style="flex:1"><b>Recordar cómo entro</b><small>Abrir directo en el último modo</small></span><input type="checkbox" data-a="remember"' + (LS.get('m3.remember', true) ? ' checked' : '') + ' style="width:20px;height:20px;accent-color:#8E6CF2"></label>' +
      '<button class="opt" type="button" data-a="status"><span class="oi">' + I.cpu + '</span><span style="flex:1"><b>Estado del servidor</b><small>' + esc(S.status ? 'Versión ' + ((S.status.versions || {}).server || '?') : 'Cómo va la VM') + '</small></span>' + I.chev.replace('<svg', '<svg width="16" height="16" style="color:var(--mut)"') + '</button></div>';
    h += '<div class="sec"><div class="sec-h"><h2 class="h2">Tu Wrapped</h2></div><div class="seg">' + [['week', 'Semana'], ['month', 'Mes'], ['year', 'Año'], ['all', 'Siempre']].map((p) => '<button type="button" class="' + (S.statsPeriod === p[0] ? 'on' : '') + '" data-a="speriod" data-p="' + p[0] + '">' + p[1] + '</button>').join('') + '</div>' +
      '<div class="seg" style="margin-top:8px"><button type="button" class="' + (!S.statsMine ? 'on' : '') + '" data-a="smine" data-m="0">Todo el grupo</button><button type="button" class="' + (S.statsMine ? 'on' : '') + '" data-a="smine" data-m="1">Solo yo</button></div>';
    if (!st) h += '<div style="height:12px"></div>' + skelRows(3);
    else {
      h += '<div class="stat" style="margin-top:14px"><div><b>' + (st.plays || 0) + '</b><span>canciones</span></div><div><b>' + (st.minutes || 0) + '</b><span>minutos</span></div><div><b>' + (st.days || 0) + '</b><span>días</span></div></div>';
      const hs = st.hours || []; const mx = Math.max(1, ...hs);
      if (hs.length) h += '<div style="margin-top:16px" class="bars">' + hs.map((v) => '<i style="height:' + Math.round(v / mx * 100) + '%"></i>').join('') + '</div><div style="display:flex;justify-content:space-between;padding:4px 18px 0;font-size:10.5px;font-weight:700;color:var(--mut2)"><span>0 h</span><span>12 h</span><span>23 h</span></div>';
      if ((st.top_artists || []).length) h += '<div class="sec"><div class="sec-h"><h2 class="h2">Artistas</h2></div><div class="hs">' + st.top_artists.map((a) => '<span class="card art"><span class="radio-av" style="' + bgi(a.art_url) + '"></span><span class="ct" style="text-align:center">' + esc(a.name) + '</span><span class="cs" style="text-align:center">' + a.plays + ' veces</span></span>').join('') + '</div></div>';
      if ((st.top_songs || []).length) { S.tuRows = st.top_songs; h += '<div class="sec"><div class="sec-h"><h2 class="h2">Canciones</h2></div><div class="rows">' + st.top_songs.map((t, i) => songRow(t, i, { num: true, act: 'tuPlay', sub: (x) => (x.uploader || '') + ' · ' + x.plays + ' veces' })).join('') + '</div></div>'; rowsCtx(st.top_songs); }
    }
    h += '<div class="sec" style="margin-top:34px"><a class="opt quiet" href="../?v2"><span class="oi">' + I.swap + '</span><span style="flex:1"><b>Usar la app anterior</b><small>Por si algo falla en la 3.0</small></span></a>' +
      '<p class="diag">3.0.4 · ' + innerWidth + '×' + innerHeight + ' de ' + screen.width + '×' + screen.height + ' · borde ' + Math.round(SCR.sb) + (SCR.gap ? ' · ajuste ' + SCR.gap : '') + (STANDALONE ? ' · app' : ' · navegador') + '</p></div>';
    return h + '</div>';
  }

  function scArtist(p) {
    const d = p.data;
    let h = '<div class="pg"><div class="phero"><span class="pbg" style="' + bgHi((d && d.art_url) || p.art) + '"></span></div><div class="ptx"><div class="pk">ARTISTA</div><div class="pt">' + esc((d && d.name) || p.name || '') + '</div></div>';
    if (!d) return h + '<div style="height:20px"></div>' + skelRows(5) + '</div>';
    rowsCtx(d.top || []);
    h += '<div class="pacts"><button class="pill w" type="button" data-a="artPlay">' + I.play + 'Escuchar</button><button class="pill g" type="button" data-a="artRadio">Radio</button><button class="ib" type="button" data-a="artShuf" aria-label="Aleatorio">' + I.shuf + '</button></div>';
    if (d.description) h += '<p class="desc">' + esc(d.description) + '</p>';
    if ((d.top || []).length) h += '<div class="sec"><div class="sec-h"><h2 class="h2">Populares</h2>' + (d.all_songs ? '<button class="link" type="button" data-a="artAll">Todas las canciones</button>' : '') + '</div><div class="rows">' + d.top.slice(0, p.more ? 10 : 5).map((t, i) => songRow(t, i, { num: true })).join('') + '</div>' +
      (!p.more && d.top.length > 5 ? '<div class="pad"><button class="pill g" type="button" data-a="artMore" style="margin:8px auto 0">Ver más</button></div>' : '') + '</div>';
    if ((d.albums || []).length) h += '<div class="sec"><div class="sec-h"><h2 class="h2">Álbumes</h2></div><div class="hs">' + d.albums.map((a, i) => cardHtml(a, 'data-a="artAlbum" data-k="albums" data-i="' + i + '"', { sub: a.year || 'Álbum', noplay: true })).join('') + '</div></div>';
    if ((d.singles || []).length) h += '<div class="sec"><div class="sec-h"><h2 class="h2">Sencillos y EP</h2></div><div class="hs">' + d.singles.map((a, i) => cardHtml(a, 'data-a="artAlbum" data-k="singles" data-i="' + i + '"', { sub: a.year || 'Sencillo', noplay: true, cls: 'sm' })).join('') + '</div></div>';
    return h + '</div>';
  }
  function scList(p) {
    const tracks = p.tracks || [];
    rowsCtx(tracks);
    const art = p.art || (tracks[0] && tracks[0].art_url);
    const total = tracks.reduce((s, t) => s + (t.duration || 0), 0);
    let h = '<div class="pg"><div class="phero" style="height:calc(300px + var(--st))"><span class="pbg blur" style="' + bgi(art) + '"></span><span class="pcv" style="' + (p.kind === 'disc' && p.disc ? discStyle(p.disc) : bgi(art)) + '"></span></div>' +
      '<div class="ptx low" style="text-align:center"><div class="pk">' + esc(p.k || (p.kind === 'album' ? 'ÁLBUM' : p.kind === 'playlist' ? 'PLAYLIST' : p.kind === 'artistSongs' ? 'TODAS LAS CANCIONES' : 'LISTA')) + '</div>' +
      '<div class="pt sm">' + esc(p.title || '') + '</div><div class="ps">' + esc(p.sub || '') + (tracks.length ? (p.sub ? ' · ' : '') + tracks.length + ' canciones' + (total > 60 ? ' · ' + Math.round(total / 60) + ' min' : '') : '') + '</div></div>';
    h += '<div class="pacts" style="justify-content:center"><button class="pill w" type="button" data-a="listPlay"' + (tracks.length ? '' : ' disabled') + '>' + I.play + 'Escuchar</button><button class="pill g" type="button" data-a="listShuf"' + (tracks.length ? '' : ' disabled') + '>' + I.shuf + 'Aleatorio</button>' +
      (p.kind === 'disc' ? '<button class="ib" type="button" data-a="discEdit" aria-label="Editar disco">' + I.pen + '</button>' : '') + '</div>';
    if (p.loading) return h + '<div style="height:16px"></div>' + skelRows(6) + '</div>';
    if (!tracks.length) return h + '<div class="sec"><p class="tip" style="text-align:center">' + (p.kind === 'disc' ? 'Este disco está vacío. Toca el corazón en cualquier canción para agregarla.' : 'No encontré canciones aquí.') + '</p></div></div>';
    h += '<div class="sec"><div class="rows">' + tracks.map((t, i) => songRow(t, i, { num: p.kind === 'album', remove: p.kind === 'disc' ? 'discRemove' : null, sub: p.kind === 'disc' ? (x) => (x.uploader || '') + (x.added_by ? ' · ' + x.added_by : '') : null })).join('') + '</div></div>';
    if (p.kind === 'disc') h += '<div class="sec pad" style="display:flex;justify-content:center"><button class="pill r hold" type="button" data-hold="discDelete"><svg class="ring" viewBox="0 0 200 40" preserveAspectRatio="none"><rect x="1" y="1" width="198" height="38" rx="19" pathLength="100"/></svg>' + I.trash + '<span>Mantén para borrar el disco</span></button></div>';
    return h + '</div>';
  }
  function scStatus() {
    const s = S.status;
    let h = '<div class="pg"><div class="pad" style="padding-top:52px"><h1 class="h1">Estado del servidor</h1></div>';
    if (!s) return h + '<div style="height:16px"></div>' + skelRows(4) + '</div>';
    const mem = s.mem || {}, disk = s.disk || {};
    const pct = (u, t) => (t ? Math.round(u / t * 100) : 0);
    h += '<div class="stat" style="margin-top:18px"><div><b>' + (s.cpu != null ? s.cpu + '%' : '—') + '</b><span>procesador</span></div><div><b>' + pct(mem.used, mem.total) + '%</b><span>memoria</span></div><div><b>' + pct(disk.used, disk.total) + '%</b><span>disco</span></div></div>';
    const d = s.discord || {};
    h += '<div class="sec"><div class="rows">' +
      '<div class="row"><span style="flex:1"><span class="rt">Versión</span><span class="ra">' + esc((s.versions || {}).server || '?') + '</span></span></div>' +
      '<div class="row"><span style="flex:1"><span class="rt">Discord</span><span class="ra">' + (d.ready ? 'Conectado' + (d.ping ? ' · ' + d.ping + ' ms' : '') + (d.voice ? ' · en ' + esc(d.voice) : '') : 'Desconectado') + '</span></span></div>' +
      '<div class="row"><span style="flex:1"><span class="rt">Conectados a Cumito</span><span class="ra">' + (s.listeners || 0) + '</span></span></div>' +
      '<div class="row"><span style="flex:1"><span class="rt">Encendido hace</span><span class="ra">' + Math.round((s.uptime_bot || 0) / 3600) + ' h</span></span></div></div></div>';
    return h + '</div>';
  }

  /* ======================= pintar ======================= */
  let lastScreen = '';
  function renderScreen(force) {
    if (!S.mode) return;
    const p = top();
    let html;
    if (p) html = p.type === 'artist' ? scArtist(p) : p.type === 'status' ? scStatus() : scList(p);
    else html = S.tab === 'search' ? scSearch() : S.tab === 'discos' ? scDiscos() : S.tab === 'tu' ? scTu() : scHome();
    if (p) html = '<button class="back" type="button" data-a="back" aria-label="Volver">' + I.back + '</button>' + html;
    if (!force && html === lastScreen) return;
    const sc = $('screen');
    const keepScroll = !force;
    const y = sc.scrollTop;
    // el buscador no se repinta mientras escribes (perdería el teclado)
    const focused = document.activeElement && document.activeElement.id === 'sq';
    if (focused && S.tab === 'search' && !p) { const b = $('sres'); if (b) b.innerHTML = searchBody(); lastScreen = html; return; }
    sc.innerHTML = html.replace(/class="pg"/, keepScroll ? 'class="pg" style="animation:none"' : 'class="pg"');
    if (keepScroll) sc.scrollTop = y;
    lastScreen = html;
  }
  function renderTabs() {
    const t = $('tabs');
    const tabs = [['home', 'Inicio', I.home], ['search', 'Buscar', I.search], ['discos', 'Discos', I.disc], ['tu', 'Tú', I.user]];
    const html = tabs.map((x) => '<button class="tab' + (S.tab === x[0] ? ' on' : '') + '" type="button" data-a="tab" data-t="' + x[0] + '">' + (S.tab === x[0] && x[0] === 'home' ? I.homeF : x[2]) + x[1] + '</button>').join('');
    if (t.innerHTML !== html) t.innerHTML = html;
    t.classList.toggle('hide', !S.mode);
  }
  function renderMini() {
    const m = $('mini');
    const v = PV(), np = v.np;
    if (!S.mode || !np || S.playerOpen) { m.classList.add('hide'); return; }
    const key = [np.title, np.art_url, np.paused, S.mode].join('|');
    if (m.dataset.k !== key) {
      m.dataset.k = key;
      m.innerHTML = '<span class="mc" style="' + bgi(np.art_url) + '"></span><button type="button" data-a="openPlayer" style="flex:1;min-width:0;text-align:left"><span class="mode">' + (S.mode === 'solo' ? (E.follow ? 'EN LA SALA DE ' + esc(E.follow === '@discord' ? 'LAPAJA' : E.follow).toUpperCase() : 'EN TU CEL') : 'EN LAPAJA') + '</span><span class="mt ell">' + esc(np.title) + '</span><span class="ma ell">' + esc(np.uploader || '') + '</span></button>' +
        '<span class="eq' + (np.paused ? ' off' : '') + '" style="color:var(--lil)"><i></i><i></i><i></i></span><button class="cb sm" type="button" data-a="toggle" aria-label="' + (np.paused ? 'Seguir' : 'Pausar') + '">' + (np.paused ? I.play : I.pause) + '</button>' +
        '<button class="cb sm" type="button" data-a="skip" aria-label="Siguiente">' + I.next + '</button><span class="mb"><i id="mbar"></i></span>';
    }
    m.classList.remove('hide');
  }
  function renderBg() {
    const np = PV().np;
    const art = np && np.art_url;
    const k = art || '';
    const bg = $('bg');
    if (bg.dataset.k === k) return;
    bg.dataset.k = k;
    bg.querySelectorAll('.aur').forEach((a, i) => {
      a.style.backgroundImage = art && i < 2 ? "url('" + art + "')" : '';
      a.style.backgroundSize = 'cover';
    });
  }
  function render(force) {
    $('entry').classList.toggle('hide', !!S.mode);
    if (!S.mode) { renderEntry(); return; }
    renderTabs(); renderMini(); renderBg(); renderScreen(force);
    if (S.playerOpen) renderPlayer();
    if (S.playerOpen || $('lyr').classList.contains('on')) askLyrics();
    if (S.sheet === 'queue') renderQueue();
    if (S.sheet === 'room') renderRoom();
  }

  /* ======================= entrada (LAPAJA / modo solo) ======================= */
  function renderEntry() {
    const el = $('entry');
    if (!S.me) {
      if (el.dataset.k === 'name') return;
      el.dataset.k = 'name';
      el.innerHTML = '<div class="glow"></div><img class="ghost" src="cumito.png" alt="Cumito"><div class="q">¡Hola! ¿Cómo te llamas?</div><div class="hi">Así te van a ver los demás en Cumito</div>' +
        '<input id="nmIn" class="nm-in" maxlength="32" autocomplete="nickname" placeholder="Tu nombre" enterkeyhint="go"><button class="pill w" type="button" data-a="setName" style="margin-top:14px;height:48px;padding:0 30px">Entrar</button>';
      return;
    }
    const vm = S.g.voice_members || [];
    const gnp = S.g.now_playing;
    const solos = (S.g.listening || []).filter((e) => e.who !== S.me).map((e) => e.who);
    const key = JSON.stringify([vm, gnp && gnp.title, solos, S.conn]);
    if (el.dataset.k === key) return;
    el.dataset.k = key;
    const list = (names) => names.length <= 2 ? names.join(' y ') : names.slice(0, 2).join(', ') + ' y ' + (names.length - 2) + ' más';
    el.innerHTML = '<div class="glow"></div><img class="ghost" src="cumito.png" alt="Cumito"><div class="q">¿Cómo quieres entrar?</div><div class="hi">Hola, ' + esc(S.me) + (S.conn ? '' : ' · conectando…') + '</div>' +
      '<div class="prof"><button class="pf" type="button" data-a="enter" data-m="group"><span class="tile lp"><span class="mono">LP</span>' + (gnp ? '<span class="badge"><span class="live"></span>EN VIVO</span>' : '') + '</span><span class="nm">LAPAJA</span>' +
      stackHtml(vm.map((n) => ({ name: n })), 4) + '<span class="who">' + (vm.length ? vm.length + ' en Discord' : 'Nadie en la llamada') + '<br>' + (gnp ? 'sonando ' + esc(gnp.title) : 'no suena nada') + '</span></button>' +
      '<button class="pf" type="button" data-a="enter" data-m="solo"><span class="tile so">' + I.phones + '</span><span class="nm">Modo solo</span>' + stackHtml(solos.map((n) => ({ name: n })), 4) +
      '<span class="who">' + (solos.length ? esc(list(solos)) + '<br>escuchando solos' : 'Tu música<br>en tu cel') + '</span></button></div>' +
      '<label class="rem"><input type="checkbox" id="remIn"' + (LS.get('m3.remember', true) ? ' checked' : '') + '>Recordar cómo entré</label>';
  }
  function enterMode(m) {
    if (S.mode === m) { render(true); return; }
    if (S.mode === 'solo' && m !== 'solo') E.leave();
    S.mode = m;
    const r = $('remIn'); if (r) LS.set('m3.remember', r.checked);
    LS.set('m3.mode', m);
    if (m === 'solo') { E.enter(); toast('Modo solo: la música suena en tu celular'); }
    S.tab = 'home'; S.stack = []; S.feed.at = 0;
    loadFeed(true);
    render(true);
  }

  /* ======================= reproductor completo ======================= */
  function openPlayer() { if (!PV().np) return; S.playerOpen = true; $('player').classList.add('on'); renderMini(); renderPlayer(true); askLyrics(); }
  function closePlayer() { S.playerOpen = false; $('player').classList.remove('on'); renderMini(); }
  let plKey = '';
  function renderPlayer(force) {
    const v = PV(), np = v.np;
    const el = $('player');
    if (!np) { if (S.playerOpen) closePlayer(); return; }
    const room = myRoom();
    const mem = room ? roomMembers(room) : [];
    const k = JSON.stringify([np.title, np.art_url, np.paused, v.repeat, v.radio, v.canPrev, room, mem.map((m) => m.name), v.queue.length, S.mode, liked(np)]);
    el.classList.toggle('is-paused', !!np.paused);
    if (!$('pbody')) el.innerHTML = '<span class="pbg2" id="pbg2"></span><div class="pl-wall" id="pwall"></div><div class="pl-body" id="pbody"></div>';
    setWall(np.art_url);
    if (!force && k === plKey) return;
    plKey = k;
    const from = S.mode === 'solo' ? (E.follow ? 'Sala de ' + (E.follow === '@discord' ? 'LAPAJA' : E.follow) : 'Tu celular') : 'LAPAJA · Discord';
    $('pbody').innerHTML = '<div class="sgrab" data-drag="player" style="padding:2px 0 6px"><span class="grab"></span></div>' +
      '<div class="pl-top"><button class="ib" type="button" data-a="closePlayer" aria-label="Bajar">' + I.down + '</button><div class="ctr"><div class="k">' + (S.mode === 'solo' ? 'SONANDO EN' : 'SONANDO EN') + '</div><div class="f ell">' + esc(from) + '</div></div>' +
      '<button class="ib" type="button" data-a="openQueue" aria-label="Playlist">' + I.list + '</button></div>' +
      '<div class="pl-space"></div>' +
      (room ? '<div class="pl-roomrow"><button class="pl-room" type="button" data-a="openRoom">' + stackHtml(mem, 3).replace(/class="av"/g, 'class="av flo"') + '<span>' + (room === S.me ? 'Tu sala' : 'Sala de ' + esc(room === '@discord' ? 'LAPAJA' : room)) + '</span></button></div>' : '') +
      '<div class="pl-info"><div style="flex:1;min-width:0"><div class="t ell">' + esc(np.title) + '</div><div class="a ell">' + esc(np.uploader || '') + (S.mode !== 'solo' && np.who ? ' · la puso ' + esc(np.who) : '') + '</div></div>' +
      '<button class="heart" type="button" data-a="heartNow" aria-label="Guardar en un disco">' + (liked(np) ? I.heartF : I.heart) + '</button></div>' +
      '<div class="seek" id="seek"><div class="bar" id="sbar"><span class="fill" id="sfill"></span><span class="knob" id="sknob"></span></div><div class="tm"><span id="tnow">0:00</span><span id="tdur">' + fmt(np.duration) + '</span></div></div>' +
      '<div class="ctrls"><button class="cb sm' + (S.mode === 'solo' ? ' dim' : ' dim') + '" type="button" data-a="shuffle" aria-label="Mezclar la lista">' + I.shuf + '</button>' +
      '<button class="cb" type="button" data-a="prev" aria-label="Anterior"' + (v.canPrev || S.mode === 'solo' ? '' : ' disabled') + '>' + I.prev + '</button>' +
      '<button class="cb play" type="button" data-a="toggle" aria-label="' + (np.paused ? 'Seguir' : 'Pausar') + '">' + (np.paused ? I.play : I.pause) + '</button>' +
      '<button class="cb" type="button" data-a="skip" aria-label="Siguiente">' + I.next + '</button>' +
      '<button class="cb sm' + (v.repeat !== 'off' ? ' on' : ' dim') + '" type="button" data-a="repeat" aria-label="Repetir">' + (v.repeat === 'one' ? I.rep1 : I.rep) + '</button></div>' +
      '<div class="pl-low"><button class="lycard" type="button" data-a="openLyrics"><span class="k"><span>LETRA</span><span style="color:var(--mint)">' + (S.lyr.lines ? 'Karaoke' : '') + '</span></span><span class="l1 ell" id="ly1">' + esc(lyLine(0)) + '</span><span class="l2 ell hide" id="ly2"></span></button>' +
      '<button class="qbtn" type="button" data-a="openQueue">' + I.list + '<span>Lista' + (v.queue.length ? ' · ' + v.queue.length : '') + '</span></button></div>';
    tick();
  }
  function liked() { return false; }
  // la portada de fondo: al cambiar de canción, la nueva aparece suave encima
  function setWall(url) {
    const w = $('pwall'), b = $('pbg2');
    if (!w) return;
    const k = url || '';
    if (w.dataset.k === k) return;
    w.dataset.k = k;
    if (b) b.style.backgroundImage = url ? q(url) : '';
    const d = document.createElement('div');
    d.className = 'wimg';
    if (url) d.style.backgroundImage = q(url);
    // la versión en alta se pone apenas carga (si YouTube no la tiene, se queda la normal)
    const hu = hiUrl(url, true);
    if (hu) { const im = new Image(); im.onload = () => { if (im.naturalWidth > 200 && d.isConnected) d.style.backgroundImage = q(hu) + ',' + q(url); }; im.src = hu; }
    w.appendChild(d);
    void d.offsetWidth;
    d.classList.add('on');
    const old = Array.from(w.children).filter((x) => x !== d);
    setTimeout(() => old.forEach((x) => x.remove()), 1100);
  }

  // barra de progreso (se mueve sola)
  let seeking = null;
  function tick() {
    const v = PV(), np = v.np;
    const mb = $('mbar');
    const pos = seeking != null ? seeking : np ? Math.min(np.duration || 0, np.elapsed) : 0;
    const pct = np && np.duration ? Math.min(100, pos / np.duration * 100) : 0;
    if (mb) mb.style.width = pct + '%';
    if (S.playerOpen) {
      const f = $('sfill'), kn = $('sknob'), tn = $('tnow');
      if (f) f.style.width = pct + '%';
      if (kn) kn.style.left = pct + '%';
      if (tn) tn.textContent = fmt(pos);
      lyFollow(pos);
    }
    if ($('lyr').classList.contains('on')) lyFollow(pos);
  }
  setInterval(() => { if (S.mode) tick(); }, 500);
  // arrastrar en la barra para adelantar
  document.addEventListener('pointerdown', (e) => {
    const bar = e.target.closest('#sbar');
    if (!bar) return;
    const np = PV().np;
    if (!np || !np.duration) return;
    const r = bar.getBoundingClientRect();
    const at = (x) => Math.max(0, Math.min(1, (x - r.left) / r.width)) * np.duration;
    seeking = at(e.clientX); $('seek').classList.add('drag'); tick();
    const mv = (ev) => { seeking = at(ev.clientX); tick(); };
    const up = () => {
      window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up); window.removeEventListener('pointercancel', up);
      const s = $('seek'); if (s) s.classList.remove('drag');
      const pos = seeking; seeking = null;
      if (pos != null) act('seek', { pos: Math.round(pos) });
      if (S.mode !== 'solo' && S.g.now_playing) { S.g.now_playing.elapsed = pos; S.gAt = performance.now(); }
      tick();
    };
    window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up); window.addEventListener('pointercancel', up);
  });

  /* ======================= letra ======================= */
  function lyKey(np) { return np ? np.webpage_url || np.title : null; }
  function askLyrics(retry) {
    const np = PV().np;
    const k = lyKey(np);
    if (!np || (!retry && S.lyr.key === k)) return;
    S.lyr = { key: k, lines: null, plain: null, found: false, loading: true, tries: retry && S.lyr.key === k ? S.lyr.tries : 0 };
    lastLy = -2; plKey = '';
    if (S.playerOpen) renderPlayer(true);
    if ($('lyr').classList.contains('on')) renderLyrics();
    if (S.mode === 'solo') cmd('lyrics', { webpage_url: np.webpage_url, title: np.title, uploader: np.uploader, duration: np.duration });
    else cmd('lyrics');
  }
  function onLyrics(d) {
    const np = PV().np;
    if (!np || lyKey(np) !== S.lyr.key || (d.webpage_url && np.webpage_url && d.webpage_url !== np.webpage_url)) return;
    if (d.pending && (S.lyr.tries || 0) < 5) { S.lyr.tries = (S.lyr.tries || 0) + 1; const k0 = S.lyr.key; setTimeout(() => { if (S.lyr.key === k0) askLyrics(true); }, 2500); return; }
    S.lyr.loading = false; S.lyr.found = !!d.found;
    S.lyr.lines = d.synced ? parseLrc(d.synced) : null;
    S.lyr.plain = d.plain || null;
    plKey = ''; lastLy = -2;
    if (S.playerOpen) renderPlayer(true);
    if ($('lyr').classList.contains('on')) renderLyrics();
  }
  function parseLrc(txt) {
    const out = [];
    String(txt).split(/\r?\n/).forEach((l) => {
      const m = l.match(/^\s*\[(\d+):(\d+(?:\.\d+)?)\](.*)$/);
      if (m) out.push({ t: +m[1] * 60 + +m[2], text: m[3].trim() || '♪' });
    });
    return out.length ? out : null;
  }
  function lyIdx(pos) { const L = S.lyr.lines; if (!L) return -1; let i = -1; for (let j = 0; j < L.length; j++) if (L[j].t <= pos + 0.3) i = j; return i; }
  function lyLine(off) {
    const L = S.lyr.lines;
    if (!L) return off ? '' : (S.lyr.loading ? 'Buscando la letra…' : S.lyr.plain ? 'Toca para ver la letra' : 'Sin letra por ahora');
    const np = PV().np;
    const i = Math.max(0, lyIdx(np ? np.elapsed : 0)) + off;
    return (L[i] && L[i].text) || '';
  }
  let lastLy = -2;
  function lyFollow(pos) {
    const i = lyIdx(pos);
    if (i === lastLy) return;
    lastLy = i;
    const a = $('ly1'), b = $('ly2');
    if (a && S.lyr.lines) { a.textContent = (S.lyr.lines[Math.max(0, i)] || {}).text || ''; b.textContent = (S.lyr.lines[Math.max(0, i) + 1] || {}).text || ''; }
    const box = document.querySelector('#lyr .lbody');
    if (box) {
      box.querySelectorAll('.ln').forEach((el, j) => { el.classList.toggle('on', j === i); el.classList.toggle('past', j < i); });
      const cur = box.querySelector('.ln.on');
      if (cur) box.scrollTo({ top: cur.offsetTop - box.clientHeight * 0.38, behavior: 'smooth' });
    }
  }
  function openLyrics() { $('lyr').classList.add('on'); renderLyrics(); }
  function renderLyrics() {
    const np = PV().np;
    const L = S.lyr.lines;
    lastLy = -2;
    $('lyr').innerHTML = '<div class="pl-top"><button class="ib" type="button" data-a="closeLyrics" aria-label="Cerrar">' + I.down + '</button><div class="ctr"><div class="k">LETRA</div><div class="f ell">' + esc(np ? np.title : '') + '</div></div><span style="width:42px"></span></div>' +
      '<div class="lbody">' + (L ? L.map((l, i) => '<p class="ln" data-a="lySeek" data-i="' + i + '">' + esc(l.text) + '</p>').join('') : S.lyr.plain ? '<div class="plain">' + esc(S.lyr.plain) + '</div>' : '<p class="tip" style="text-align:center">' + (S.lyr.loading ? 'Buscando la letra…' : 'No encontré la letra de esta canción.') + '</p>') + '</div>';
    tick();
  }

  /* ======================= hojas: playlist, discos, sala ======================= */
  function openSheet(kind) { S.sheet = kind; $('veil').classList.add('on'); $('sheet').classList.add('on'); }
  function closeSheet() { S.sheet = null; $('veil').classList.remove('on'); $('sheet').classList.remove('on'); $('sheet').style.transform = ''; }
  let qKey = '';
  function openQueue() { openSheet('queue'); qKey = ''; renderQueue(); }
  function renderQueue() {
    if (DRAG.on) return;
    const v = PV(), np = v.np, q = v.queue;
    const k = JSON.stringify([np && np.title, np && np.paused, q.map((t) => [t.uid, t.title, t.art_url]), v.radio, S.qgen, S.mode]);
    if (k === qKey) return;
    qKey = k;
    let h = '<div class="sgrab" data-drag="sheet"><span class="grab"></span><small>Arrastra hacia abajo para cerrar</small></div>' +
      '<div class="sh"><h2 class="h2" style="font-size:24px">Playlist</h2><span style="display:flex;gap:8px">' +
      '<button class="pill ' + (v.radio ? 'on' : 'g') + '" type="button" data-a="radioToggle" style="height:36px;padding:0 14px 0 9px"><span class="vinyl"></span>' + (v.radio ? 'Radio' : 'Radio') + '</button>' +
      '<button class="pill r hold" type="button" data-hold="clear" style="height:36px"' + (q.length ? '' : ' disabled') + '><svg class="ring" viewBox="0 0 120 36" preserveAspectRatio="none"><rect x="1" y="1" width="118" height="34" rx="17" pathLength="100"/></svg><span>Borrar lista</span></button></span></div><div class="sbody" id="qbody">';
    if (np) h += '<div class="nowc"><span class="rc" style="' + bgi(np.art_url) + '"></span><span style="flex:1;min-width:0"><span class="k">SONANDO AHORA</span><span class="ell" style="font-size:15px;font-weight:800">' + esc(np.title) + '</span><span class="ell" style="font-size:12px;font-weight:600;color:var(--mut)">' + esc(np.uploader || '') + '</span></span><span class="eq' + (np.paused ? ' off' : '') + '" style="color:var(--mint);margin-right:6px"><i></i><i></i><i></i></span></div>';
    if (!q.length) {
      h += np ? '<div class="qempty">La lista está vacía.<br>¿Sigo con canciones parecidas a esta?<br><button class="pill p" type="button" data-a="radioGen" style="margin:14px auto 0">' + (S.qgen ? '<span class="vinyl spin"></span>Buscando…' : '<span class="vinyl"></span>Generar recomendaciones') + '</button></div>' : '<div class="qempty">No hay nada en la lista. Busca algo para empezar.</div>';
    } else {
      h += '<div class="slab">SIGUEN · toca una para ponerla · arrastra los puntitos</div><div id="qlist">' + q.map((t) => '<div class="qrow" data-uid="' + t.uid + '"><span class="rc" style="' + bgi(t.art_url) + '"></span>' +
        '<span style="flex:1;min-width:0"><span class="rt ell" style="font-size:15px;font-weight:700">' + esc(t.title) + '</span><span class="ell" style="font-size:12.5px;font-weight:600;color:var(--mut)">' + esc(t.uploader || '') + (t.radio ? ' · radio' : t.who && t.who !== S.me ? ' · ' + esc(t.who) : '') + (t.ready === false ? ' · preparando' : '') + '</span></span>' +
        '<span class="rd">' + (t.duration ? fmt(t.duration) : '') + '</span><button class="rb" type="button" data-a="qremove" data-uid="' + t.uid + '" aria-label="Quitar">' + I.x + '</button><span class="grip">' + I.grip + '</span></div>').join('') + '</div>';
    }
    $('sheet').innerHTML = h + '</div>';
  }
  // arrastrar para ordenar la playlist
  const DRAG = { on: false };
  (function () {
    let st = null;
    document.addEventListener('pointerdown', (e) => {
      const row = e.target.closest('#qlist .qrow');
      if (!row || e.target.closest('.rb')) return;
      st = { row: row, x: e.clientX, y: e.clientY, t: Date.now(), grip: !!e.target.closest('.grip') || e.pointerType === 'mouse' };
    });
    window.addEventListener('pointermove', (e) => {
      if (!st || DRAG.on) { if (DRAG.on) move(e); return; }
      if (Math.abs(e.clientY - st.y) > 6 || Math.abs(e.clientX - st.x) > 8) { if (st.grip) begin(e); else st = null; }
    });
    window.addEventListener('pointerup', () => {
      if (DRAG.on) { finish(); st = null; return; }
      if (st && Date.now() - st.t < 600) act('play_index', { uid: +st.row.dataset.uid });
      st = null;
    });
    window.addEventListener('pointercancel', () => { if (DRAG.on) finish(true); st = null; });
    function begin(e) {
      const rows = Array.from(document.querySelectorAll('#qlist .qrow'));
      rows.forEach((r) => { r.style.animation = 'none'; r.style.transition = 'transform .25s var(--out)'; });
      const r = st.row.getBoundingClientRect();
      Object.assign(DRAG, { on: true, rows: rows, from: rows.indexOf(st.row), to: rows.indexOf(st.row), h: r.height, dy: e.clientY - r.top, top0: rows.map((x) => x.getBoundingClientRect().top) });
      const lift = st.row.cloneNode(true);
      lift.classList.add('lift'); lift.style.width = r.width + 'px'; lift.style.left = r.left + 'px'; lift.style.top = r.top + 'px';
      document.body.appendChild(lift); DRAG.lift = lift;
      st.row.classList.add('ghost');
    }
    function move(e) {
      DRAG.lift.style.top = (e.clientY - DRAG.dy) + 'px';
      const y = e.clientY - DRAG.dy + DRAG.h / 2;
      let to = 0;
      DRAG.top0.forEach((t, i) => { if (y > t + DRAG.h / 2) to = i; });
      to = Math.max(0, Math.min(DRAG.rows.length - 1, to));
      DRAG.to = to;
      DRAG.rows.forEach((row, i) => {
        let off = 0;
        if (i !== DRAG.from) { if (DRAG.from < to && i > DRAG.from && i <= to) off = -DRAG.h; if (DRAG.from > to && i < DRAG.from && i >= to) off = DRAG.h; }
        row.style.transform = off ? 'translateY(' + off + 'px)' : '';
      });
      const b = $('qbody'), br = b.getBoundingClientRect();
      if (e.clientY < br.top + 40) b.scrollTop -= 8;
      if (e.clientY > br.bottom - 40) b.scrollTop += 8;
    }
    function finish(cancel) {
      const uid = +DRAG.rows[DRAG.from].dataset.uid, to = DRAG.to, from = DRAG.from;
      DRAG.lift.remove();
      DRAG.rows.forEach((r) => { r.style.transform = ''; r.classList.remove('ghost'); });
      DRAG.on = false;
      if (!cancel && to !== from) act('queue_move', { uid: uid, to: to });
      qKey = ''; renderQueue();
    }
  })();
  // la sala
  function openRoom(id) {
    S.roomId = id || myRoom();
    if (!S.roomId) return;
    openSheet('room'); S.roomKey = ''; renderRoom();
  }
  function renderRoom() {
    const id = S.roomId;
    const host = roomHosts().find((h) => h.id === id) || (id === S.me && E.cur ? { id: S.me, who: S.me, track: E.view().np || {}, paused: !E.want } : null);
    if (!host) { $('sheet').innerHTML = '<div class="sgrab" data-drag="sheet"><span class="grab"></span></div><div class="qempty">Esta sala ya se cerró.</div>'; return; }
    const mem = roomMembers(id);
    const inIt = E.on && E.follow === id;
    const k = JSON.stringify([id, host.track.title, host.paused, mem.map((m) => m.name), inIt, S.mode]);
    if (k === S.roomKey) return;
    S.roomKey = k;
    const dc = id === '@discord';
    const P = [[14, 66], [86, 66], [24, 86], [76, 86], [6, 78], [94, 78], [40, 95], [60, 95]];
    const people = mem.slice(0, 8).map((m, i) => '<span class="who' + (m.host ? ' host' : '') + (m.me ? ' me' : '') + '" style="left:' + P[i][0] + '%;top:' + (P[i][1] * 3.8 - 40) + 'px;animation-delay:' + (i * 0.2) + 's">' +
      '<span class="hd" style="background:' + pcolor(m.name) + '">' + esc(initial(m.name)) + '</span><span class="bd" style="background:' + pcolor(m.name) + '"></span><span class="sh2"></span><span class="nm">' + esc(m.me ? 'Tú' : m.name) + '</span></span>').join('');
    const h = '<div class="sgrab" data-drag="sheet"><span class="grab"></span></div><div class="sh"><span style="min-width:0"><h2 class="h2" style="font-size:22px">' + (dc ? 'Sala de LAPAJA' : id === S.me ? 'Tu sala' : 'Sala de ' + esc(id)) + '</h2>' +
      '<span class="kicker">' + mem.length + (dc ? ' en la llamada' : ' escuchando') + (dc ? '' : ' · ' + esc(id === S.me ? 'tú pones' : id + ' pone') + ' la música') + '</span></span></div>' +
      '<div class="sbody"><div class="room' + (host.paused ? ' paused' : '') + '">' +
      '<svg class="shell" viewBox="0 0 390 380" preserveAspectRatio="xMidYMid meet" aria-hidden="true"><polygon points="20,240 195,150 195,10 20,100" fill="#231C3D"/><polygon points="195,150 370,240 370,100 195,10" fill="#1B1631"/><polygon points="195,150 370,240 195,330 20,240" fill="#2E2550"/>' +
      '<path d="M107 195L282 285M150 172L325 262M65 218L240 308M282 195L107 285M240 172L65 262M325 218L150 308" stroke="rgba(201,180,248,.09)" stroke-width="1.5"/><ellipse cx="195" cy="245" rx="120" ry="58" fill="#3B2F68" opacity=".7"/>' +
      '<polygon points="250,92 330,133 330,190 250,149" fill="#0E0B1E" stroke="#3B3166" stroke-width="5"/><circle cx="290" cy="126" r="9" fill="#F4F2FA" opacity=".9"/><polygon points="55,132 150,83 150,115 55,164" fill="none" stroke="#C9B4F8" stroke-width="3"/></svg>' +
      '<img class="cumi" src="cumito.png" alt="Cumito, el DJ">' +
      '<span class="note" style="left:34%;top:96px;--dx:-30px">' + I.note.replace('<svg', '<svg width="18" height="18"') + '</span><span class="note" style="left:64%;top:86px;--dx:26px;animation-delay:1s">' + I.note.replace('<svg', '<svg width="15" height="15"') + '</span><span class="note" style="left:50%;top:70px;--dx:6px;animation-delay:2s">' + I.note.replace('<svg', '<svg width="13" height="13"') + '</span>' +
      '<svg class="desk" viewBox="0 0 170 110" aria-hidden="true"><polygon points="85,0 170,38 85,76 0,38" fill="#4A3D80"/><polygon points="0,38 85,76 85,110 0,72" fill="#2A2150"/><polygon points="85,76 170,38 170,72 85,110" fill="#362B63"/>' +
      '<g transform="translate(52 36) scale(1 .5)"><circle r="22" fill="#15111F"/><g class="tt"><circle r="22" fill="none" stroke="#3B3166" stroke-width="2"/><circle r="6" fill="#E8618C"/><rect x="-1.5" y="-21" width="3" height="10" fill="#C9B4F8"/></g></g>' +
      '<g transform="translate(118 36) scale(1 .5)"><circle r="22" fill="#15111F"/><g class="tt"><circle r="22" fill="none" stroke="#3B3166" stroke-width="2"/><circle r="6" fill="#A8E6F5"/><rect x="-1.5" y="-21" width="3" height="10" fill="#C9B4F8"/></g></g></svg>' +
      people + '</div>' +
      '<div class="nowc" style="margin-top:8px"><span class="rc" style="' + bgi(host.track.art_url) + '"></span><span style="flex:1;min-width:0"><span class="k">' + (host.paused ? 'EN PAUSA' : 'SONANDO') + '</span><span class="ell" style="font-size:15px;font-weight:800">' + esc(host.track.title || '') + '</span><span class="ell" style="font-size:12px;font-weight:600;color:var(--mut)">' + esc(host.track.uploader || '') + '</span></span></div>' +
      '<div class="pad" style="margin-top:12px">' + (inIt ? '<button class="pill r" type="button" data-a="leaveRoom" style="width:100%;height:50px;font-size:15px">Salir de la sala</button><p class="tip" style="text-align:center;margin-top:8px">Vuelves a tu música donde la dejaste</p>'
        : id === S.me ? '<p class="tip" style="text-align:center">Los demás están escuchando lo mismo que tú.</p>'
          : '<button class="pill p" type="button" data-a="room" data-id="' + esc(id) + '" style="width:100%;height:50px;font-size:15px">Entrar a la sala</button>') + '</div></div>';
    $('sheet').innerHTML = h;
  }
  // elegir disco para guardar una canción
  function openPicker(m, refresh) {
    if (!m) return;
    S.pickMeta = m;
    if (!refresh) openSheet('picker');
    $('sheet').innerHTML = '<div class="sgrab" data-drag="sheet"><span class="grab"></span></div><div class="sh"><span style="min-width:0"><h2 class="h2">Guardar en un disco</h2><span class="kicker ell">' + esc(m.title) + '</span></span></div><div class="sbody"><div class="picks">' +
      '<button class="pick" type="button" data-a="pickNew"><span class="pc" style="background:var(--vio)">' + I.plus.replace('<svg', '<svg width="20" height="20"') + '</span><span style="flex:1;font-size:15px;font-weight:800">Nuevo disco</span></button>' +
      S.albums.map((a, i) => '<button class="pick" type="button" data-a="pick" data-i="' + i + '"><span class="pc" style="' + discStyle(a) + '"></span><span style="flex:1;min-width:0"><span class="ell" style="font-size:15px;font-weight:800">' + esc(a.name) + '</span><span class="ell" style="font-size:12px;font-weight:600;color:var(--mut)">' + esc(a.owner || '') + ' · ' + (a.count || 0) + ' canciones</span></span></button>').join('') + '</div></div>';
  }
  // pedir un texto (nombre del disco, mi nombre)
  function askText(title, value, cb) {
    openSheet('text');
    $('sheet').innerHTML = '<div class="sgrab" data-drag="sheet"><span class="grab"></span></div><div class="sh"><h2 class="h2">' + esc(title) + '</h2></div><div class="pad"><input id="txIn" class="nm-in" style="margin-top:6px;max-width:none;text-align:left" maxlength="48" value="' + esc(value || '') + '" enterkeyhint="done"><button class="pill w" type="button" data-a="txOk" style="width:100%;height:50px;margin-top:12px;font-size:15px">Listo</button></div>';
    S.textCb = cb;
    setTimeout(() => { const i = $('txIn'); if (i) { i.focus(); i.select(); } }, 350);
  }
  // arrastrar hacia abajo para cerrar (hojas y reproductor)
  (function () {
    let d = null;
    const target = (kind) => (kind === 'player' ? $('player') : $('sheet'));
    document.addEventListener('touchstart', (e) => {
      if (e.touches.length !== 1) return;
      const t = e.target;
      let kind = null;
      if (t.closest('#sheet .sgrab, #sheet .sh')) kind = 'sheet';
      else if (t.closest('#sheet .sbody') && !t.closest('.grip, .rb, button, input') ) kind = 'sheet-list';
      else if (S.playerOpen && t.closest('#player') && !t.closest('#sbar, .ctrls, .lycard, .qbtn, button')) kind = 'player';
      else if (S.playerOpen && t.closest('#player .sgrab, #player .pl-top')) kind = 'player';
      if (!kind) return;
      d = { kind: kind, y0: e.touches[0].clientY, on: false, t0: 0, dy: 0 };
    }, { passive: true });
    document.addEventListener('touchmove', (e) => {
      if (!d || DRAG.on) return;
      const y = e.touches[0].clientY, dy = y - d.y0;
      if (!d.on) {
        const list = d.kind === 'sheet-list' ? $('qbody') || document.querySelector('#sheet .sbody') : null;
        if (dy > 8 && (!list || list.scrollTop <= 0)) { d.on = true; d.y0 = y; d.t0 = performance.now(); target(d.kind === 'player' ? 'player' : 'sheet').classList.add('drag'); }
        else if (Math.abs(dy) > 8) { d = null; return; }
        else return;
      }
      d.dy = Math.max(0, y - d.y0);
      target(d.kind === 'player' ? 'player' : 'sheet').style.transform = 'translateY(' + d.dy + 'px)';
      if (e.cancelable) e.preventDefault();
    }, { passive: false });
    const end = () => {
      if (!d) return;
      const w = d; d = null;
      if (!w.on) return;
      const el = target(w.kind === 'player' ? 'player' : 'sheet');
      el.classList.remove('drag');
      el.style.transform = '';
      const v = w.dy / Math.max(1, performance.now() - w.t0);
      if (w.dy > el.getBoundingClientRect().height * 0.22 || (v > 0.7 && w.dy > 40)) { if (w.kind === 'player') closePlayer(); else closeSheet(); }
    };
    document.addEventListener('touchend', end);
    document.addEventListener('touchcancel', end);
  })();

  /* ======================= mantener presionado ======================= */
  const HOLD = { el: null, t: null, alt: false };
  document.addEventListener('pointerdown', (e) => {
    const b = e.target.closest('[data-hold]');
    if (!b || b.disabled) return;
    e.preventDefault();
    HOLD.el = b; HOLD.alt = !HOLD.alt;
    b.classList.remove('holding', 'b'); void b.offsetWidth;
    b.classList.toggle('b', HOLD.alt); b.classList.add('holding');
    const sp = b.querySelector('span'); if (sp && !b.dataset.txt) b.dataset.txt = sp.textContent;
    if (sp) sp.textContent = 'Sigue presionando…';
    if (navigator.vibrate) try { navigator.vibrate(15); } catch (er) {}
    clearTimeout(HOLD.t);
    HOLD.t = setTimeout(() => {
      b.classList.remove('holding');
      if (sp) sp.textContent = b.dataset.txt;
      HOLD.el = null;
      if (navigator.vibrate) try { navigator.vibrate([30, 40, 60]); } catch (er) {}
      holdDone(b.dataset.hold);
    }, 2000);
  });
  function holdCancel() {
    const b = HOLD.el;
    if (!b) return;
    clearTimeout(HOLD.t);
    b.classList.remove('holding');
    const sp = b.querySelector('span'); if (sp) sp.textContent = b.dataset.txt || sp.textContent;
    HOLD.el = null;
  }
  ['pointerup', 'pointercancel'].forEach((ev) => document.addEventListener(ev, holdCancel));
  document.addEventListener('pointerout', (e) => { if (HOLD.el && e.target === HOLD.el && !HOLD.el.contains(e.relatedTarget)) holdCancel(); });
  function holdDone(k) {
    if (k === 'clear') { act('queue_clear'); toast('Lista borrada'); }
    else if (k === 'discDelete') { const p = top(); if (p && p.disc) { cmd('album_delete', { id: p.disc.id }); toast('Disco borrado'); pop(); } }
  }

  /* ======================= toques ======================= */
  const A = {
    tab: (t) => goTab(t.dataset.t),
    back: () => pop(),
    hfilter: (t) => { S.homeFilter = t.dataset.f; renderScreen(true); },
    openPlayer: () => openPlayer(),
    closePlayer: () => closePlayer(),
    toggle: () => { const np = PV().np; if (!np) return; act(np.paused ? 'resume' : 'pause'); if (S.mode !== 'solo') { np.paused = !np.paused; S.g.now_playing.paused = np.paused; S.g.now_playing.elapsed = gElapsed(); S.gAt = performance.now(); render(); } },
    skip: () => { act('skip'); },
    prev: () => act('prev'),
    shuffle: () => { act('shuffle'); if (S.mode !== 'solo') toast('Lista mezclada'); },
    repeat: () => { const v = PV(); const nx = v.repeat === 'off' ? 'all' : v.repeat === 'all' ? 'one' : 'off'; act('set_repeat', { mode: nx }); toast(nx === 'off' ? 'Sin repetir' : nx === 'all' ? 'Repetir la lista' : 'Repetir esta canción'); if (S.mode !== 'solo') { S.g.repeat = nx; render(); } },
    openQueue: () => openQueue(),
    openLyrics: () => openLyrics(),
    closeLyrics: () => $('lyr').classList.remove('on'),
    lySeek: (t) => { const l = (S.lyr.lines || [])[+t.dataset.i]; if (l) act('seek', { pos: Math.max(0, Math.floor(l.t)) }); },
    radioToggle: () => { const on = !PV().radio; act('set_radio', { on: on }); if (S.mode !== 'solo') { S.g.radio = on; render(); } toast(on ? 'Radio prendida: cuando se acabe la lista, siguen parecidas' : 'Radio apagada'); },
    radioGen: () => { if (S.qgen) return; S.qgen = true; act('radio_now'); qKey = ''; renderQueue(); setTimeout(() => { if (S.qgen) { S.qgen = false; qKey = ''; renderQueue(); } }, 15000); },
    qremove: (t) => act('queue_remove', { uid: +t.dataset.uid }),
    openRoom: () => openRoom(),
    room: (t) => {
      const id = t.dataset.id;
      if (E.on && E.follow === id) { openRoom(id); return; }
      if (S.mode !== 'solo') { enterMode('solo'); }
      E.followTo(id);
      toast(id === '@discord' ? 'Escuchando lo mismo que en LAPAJA' : 'Entraste a la sala de ' + id);
      openRoom(id);
    },
    leaveRoom: () => { E.leaveRoom(); closeSheet(); },
    // inicio
    mix: (t, e) => { if (e.target.closest('[data-a="mixPlay"]')) return A.mixPlay(t); openMix(+t.dataset.i); },
    mixPlay: (t) => { const m = ((S.feed.data || {}).mixes || [])[+t.dataset.i]; if (m) { playTracks(m.tracks, 0); toast('Poniendo «' + m.title + '»'); } },
    artistRadio: (t) => { const r = ((S.feed.data || {}).radios || [])[+t.dataset.i]; if (!r) return; if (r.id) openArtist(r.id, r.name, r.art_url); else if (r.seed) radioFrom(r.seed); },
    feedPl: (t) => { const p = ((S.feed.data || {}).playlists || [])[+t.dataset.i]; if (p) openPlaylist(p.url, p.title, p.art_url); },
    recPlay: (t) => { const m = (S.homeRec || [])[+t.dataset.i]; if (m) playOne(m); },
    discOpen: (t) => { const a = S.albums[+t.dataset.i]; if (a) openDisc(a); },
    // buscar
    skind: (t) => { S.search.kind = t.dataset.k; S.search.res = null; if (S.tab !== 'search') goTab('search'); renderScreen(true); doSearch(true); },
    sclear: () => { S.search.q = ''; S.search.res = null; renderScreen(true); const i = $('sq'); if (i) i.focus(); },
    srecent: (t) => { S.search.q = S.recent[+t.dataset.i] || ''; renderScreen(true); doSearch(true); },
    slink: () => { playLink(S.search.q.trim()); },
    topres: () => { const t = (S.search.res || {}).top; if (!t) return; if (t.type === 'artist') openArtist(t.id, t.name, t.art_url); else if (t.type === 'song') playOne(t); else if (t.type === 'album') openAlbum(t.id, t.title, t.art_url); else if (t.type === 'playlist') openPlaylist(t.url, t.title, t.art_url); },
    sArtist: (t) => { const r = S.search.res || {}; const a = (S.search.kind === 'all' ? r.artists : r.results || [])[+t.dataset.i]; if (a) openArtist(a.id, a.name, a.art_url); },
    sPl: (t) => { const r = S.search.res || {}; const p = (S.search.kind === 'all' ? r.playlists : r.results || [])[+t.dataset.i]; if (p) openPlaylist(p.url, p.title, p.art_url); },
    sAlbum: (t) => { const r = S.search.res || {}; const a = (S.search.kind === 'all' ? r.albums : r.results || [])[+t.dataset.i]; if (a) openAlbum(a.id, a.title, a.art_url); },
    // filas de canciones (en cualquier lista)
    rowPlay: (t) => {
      const i = +t.dataset.i, p = top(), m = ROWS[i];
      if (!m) return;
      if (p && p.type === 'list') playTracks(p.tracks, i);
      else if (p && p.type === 'artist') playTracks((p.data || {}).top || [], i);
      else playOne(m);
    },
    tuPlay: (t) => { const m = (S.tuRows || [])[+t.dataset.i]; if (m) playOne(m); },
    addRow: (t) => { const m = ROWS[+t.dataset.i]; if (m) { addOne(m); t.classList.add('ok'); t.innerHTML = I.check; } },
    heartRow: (t) => { const m = ROWS[+t.dataset.i]; if (m) openPicker(m); },
    heartNow: () => { const np = PV().np; if (np) openPicker({ title: np.title, uploader: np.uploader, art_url: np.art_url, webpage_url: np.webpage_url, duration: np.duration }); },
    pick: (t) => { const a = S.albums[+t.dataset.i]; if (a && S.pickMeta) { cmd('album_add', { id: a.id, tracks: [S.pickMeta] }); toast('Guardada en «' + a.name + '»'); closeSheet(); } },
    pickNew: () => { const m = S.pickMeta; askText('Nombre del disco nuevo', '', (name) => { if (!name) return; S.pendingAdd = { name: name, meta: m }; cmd('album_create', { name: name }); }); },
    // artista
    artPlay: () => { const p = top(); if (p && p.data) playTracks(p.data.top, 0); },
    artShuf: () => { const p = top(); if (p && p.data) playTracks(p.data.top, 0, true); },
    artRadio: () => { const p = top(); const s = p && p.data && p.data.top[0]; if (s) radioFrom(s); },
    artMore: () => { const p = top(); if (p) { p.more = true; renderScreen(true); } },
    artAll: () => { const p = top(); const d = p && p.data; if (d && d.all_songs) { push({ type: 'list', kind: 'artistSongs', id: d.all_songs, title: d.name, art: d.art_url, tracks: [], loading: true, sub: 'Todas sus canciones' }); cmd('artist_songs', { id: d.all_songs }); } },
    artAlbum: (t) => { const p = top(); const a = p && p.data && (p.data[t.dataset.k] || [])[+t.dataset.i]; if (a) openAlbum(a.id, a.title, a.art_url); },
    // listas
    listPlay: () => { const p = top(); if (!p) return; if (p.kind === 'disc' && S.mode !== 'solo') { cmd('album_play', { id: p.id, shuffle: false }); toast('Poniendo «' + p.title + '» en LAPAJA'); return; } playTracks(p.tracks, 0); },
    listShuf: () => { const p = top(); if (!p) return; if (p.kind === 'disc' && S.mode !== 'solo') { cmd('album_play', { id: p.id, shuffle: true }); toast('Poniendo «' + p.title + '» en aleatorio'); return; } playTracks(p.tracks, 0, true); },
    discRemove: (t) => { const p = top(); const tr = p && p.tracks[+t.dataset.i]; if (tr && p.disc) { cmd('album_remove', { id: p.disc.id, track_id: tr.id }); p.tracks.splice(+t.dataset.i, 1); renderScreen(true); } },
    discNew: () => askText('Nombre del disco nuevo', '', (name) => { if (name) { cmd('album_create', { name: name }); toast('Disco «' + name + '» creado'); } }),
    discEdit: () => {
      const p = top(); if (!p || !p.disc) return;
      openSheet('text');
      $('sheet').innerHTML = '<div class="sgrab" data-drag="sheet"><span class="grab"></span></div><div class="sh"><h2 class="h2">Editar disco</h2></div><div class="sbody">' +
        '<button class="opt" type="button" data-a="discRename"><span class="oi">' + I.pen + '</span><span><b>Cambiar el nombre</b><small>' + esc(p.disc.name) + '</small></span></button>' +
        '<label class="opt"><span class="oi">' + I.img + '</span><span><b>Cambiar la portada</b><small>Una foto de tu cel</small></span><input type="file" accept="image/*" id="coverIn" class="hide"></label></div>';
      $('coverIn').onchange = () => pickCover($('coverIn').files[0], (b64) => { cmd('album_update', { id: p.disc.id, cover_b64: b64 }); toast('Portada cambiada'); closeSheet(); });
    },
    discRename: () => { const p = top(); if (p && p.disc) askText('Nombre del disco', p.disc.name, (name) => { if (name) { cmd('album_update', { id: p.disc.id, name: name }); p.title = name; renderScreen(true); } }); },
    txOk: () => { const v = ($('txIn') || {}).value || ''; const cb = S.textCb; S.textCb = null; closeSheet(); if (cb) cb(v.trim()); },
    // tú
    entry: () => { S.mode = null; render(); },
    rename: () => askText('Tu nombre', S.me, (n) => { if (n && n !== S.me) { setName(n); toast('Ahora eres ' + n); } }),
    status: () => { push({ type: 'status' }); cmd('status'); },
    speriod: (t) => { S.statsPeriod = t.dataset.p; S.stats = null; renderScreen(true); cmd('stats', { period: S.statsPeriod, who: S.statsMine ? S.me : null }); },
    smine: (t) => { S.statsMine = t.dataset.m === '1'; S.stats = null; renderScreen(true); cmd('stats', { period: S.statsPeriod, who: S.statsMine ? S.me : null }); },
    // entrada
    setName: () => { const v = (($('nmIn') || {}).value || '').trim(); if (!v) { toast('Escribe tu nombre'); return; } setName(v); },
    enter: (t) => { if (t.dataset.m === 'solo') E.unlock(); enterMode(t.dataset.m); },
  };
  function radioFrom(seed) {
    if (S.mode === 'solo') E.radioFrom(seed);
    else { cmd('play', { query: seed.webpage_url }); cmd('set_radio', { on: true }); toast('Radio prendida en LAPAJA'); }
  }
  function setName(n) {
    S.me = String(n).slice(0, 32);
    LS.set('name', S.me);
    if (ws) { try { ws.close(); } catch (e) {} } else connect();
    render(true);
  }
  function pickCover(f, cb) {
    if (!f) return;
    const img = new Image();
    img.onload = () => {
      const k = Math.min(1, 700 / Math.min(img.width, img.height));
      const c = document.createElement('canvas');
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
      const g = c.getContext('2d'); g.fillStyle = '#100E16'; g.fillRect(0, 0, c.width, c.height); g.drawImage(img, 0, 0, c.width, c.height);
      cb(c.toDataURL('image/jpeg', 0.88).split(',')[1]);
      URL.revokeObjectURL(img.src);
    };
    img.onerror = () => toast('No pude abrir esa imagen');
    img.src = URL.createObjectURL(f);
  }
  document.addEventListener('click', (e) => {
    const t = e.target.closest('[data-a]');
    if (!t || t.disabled) return;
    if (t.matches('input[type=checkbox]')) { if (t.dataset.a === 'remember') LS.set('m3.remember', t.checked); return; }
    const f = A[t.dataset.a];
    if (f) { e.preventDefault(); f(t, e); }
  });
  $('veil').addEventListener('click', () => { const cb = S.textCb; S.textCb = null; closeSheet(); if (cb && S.sheet === 'text') cb(''); });
  document.addEventListener('input', (e) => { if (e.target.id === 'sq') { S.search.q = e.target.value; doSearch(false); const x = e.target.parentNode.querySelector('.x'); if (!!S.search.q !== !!x) { /* el botón de borrar aparece en el próximo pintado */ } } });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    if (e.target.id === 'sq') { e.preventDefault(); e.target.blur(); if (isUrl(S.search.q.trim())) playLink(S.search.q.trim()); else doSearch(true); }
    else if (e.target.id === 'txIn') { e.preventDefault(); A.txOk(); }
    else if (e.target.id === 'nmIn') { e.preventDefault(); A.setName(); }
  });
  function goBack() {
    if ($('lyr').classList.contains('on')) { $('lyr').classList.remove('on'); return true; }
    if (S.sheet) { closeSheet(); return true; }
    if (S.playerOpen) { closePlayer(); return true; }
    if (S.stack.length) { pop(); return true; }
    return false;
  }
  // Android: el botón de atrás. En iPhone no se usa el historial (el gesto del
  // sistema dejaba la pantalla en blanco unos segundos); va el gesto de abajo.
  const IOS = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  if (!IOS) {
    window.addEventListener('popstate', () => { goBack(); history.pushState(null, ''); });
    history.pushState(null, '');
  }
  // deslizar desde el borde izquierdo hacia adentro = volver
  (function () {
    let g = null;
    const layer = () => ($('lyr').classList.contains('on') ? $('lyr') : S.sheet ? $('sheet') : S.playerOpen ? $('player') : S.stack.length ? $('screen') : null);
    document.addEventListener('touchstart', (e) => {
      const t = e.touches[0];
      if (e.touches.length !== 1 || t.clientX > 28) return;
      const el = layer();
      if (!el) return;
      g = { el: el, x0: t.clientX, y0: t.clientY, dx: 0, on: false, t0: performance.now() };
    }, { passive: true });
    document.addEventListener('touchmove', (e) => {
      if (!g) return;
      const t = e.touches[0], dx = t.clientX - g.x0, dy = t.clientY - g.y0;
      if (!g.on) {
        if (Math.abs(dy) > 14 && Math.abs(dy) > dx) { g = null; return; }
        if (dx < 10) return;
        g.on = true; g.el.classList.add('edge');
      }
      g.dx = Math.max(0, dx);
      g.el.style.transform = 'translateX(' + g.dx + 'px)';
      if (e.cancelable) e.preventDefault();
    }, { passive: false });
    const end = () => {
      if (!g) return;
      const w = g; g = null;
      if (!w.on) return;
      const fast = w.dx / Math.max(1, performance.now() - w.t0) > 0.6 && w.dx > 50;
      const go = w.dx > innerWidth * 0.3 || fast;
      w.el.classList.remove('edge');
      w.el.classList.add('edge-end');
      w.el.style.transform = go ? 'translateX(' + innerWidth + 'px)' : '';
      setTimeout(() => {
        w.el.classList.remove('edge-end');
        w.el.classList.add('edge');
        if (go) goBack();
        w.el.style.transform = '';
        void w.el.offsetWidth;
        w.el.classList.remove('edge');
      }, 260);
    };
    document.addEventListener('touchend', end);
    document.addEventListener('touchcancel', end);
  })();

  /* ======================= avisitos ======================= */
  let toastT = null;
  function toast(text, ms) {
    const t = $('toast');
    t.textContent = text; t.classList.add('on');
    clearTimeout(toastT);
    toastT = setTimeout(() => t.classList.remove('on'), ms || 2300);
  }

  /* ======================= arrancar ======================= */
  window.CUMITO3 = { S: S, E: E, render: render, onMsg: onMsg, act: act, PV: PV };
  const rem = LS.get('m3.remember', true), lastMode = LS.get('m3.mode', null);
  if (S.me && rem && lastMode) { S.mode = lastMode; if (lastMode === 'solo') E.enter(); }
  measure();
  render(true);
  connect();
  setInterval(() => { if (S.mode === 'home') {} if (S.tab === 'home' && !S.stack.length && S.mode) renderScreen(); }, 20000);
})();
